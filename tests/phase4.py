#!/usr/bin/env python3
"""Two independent processes, disposable Redis outage, recovery and history."""
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
processes = []
clients = []
tmp = tempfile.TemporaryDirectory(prefix='phase4-', dir=ROOT / 'build')
db = str(Path(tmp.name) / 'messages.db')

def start_redis():
    p = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', '16379', '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(p)
    time.sleep(0.5)
    assert p.poll() is None, 'temporary Redis did not start'
    return p

def start_server(port, name):
    p = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--port', str(port), '--instance-id', name,
                          '--redis-port', '16379', '--db', db], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    processes.append(p)
    return p

def wait_subscribers():
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = subprocess.run(['redis-cli', '-h', '127.0.0.1', '-p', '16379', '--raw', 'PUBSUB', 'NUMSUB', 'cpp-realtime-messages-v1'],
                                capture_output=True, text=True)
        lines = result.stdout.splitlines()
        if result.returncode == 0 and len(lines) >= 2 and lines[1] == '2':
            return
        time.sleep(0.2)
    raise AssertionError('both instances did not subscribe to Redis')

def wait_listener(port, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f'server on port {port} did not listen')

def auth_join(client, token):
    client.send({'type': 'auth', 'token': token}); assert client.read()['type'] == 'auth_ok'
    client.send({'type': 'join', 'room_id': 'room_001'}); assert client.read()['type'] == 'joined'

def send(client, msgid, content):
    client.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': msgid, 'content': content})
    ack = client.read(); assert ack['type'] == 'send_ok' and not ack['duplicate'], ack
    own = client.read(); assert own['type'] == 'message' and own['message_id'] == ack['message_id'], own
    return ack['message_id']

try:
    redis = start_redis()
    a_proc = start_server(9001, 'A'); b_proc = start_server(9002, 'B')
    wait_subscribers()
    for proc in (a_proc, b_proc):
        if proc.poll() is not None:
            raise AssertionError('server did not start: ' + proc.stderr.read().decode(errors='replace'))
    wait_listener(9001, a_proc); wait_listener(9002, b_proc)
    a, b = Client(9001), Client(9002); clients.extend([a, b])
    auth_join(a, 'demo-alice'); auth_join(b, 'demo-bob')
    first = send(a, 'a1', 'across')
    assert b.read()['message_id'] == first
    second = send(b, 'b1', 'back')
    assert a.read()['message_id'] == second
    redis.terminate(); redis.wait(timeout=5)
    time.sleep(1)
    missed = send(a, 'a2', 'offline')
    b.sock.settimeout(0.5)
    try:
        b.read(); raise AssertionError('unexpected cross-instance delivery during Redis outage')
    except socket.timeout:
        pass
    b.sock.settimeout(3)
    b.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': second})
    assert [m['message_id'] for m in b.read()['messages']] == [missed]
    redis = start_redis()
    wait_subscribers()
    resumed = send(a, 'a3', 'resumed')
    assert b.read()['message_id'] == resumed
    b.close(); clients.remove(b)
    lost = send(a, 'a4', 'while disconnected')
    b = Client(9002); clients.append(b); auth_join(b, 'demo-bob')
    b.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': resumed})
    assert [m['message_id'] for m in b.read()['messages']] == [lost]
    b.send({'type': 'ack', 'room_id': 'room_001', 'message_id': lost})
    assert b.read()['type'] == 'ack_ok'
    b.send({'type': 'history', 'room_id': 'room_001'})
    assert b.read()['messages'] == []
    for process in (a_proc, b_proc):
        process.terminate()
        assert process.wait(timeout=5) == 0, 'server did not shut down cleanly'
    print('PASS: two processes, bidirectional Redis delivery, outage history, resubscription and offline recovery')
finally:
    for client in clients:
        client.close()
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    tmp.cleanup()

#!/usr/bin/env python3
"""Two independent processes, disposable Redis outage, recovery and history."""
import socket
import json
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
    client.send({'type': 'create_room', 'room_id': 'room_001'}); assert client.read()['type'] in ('room_created', 'error')
    client.send({'type': 'join', 'room_id': 'room_001'}); assert client.read()['type'] == 'joined'

def send(client, msgid, content):
    client.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': msgid, 'content': content})
    ack = client.read(); assert ack['type'] == 'send_ok' and not ack['duplicate'], ack
    own = client.read(); assert own['type'] == 'message' and own['message_id'] == ack['message_id'], own
    return ack['message_id']

try:
    redis = start_redis()
    a_proc = start_server(19103, 'A'); b_proc = start_server(19104, 'B')
    wait_subscribers()
    for proc in (a_proc, b_proc):
        if proc.poll() is not None:
            raise AssertionError('server did not start: ' + proc.stderr.read().decode(errors='replace'))
    wait_listener(19103, a_proc); wait_listener(19104, b_proc)
    a, b = Client(19103), Client(19104); clients.extend([a, b])
    auth_join(a, 'demo-alice'); auth_join(b, 'demo-bob')
    # A numeric overflow in an untrusted Redis event must not kill the subscriber thread/process.
    invalid = subprocess.run(['redis-cli', '-p', '16379', '--raw', 'PUBLISH', 'cpp-realtime-messages-v1', '{"x":1e99999}'],
                             capture_output=True, text=True, check=True)
    assert invalid.stdout.strip() == '2'
    first = send(a, 'a1', 'across')
    assert b.read()['message_id'] == first
    # Restart after a successful publish, without publishing during the outage:
    # the publisher's previous TCP context is stale when the first new event arrives.
    redis.terminate(); redis.wait(timeout=5)
    time.sleep(1)
    redis = start_redis(); wait_subscribers()
    quiet_restart = send(a, 'after-quiet-restart', 'first after restart')
    delivered = b.read()
    assert delivered['message_id'] == quiet_restart
    # Replaying the same Redis event must not duplicate the local delivery.
    duplicate = json.dumps({'instance_id': 'A', 'message': delivered, 'recipients': ['alice', 'bob']})
    subprocess.run(['redis-cli', '-p', '16379', '--raw', 'PUBLISH', 'cpp-realtime-messages-v1', duplicate],
                   capture_output=True, text=True, check=True)
    b.sock.settimeout(.4)
    try:
        b.read(); raise AssertionError('duplicate Redis event was delivered twice')
    except socket.timeout:
        pass
    b.sock.settimeout(3)
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
    b = Client(19104); clients.append(b); auth_join(b, 'demo-bob')
    b.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': resumed})
    assert [m['message_id'] for m in b.read()['messages']] == [lost]
    b.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': resumed})
    assert [m['message_id'] for m in b.read()['messages']] == [lost]
    b.send({'type': 'ack', 'room_id': 'room_001', 'message_id': lost})
    assert b.read()['type'] == 'ack_ok'
    b.send({'type': 'history', 'room_id': 'room_001'})
    history = b.read()
    assert history['after_message_id'] == 0
    assert [m['message_id'] for m in history['messages']] == [first, quiet_restart, second, missed, resumed, lost]
    for message_id in (first, quiet_restart, second, missed, resumed):
        b.send({'type': 'ack', 'room_id': 'room_001', 'message_id': message_id})
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

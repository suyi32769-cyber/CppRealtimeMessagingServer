#!/usr/bin/env python3
"""Exercise real idle ping/pong timeout and slow-consumer behavior in isolation."""
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
MODE = sys.argv[1]
assert MODE in ('heartbeat', 'backpressure')
PORT = 19004 if MODE == 'heartbeat' else 19005

def connect_when_ready(process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try: return Client(PORT)
        except OSError: time.sleep(.1)
    raise RuntimeError('server failed to start')

def auth_join(client, token):
    client.send({'type': 'auth', 'token': token}); assert client.read()['type'] == 'auth_ok'
    client.send({'type': 'create_room', 'room_id': 'room'}); assert client.read()['type'] in ('room_created', 'error')
    client.send({'type': 'join', 'room_id': 'room'}); assert client.read()['type'] == 'joined'

with tempfile.TemporaryDirectory(prefix='realtime-network-') as tmp:
    log_path = Path(tmp) / 'server.log'
    with log_path.open('w') as log:
        server = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--no-redis', '--port', str(PORT),
                                   '--db', str(Path(tmp) / 'messages.db')], stdout=subprocess.DEVNULL, stderr=log)
        clients = []
        thread = None
        stop = threading.Event()
        try:
            first = connect_when_ready(server); clients.append(first)
            second = Client(PORT); clients.append(second)
            if MODE == 'heartbeat':
                # One client answers protocol pings; the other never does.
                first.sock.settimeout(1)
                pongs = []
                def answer_pings():
                    while not stop.is_set():
                        try:
                            opcode, payload = first.read_frame()
                            if opcode == 9:
                                first.send_raw(payload, opcode=10); pongs.append(1)
                            elif opcode == 8: raise RuntimeError('responsive client closed')
                        except socket.timeout: pass
                        except Exception as exc:
                            pongs.append(exc); return
                thread = threading.Thread(target=answer_pings); thread.start()
                second.sock.settimeout(55)
                start = time.monotonic()
                opcode, _ = second.read_frame()
                assert opcode == 9, f'expected WebSocket ping, got {opcode}'
                try:
                    opcode, _ = second.read_frame()
                    assert opcode == 8, f'expected close, got {opcode}'
                except (EOFError, ConnectionResetError): pass
                elapsed = time.monotonic() - start
                stop.set(); thread.join(timeout=5); assert not thread.is_alive()
                assert pongs and all(x == 1 for x in pongs), pongs
                first.sock.settimeout(3)
                first.send({'type': 'ping'})
                while True:
                    opcode, data = first.read_frame()
                    if opcode == 9: first.send_raw(data, opcode=10); continue
                    assert opcode == 1 and b'"pong"' in data, (opcode, data)
                    break
                print(f'PASS: nonresponsive client closed after {elapsed:.2f}s; pong client remained connected ({len(pongs)} ping(s))')
            else:
                first.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                first.sock.settimeout(5); second.sock.settimeout(10)
                auth_join(first, 'demo-bob'); auth_join(second, 'demo-alice')
                deadline = time.monotonic() + 35
                sent = 0
                while time.monotonic() < deadline and sent < 12000:
                    sent += 1
                    second.send({'type': 'send', 'room_id': 'room', 'client_msg_id': str(sent), 'content': 'x' * 4096})
                    response = second.read(); assert response['type'] == 'send_ok', response
                    assert second.read()['message_id'] == response['message_id']
                    if sent % 25 == 0 and 'backpressure limit reached' in log_path.read_text(): break
                log.flush()
                assert 'backpressure limit reached' in log_path.read_text(), f'no backpressure after {sent} messages'
                close_deadline = time.monotonic() + 5
                while time.monotonic() < close_deadline and 'backpressured connection closed' not in log_path.read_text():
                    time.sleep(.05)
                assert 'backpressured connection closed' in log_path.read_text(), 'slow connection did not close'
                second.send({'type': 'ping'}); assert second.read()['type'] == 'pong'
                assert server.poll() is None
                print(f'PASS: slow subscriber closed after backpressure at {sent} messages; healthy client responsive')
        finally:
            stop.set()
            for client in clients: client.close()
            if thread is not None: thread.join(timeout=5)
            if server.poll() is None:
                server.terminate(); assert server.wait(timeout=8) == 0

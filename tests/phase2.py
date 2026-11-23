#!/usr/bin/env python3
"""Exercise two independent clients against a single local server."""
import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class Client:
    def __init__(self):
        self.sock = socket.create_connection(('127.0.0.1', 9001), timeout=3)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET / HTTP/1.1\r\nHost: 127.0.0.1:9001\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        response = b''
        while not response.endswith(b'\r\n\r\n'):
            chunk = self.sock.recv(1)
            if not chunk:
                raise EOFError('closed during handshake')
            response += chunk
        assert response.startswith(b'HTTP/1.1 101 '), response

    def send(self, obj):
        data = json.dumps(obj).encode()
        assert len(data) < 126
        mask = os.urandom(4)
        self.sock.sendall(bytes([0x81, 0x80 | len(data)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def read(self):
        def exact(n):
            result = b''
            while len(result) < n:
                part = self.sock.recv(n - len(result))
                if not part:
                    raise EOFError('socket closed')
                result += part
            return result
        head = exact(2)
        length = head[1] & 127
        if length == 126:
            length = struct.unpack('!H', exact(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', exact(8))[0]
        assert head[0] & 15 == 1
        return json.loads(exact(length))

    def close(self):
        self.sock.close()

temp = tempfile.TemporaryDirectory(prefix='phase2-', dir=ROOT / 'build')
db = str(Path(temp.name) / 'messages.db')
server = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--no-redis', '--db', db], cwd=ROOT, stdout=subprocess.DEVNULL)
clients = []
try:
    time.sleep(1)
    assert server.poll() is None, 'server did not start'
    a, b = Client(), Client()
    clients.extend([a, b])
    a.send({'type': 'join', 'room_id': 'room_001'})
    assert a.read()['message'] == 'authentication required'
    a.send({'type': 'auth', 'token': 'wrong'})
    assert a.read()['message'] == 'invalid credentials'
    for client, token, user in ((a, 'demo-alice', 'alice'), (b, 'demo-bob', 'bob')):
        client.send({'type': 'auth', 'token': token})
        assert client.read() == {'type': 'auth_ok', 'user_id': user}
        client.send({'type': 'join', 'room_id': 'room_001'})
        assert client.read() == {'type': 'joined', 'room_id': 'room_001'}
    a.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '1', 'content': 'hello'})
    first_ack = a.read()
    assert first_ack['type'] == 'send_ok' and not first_ack['duplicate']
    first_id = first_ack['message_id']
    for client in (a, b):
        message = client.read()
        assert message['type'] == 'message' and message['message_id'] == first_id and message['sender_id'] == 'alice' and message['content'] == 'hello', message
    a.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '1', 'content': 'hello'})
    retry = a.read()
    assert retry['type'] == 'send_ok' and retry['duplicate'] and retry['message_id'] == first_id
    a.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '1', 'content': 'conflict'})
    assert a.read()['message'] == 'client_msg_id conflict'
    a.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': -1})
    assert a.read()['message'] == 'invalid after_message_id'
    b.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '2', 'content': 'reply'})
    second_ack = b.read()
    assert second_ack['type'] == 'send_ok' and not second_ack['duplicate']
    for client in (a, b):
        message = client.read()
        assert message['message_id'] == second_ack['message_id'] and message['sender_id'] == 'bob' and message['content'] == 'reply'
    b.send({'type': 'ack', 'room_id': 'room_001', 'message_id': first_id})
    assert b.read()['type'] == 'ack_ok'
    b.send({'type': 'leave', 'room_id': 'room_001'})
    assert b.read() == {'type': 'left', 'room_id': 'room_001'}
    b.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '2', 'content': 'no'})
    assert b.read()['message'] == 'not in room'
    a.send({'type': 'send', 'room_id': 'room_001', 'client_msg_id': '3', 'content': 'after leave'})
    assert a.read()['type'] == 'send_ok'
    assert a.read()['content'] == 'after leave'
    b.sock.settimeout(0.4)
    try:
        b.read()
        raise AssertionError('left client received a broadcast')
    except socket.timeout:
        pass
    a.close(); b.close(); clients.clear()
    server.terminate(); assert server.wait(timeout=5) == 0, 'server did not shut down cleanly'
    server = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--no-redis', '--db', db], cwd=ROOT, stdout=subprocess.DEVNULL)
    time.sleep(1)
    assert server.poll() is None, 'server restart failed'
    b = Client(); clients.append(b)
    b.send({'type': 'auth', 'token': 'demo-bob'}); assert b.read()['type'] == 'auth_ok'
    b.send({'type': 'join', 'room_id': 'room_001'}); assert b.read()['type'] == 'joined'
    b.send({'type': 'history', 'room_id': 'room_001'})
    history = b.read()
    assert history['after_message_id'] == first_id
    assert [item['content'] for item in history['messages']] == ['reply', 'after leave']
    b.send({'type': 'history', 'room_id': 'room_001', 'after_message_id': 0})
    assert len(b.read()['messages']) == 3
    print('PASS: bidirectional rooms, deduplication, ACK and history after restart')
finally:
    for client in clients:
        client.close()
    server.terminate()
    assert server.wait(timeout=5) == 0, 'server did not shut down cleanly'
    temp.cleanup()

#!/usr/bin/env python3
"""Small dependency-free WebSocket handshake and text-frame smoke test."""
import base64
import json
import os
import socket
import struct
import sys

payload = sys.argv[1].encode()
expected = sys.argv[2].encode()
key = base64.b64encode(os.urandom(16)).decode()
with socket.create_connection(('127.0.0.1', 9001), timeout=5) as sock:
    sock.sendall((f'GET / HTTP/1.1\r\nHost: 127.0.0.1:9001\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
    response = b''
    while b'\r\n\r\n' not in response:
        response += sock.recv(1)
    assert response.startswith(b'HTTP/1.1 101 '), response
    assert len(payload) < 126
    mask = os.urandom(4)
    sock.sendall(bytes([0x81, 0x80 | len(payload)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    def read_exact(count):
        data = b''
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise EOFError('connection closed')
            data += chunk
        return data
    header = read_exact(2)
    length = header[1] & 127
    if length == 126:
        length = struct.unpack('!H', read_exact(2))[0]
    elif length == 127:
        length = struct.unpack('!Q', read_exact(8))[0]
    result = read_exact(length)
    try:
        matches = json.loads(result) == json.loads(expected)
    except (ValueError, UnicodeDecodeError):
        matches = result == expected
    assert header[0] & 15 == 1 and matches, (header, result)
    print('PASS: HTTP 101, sent', repr(payload.decode()), 'received', repr(result.decode()))

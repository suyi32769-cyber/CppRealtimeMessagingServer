import base64
import json
import os
import socket
import struct

class Client:
    def __init__(self, port=9001):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=3)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        response = b''
        while not response.endswith(b'\r\n\r\n'):
            chunk = self.sock.recv(1)
            if not chunk:
                raise EOFError('closed during handshake')
            response += chunk
        assert response.startswith(b'HTTP/1.1 101 '), response

    def send(self, obj):
        self.send_raw(json.dumps(obj).encode())

    def send_raw(self, data, opcode=1):
        mask = os.urandom(4)
        length = len(data)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack('!H', length)
        else:
            header += bytes([0x80 | 127]) + struct.pack('!Q', length)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def read_frame(self):
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
        return head[0] & 15, exact(length)

    def read(self):
        opcode, payload = self.read_frame()
        assert opcode == 1, (opcode, payload)
        return json.loads(payload)

    def close(self):
        self.sock.close()

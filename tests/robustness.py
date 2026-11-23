#!/usr/bin/env python3
"""Check invalid inputs and a real SQLite writer-lock failure, then recovery."""
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='realtime-robust-') as tmp:
    db = str(Path(tmp) / 'messages.db')
    server = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--no-redis', '--port', '19003', '--db', db],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clients = []
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                c = Client(19003); clients.append(c); break
            except OSError:
                assert server.poll() is None and time.monotonic() < deadline, 'server failed to start'
                time.sleep(0.1)
        c.sock.settimeout(8)
        c.send_raw(b'{broken')
        assert c.read()['type'] == 'error'
        c.send({'type': 'auth', 'token': 'demo-alice'}); assert c.read()['type'] == 'auth_ok'
        c.send({'type': 'join', 'room_id': 'room'}); assert c.read()['type'] == 'joined'
        with sqlite3.connect(db, timeout=1) as connection:
            connection.execute('BEGIN IMMEDIATE')
            c.send({'type': 'send', 'room_id': 'room', 'client_msg_id': 'lock', 'content': 'blocked'})
            assert c.read()['message'] == 'storage failure'
            connection.rollback()
        c.send({'type': 'send', 'room_id': 'room', 'client_msg_id': 'ok', 'content': 'recovered'})
        assert c.read()['type'] == 'send_ok'
        assert c.read()['content'] == 'recovered'
        c.send_raw(b'x' * 16385)
        try:
            opcode, payload = c.read_frame()
            assert opcode == 8, (opcode, payload)
        except (EOFError, ConnectionResetError):
            pass  # uWebSockets may terminate TCP directly on an oversized frame.
        another = Client(19003); clients.append(another)
        another.send({'type': 'ping'}); assert another.read()['type'] == 'pong'
        assert server.poll() is None
        print('PASS: malformed JSON, SQLite lock error and recovery, oversized frame, process survives')
    finally:
        for c in clients: c.close()
        if server.poll() is None:
            server.terminate()
            assert server.wait(timeout=8) == 0, 'unclean server shutdown'

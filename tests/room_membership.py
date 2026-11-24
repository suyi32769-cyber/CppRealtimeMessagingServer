#!/usr/bin/env python3
"""Exercise persistent membership and cross-instance authorization."""
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
children, clients = [], []

def start(command):
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    children.append(process)
    return process

def connect(port, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try: return Client(port)
        except OSError: time.sleep(.1)
    raise AssertionError('server failed to start')

def request(c, payload, expected):
    c.send(payload)
    result = c.read()
    assert result['type'] == expected, result
    return result

def login(c, token):
    request(c, {'type': 'auth', 'token': token}, 'auth_ok')

with tempfile.TemporaryDirectory(prefix='room-members-') as tmp:
    db = str(Path(tmp) / 'messages.db')
    try:
        redis = start(['redis-server', '--bind', '127.0.0.1', '--port', '16382', '--save', '', '--appendonly', 'no'])
        time.sleep(.5)
        assert redis.poll() is None
        a_process = start([str(ROOT / 'build/realtime_server'), '--port', '19111', '--instance-id', 'membership-A', '--redis-port', '16382', '--db', db])
        b_process = start([str(ROOT / 'build/realtime_server'), '--port', '19112', '--instance-id', 'membership-B', '--redis-port', '16382', '--db', db])
        a = connect(19111, a_process); b = connect(19112, b_process); b2 = connect(19112, b_process)
        clients.extend([a, b, b2])
        login(a, 'demo-alice'); login(b, 'demo-bob'); login(b2, 'demo-bob')
        request(b, {'type': 'join', 'room_id': 'missing'}, 'error')
        request(a, {'type': 'create_room', 'room_id': 'room'}, 'room_created')
        request(b, {'type': 'create_room', 'room_id': 'room'}, 'error')
        request(b, {'type': 'history', 'room_id': 'room'}, 'error')
        for c in (a, b, b2): request(c, {'type': 'join', 'room_id': 'room'}, 'joined')
        with sqlite3.connect(db) as sql:
            assert sql.execute('SELECT user_id FROM room_members WHERE room_id=? ORDER BY user_id', ('room',)).fetchall() == [('alice',), ('bob',)]
        request(b, {'type': 'leave', 'room_id': 'room'}, 'left')
        with sqlite3.connect(db) as sql:
            assert sql.execute('SELECT count(*) FROM room_members WHERE room_id=? AND user_id=?', ('room', 'bob')).fetchone()[0] == 0
        request(b2, {'type': 'history', 'room_id': 'room'}, 'error')
        request(b2, {'type': 'send', 'room_id': 'room', 'client_msg_id': 'denied', 'content': 'denied'}, 'error')
        request(a, {'type': 'send', 'room_id': 'room', 'client_msg_id': 'first', 'content': 'hello'}, 'send_ok')
        assert a.read()['content'] == 'hello'
        b2.sock.settimeout(.8)
        try:
            b2.read()
            raise AssertionError('former member received a broadcast')
        except socket.timeout:
            pass
        b2.sock.settimeout(3)
        request(b2, {'type': 'join', 'room_id': 'room'}, 'joined')
        request(a, {'type': 'send', 'room_id': 'room', 'client_msg_id': 'second', 'content': 'welcome'}, 'send_ok')
        assert a.read()['content'] == 'welcome'
        assert b2.read()['content'] == 'welcome'
        for c in clients: c.close()
        clients.clear()
        for p in (a_process, b_process):
            p.terminate(); assert p.wait(timeout=8) == 0
        with sqlite3.connect(db) as sql:
            assert sql.execute('SELECT user_id FROM room_members WHERE room_id=? ORDER BY user_id', ('room',)).fetchall() == [('alice',), ('bob',)]
        restarted = start([str(ROOT / 'build/realtime_server',), '--port', '19111', '--instance-id', 'membership-A', '--redis-port', '16382', '--db', db])
        b = connect(19111, restarted); clients.append(b); login(b, 'demo-bob')
        request(b, {'type': 'join', 'room_id': 'room'}, 'joined')
        history = request(b, {'type': 'history', 'room_id': 'room', 'after_message_id': 0}, 'history')
        assert [m['content'] for m in history['messages']] == ['hello', 'welcome']
        print('PASS: creation, persistent membership, cross-instance access checks and broadcasts')
    finally:
        for c in clients: c.close()
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=8)
                except subprocess.TimeoutExpired: p.kill(); p.wait()

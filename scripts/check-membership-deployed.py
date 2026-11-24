#!/usr/bin/env python3
"""Check membership enforcement on deployed instances using a new test room."""
import socket
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
from ws_client import Client

room = 'members-' + uuid.uuid4().hex
clients = []
def request(client, payload, expected):
    client.send(payload)
    response = client.read()
    assert response['type'] == expected, response
    return response
try:
    a, b, stale = Client(9001), Client(9002), Client(9002)
    clients.extend([a, b, stale])
    for client, token in ((a, 'demo-alice'), (b, 'demo-bob'), (stale, 'demo-bob')):
        request(client, {'type': 'auth', 'token': token}, 'auth_ok')
    request(a, {'type': 'create_room', 'room_id': room}, 'room_created')
    request(b, {'type': 'history', 'room_id': room}, 'error')
    for client in (a, b, stale): request(client, {'type': 'join', 'room_id': room}, 'joined')
    request(b, {'type': 'leave', 'room_id': room}, 'left')
    request(stale, {'type': 'history', 'room_id': room}, 'error')
    request(stale, {'type': 'send', 'room_id': room, 'client_msg_id': uuid.uuid4().hex, 'content': 'denied'}, 'error')
    request(a, {'type': 'send', 'room_id': room, 'client_msg_id': uuid.uuid4().hex, 'content': 'membership-check'}, 'send_ok')
    assert a.read()['content'] == 'membership-check'
    stale.sock.settimeout(1)
    try:
        stale.read()
        raise AssertionError('former member received a new broadcast')
    except socket.timeout:
        pass
    print('PASS: former member cannot read, send, or receive new broadcasts; room=' + room)
finally:
    for client in clients: client.close()

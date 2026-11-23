#!/usr/bin/env python3
"""Send a real persisted test message through already-running local instances."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
from ws_client import Client

room = 'check-' + uuid.uuid4().hex
clients = []
try:
    a, b = Client(9001), Client(9002)
    clients.extend([a, b])
    for client, token in ((a, 'demo-alice'), (b, 'demo-bob')):
        client.send({'type': 'auth', 'token': token}); assert client.read()['type'] == 'auth_ok'
        client.send({'type': 'join', 'room_id': room}); assert client.read()['type'] == 'joined'
    a.send({'type': 'send', 'room_id': room, 'client_msg_id': uuid.uuid4().hex, 'content': 'deployment-check'})
    confirmation = a.read(); assert confirmation['type'] == 'send_ok' and not confirmation['duplicate']
    assert a.read()['message_id'] == confirmation['message_id']
    assert b.read()['message_id'] == confirmation['message_id']
    b.send({'type': 'ack', 'room_id': room, 'message_id': confirmation['message_id']})
    assert b.read()['type'] == 'ack_ok'
    print('PASS: deployed instances exchange a persisted message and ACK; room=' + room)
finally:
    for client in clients: client.close()

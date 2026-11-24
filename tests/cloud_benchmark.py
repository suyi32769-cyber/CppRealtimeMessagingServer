#!/usr/bin/env python3
"""Paced two-client smoke benchmark; reports successes and failures separately."""
import json
import os
import platform
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
CLIENTS, SECONDS, PAUSE = 2, 5, 0.05
samples, errors, children = [], [], []
lock = threading.Lock()
ready = threading.Barrier(CLIENTS + 1)
start = threading.Event()
deadline = 0

def wait_port(port, process):
    until = time.monotonic() + 12
    while time.monotonic() < until and process.poll() is None:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.3): return
        except OSError: time.sleep(.1)
    raise RuntimeError(f'port {port} did not start')

def run_client(index):
    client = None
    try:
        client = Client(19111 + index); client.sock.settimeout(15)
        client.send({'type': 'auth', 'token': ('demo-alice', 'demo-bob')[index]})
        assert client.read()['type'] == 'auth_ok'
        room = f'bench-{index}'
        client.send({'type': 'create_room', 'room_id': room}); assert client.read()['type'] in ('room_created', 'error')
        client.send({'type': 'join', 'room_id': room}); assert client.read()['type'] == 'joined'
        ready.wait(timeout=15); start.wait()
        count = 0
        while time.monotonic() < deadline:
            count += 1
            begin = time.perf_counter()
            client.send({'type': 'send', 'room_id': room, 'client_msg_id': f'{index}-{count}', 'content': 'x' * 16})
            response = client.read()
            if response.get('type') != 'send_ok':
                with lock: errors.append(str(response))
            else:
                latency = (time.perf_counter() - begin) * 1000
                event = client.read()
                if event.get('message_id') != response['message_id']: raise RuntimeError('wrong message ID')
                with lock: samples.append(latency)
            time.sleep(PAUSE)
    except Exception as exc:
        with lock: errors.append(f'client {index}: {exc}')
        ready.abort()
    finally:
        if client: client.close()

with tempfile.TemporaryDirectory(prefix='realtime-cloud-bench-') as tmp:
    workers = []
    try:
        redis = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', '16381', '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(redis); wait_port(16381, redis)
        db = str(Path(tmp) / 'messages.db')
        for index in range(CLIENTS):
            port = 19111 + index
            p = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--port', str(port), '--instance-id', f'cloud-{index}',
                                  '--redis-port', '16381', '--db', db], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(p)
        for index, p in enumerate(children[1:]): wait_port(19111 + index, p)
        for index in range(CLIENTS):
            t = threading.Thread(target=run_client, args=(index,)); workers.append(t); t.start()
        ready.wait(timeout=20)
        begin = time.monotonic(); deadline = begin + SECONDS; start.set()
        for t in workers: t.join(timeout=20)
        elapsed = time.monotonic() - begin
        if any(t.is_alive() for t in workers): raise RuntimeError('client timed out')
        if not samples: raise RuntimeError(f'no successful messages: {errors}')
        samples.sort()
        def p(q): return round(samples[int((len(samples) - 1) * q)], 3)
        print(json.dumps({'environment': platform.platform(), 'logical_cpus': os.cpu_count(), 'clients': CLIENTS,
                          'content_bytes': 16, 'pause_ms_per_client': round(PAUSE * 1000),
                          'elapsed_seconds': round(elapsed, 3), 'successful_messages': len(samples),
                          'messages_per_second': round(len(samples) / elapsed, 2),
                          'ack_latency_ms_p50': p(.5), 'ack_latency_ms_p95': p(.95),
                          'ack_latency_ms_p99': p(.99), 'errors': errors}, indent=2))
    finally:
        start.set()
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=8)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
        for t in workers: t.join(timeout=4)

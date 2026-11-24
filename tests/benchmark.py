#!/usr/bin/env python3
"""Small local concurrency probe, not a production capacity benchmark."""
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
COUNT, DURATION, CONTENT = 8, 5, 'x' * 16
latencies, errors = [], []
lock = threading.Lock()
ready = threading.Barrier(COUNT + 1)
start = threading.Event()
deadline = 0.0

def wait_port(port, process):
    end = time.monotonic() + 15
    while time.monotonic() < end and process.poll() is None:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2): return
        except OSError: time.sleep(0.1)
    raise RuntimeError(f'process on {port} failed to start')

def client_task(index):
    client = None
    try:
        client = Client(19001 if index % 2 == 0 else 19002)
        client.sock.settimeout(15)
        client.send({'type': 'auth', 'token': 'demo-alice' if index % 2 == 0 else 'demo-bob'})
        assert client.read()['type'] == 'auth_ok'
        room = f'r{index}'
        client.send({'type': 'create_room', 'room_id': room}); assert client.read()['type'] in ('room_created', 'error')
        client.send({'type': 'join', 'room_id': room}); assert client.read()['type'] == 'joined'
        ready.wait(timeout=10); start.wait()
        seq = 0
        local = []
        while time.monotonic() < deadline:
            seq += 1
            begin = time.perf_counter()
            client.send({'type': 'send', 'room_id': room, 'client_msg_id': f'{index}-{seq}', 'content': CONTENT})
            response = client.read()
            if response.get('type') != 'send_ok': raise RuntimeError(str(response))
            local.append((time.perf_counter() - begin) * 1000)
            message = client.read()
            if message.get('message_id') != response['message_id']: raise RuntimeError('incorrect local message')
        with lock: latencies.extend(local)
    except Exception as exc:
        with lock: errors.append(f'client {index}: {exc}')
        try: ready.abort()
        except Exception: pass
    finally:
        if client: client.close()

def percentile(sorted_values, percent):
    return sorted_values[min(len(sorted_values) - 1, int((len(sorted_values) - 1) * percent))]

processes, threads = [], []
with tempfile.TemporaryDirectory(prefix='bench-') as tmp:
    try:
        redis = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', '16380', '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(redis); wait_port(16380, redis)
        db = str(Path(tmp) / 'messages.db')
        log = open(Path(tmp) / 'server.log', 'w+')
        for port, name in ((19001, 'bench-A'), (19002, 'bench-B')):
            proc = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--port', str(port), '--instance-id', name,
                                     '--redis-port', '16380', '--db', db], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=log)
            processes.append(proc)
        for port, proc in zip((19001, 19002), processes[1:]): wait_port(port, proc)
        for i in range(COUNT):
            t = threading.Thread(target=client_task, args=(i,)); threads.append(t); t.start()
        ready.wait(timeout=15)
        begin = time.monotonic(); deadline = begin + DURATION; start.set()
        for t in threads: t.join(timeout=15)
        elapsed = time.monotonic() - begin
        if any(t.is_alive() for t in threads): raise RuntimeError('benchmark client did not finish')
        if errors or not latencies:
            log.flush(); log.seek(0)
            raise RuntimeError(f'benchmark failed: {errors}; server log: {log.read()[-4000:]}')
        latencies.sort()
        result = {'environment': platform.platform(), 'database_directory': str(Path(tmp).parent), 'logical_cpus': os.cpu_count(), 'clients': COUNT,
                  'content_bytes': len(CONTENT), 'target_seconds': DURATION, 'elapsed_seconds': round(elapsed, 3),
                  'successful_messages': len(latencies), 'messages_per_second': round(len(latencies) / elapsed, 2),
                  'ack_latency_ms_p50': round(percentile(latencies, .50), 3),
                  'ack_latency_ms_p95': round(percentile(latencies, .95), 3),
                  'ack_latency_ms_p99': round(percentile(latencies, .99), 3), 'errors': errors}
        print(json.dumps(result, indent=2))
    finally:
        start.set()
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=8)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        for t in threads: t.join(timeout=4)

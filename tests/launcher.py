#!/usr/bin/env python3
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent

def wait_for(port, listening, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.2): active = True
        except OSError: active = False
        if active == listening: return
        time.sleep(.1)
    raise RuntimeError(f'port {port} state did not become {listening}')

with tempfile.TemporaryDirectory(prefix='realtime-launch-') as tmp:
    redis = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', '16379', '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    launcher = None
    try:
        wait_for(16379, True)
        assert redis.poll() is None
        env = os.environ.copy(); env['REDIS_PORT'] = '16379'
        launcher = subprocess.Popen(['bash', str(ROOT / 'scripts/run-demo.sh'), str(Path(tmp) / 'db.sqlite')], cwd=ROOT,
                                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for port in (9001, 9002): wait_for(port, True)
        for port in (9001, 9002):
            c = Client(port); c.send({'type': 'ping'}); assert c.read()['type'] == 'pong'; c.close()
        assert launcher.poll() is None
        launcher.terminate(); launcher.wait(timeout=10)
        for port in (9001, 9002): wait_for(port, False)
        print('PASS: demo launcher starts and stops both local instances')
    finally:
        if launcher is not None and launcher.poll() is None:
            launcher.terminate(); launcher.wait(timeout=10)
        if redis.poll() is None:
            redis.terminate(); redis.wait(timeout=5)

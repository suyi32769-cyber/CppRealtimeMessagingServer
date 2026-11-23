#!/usr/bin/env python3
"""Run phase-1 smoke tests with temporary local processes; needs a completed build."""
import subprocess
import sys
import time
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent

def run_with_server(server, checks):
    process = subprocess.Popen(server, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError(f'{server[0]} exited before test')
        for command in checks:
            subprocess.run(command, cwd=root, check=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

run_with_server(['redis-server', '--bind', '127.0.0.1', '--port', '16379', '--save', '', '--appendonly', 'no'],
                [[str(root / 'build/dependency_smoke')]])
with tempfile.TemporaryDirectory(prefix='phase1-', dir=root / 'build') as tmp:
    run_with_server([str(root / 'build/realtime_server'), '--no-redis', '--db', str(Path(tmp) / 'messages.db')], [
        [sys.executable, str(root / 'tests/ws_smoke.py'), '{"type":"ping"}', '{"type":"pong"}'],
        [sys.executable, str(root / 'tests/ws_smoke.py'), 'invalid', '{"type":"error","message":"expected JSON object with type ping"}'],
    ])

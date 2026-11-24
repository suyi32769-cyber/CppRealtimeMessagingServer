#!/usr/bin/env python3
"""Restart only the two verified processes recorded by deploy-local.sh; preserve data."""
import os
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2 or not Path(sys.argv[1]).is_absolute():
    raise SystemExit('Usage: python3 scripts/restart-deployed.py /absolute/data-directory')
data = Path(sys.argv[1]).resolve()
database = str(data / 'messages.db')
if not Path(database).is_file(): raise SystemExit('Existing database not found')
connections = subprocess.run(['ss', '-Htn', 'state', 'established', '( sport = :9001 or sport = :9002 )'],
                             capture_output=True, text=True, check=True)
if connections.stdout.strip(): raise SystemExit('Active clients detected; refusing to disconnect them')
old = []
try:
    for name, port in (('A', '9001'), ('B', '9002')):
        pid = int((data / f'{name}.pid').read_text().strip())
        if pid <= 1: raise RuntimeError('invalid recorded PID')
        pidfd = os.pidfd_open(pid)
        old.append(pidfd)
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]
        expected_tail = ['--port', port, '--instance-id', name, '--db', database]
        cwd = os.readlink(f'/proc/{pid}/cwd')
        decoded = [os.fsdecode(value) for value in args]
        if (not decoded or decoded[0] not in ('./build/realtime_server', str(ROOT / 'build/realtime_server'))
                or decoded[1:] != expected_tail or Path(cwd).resolve() != ROOT):
            raise RuntimeError(f'PID {pid} does not match the expected instance; no signal sent')
    for fd in old: signal.pidfd_send_signal(fd, signal.SIGTERM)
    poller = select.poll()
    for fd in old: poller.register(fd, select.POLLIN)
    done = set()
    deadline = time.monotonic() + 10
    while len(done) < len(old) and time.monotonic() < deadline:
        done.update(fd for fd, _ in poller.poll(200))
    if len(done) != len(old): raise RuntimeError('old instances did not exit in time')
finally:
    for fd in old: os.close(fd)

new = []
try:
    for name, port in (('A', 9001), ('B', 9002)):
        with (data / f'{name}.log').open('ab') as log:
            process = subprocess.Popen([str(ROOT / 'build/realtime_server'), '--port', str(port), '--instance-id', name,
                                        '--db', database], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
        new.append((name, port, process))
    for name, port, process in new:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError(f'new instance {name} failed to listen')
    for name, port, process in new:
        temp = data / f'{name}.pid.new'
        temp.write_text(f'{process.pid}\n')
        os.replace(temp, data / f'{name}.pid')
    print('Restarted ' + ' '.join(f'{name}={process.pid}' for name, _, process in new))
except Exception:
    for _, _, process in new:
        if process.poll() is None: process.terminate()
    for _, _, process in new:
        if process.poll() is None: process.wait(timeout=10)
    raise

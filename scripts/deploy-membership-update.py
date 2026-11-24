#!/usr/bin/env python3
"""Install a pre-tested membership build, backing up the live database and files."""
import os
import shutil
import sqlite3
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

root = Path('/opt/CppRealtimeMessagingServer')
stage = Path('/tmp/realtime-membership-check')
data = Path('/opt/CppRealtimeMessagingServer-data')
live = root / 'build/realtime_server'
if not (stage / 'build/realtime_server').is_file() or not (data / 'messages.db').is_file():
    raise SystemExit('Missing verified stage or live database')

active = subprocess.run(['ss', '-Htn', 'state', 'established', '( sport = :9001 or sport = :9002 )'], capture_output=True, text=True, check=True)
if active.stdout.strip():
    raise SystemExit('Active clients detected; refusing to interrupt them')

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = data / 'backups' / ('before-membership-' + stamp)
backup.mkdir(parents=True, exist_ok=False)
with sqlite3.connect(f'file:{data / "messages.db"}?mode=ro', uri=True) as source, sqlite3.connect(backup / 'messages.db') as dest:
    source.backup(dest)
    assert dest.execute('PRAGMA integrity_check').fetchone() == ('ok',)
shutil.copy2(live, backup / 'realtime_server')
paths = ['CMakeLists.txt', 'src', 'tests', 'scripts', 'docs/phase2.md']
with tarfile.open(backup / 'source.tar.gz', 'w:gz') as archive:
    for name in paths:
        path = root / name
        if path.exists(): archive.add(path, arcname=name)
print('Backup:', backup, flush=True)

for name in ['CMakeLists.txt', 'src', 'tests', 'scripts']:
    src, target = stage / name, root / name
    if src.is_dir(): shutil.copytree(src, target, dirs_exist_ok=True)
    else: shutil.copy2(src, target)
if (stage / 'docs/phase2.md').is_file(): shutil.copy2(stage / 'docs/phase2.md', root / 'docs/phase2.md')
new_binary = live.with_name('realtime_server.membership-new')
shutil.copy2(stage / 'build/realtime_server', new_binary)
os.replace(new_binary, live)
print('Restarting verified instances', flush=True)
subprocess.run(['python3', str(root / 'scripts/restart-deployed.py'), str(data)], cwd=root, check=True)
deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    subscribers = subprocess.run(['redis-cli', '--raw', 'PUBSUB', 'NUMSUB', 'cpp-realtime-messages-v1'], capture_output=True, text=True, check=True).stdout.splitlines()
    if len(subscribers) >= 2 and int(subscribers[1]) >= 2: break
    time.sleep(.2)
else:
    raise RuntimeError('Both Redis subscribers did not become ready')
subprocess.run(['python3', str(root / 'scripts/check-demo.py')], cwd=root, check=True)
print('Membership deployment verified', flush=True)

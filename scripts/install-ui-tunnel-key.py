#!/usr/bin/env python3
"""Install one dedicated forwarding-only key; no shell or other destination access."""
import os
from pathlib import Path

public = Path('/tmp/realtime-ui-forward-only.pub').read_text(encoding='ascii').strip()
parts = public.split()
if len(parts) != 3 or parts[0] != 'ssh-ed25519' or parts[2] != 'realtime-ui-forward-only':
    raise SystemExit('Unexpected public key format')
ssh_dir = Path('/root/.ssh')
authorized = ssh_dir / 'authorized_keys'
if not ssh_dir.is_dir() or not authorized.is_file():
    raise SystemExit('Expected existing root SSH configuration')
entry = 'restrict,port-forwarding,permitopen="127.0.0.1:9001",permitopen="127.0.0.1:9002",command="/bin/false" ' + public
existing = authorized.read_text(encoding='utf-8')
if parts[1] not in existing:
    with authorized.open('a', encoding='utf-8') as handle:
        if existing and not existing.endswith('\n'): handle.write('\n')
        handle.write(entry + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    print('Installed forwarding-only UI key for ports 9001 and 9002')
else:
    assert entry in existing, 'Public key already exists with different restrictions'
    print('Forwarding-only UI key already installed')

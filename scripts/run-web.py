#!/usr/bin/env python3
"""Run the local UI and a restricted SSH tunnel to the two demo instances."""
import argparse
import functools
import http.server
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT.parent / 'realtime-frontend-key'
parser = argparse.ArgumentParser(description='Start the local messaging UI')
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--no-browser', action='store_true')
parser.add_argument('--no-tunnel', action='store_true', help='Use existing local forwards on 19001 and 19002')
args = parser.parse_args()

url = f'http://127.0.0.1:{args.port}/'
try:
    with urllib.request.urlopen(url, timeout=.5) as existing:
        body = existing.read(65536).decode('utf-8', errors='replace')
        if '<title>Realtime · 消息实验室</title>' in body:
            print(f'界面已经运行：{url}', flush=True)
            if not args.no_browser: webbrowser.open(url)
            sys.exit(0)
except (OSError, urllib.error.URLError):
    pass

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.2): return True
    except OSError: return False

tunnel = None
httpd = None
try:
    handler = functools.partial(Handler, directory=str(ROOT / 'web'))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    if not args.no_tunnel:
        if not (KEYS / 'id_ed25519').is_file() or not (KEYS / 'known_hosts').is_file():
            raise RuntimeError(f'未找到可视化专用的 SSH 密钥或服务器指纹：{KEYS}')
        if any(listening(port) for port in (19001, 19002)):
            raise RuntimeError('本机 19001 或 19002 端口已被占用，请先关闭其他可视化启动器。')
        command = ['ssh', '-N', '-T', '-i', str(KEYS / 'id_ed25519'), '-o', 'BatchMode=yes',
                   '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30',
                   '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=yes',
                   '-o', f'UserKnownHostsFile={KEYS / "known_hosts"}',
                   '-L', '127.0.0.1:19001:127.0.0.1:9001', '-L', '127.0.0.1:19002:127.0.0.1:9002',
                   'root@8.155.139.190']
        tunnel = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and tunnel.poll() is None:
            if listening(19001) and listening(19002): break
            time.sleep(.1)
        else: raise RuntimeError('SSH 隧道未能启动，请检查服务器运行状态和网络。')
    elif not all(listening(port) for port in (19001, 19002)):
        print('提示：本地 19001 / 19002 未全部监听，请自行启动端口转发。', flush=True)
    print(f'可视化界面：{url}', flush=True)
    print('保持此窗口打开。按 Ctrl+C 关闭界面和隧道。', flush=True)
    if not args.no_browser: webbrowser.open(url)
    httpd.timeout = 1
    while tunnel is None or tunnel.poll() is None:
        httpd.handle_request()
    raise RuntimeError('SSH 隧道已断开，请重新启动可视化界面。')
except KeyboardInterrupt:
    print('\n已关闭。', flush=True)
except (OSError, RuntimeError) as exc:
    print(f'启动失败：{exc}', file=sys.stderr, flush=True)
    sys.exit(1)
finally:
    if httpd: httpd.server_close()
    if tunnel and tunnel.poll() is None:
        tunnel.terminate()
        try: tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired: tunnel.kill(); tunnel.wait()

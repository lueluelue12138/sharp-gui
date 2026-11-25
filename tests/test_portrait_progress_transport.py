"""使用真实锁定 WebSocket 客户端和本机协议夹具，无需触发 GPU 推理。"""

import base64
import hashlib
import json
import socket
import struct
import threading
import time
from uuid import uuid4

import pytest

from backend.services import portrait_progress


@pytest.mark.parametrize('node', ['3', '378', '57'])
def test_locked_client_receives_live_progress_for_each_workbench(node):
    job = str(uuid4())
    done = threading.Event()
    failures = []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)

        def serve():
            try:
                channel, _ = listener.accept()
                with channel:
                    channel.settimeout(5)
                    request = b''
                    while b'\r\n\r\n' not in request:
                        request += channel.recv(4096)
                    headers = dict(line.split(':', 1) for line in request.decode().split('\r\n')[1:] if ':' in line)
                    key = next(value.strip() for name, value in headers.items() if name.lower() == 'sec-websocket-key')
                    accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
                    channel.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                                    b'Connection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
                    payload = json.dumps({'type': 'progress', 'data': {
                        'prompt_id': job, 'node': node, 'value': 6, 'max': 9}}).encode()
                    prefix = bytes([0x81, len(payload)]) if len(payload) < 126 else b'\x81\x7e' + struct.pack('!H', len(payload))
                    channel.sendall(prefix + payload)
                    done.wait(5)
            except Exception as exc:
                failures.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        connection = portrait_progress.connect(f'http://127.0.0.1:{listener.getsockname()[1]}')
        assert connection is not None
        portrait_progress.track(connection, job)
        try:
            deadline = time.monotonic() + 3
            while not portrait_progress.progress(job) and time.monotonic() < deadline:
                time.sleep(0.01)
            assert portrait_progress.progress(job) == {'node': node, 'value': 6, 'max': 9}
            assert portrait_progress.has_active()
        finally:
            portrait_progress.finish(job)
            done.set()
            thread.join(5)
        assert not failures

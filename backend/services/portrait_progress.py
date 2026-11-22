"""Track execution events for the client ID of a Sharp GUI job."""

import json
import threading
import time
from uuid import uuid4

try:
    import websocket
except ImportError:
    websocket = None

_jobs = {}
_lock = threading.Lock()


def connect(url):
    if websocket is None:
        return None
    client_id = uuid4().hex
    try:
        connection = websocket.create_connection(
            f'ws{url[4:]}/ws?clientId={client_id}', timeout=1.5,
            http_no_proxy=['127.0.0.1', 'localhost', '::1'],
        )
    except (OSError, websocket.WebSocketException):
        return None
    return client_id, connection


def update_progress(previous, event, prompt_id):
    data = event.get('data', {})
    if not isinstance(data, dict) or data.get('prompt_id') != prompt_id:
        return previous
    kind = event.get('type')
    if kind == 'executing' and data.get('node') is not None:
        node = str(data['node'])
        return previous if previous.get('node') == node else {'node': node}
    if kind == 'progress_state':
        nodes = data.get('nodes', {})
        if not isinstance(nodes, dict):
            return previous
        running = [item for item in nodes.values() if isinstance(item, dict) and item.get('state') == 'running']
        if not running:
            return previous
        item = next((item for item in running if str(item.get('node_id')) == previous.get('node')), running[-1])
        data = {**item, 'node': item.get('node_id')}
    elif kind != 'progress':
        return previous
    value, maximum = data.get('value'), data.get('max')
    node = data.get('node')
    if node is None or type(value) not in (int, float) or type(maximum) not in (int, float) or not 0 <= value <= maximum or not 0 < maximum < 10**9:
        return previous
    return {'node': str(node), 'value': value, 'max': maximum}


def track(connection, prompt_id):
    _, channel = connection
    stop = threading.Event()
    with _lock:
        _jobs[prompt_id] = (stop, {})

    def listen():
        deadline = time.monotonic() + 6 * 60 * 60
        current = {}
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    message = channel.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if message == '':
                    break
                if not isinstance(message, str):
                    continue
                event = json.loads(message)
                data = event.get('data', {})
                if (isinstance(data, dict) and event.get('type') in {'execution_success', 'execution_error', 'execution_interrupted'}
                        and data.get('prompt_id') == prompt_id):
                    break
                updated = update_progress(current, event, prompt_id)
                if updated is not current:
                    current = updated
                    with _lock:
                        if prompt_id in _jobs:
                            _jobs[prompt_id] = (stop, current)
        except (OSError, ValueError, websocket.WebSocketException):
            pass
        finally:
            channel.shutdown()
            finish(prompt_id)

    threading.Thread(target=listen, name='portrait-progress', daemon=True).start()


def progress(prompt_id):
    with _lock:
        item = _jobs.get(prompt_id)
        return item[1] if item else {}


def finish(prompt_id):
    with _lock:
        item = _jobs.pop(prompt_id, None)
    if item:
        item[0].set()

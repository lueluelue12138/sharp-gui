from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from uuid import uuid4

from PIL import Image, ImageOps

from backend.services import portrait_progress

try:
    from pillow_heif import register_heif_opener
except ImportError:
    register_heif_opener = None

WORKFLOW_FILE = Path(__file__).with_name('portrait_workflow.json')
DEFAULT_URL = 'http://127.0.0.1:8000'
COMFY_START_TIMEOUT = 150
_comfy_launch_lock = Lock()
_comfy_launch_deadline = None
_comfy_submit_lock = Lock()
_cancelled_requests = {}
_cancelled_request_ttl = 300
_request_id_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
MAX_UPLOAD = 24 * 1024 * 1024
ASSET_ROOT = '/extensions/portrait_sharp_repair/'
RENDER_ASSETS = {'splat_renderer.js', 'splat_worker.js'}
UPLOADS = {
    'source': ('input', 'sharp_gui_portrait'),
    'reference': ('input', 'portrait_sharp_references'),
    'capture': ('temp', 'portrait_sharp_views'),
    'mask': ('temp', 'portrait_sharp_masks'),
}
REFINE_PROMPT = (
    '精修遮罩区域内的自然纹理与清晰度。图 2 只提供纹理和细节，'
    '保持图 1 里人物的身份、脸部轮廓与长宽比、五官位置、姿态、打光和色彩。'
)


class PortraitError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def comfy_url():
    value = os.environ.get('SHARP_PORTRAIT_COMFY_URL', DEFAULT_URL).strip().rstrip('/')
    try:
        url = urlsplit(value)
        if (url.scheme == 'http' and url.hostname in {'127.0.0.1', 'localhost', '::1'}
                and url.port and url.netloc == value.split('://', 1)[1] and not url.username and not url.password):
            return value
    except ValueError:
        pass
    raise PortraitError('portraitOffline', 'Set SHARP_PORTRAIT_COMFY_URL to a local HTTP address with a port.', 503)


def comfy_open(path, body=None, content_type=None, timeout=15):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    headers = {'Content-Type': content_type} if content_type else {}
    try:
        return opener.open(Request(comfy_url() + path, data=body, headers=headers), timeout=timeout)
    except HTTPError as error:
        with error:
            if error.code == 404:
                raise PortraitError('portraitExpired', 'This ComfyUI resource has expired or is unavailable.', 404) from error
            try:
                payload = json.loads(error.read(32768))
                problems = payload.get('node_errors') or {}
                message = next((entry.get('message') for node in problems.values() for entry in node.get('errors', [])), None)
                message = message or (payload.get('error') or {}).get('message')
            except (ValueError, AttributeError, TypeError):
                message = None
            raise PortraitError('portraitComfyError', message or f'ComfyUI returned HTTP {error.code}.', 502) from error
    except (URLError, TimeoutError, OSError) as error:
        raise PortraitError('portraitOffline', 'ComfyUI is unreachable on the host computer.', 503) from error


def comfy_json(path, body=None, *, timeout=15):
    encoded = json.dumps(body).encode() if body is not None else None
    try:
        with comfy_open(path, encoded, 'application/json' if encoded else None, timeout) as response:
            return json.load(response)
    except (ValueError, OSError) as error:
        raise PortraitError('portraitComfyError', 'ComfyUI returned an unreadable response.', 502) from error


@lru_cache(maxsize=1)
def workflow_template():
    return json.loads(WORKFLOW_FILE.read_text(encoding='utf-8'))


@lru_cache(maxsize=4)
def capability(_url, _interval):
    info = comfy_json('/object_info', timeout=12)
    required = {node['class_type'] for node in workflow_template().values()} | {'PortraitSharpTrajectoryFrame'}
    missing = sorted(required.difference(info))
    for node_id, key in [('7', 'unet_name'), ('8', 'clip_name'), ('9', 'vae_name'), ('10', 'lora_name'), ('219', 'lora_name')]:
        node = workflow_template()[node_id]
        schema = info.get(node['class_type'], {}).get('input', {}).get('required', {}).get(key, [])
        choices = schema[0] if schema and isinstance(schema[0], list) else []
        if choices and node['inputs'][key] not in choices:
            missing.append(node['inputs'][key])
    if not missing:
        extensions = comfy_json('/extensions')
        missing.extend(sorted(asset for asset in RENDER_ASSETS if ASSET_ROOT + asset not in extensions))
    return missing


def status():
    global _comfy_launch_deadline
    result = {'repair_prompt': workflow_template()['12']['inputs']['prompt'],
              'can_start': hasattr(os, 'startfile')}
    try:
        missing = capability(comfy_url(), int(time.monotonic() // 20))
    except PortraitError as error:
        code = error.code
        with _comfy_launch_lock:
            if code == 'portraitOffline' and _comfy_launch_deadline is not None:
                code = 'portraitStarting' if time.monotonic() < _comfy_launch_deadline else 'portraitStartTimeout'
        return {**result, 'ready': False, 'code': code, 'missing': []}
    with _comfy_launch_lock:
        _comfy_launch_deadline = None
    return {**result, 'ready': not missing, 'code': 'portraitMissing' if missing else None, 'missing': missing}


def find_comfy_desktop():
    """查找主机上已有的 Comfy Desktop，保留安装时配置的工作区。"""
    configured = os.environ.get('SHARP_PORTRAIT_COMFY_EXE')
    if configured:
        path = Path(configured)
        if path.is_absolute() and path.suffix.lower() == '.exe' and path.is_file():
            return path
        raise PortraitError('portraitStartNotFound', 'The configured Comfy Desktop executable was not found.', 404)

    for env_key in ('APPDATA', 'PROGRAMDATA'):
        root = os.environ.get(env_key)
        if root:
            programs = Path(root) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
            for name in ('Comfy Desktop.lnk', 'ComfyUI Desktop.lnk', 'ComfyUI.lnk'):
                shortcut = programs / name
                if shortcut.is_file():
                    return shortcut
    for env_key in ('LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)'):
        root = os.environ.get(env_key)
        if root:
            programs = Path(root) / 'Programs' if env_key == 'LOCALAPPDATA' else Path(root)
            for folder, name in (('Comfy Desktop', 'Comfy Desktop.exe'), ('ComfyUI', 'ComfyUI.exe')):
                exe = programs / folder / name
                if exe.is_file():
                    return exe
    raise PortraitError('portraitStartNotFound', 'Comfy Desktop was not found on the host.', 404)


def start_comfy():
    """请求 Windows 启动已有的 Comfy Desktop，并合并重复启动请求。"""
    global _comfy_launch_deadline
    if not hasattr(os, 'startfile'):
        raise PortraitError('portraitStartUnsupported', 'One-click launch is available on Windows hosts.', 501)
    comfy_url()
    with _comfy_launch_lock:
        if _comfy_launch_deadline is not None and time.monotonic() < _comfy_launch_deadline:
            return 'starting'
        try:
            comfy_json('/queue', timeout=2)
        except PortraitError as error:
            if error.code != 'portraitOffline':
                raise
        else:
            _comfy_launch_deadline = None
            return 'online'

        try:
            os.startfile(str(find_comfy_desktop()))
        except OSError as error:
            raise PortraitError('portraitStartFailed', 'Windows could not open Comfy Desktop.', 503) from error
        capability.cache_clear()
        _comfy_launch_deadline = time.monotonic() + COMFY_START_TIMEOUT
        return 'starting'


def number(value, minimum, maximum, *, integer=False):
    if type(value) not in (int, float) or not minimum <= value <= maximum or (integer and type(value) is not int):
        raise PortraitError('portraitInvalid', 'A portrait setting is out of range.')
    return value


def upload_image(kind, upload):
    if upload is None:
        raise PortraitError('portraitInvalidImage', 'Select a supported image.')
    return upload_image_stream(kind, upload.stream)


def upload_image_stream(kind, stream):
    if kind not in UPLOADS:
        raise PortraitError('portraitInvalidImage', 'Select a supported image.')
    data = stream.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise PortraitError('portraitImageTooLarge', 'The upload exceeds 24 MB.', 413)
    generated = kind in {'mask', 'capture'}
    if not generated and register_heif_opener is not None:
        register_heif_opener()
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP', 'BMP', 'HEIF', 'HEIC'} or image.width * image.height > 40_000_000:
                raise ValueError
            if generated and (image.format != 'PNG' or image.mode != 'RGBA' or max(image.size) > 4096):
                raise ValueError
            if not generated:
                image = ImageOps.exif_transpose(image).convert('RGB')
                encoded = io.BytesIO()
                image.save(encoded, 'PNG', compress_level=2)
                data = encoded.getvalue()
            else:
                image.verify()
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise PortraitError('portraitInvalidImage', 'Upload a supported photo with up to 40 megapixels.') from error
    filename = f'{uuid4()}.png'
    storage, folder = UPLOADS[kind]
    boundary = uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
             for key, value in [('type', storage), ('subfolder', folder)]]
    parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode(),
                  data, f'\r\n--{boundary}--\r\n'.encode()])
    with comfy_open('/upload/image', b''.join(parts), f'multipart/form-data; boundary={boundary}', 60) as response:
        saved = json.load(response)
    if saved.get('name') != filename or saved.get('subfolder') != folder or saved.get('type') != storage:
        raise PortraitError('portraitComfyError', 'ComfyUI did not save the expected image.', 502)
    return {'filename': filename, 'subfolder': folder, 'type': storage}


def camera_inputs(camera, token, capture, edge):
    if not isinstance(camera, dict) or not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{64}', token):
        raise PortraitError('portraitInvalid', 'Build a Gaussian preview before selecting a camera.')
    matrices = {}
    for key, size in [('w2c', 4), ('K', 3)]:
        rows = camera.get(key)
        if not isinstance(rows, list) or len(rows) != size or any(not isinstance(row, list) or len(row) != size for row in rows):
            raise PortraitError('portraitInvalid', 'Invalid camera matrix.')
        matrices[key] = [[number(value, -1e7, 1e7) for value in row] for row in rows]
    width = number(camera.get('width'), 1, 32000, integer=True)
    height = number(camera.get('height'), 1, 32000, integer=True)
    edge = number(edge, 512, 2560, integer=True)
    if edge % 32:
        raise PortraitError('portraitInvalid', 'Choose a supported output size.')
    return {**matrices, 'token': token, 'capture': capture, 'width': width, 'height': height}, edge


def frame_size(width, height, edge):
    return [max(64, math.floor(value * edge / max(width, height) / 32 + 0.5) * 32) for value in (width, height)]


def match_reference_crop(prompt, crop, reference_edge):
    """让近景使用对应的原图局部作为细节参考。"""
    bounds = crop.get('bounds') if isinstance(crop, dict) else None
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise PortraitError('portraitInvalid', 'Invalid close-up reference crop.')
    left, top, right, bottom = (number(value, 0, 1) for value in bounds)
    if right - left < 0.2 or bottom - top < 0.2:
        raise PortraitError('portraitInvalid', 'The close-up reference crop is too small.')
    width = number(crop.get('width'), 1, 32000, integer=True)
    height = number(crop.get('height'), 1, 32000, integer=True)
    width, height = frame_size(width, height, min(max(width, height), reference_edge))
    crop_x, crop_y = round(left * width), round(top * height)
    prompt['10001'] = {'class_type': 'ImageCrop', 'inputs': {
        'image': ['3', 3], 'x': crop_x, 'y': crop_y,
        'width': round(right * width) - crop_x, 'height': round(bottom * height) - crop_y,
    }}
    prompt['12']['inputs']['image_2'] = ['10001', 0]


def submit(stage, source, options, *, model_token=None, capture=None, detail=None):
    prompt = copy.deepcopy(workflow_template())
    prompt['1']['inputs']['image'] = f'{source["subfolder"]}/{source["filename"]}'
    prompt['2']['inputs']['lens_mm'] = number(options.get('lens', 30), 12, 120)
    targets = ['3']
    if stage in {'repair', 'frame'}:
        # 工作台只覆盖用户参数，基础修复沿用 ComfyUI 原工作流的采样链路。
        repair_prompt = options.get('repair_prompt', '')
        if not isinstance(repair_prompt, str) or len(repair_prompt) > 4000:
            raise PortraitError('portraitInvalid', 'The repair prompt can contain up to 4,000 characters.')
        if repair_prompt.strip():
            prompt['12']['inputs']['prompt'] = repair_prompt.strip()
        camera_settings = prompt['3']['inputs']
        camera, edge = camera_inputs(options.get('camera'), model_token, capture, options.get('edge', camera_settings['long_edge']))
        reference_edge = number(options.get('repair_reference_edge', camera_settings['reference_edge']), 512, 2560, integer=True)
        if reference_edge % 32:
            raise PortraitError('portraitInvalid', 'Choose a supported source reference size.')
        camera_settings.update(camera=json.dumps(camera), long_edge=edge, reference_edge=reference_edge)
        reference_crop = options.get('reference_crop')
        if reference_crop is not None and (stage != 'frame' or options.get('mode') == 'repair'):
            match_reference_crop(prompt, reference_crop, reference_edge)
        prompt['14']['inputs']['noise_seed'] = number(options.get('seed', 1), 0, 2**53 - 1, integer=True)
        targets = ['20', '22']
        if stage == 'frame':
            sequence = options.get('sequence')
            mode = options.get('mode')
            if not isinstance(sequence, str) or not re.fullmatch(r'\d{8}-\d{6}-[a-f0-9]{8}', sequence) or mode not in {'repair', 'preview'}:
                raise PortraitError('portraitInvalid', 'Invalid trajectory settings.')
            count = number(options.get('count'), 1, 240, integer=True)
            index = number(options.get('index'), 1, count, integer=True)
            width, height = frame_size(camera['width'], camera['height'], edge)
            metadata = {'index': index, 'count': count, 'mode': mode, 'keyframe': options.get('keyframe') is True,
                        'camera': camera, 'width': width, 'height': height}
            prompt['10000'] = {'class_type': 'PortraitSharpTrajectoryFrame', 'inputs': {
                'image': ['19', 0] if mode == 'repair' else ['3', 4], 'sequence': sequence, 'metadata': json.dumps(metadata),
            }}
            targets = ['10000']
    if stage == 'refine':
        text = options.get('prompt', '')
        if not isinstance(text, str) or len(text) > 4000:
            raise PortraitError('portraitInvalid', 'The refinement prompt can contain up to 4,000 characters.')
        prompt['204']['inputs']['value'] = text.strip() or REFINE_PROMPT
        prompt['206']['inputs']['用户提示词'] = text.strip() or REFINE_PROMPT
        prompt['215']['inputs']['switch'] = options.get('optimize') is True
        prompt['22']['inputs'] = {'selection': json.dumps(detail)}
        prompt['352']['inputs']['denoise'] = number(options.get('strength', 0.44), 0.1, 1)
        maximum = number(options.get('sample_edge', 2048), 768, 3072, integer=True)
        prompt['222']['inputs'].update({'值': maximum, 'ghs_dom': str(maximum)})
        prompt['205']['inputs'].update({
            '遮罩扩展百分比': number(options.get('expand', 4), 0, 30, integer=True),
            '遮罩羽化百分比': number(options.get('feather', 5), 0, 30, integer=True),
            '颜色还原强度': number(options.get('color', 1), 0, 1),
        })
        prompt['224']['inputs']['seed'] = secrets.randbelow(2**50)
        targets = ['31']
    submission = {'prompt': prompt, 'partial_execution_targets': targets}
    request_id = options.get('request_id')
    if request_id is not None:
        if not isinstance(request_id, str) or not re.fullmatch(_request_id_pattern, request_id):
            raise PortraitError('portraitInvalid', 'Invalid portrait request ID.')
        fingerprint = hashlib.sha256(json.dumps([stage, source, options], sort_keys=True).encode()).hexdigest()
        submission.update(prompt_id=request_id, extra_data={'sharp_gui_portrait_request': fingerprint})
    connection = None
    try:
        with _comfy_submit_lock:
            if request_id:
                if _cancelled_requests.get((request_id, source['filename']), 0) > time.monotonic():
                    raise PortraitError('portraitCancelled', 'This portrait task was cancelled.', 409)
                existing = find_comfy_prompt(request_id)
                if existing is not None:
                    if existing[3].get('sharp_gui_portrait_request') != fingerprint:
                        raise PortraitError('portraitInvalid', 'This request ID belongs to another task.', 409)
                    return request_id
            connection = portrait_progress.connect(comfy_url())
            if connection:
                submission['client_id'] = connection[0]
            result = comfy_json('/prompt', submission, timeout=25)
        if not isinstance(result.get('prompt_id'), str):
            raise PortraitError('portraitComfyError', 'ComfyUI did not return a job ID.', 502)
    except BaseException:
        if connection:
            connection[1].shutdown()
        raise
    if connection:
        portrait_progress.track(connection, result['prompt_id'])
    return result['prompt_id']


def find_comfy_prompt(prompt_id):
    """查找同一个请求，页面恢复或连接重试时复用原来的任务。"""
    queue = comfy_json('/queue')
    for key in ('queue_running', 'queue_pending'):
        for entry in queue.get(key, []):
            if entry[1] == prompt_id:
                return entry
    history = comfy_json(f'/history/{prompt_id}').get(prompt_id)
    return history['prompt'] if history else None


def cancel_job(prompt_id, source_filename, *, unconfirmed=False):
    """只取消此工作台的任务，并阻止仍在途中的同一提交重新入队。"""
    pattern = _request_id_pattern if unconfirmed else r'[a-f0-9-]{36}'
    if not isinstance(prompt_id, str) or not re.fullmatch(pattern, prompt_id):
        raise PortraitError('portraitInvalid', 'Invalid job ID.')
    with _comfy_submit_lock:
        entry = find_comfy_prompt(prompt_id) if unconfirmed else None
        if entry is not None:
            image = entry[2].get('1', {}).get('inputs', {}).get('image')
            if image != f'sharp_gui_portrait/{source_filename}' or not entry[3].get('sharp_gui_portrait_request'):
                raise PortraitError('portraitInvalid', 'This request ID belongs to another task.', 409)
        if not unconfirmed or entry is not None:
            result = comfy_json(f'/api/jobs/{prompt_id}/cancel', {})
            if not isinstance(result, dict) or type(result.get('cancelled')) is not bool:
                raise PortraitError('portraitComfyError', 'ComfyUI did not acknowledge the cancellation.', 502)
        now = time.monotonic()
        for key, expires_at in list(_cancelled_requests.items()):
            if expires_at <= now:
                del _cancelled_requests[key]
        _cancelled_requests[(prompt_id, source_filename)] = now + _cancelled_request_ttl


def recent_legacy_jobs():
    """找回更新前已在 ComfyUI 中登记的近期建模和修复任务。"""
    queue = comfy_json('/queue')
    history = comfy_json('/history?max_items=24')
    entries = [(item['prompt'], item.get('outputs', {}), False) for item in history.values()]
    entries.extend((item, {}, True) for key in ('queue_running', 'queue_pending') for item in queue.get(key, []))
    cutoff = (time.time() - 1800) * 1000
    latest, models = {}, {}
    for entry, outputs, active in entries:
        if len(entry) < 5:
            continue
        _, job_id, graph, metadata, targets = entry[:5]
        started_at = metadata.get('create_time')
        if type(started_at) not in (int, float) or (not active and started_at < cutoff) or metadata.get('sharp_gui_portrait_request'):
            continue
        image = graph.get('1', {}).get('inputs', {}).get('image', '')
        if not isinstance(image, str) or not re.fullmatch(r'sharp_gui_portrait/[a-f0-9-]{36}\.png', image):
            continue
        source = image.split('/')[-1]
        stage = 'build' if targets == ['3'] else 'repair' if isinstance(targets, list) and set(targets) == {'20', '22'} else None
        if not stage:
            continue
        lens = graph.get('2', {}).get('inputs', {}).get('lens_mm', 30)
        context = {'stage': stage, 'source': source, 'lens': lens, 'id': job_id}
        camera = graph.get('3', {}).get('inputs', {})
        saved_camera = None
        if stage == 'repair':
            try:
                saved_camera = json.loads(camera.get('camera', '{}'))
                capture = saved_camera.get('capture')
            except (ValueError, AttributeError, TypeError):
                continue
            if not isinstance(capture, str) or not re.fullmatch(r'[a-f0-9-]{36}\.png', capture):
                continue
            context['capture'] = {'filename': capture, 'subfolder': 'portrait_sharp_views', 'type': 'temp'}
        view = outputs.get('3', {}).get('portrait_sharp_view')
        if view:
            models[source] = view[0]
        order = (active, started_at)
        if source not in latest or latest[source]['order'] < order:
            latest[source] = {
                'context': context, 'started_at': started_at, 'edge': camera.get('long_edge', 1920),
                'camera': saved_camera, 'order': order,
            }
    recovered = sorted(latest.values(), key=lambda item: item['order'], reverse=True)[:4]
    for item in recovered:
        item['model'] = models.get(item['context']['source'])
    return recovered


def get_job(prompt_id):
    if not re.fullmatch(r'[a-f0-9-]{36}', prompt_id):
        raise PortraitError('portraitInvalid', 'Invalid job ID.')
    history = comfy_json(f'/history/{prompt_id}').get(prompt_id)
    if history:
        portrait_progress.finish(prompt_id)
        status_info = history.get('status', {})
        if status_info.get('status_str') != 'success':
            for kind, details in reversed(status_info.get('messages', [])):
                if kind == 'execution_error':
                    return {'state': 'error', 'message': str(details.get('exception_message', ''))[:450]}
            return {'state': 'error', 'message': ''}
        return {'state': 'done', 'outputs': history.get('outputs', {})}
    queue = comfy_json('/queue')
    for state, key in [('running', 'queue_running'), ('queued', 'queue_pending')]:
        if any(entry[1] == prompt_id for entry in queue.get(key, [])):
            return {'state': state, **portrait_progress.progress(prompt_id)}
    if comfy_json(f'/history/{prompt_id}').get(prompt_id):
        return {'state': 'running'}
    raise PortraitError('portraitExpired', 'The ComfyUI job is no longer available.', 404)


def comfy_preview_folder():
    """定位正在运行的 ComfyUI 的专用取景模型缓存。"""
    override = os.environ.get('SHARP_PORTRAIT_COMFY_TEMP')
    if override:
        root = Path(override)
    else:
        argv = comfy_json('/system_stats').get('system', {}).get('argv', [])
        directories = {}
        if isinstance(argv, list) and all(isinstance(arg, str) for arg in argv):
            for index, arg in enumerate(argv):
                key, separator, value = arg.partition('=')
                if key in {'--temp-directory', '--base-directory'}:
                    directories[key] = value if separator else (argv[index + 1:index + 2] or [''])[0]
        base = directories.get('--temp-directory', directories.get('--base-directory'))
        if base is None and isinstance(argv, list) and argv and isinstance(argv[0], str) and Path(argv[0]).name == 'main.py':
            base = str(Path(argv[0]).parent)
        root = Path(base or '') / 'temp'

    if not root.is_absolute():
        raise PortraitError('portraitCacheUnknown', 'Could not locate the ComfyUI preview cache on this host.', 503)
    directory = root.resolve() / 'portrait_sharp'
    if directory.resolve() != directory:
        raise PortraitError('portraitCacheUnknown', 'The ComfyUI preview cache redirects to another folder.', 503)
    return directory


def release_memory():
    with _comfy_submit_lock:
        queue = comfy_json('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise PortraitError('portraitEngineBusy', 'Wait for the ComfyUI queue to finish before releasing memory.', 409)
        try:
            folder = comfy_preview_folder()
            files = list(folder.iterdir()) if folder.is_dir() else []
        except OSError as error:
            raise PortraitError('portraitCacheUnknown', 'Could not read the ComfyUI preview cache.', 503) from error

        flags = json.dumps({'unload_models': True, 'free_memory': True}).encode()
        with comfy_open('/free', flags, 'application/json'):
            pass
        removed, failed = 0, 0
        for file in files:
            if not re.fullmatch(r'[a-f0-9]{64}\.ply', file.name) or file.is_symlink() or not file.is_file():
                continue
            try:
                file.unlink()
                removed += 1
            except FileNotFoundError:
                continue
            except OSError:
                failed += 1
        return {'requested': True, 'removed': removed, 'failed': failed}


def open_media(media):
    fields = {field: media[field] for field in ('filename', 'subfolder', 'type')}
    return comfy_open('/view?' + urlencode(fields), timeout=45)

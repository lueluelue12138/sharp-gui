from __future__ import annotations

import copy
from collections import deque
from contextlib import suppress
import hashlib
import io
import json
import math
import os
import re
import secrets
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps

from backend.services import portrait_progress
from backend.services.static_files import is_real_path_inside

try:
    from pillow_heif import register_heif_opener
except ImportError:
    register_heif_opener = None

WORKFLOW_FILE = Path(__file__).with_name('portrait_workflow.json')
EDIT_WORKFLOW_FILE = Path(__file__).with_name('image_edit_workflow.json')
EXTEND_WORKFLOW_FILE = Path(__file__).with_name('image_extend_workflow.json')
VISUAL_WORKFLOWS = {'photo-edit', 'photo-extend', 'spatial-reframing'}
EXTEND_RATIOS = {'自由比例', '原始比例', '1:1', '2:3', '3:2', '3:4', '4:3', '5:7', '9:16', '16:9', '21:9', '1:2', '2:1'}
DEFAULT_URL = 'http://127.0.0.1:8000'
COMFY_START_TIMEOUT = 150
_comfy_launch_lock = Lock()
_comfy_launch_deadline = None
_comfy_submit_lock = Lock()
_cancelled_requests = {}
_cancelled_request_ttl = 300
_request_id_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
MAX_UPLOAD = 24 * 1024 * 1024
MAX_CAPTURE_UPLOAD = 64 * 1024 * 1024
MAX_RESULT = 128 * 1024 * 1024
MAX_PIXEL_EDGE = 3840
NATIVE_CAMERA_EDGE = 2560
NATIVE_DETAIL_REFERENCE_EDGES = {768, 1024, 1344, 1536, 2048}
ASSET_ROOT = '/extensions/portrait_sharp_repair/'
RENDER_ASSETS = {'splat_renderer.js', 'splat_worker.js'}
UPLOADS = {
    'source': ('input', 'sharp_gui_portrait'),
    'reference': ('input', 'portrait_sharp_references'),
    'capture': ('temp', 'portrait_sharp_views'),
    'mask': ('temp', 'portrait_sharp_masks'),
}
PHOTO_EXTENSIONS = {
    'PNG': ('.png',), 'JPEG': ('.jpg', '.jpeg', '.jpe', '.jfif'), 'WEBP': ('.webp',), 'BMP': ('.bmp',),
    'HEIF': ('.heif', '.heic'), 'HEIC': ('.heic', '.heif'),
}
PHOTO_MIME_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.jpe': 'image/jpeg', '.jfif': 'image/jpeg',
    '.webp': 'image/webp', '.bmp': 'image/bmp', '.heif': 'image/heif', '.heic': 'image/heic',
}
REFINE_PROMPT = (
    '精修遮罩区域内的自然纹理与清晰度。图 2 只提供纹理和细节，'
    '保持图 1 里人物的身份、脸部轮廓与长宽比、五官位置、姿态、打光和色彩。'
)
REPAIR_DETAIL_INSTRUCTION = (
    'Write one or two short English sentences describing which gaps or smeared edges in <image1> need repair '
    'and what nearby surfaces or textures should continue into them. <image1> is the target camera view. '
    'Use <image2> only to identify matching details visible from the viewpoint in <image1>. '
    'Keep the head orientation and occlusion in <image1>. Omit details you cannot verify.'
)
REPAIR_VIEW_CONSTRAINTS = (
    'Preserve the camera viewpoint, framing, perspective, body and head orientation, and occlusion shown in image 1. '
    'Use image 2 to restore the same person’s visible hair, hands, clothing and accessories. '
    'Use its facial details only if the face is visible in image 1.'
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


@lru_cache(maxsize=1)
def edit_workflow_template():
    return json.loads(EDIT_WORKFLOW_FILE.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def extend_workflow_template():
    return json.loads(EXTEND_WORKFLOW_FILE.read_text(encoding='utf-8'))


def visual_workflow_file(name):
    if name not in VISUAL_WORKFLOWS:
        raise PortraitError('portraitInvalid', 'Unknown visual workflow.', 404)
    return Path(__file__).with_name('workflows') / f'{name}.json'


def visual_workflow_dependencies(name):
    nodes = json.loads(visual_workflow_file(name).read_text(encoding='utf-8'))['nodes']
    model_loaders = {'UNETLoader', 'CLIPLoader', 'VAELoader', 'LoraLoaderModelOnly'}
    extensions, models, optimizer_models = set(), set(), set()
    for node in nodes:
        node_type = node['type']
        properties = node.get('properties', {})
        pack = properties.get('aux_id') or properties.get('cnr_id')
        if node_type.startswith('PortraitSharp') or node_type == 'PortraitSplatFill':
            pack = 'portrait_sharp_repair'
        if ' (rgthree)' in node_type:
            pack = 'rgthree/rgthree-comfy'
        if pack and pack != 'comfy-core':
            extensions.add(pack)
        if node_type in model_loaders:
            models.add(node['widgets_values'][0])
        if node_type == 'QwenImagePromptOptimizer':
            optimizer_models.update(node['widgets_values'][1:4])
        if node_type == 'PortraitSharpPredict':
            models.add('sharp_2572gikvuh.pt')
    return {'extensions': sorted(extensions), 'models': sorted(models), 'optimizer_models': sorted(optimizer_models),
            'nodes': sorted({node['type'] for node in nodes})}


@lru_cache(maxsize=4)
def comfy_node_info(_url, _interval):
    return comfy_json('/object_info', timeout=12)


def missing_inputs(info, template, fields):
    missing = []
    for node_id, key in fields:
        node = template[node_id]
        schema = info.get(node['class_type'], {}).get('input', {}).get('required', {}).get(key, [])
        choices = schema[0] if schema and isinstance(schema[0], list) else None
        if choices is not None and node['inputs'][key] not in choices:
            missing.append(node['inputs'][key])
    return missing


@lru_cache(maxsize=4)
def capability(_url, _interval):
    info = comfy_node_info(_url, _interval)
    required = {node['class_type'] for node in workflow_template().values()} | {'PortraitSharpTrajectoryFrame'}
    missing = sorted(required.difference(info))
    missing.extend(missing_inputs(info, workflow_template(), [
        ('7', 'unet_name'), ('8', 'clip_name'), ('9', 'vae_name'), ('10', 'lora_name'), ('219', 'lora_name'),
    ]))
    if not missing:
        extensions = comfy_json('/extensions')
        missing.extend(sorted(asset for asset in RENDER_ASSETS if ASSET_ROOT + asset not in extensions))
    return missing


def edit_capability(url, interval):
    info = comfy_node_info(url, interval)
    template = edit_workflow_template()
    optimizer = template['179']['class_type']
    required = {node['class_type'] for node in template.values()} - {optimizer}
    missing = sorted(required.difference(info))
    missing.extend(missing_inputs(info, template, [
        ('363', 'unet_name'), ('362', 'clip_name'), ('361', 'vae_name'), ('258', 'lora_name'),
    ]))
    optimizer_missing = [optimizer] if optimizer not in info else missing_inputs(info, template, [
        ('179', '文生图模型'), ('179', '图生图模型'), ('179', '视觉模型'),
    ])
    return missing, optimizer_missing


def repair_optimizer_missing(info):
    template = workflow_template()
    required = {template['206']['class_type'], 'StringConcatenate'}
    return sorted(required.difference(info)) + missing_inputs(info, template, [
        ('206', '文生图模型'), ('206', '图生图模型'), ('206', '视觉模型'),
    ])


def status(*, edit=False, extend=False):
    global _comfy_launch_deadline
    result = {'repair_prompt': workflow_template()['12']['inputs']['prompt'],
              'can_start': hasattr(os, 'startfile')}
    try:
        url, interval = comfy_url(), int(time.monotonic() // 20)
        if edit:
            missing, result['optimizer_missing'] = edit_capability(url, interval)
        elif extend:
            info = comfy_node_info(url, interval)
            template = extend_workflow_template()
            missing = sorted({node['class_type'] for node in template.values()}.difference(info))
            missing.extend(missing_inputs(info, template, [
                ('14', 'unet_name'), ('8', 'clip_name'), ('9', 'vae_name'), ('17', 'lora_name'),
            ]))
        else:
            missing = capability(url, interval)
            result['repair_optimizer_missing'] = repair_optimizer_missing(comfy_node_info(url, interval))
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


def comfy_desktop_instance():
    """从 Desktop 的本机登记中选择当前端口对应的实例。旧版 Desktop 无需额外操作。"""
    root = os.environ.get('APPDATA')
    if not root:
        return None
    path = Path(root) / 'Comfy Desktop' / 'installations.json'
    if not path.is_file():
        return None
    try:
        records = json.loads(path.read_text(encoding='utf-8-sig'))
        local = [item for item in records if isinstance(item, dict) and item.get('status') == 'installed'
                 and item.get('sourceId') in {'standalone', 'portable', 'desktop', 'comfybuilder'}
                 and isinstance(item.get('name'), str) and item['name'].strip()]
    except (OSError, ValueError, TypeError) as error:
        raise PortraitError('portraitStartFailed', 'Could not read the registered Desktop instances.', 503) from error
    port = urlsplit(comfy_url()).port or 80
    matches = [item for item in local if re.search(rf'(?:^|\s)--port(?:\s+|=)["\']?{port}(?:["\']?\s|["\']?$)',
                                                 str(item.get('launchArgs', '')))]
    targets = matches or local
    if len(targets) != 1 or sum(isinstance(item, dict) and item.get('name') == targets[0]['name'] for item in records) != 1:
        raise PortraitError('portraitStartInstance', 'Could not identify a unique local Desktop instance.', 409)
    return targets[0]['name']


def launch_comfy_instance(name):
    """通过 Desktop 实例卡片的原生启动动作打开实例，兼容已打开的仪表盘。"""
    helper = Path(__file__).resolve().parents[2] / 'tools' / 'start_comfy_desktop.ps1'
    try:
        subprocess.run([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-ExecutionPolicy', 'Bypass',
            '-File', str(helper), '-InstanceName', name, '-ServerUrl', comfy_url(),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=70, check=False)
    except (OSError, subprocess.TimeoutExpired):
        # 状态轮询仍会检查真实服务，未就绪时沿用启动超时提示。
        pass


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

        instance = comfy_desktop_instance()
        try:
            os.startfile(str(find_comfy_desktop()))
        except OSError as error:
            raise PortraitError('portraitStartFailed', 'Windows could not open Comfy Desktop.', 503) from error
        capability.cache_clear()
        _comfy_launch_deadline = time.monotonic() + COMFY_START_TIMEOUT
        if instance:
            Thread(target=launch_comfy_instance, args=(instance,), daemon=True).start()
        return 'starting'


def number(value, minimum, maximum, *, integer=False):
    if type(value) not in (int, float) or not minimum <= value <= maximum or (integer and type(value) is not int):
        raise PortraitError('portraitInvalid', 'A portrait setting is out of range.')
    return value


def upload_image(kind, upload):
    if upload is None:
        raise PortraitError('portraitInvalidImage', 'Select a supported image.')
    return upload_image_stream(kind, upload.stream)


def upload_image_stream(kind, stream, *, from_result=False, edit_source=False, extend_source=False):
    prepared, _, _ = prepare_image_upload(kind, stream, from_result=from_result, edit_source=edit_source,
                                            extend_source=extend_source)
    storage, folder = UPLOADS[kind]
    return upload_png(prepared, storage, folder, f'{uuid4()}.png')


def prepare_image_upload(kind, stream, *, from_result=False, edit_source=False, extend_source=False):
    if kind not in UPLOADS:
        raise PortraitError('portraitInvalidImage', 'Select a supported image.')
    limit = MAX_RESULT if from_result else upload_limit(kind)
    original = stream.read(limit + 1)
    if len(original) > limit:
        raise PortraitError(upload_limit_code(kind), f'The image exceeds {limit // (1024 * 1024)} MB.', 413)
    generated = kind in {'mask', 'capture'}
    if not generated and register_heif_opener is not None:
        register_heif_opener()
    try:
        with Image.open(io.BytesIO(original)) as image:
            # Camera JPEGs can include an auxiliary image in an MPF segment.
            # Pillow opens them as MPO and starts on the primary JPEG frame.
            image_format = 'JPEG' if image.format == 'MPO' else image.format
            if image_format not in PHOTO_EXTENSIONS or image.width * image.height > (8192**2 if from_result else 40_000_000):
                raise ValueError
            if from_result and image_format != 'PNG':
                raise ValueError
            if generated and (image_format != 'PNG' or image.mode != 'RGBA' or max(image.size) > 4096):
                raise ValueError
            if not generated and not from_result:
                image = ImageOps.exif_transpose(image)
                if edit_source:
                    rgba = image.convert('RGBA')
                    background = Image.new('RGB', rgba.size, 'white')
                    background.paste(rgba, mask=rgba.getchannel('A'))
                    image = background
                elif extend_source and ('A' in image.getbands() or 'transparency' in image.info):
                    rgba = image.convert('RGBA')
                    image = rgba if rgba.getchannel('A').getextrema()[0] < 255 else image.convert('RGB')
                else:
                    image = image.convert('RGB')
                encoded = io.BytesIO()
                image.save(encoded, 'PNG', compress_level=2)
            else:
                image.verify()
                return original, original, image_format
        return encoded.getvalue(), original, image_format
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise PortraitError('portraitInvalidImage', 'Upload a supported photo with up to 40 megapixels.') from error


def uploaded_original_path(paths, filename):
    folder = Path(paths.input_folder) / '.workbench-originals'
    path = folder / filename
    if (not re.fullmatch(r'[a-f0-9-]{36}\.[a-z]+', filename) or path.suffix not in PHOTO_MIME_TYPES
            or not is_real_path_inside(path, folder) or not is_real_path_inside(path, paths.workspace_folder)):
        raise PortraitError('portraitExpired', 'The uploaded original is unavailable.', 404)
    return path


def upload_source_photo(paths, upload, *, edit_source=False, extend_source=False):
    """保存上传文件的原始字节，并把工作用的 PNG 交给 ComfyUI。"""
    if upload is None:
        raise PortraitError('portraitInvalidImage', 'Select a supported image.')
    prepared, original, image_format = prepare_image_upload('source', upload.stream, edit_source=edit_source,
                                                             extend_source=extend_source)
    name = (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    stem, extension = os.path.splitext(re.sub(r'[\x00-\x1f<>:"|?*]', '_', name))
    extensions = PHOTO_EXTENSIONS[image_format]
    if extension.lower() not in extensions:
        extension = extensions[0]
    download_name = f'{stem[:128].strip(" .") or "original"}{extension}'
    photo_id = uuid4()
    path = uploaded_original_path(paths, f'{photo_id}{extension.lower()}')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file = path.open('xb')
        try:
            with file:
                file.write(original)
        except OSError:
            with suppress(OSError):
                path.unlink(missing_ok=True)
            raise
    except OSError as error:
        raise PortraitError('portraitOriginalSaveFailed', 'Could not save the uploaded original.', 500) from error
    try:
        media = upload_png(prepared, *UPLOADS['source'], f'{photo_id}.png')
    except Exception:
        with suppress(OSError):
            path.unlink(missing_ok=True)
        raise
    return media, {'file': path.name, 'name': download_name}


def upload_png(data, storage, folder, filename):
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


def has_local_edit_area(alpha):
    """Match the crop node's 8-connected threshold on source-size mask pixels."""
    selected = np.asarray(alpha) > 25
    minimum = math.ceil(selected.size * 0.002)
    if np.count_nonzero(selected) < minimum:
        return False
    # Consume contiguous horizontal runs, checking diagonal neighbours as well.
    pixels = ((row, column) for row in range(selected.shape[0]) for column in np.flatnonzero(selected[row]))
    for row, column in pixels:
        if not selected[row, column]:
            continue
        frontier = deque([(row, column)])
        area = 0
        while frontier:
            y, x = frontier.popleft()
            if not selected[y, x]:
                continue
            left = x
            right = x + 1
            while left > 0 and selected[y, left - 1]:
                left -= 1
            while right < selected.shape[1] and selected[y, right]:
                right += 1
            selected[y, left:right] = False
            area += right - left
            if area >= minimum:
                return True
            start = max(0, left - 1)
            stop = min(selected.shape[1], right + 1)
            for neighbour in (y - 1, y + 1):
                if 0 <= neighbour < selected.shape[0]:
                    line = np.flatnonzero(selected[neighbour, start:stop])
                    if line.size:
                        starts = line[np.r_[True, np.diff(line) > 1]]
                        frontier.extend((neighbour, start + int(index)) for index in starts)
    return False


def prepare_edit_mask(source, upload, *, extend=False):
    if upload is None:
        raise PortraitError('portraitInvalidImage', 'Select a supported mask.')
    try:
        with Image.open(upload.stream) as mask, open_media(source) as original:
            if mask.format != 'PNG' or mask.mode != 'RGBA' or max(mask.size) > 4096:
                raise ValueError
            with Image.open(io.BytesIO(original.read(MAX_RESULT + 1))) as image:
                if image.width * image.height > (8192**2 if extend else 40_000_000):
                    raise ValueError
                alpha = mask.getchannel('A').resize(image.size, Image.Resampling.NEAREST)
                if not extend and not has_local_edit_area(alpha):
                    raise PortraitError('editMaskTooSmall', 'Expand the local mask to keep the edit confined to the selected region.')
                # This is the native Goohai clipspace format. RGB stays intact and
                # selected pixels are represented by inverted alpha.
                rgba = image.convert('RGBA')
                keep = ImageOps.invert(alpha)
                if extend:
                    keep = Image.fromarray((np.asarray(keep, dtype=np.uint16) * np.asarray(rgba.getchannel('A')) // 255).astype(np.uint8))
                rgba.putalpha(keep)
                encoded = io.BytesIO()
                rgba.save(encoded, 'PNG', compress_level=2)
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise PortraitError('portraitInvalidImage', 'The editing mask could not be read.') from error
    return upload_png(encoded.getvalue(), 'input', 'sharp_gui_edit',
                      f'clipspace-painted-output-sharp-{uuid4()}-edit.png')


def upload_limit(kind):
    return MAX_CAPTURE_UPLOAD if kind == 'capture' else MAX_UPLOAD


def upload_limit_code(kind):
    return 'portraitCaptureTooLarge' if kind == 'capture' else 'portraitImageTooLarge'


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
    edge = number(edge, 512, MAX_PIXEL_EDGE, integer=True)
    if edge % 32:
        raise PortraitError('portraitInvalid', 'Choose a supported output size.')
    return {**matrices, 'token': token, 'capture': capture, 'width': width, 'height': height}, edge


def frame_size(width, height, edge):
    return [max(64, math.floor(value * edge / max(width, height) / 32 + 0.5) * 32) for value in (width, height)]


def camera_edge_input(prompt, node_id, edge):
    # Older camera node schemas cap literal widgets at 2560, but accept a linked integer.
    if edge <= NATIVE_CAMERA_EDGE:
        return edge
    prompt[node_id] = {'class_type': 'PrimitiveInt', 'inputs': {'value': edge}}
    return [node_id, 0]


def set_detail_reference_size(prompt, detail):
    edge = detail['reference_edge']
    if edge not in NATIVE_DETAIL_REFERENCE_EDGES:
        detail = {key: value for key, value in detail.items() if key != 'reference_edge'}
        prompt['10004'] = {'class_type': '图像缩放范围孤海', 'inputs': {
            '图像': ['22', 2], '限制模式': '长边', '最小尺寸': 32, '最大尺寸': edge, '整除数': 32,
        }}
        prompt['206']['inputs']['图像_02'] = ['10004', 0]
        prompt['207']['inputs']['image_02'] = ['10004', 0]
    prompt['22']['inputs'] = {'selection': json.dumps(detail)}


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


def build_edit_prompt(source, options, *, reference=None, masked=None):
    text = options.get('prompt')
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise PortraitError('editDescriptionRequired', 'Enter an editing description of up to 4,000 characters.')
    if not reference and '<image2>' in text.lower():
        raise PortraitError('editReferenceRequired', 'Add the referenced image or remove its mention.')
    optimize = options.get('optimize', True)
    if type(optimize) is not bool:
        raise PortraitError('portraitInvalid', 'Invalid prompt optimization setting.')
    prompt = copy.deepcopy(edit_workflow_template())
    image = masked or source
    prompt['369']['inputs']['image'] = f'{image["subfolder"]}/{image["filename"]}' + (' [input]' if masked else '')
    prompt['359']['inputs']['value'] = text.strip()
    seed = options.get('seed')
    prompt['388']['inputs']['seed'] = (secrets.randbelow(2**50) if seed is None
                                       else number(seed, 0, 2**53 - 1, integer=True))
    maximum = number(options.get('sample_edge', 2048), 768, MAX_PIXEL_EDGE, integer=True)
    prompt['368']['inputs'].update({'值': maximum, 'ghs_dom': str(maximum)})
    prompt['385']['inputs']['switch'] = optimize
    if reference:
        prompt['526']['inputs']['image'] = f'{reference["subfolder"]}/{reference["filename"]}'
    else:
        prompt['255']['inputs'].pop('image_02')
        prompt['179']['inputs'].pop('图像_02')
        del prompt['526'], prompt['527']
    if not optimize:
        prompt['385']['inputs'].pop('on_true')
        del prompt['179']
    output_edge = options.get('output_edge')
    if output_edge is not None:
        save = prompt['370']['inputs']
        prompt['10000'] = {'class_type': '图像缩放V2_孤海', 'inputs': {
            '图像': save['images'],
            '缩放方法': '按长边等比例',
            '将边缩放到': number(output_edge, 256, MAX_PIXEL_EDGE, integer=True),
            '宽度': 0, '高度': 0, '缩放插值': 'Lanczos', '缩放模式': '拉伸',
            '固定方向': '居中', '执行条件': '总是', '填充颜色': '#364254', '整除数': 0,
        }}
        save['images'] = ['10000', 0]
    return prompt


def submit_edit(source, options, *, reference=None, masked=None):
    prompt = build_edit_prompt(source, options, reference=reference, masked=masked)
    return submit_prompt('edit', source, options, prompt, ['370', '386'])


def build_extend_prompt(source, options, *, masked=None):
    template = extend_workflow_template()
    prompt = copy.deepcopy(template)
    board = prompt['48']['inputs']
    text = options.get('prompt', '')
    if not isinstance(text, str) or len(text) > 4000:
        raise PortraitError('portraitInvalid', 'The supplemental prompt can contain up to 4,000 characters.')

    # These inputs are normalized PNGs. Read just IHDR to check the canvas
    # against the actual source, including workspaces saved before this feature.
    with open_media(source) as image:
        header = image.read(26)
    if not header.startswith(b'\x89PNG\r\n\x1a\n') or len(header) != 26:
        raise PortraitError('portraitInvalidImage', 'The source photo could not be read.')
    width, height = int.from_bytes(header[16:20], 'big'), int.from_bytes(header[20:24], 'big')
    has_alpha = header[25] in (4, 6)
    size = options.get('size')
    if size != [width, height]:
        raise PortraitError('extendSourceSize', 'The source dimensions have changed. Reload the photo.')
    pads = options.get('pads')
    if not isinstance(pads, list) or len(pads) != 4:
        raise PortraitError('portraitInvalid', 'Supply four canvas edges.')
    left, right, top, bottom = (number(value, -8192 * 8, 8192 * 8, integer=True) for value in pads)
    total_w, total_h = width + left + right, height + top + bottom
    if min(total_w, total_h) < 1 or total_w * total_h > 8192**2:
        raise PortraitError('extendCanvasTooLarge', 'Use a canvas of at most 67 megapixels.')
    unit = options.get('unit')
    ratio = options.get('ratio')
    multiple = options.get('multiple', board['整除数'])
    color = options.get('color', board['外补颜色'])
    translated = options.get('translated', False)
    if (unit not in ('pixels', 'percent') or not isinstance(ratio, str) or ratio not in EXTEND_RATIOS
            or type(multiple) is not int or multiple not in (0, 8, 16, 32, 64) or type(translated) is not bool
            or not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color)):
        raise PortraitError('portraitInvalid', 'Invalid canvas settings.')
    output_edge = number(options.get('output_edge', board['最大输出长边']), 0, 8192, integer=True)
    if multiple and max(pads) <= 0 and min(total_w, total_h) < multiple:
        # Native rounding can upscale a very narrow crop even with an output limit.
        if max(total_w, total_h) * multiple**2 / min(total_w, total_h) > 8192**2:
            raise PortraitError('extendCanvasTooLarge', 'Use a canvas of at most 67 megapixels.')
    if not translated:
        for first, second, dimension in ((left, right, width), (top, bottom, height)):
            if max(0, -first) + max(0, -second) > dimension - math.ceil(dimension * 0.1):
                raise PortraitError('portraitInvalid', 'Invalid canvas crop.')
        if ratio not in ('自由比例', '原始比例'):
            rw, rh = map(int, ratio.split(':'))
            if total_w * rh != total_h * rw:
                raise PortraitError('portraitInvalid', 'The canvas does not match the selected aspect ratio.')
        if ratio == '原始比例' and abs(total_w * height - total_h * width) > max(width, height):
            raise PortraitError('portraitInvalid', 'The canvas does not match the original aspect ratio.')
    unit_label = '像素' if unit == 'pixels' else '百分比'
    raw = [max(-3000, min(3000, math.floor((v if unit == 'pixels' else 100 * v / base) + 0.5)))
           for v, base in zip(pads, (width, width, height, height))]
    board.update(zip(('左', '右', '上', '下'), raw))
    board.update({'单位': unit_label, '整除数': multiple, '外补颜色': color,
                  '最大输出长边': output_edge,
                  'gh_visual_ratio': ratio, 'gh_visual_layout': json.dumps({
                      'signature': [width, height, unit_label, *raw], 'pads': pads, 'translated': translated,
                  }, separators=(',', ':'))})
    image = masked or source
    prompt['1']['inputs']['image'] = f'{image["subfolder"]}/{image["filename"]}' + (' [input]' if masked else '')
    prompt['2']['inputs']['Text'] = text.strip()
    seed = options.get('seed')
    prompt['18']['inputs']['noise_seed'] = (secrets.randbelow(2**50) if seed is None
                                           else number(seed, 0, 2**53 - 1, integer=True))
    maximum = number(options.get('sample_edge', 2048), 768, MAX_PIXEL_EDGE, integer=True)
    prompt['27']['inputs'].update({'值': maximum, 'ghs_dom': str(maximum)})
    if not masked and not has_alpha and max(pads) <= 0:
        # There is nothing for the sampler to fill. Export the board's crop or resize.
        prompt['46']['inputs']['images'] = ['48', 0]
        return prompt, ['46']
    return prompt, ['46', '51']


def submit_extend(source, options, *, masked=None):
    prompt, targets = build_extend_prompt(source, options, masked=masked)
    return submit_prompt('extend', source, options, prompt, targets)


def optimize_repair_prompt(prompt):
    condition = prompt['12']['inputs']
    base_prompt = condition['prompt']
    if base_prompt == workflow_template()['12']['inputs']['prompt']:
        # 把脸部参考收紧到目标机位可见的范围，同时保留原有的背景修补要求。
        base_prompt = base_prompt.replace(
            "Use image 2 as the detail reference for the same person's face, hair, hands, clothing and accessories. ", '',
        )
    optimizer = copy.deepcopy(prompt['206'])
    optimizer['inputs'].update({
        '用户提示词': REPAIR_DETAIL_INSTRUCTION,
        '输出语言': 'English',
        '卸载模型': '运行后自动卸载',
        '图像_01': condition['image_1'],
        '图像_02': condition['image_2'],
    })
    prompt['10004'] = optimizer
    prompt['10005'] = {'class_type': 'StringConcatenate', 'inputs': {
        'string_a': ['10004', 0], 'string_b': f'{base_prompt} {REPAIR_VIEW_CONSTRAINTS}', 'delimiter': '\n',
    }}
    condition['prompt'] = ['10005', 0]


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
        reference_edge = number(options.get('repair_reference_edge', camera_settings['reference_edge']), 512, MAX_PIXEL_EDGE, integer=True)
        if reference_edge % 32:
            raise PortraitError('portraitInvalid', 'Choose a supported source reference size.')
        camera_settings.update(camera=json.dumps(camera), long_edge=camera_edge_input(prompt, '10002', edge),
                               reference_edge=camera_edge_input(prompt, '10003', reference_edge))
        reference_crop = options.get('reference_crop')
        if reference_crop is not None and (stage != 'frame' or options.get('mode') == 'repair'):
            match_reference_crop(prompt, reference_crop, reference_edge)
        prompt['14']['inputs']['noise_seed'] = number(options.get('seed', 1), 0, 2**53 - 1, integer=True)
        targets = ['20', '22']
        if stage == 'repair' and options.get('repair_optimize') is True:
            optimize_repair_prompt(prompt)
            prompt['10006'] = {'class_type': 'easy showAnything', 'inputs': {'anything': prompt['12']['inputs']['prompt']}}
            targets.append('10006')
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
        set_detail_reference_size(prompt, detail)
        prompt['352']['inputs']['denoise'] = number(options.get('strength', 0.44), 0.1, 1)
        maximum = number(options.get('sample_edge', 2048), 768, MAX_PIXEL_EDGE, integer=True)
        prompt['222']['inputs'].update({'值': maximum, 'ghs_dom': str(maximum)})
        prompt['205']['inputs'].update({
            '遮罩扩展百分比': number(options.get('expand', 4), 0, 30, integer=True),
            '遮罩羽化百分比': number(options.get('feather', 5), 0, 30, integer=True),
            '颜色还原强度': number(options.get('color', 1), 0, 1),
        })
        prompt['224']['inputs']['seed'] = secrets.randbelow(2**50)
        targets = ['31']
    return submit_prompt(stage, source, options, prompt, targets)


def submit_prompt(stage, source, options, prompt, targets):
    submission = {'prompt': prompt, 'partial_execution_targets': targets}
    request_id = options.get('request_id')
    if request_id is not None:
        if not isinstance(request_id, str) or not re.fullmatch(_request_id_pattern, request_id):
            raise PortraitError('portraitInvalid', 'Invalid portrait request ID.')
        fingerprint = hashlib.sha256(json.dumps([stage, source, options], sort_keys=True).encode()).hexdigest()
        submission.update(prompt_id=request_id, extra_data={'sharp_gui_portrait_request': fingerprint})
        if stage in {'edit', 'extend'}:
            submission['extra_data']['sharp_gui_edit_source'] = source['filename']
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
            metadata = entry[3]
            matches_source = (image == f'sharp_gui_portrait/{source_filename}'
                              or metadata.get('sharp_gui_edit_source') == source_filename)
            if not matches_source or not metadata.get('sharp_gui_portrait_request'):
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
        result = {'state': 'done', 'outputs': history.get('outputs', {})}
        entry = history.get('prompt', [])
        if len(entry) > 2:
            condition = entry[2].get('12', {})
            if condition.get('class_type') == 'PortraitSharpQwenCondition':
                text = condition['inputs'].get('prompt')
                if isinstance(text, str):
                    result['repair_prompt'] = text
        return result
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

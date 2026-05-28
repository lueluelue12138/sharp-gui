import ssl
# Disable SSL verification for networks with SSL proxy (corporate/school networks)
ssl._create_default_https_context = ssl._create_unverified_context

import os
import subprocess
import json
import sys
import threading
import queue
import time
import uuid
import shutil
import base64
import gzip
import datetime
import platform
import traceback
import hashlib
import hmac
import ipaddress
import secrets
import socket
import tempfile
import zipfile
import numpy as np
from io import BytesIO
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, Response, g
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageOps
from plyfile import PlyData

# --- 配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# 前端模式: "react" 或 "legacy"
FRONTEND_MODE = os.environ.get('SHARP_FRONTEND_MODE', 'react')
REACT_BUILD_DIR = os.path.join(BASE_DIR, 'frontend', 'dist')
SHARP_VERBOSE = os.environ.get('SHARP_VERBOSE', '').strip().lower() in {'1', 'true', 'yes', 'on', 'debug', 'verbose'}
SHARP_LOG_LEVEL = os.environ.get('SHARP_LOG_LEVEL', 'DEBUG' if SHARP_VERBOSE else 'INFO').strip().upper()
SHARP_LOG_FILE = os.environ.get('SHARP_LOG_FILE', os.path.join(BASE_DIR, 'sharp-gui-verbose.log'))

# 默认文件夹
DEFAULT_WORKSPACE_FOLDER = BASE_DIR  # 工作目录默认为应用根目录
ALLOWED_IMAGE_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.webp',
    '.JPG', '.JPEG', '.PNG', '.WEBP',
)
MAX_THUMBNAIL_REPAIRS_PER_REQUEST = 6
THUMBNAIL_CACHE_SECONDS = 86400
DEFAULT_FILE_CACHE_SECONDS = 3600
WORKSPACE_FILES_PREFIX = 'workspace/'
PHOTO_THUMBNAIL_WIDTH = 480
PHOTO_DEFAULT_PAGE_SIZE = 60
PHOTO_MAX_PAGE_SIZE = 120
PHOTO_MAX_CONVERSION_BATCH = 100
PHOTO_MAX_DOWNLOAD_BATCH = 200
ACCESS_COOKIE_NAME = 'sharp_gui_access'
ACCESS_PUBLIC = 'public'
ACCESS_UNLOCKED = 'unlocked'
ACCESS_OWNER = 'owner'
LOGIN_FAILURE_WINDOW_SECONDS = 300
LOGIN_FAILURE_MAX_DELAY_SECONDS = 8
login_failure_lock = threading.Lock()
login_failures = {}


def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # 兼容旧配置格式
                if 'workspace_folder' not in config and 'input_folder' in config:
                    # 从旧格式迁移：取 input_folder 的父目录作为 workspace
                    old_input = config.get('input_folder', '')
                    if old_input.endswith('/inputs') or old_input.endswith('\\inputs'):
                        config['workspace_folder'] = os.path.dirname(old_input)
                    else:
                        config['workspace_folder'] = DEFAULT_WORKSPACE_FOLDER
                return config
        except:
            pass
    return {'workspace_folder': DEFAULT_WORKSPACE_FOLDER}


def save_config(config):
    """保存配置文件"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def is_local_request():
    """检测是否为本机访问"""
    remote_addr = request.remote_addr
    # 本机 IP 列表
    local_ips = ['127.0.0.1', 'localhost', '::1', '::ffff:127.0.0.1']
    return remote_addr in local_ips


def get_default_access_control_config():
    return {
        'enabled': False,
        'password_hash': '',
        'session_secret': '',
        'session_days': 30,
        'allow_localhost_bypass': True,
        'allow_remote_generation': False,
        'session_version': 1,
        'lan_bind_enabled': True,
    }


def coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off'}:
            return False
    return default


def coerce_int(value, default, minimum=None, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def normalize_access_control_config(current_config):
    defaults = get_default_access_control_config()
    raw = current_config.get('access_control')
    changed = False

    if not isinstance(raw, dict):
        raw = {}
        changed = True

    normalized = {
        'enabled': coerce_bool(raw.get('enabled'), defaults['enabled']),
        'password_hash': raw.get('password_hash') if isinstance(raw.get('password_hash'), str) else '',
        'session_secret': raw.get('session_secret') if isinstance(raw.get('session_secret'), str) else '',
        'session_days': coerce_int(raw.get('session_days'), defaults['session_days'], 1, 365),
        'allow_localhost_bypass': coerce_bool(raw.get('allow_localhost_bypass'), defaults['allow_localhost_bypass']),
        'allow_remote_generation': coerce_bool(raw.get('allow_remote_generation'), defaults['allow_remote_generation']),
        'session_version': coerce_int(raw.get('session_version'), defaults['session_version'], 1),
        'lan_bind_enabled': coerce_bool(raw.get('lan_bind_enabled'), defaults['lan_bind_enabled']),
    }

    if not normalized['session_secret']:
        normalized['session_secret'] = secrets.token_urlsafe(32)
        changed = True

    for key, value in normalized.items():
        if raw.get(key) != value:
            changed = True
            break

    current_config['access_control'] = normalized
    return normalized, changed


def get_access_control_config(persist_missing=True):
    current_config = load_config()
    access_config, changed = normalize_access_control_config(current_config)
    if changed and persist_missing:
        save_config(current_config)
    return access_config


def has_access_code(access_config):
    return bool(access_config.get('password_hash'))


def is_access_control_enabled(access_config):
    return coerce_bool(access_config.get('enabled'), False)


def get_request_hostname():
    host = request.host.split('@')[-1].strip().lower()
    if host.startswith('['):
        end = host.find(']')
        return host[1:end] if end != -1 else host.strip('[]')
    return host.split(':', 1)[0]


def is_loopback_host(hostname):
    hostname = (hostname or '').strip().strip('[]').lower()
    if hostname in {'localhost', '127.0.0.1', '::1'}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def is_private_host(hostname):
    hostname = (hostname or '').strip().strip('[]').lower()
    if hostname in {'localhost', socket.gethostname().lower()}:
        return True
    try:
        address = ipaddress.ip_address(hostname)
        return address.is_loopback or address.is_private or address.is_link_local
    except ValueError:
        return hostname.endswith('.local')


def is_allowed_request_host():
    hostname = get_request_hostname()
    if not hostname:
        return False
    return is_private_host(hostname)


def is_origin_allowed(origin_value):
    if not origin_value:
        return True
    parsed = urlparse(origin_value)
    origin_host = (parsed.hostname or '').lower()
    request_host = get_request_hostname()
    if not origin_host:
        return False
    if origin_host == request_host:
        return True
    if is_loopback_host(origin_host) and is_loopback_host(request_host):
        return True
    if is_local_request() and is_loopback_host(origin_host):
        return True
    return False


def is_request_origin_allowed():
    fetch_site = request.headers.get('Sec-Fetch-Site', '').strip().lower()
    if fetch_site == 'cross-site':
        return False

    origin = request.headers.get('Origin')
    if origin and not is_origin_allowed(origin):
        return False

    referer = request.headers.get('Referer')
    if referer and not is_origin_allowed(referer):
        return False

    return True


def is_owner_request(access_config=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    if not coerce_bool(access_config.get('allow_localhost_bypass'), True):
        return False
    return is_local_request() and is_allowed_request_host()


def encode_session_payload(payload):
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(',', ':')).encode('utf-8')
    ).decode('ascii').rstrip('=')
    return encoded


def decode_session_payload(encoded):
    padding = '=' * (-len(encoded) % 4)
    data = base64.urlsafe_b64decode((encoded + padding).encode('ascii'))
    return json.loads(data.decode('utf-8'))


def sign_session_payload(encoded, secret):
    return hmac.new(secret.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).hexdigest()


def create_access_session_token(access_config):
    now = int(time.time())
    session_days = coerce_int(access_config.get('session_days'), 30, 1, 365)
    payload = {
        'v': coerce_int(access_config.get('session_version'), 1, 1),
        'iat': now,
        'exp': now + session_days * 86400,
        'nonce': secrets.token_urlsafe(8),
    }
    encoded = encode_session_payload(payload)
    signature = sign_session_payload(encoded, access_config['session_secret'])
    return f'{encoded}.{signature}', payload['exp']


def verify_access_session_token(token, access_config):
    if not token or not isinstance(token, str) or '.' not in token:
        return False
    encoded, signature = token.rsplit('.', 1)
    expected_signature = sign_session_payload(encoded, access_config.get('session_secret', ''))
    if not hmac.compare_digest(signature, expected_signature):
        return False
    try:
        payload = decode_session_payload(encoded)
    except Exception:
        return False
    if coerce_int(payload.get('v'), 0) != coerce_int(access_config.get('session_version'), 1, 1):
        return False
    if coerce_int(payload.get('exp'), 0) < int(time.time()):
        return False
    return True


def is_authenticated_request(access_config=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    if not is_access_control_enabled(access_config):
        return True
    if is_owner_request(access_config):
        return True
    return verify_access_session_token(request.cookies.get(ACCESS_COOKIE_NAME), access_config)


def get_login_failure_key():
    return request.remote_addr or 'unknown'


def prune_login_failures(at_time=None):
    now = at_time or time.time()
    cutoff = now - LOGIN_FAILURE_WINDOW_SECONDS
    for key in list(login_failures.keys()):
        login_failures[key] = [timestamp for timestamp in login_failures[key] if timestamp >= cutoff]
        if not login_failures[key]:
            login_failures.pop(key, None)


def get_login_delay_seconds():
    key = get_login_failure_key()
    now = time.time()
    with login_failure_lock:
        prune_login_failures(now)
        failure_count = len(login_failures.get(key, []))
    if failure_count < 3:
        return 0
    return min(LOGIN_FAILURE_MAX_DELAY_SECONDS, 2 ** (failure_count - 3))


def record_login_failure():
    key = get_login_failure_key()
    now = time.time()
    with login_failure_lock:
        prune_login_failures(now)
        login_failures.setdefault(key, []).append(now)


def clear_login_failures():
    with login_failure_lock:
        login_failures.pop(get_login_failure_key(), None)


def get_required_access_level(access_config=None):
    path = request.path
    method = request.method.upper()

    if method == 'OPTIONS':
        return ACCESS_PUBLIC

    if path in {'/', '/api/auth/status', '/api/auth/login'}:
        return ACCESS_PUBLIC
    if path.startswith('/assets/'):
        return ACCESS_PUBLIC
    if path in {'/favicon.ico', '/favicon.svg', '/favicon-96x96.png',
                '/apple-touch-icon.png', '/site.webmanifest',
                '/web-app-manifest-192x192.png', '/web-app-manifest-512x512.png',
                '/logo.png'}:
        return ACCESS_PUBLIC

    if path in {'/api/auth/access-code', '/api/auth/revoke', '/api/auth/settings'}:
        return ACCESS_OWNER
    if path == '/api/auth/logout':
        return ACCESS_UNLOCKED

    if path == '/api/settings':
        return ACCESS_OWNER if method != 'GET' else ACCESS_UNLOCKED
    if path in {'/api/browse-folder', '/api/restart', '/api/convert-all'}:
        return ACCESS_OWNER
    if path.startswith('/api/delete/') or (path.startswith('/api/task/') and path.endswith('/cancel')):
        return ACCESS_OWNER
    if path == '/api/photo-albums' and method != 'GET':
        return ACCESS_OWNER
    if path.startswith('/api/photo-albums/') and (method == 'DELETE' or path.endswith('/scan')):
        return ACCESS_OWNER
    if path in {'/api/generate', '/api/photo-conversions'}:
        access_config = access_config or get_access_control_config(persist_missing=False)
        if not is_access_control_enabled(access_config):
            return ACCESS_OWNER
        return ACCESS_UNLOCKED if coerce_bool(access_config.get('allow_remote_generation'), False) else ACCESS_OWNER

    if path.startswith('/api/') or path.startswith('/files/'):
        return ACCESS_UNLOCKED

    return ACCESS_PUBLIC


def make_auth_error(message, status_code, code, **extra):
    payload = {'error': message, 'code': code}
    payload.update(extra)
    return jsonify(payload), status_code


def build_auth_status(access_config=None, authenticated_override=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    owner = is_owner_request(access_config)
    authenticated = owner or verify_access_session_token(request.cookies.get(ACCESS_COOKIE_NAME), access_config)
    if authenticated_override is not None:
        authenticated = authenticated_override
    access_control_enabled = is_access_control_enabled(access_config)
    access_code_configured = has_access_code(access_config)
    if not access_control_enabled:
        authenticated = True
    return {
        'authenticated': authenticated,
        'is_owner': owner,
        'is_local': owner,
        'access_control_enabled': access_control_enabled,
        'setup_required': access_control_enabled and not access_code_configured,
        'setup_recommended': (not access_control_enabled) or (not access_code_configured),
        'has_access_code': access_code_configured,
        'session_days': coerce_int(access_config.get('session_days'), 30, 1, 365),
        'allow_localhost_bypass': coerce_bool(access_config.get('allow_localhost_bypass'), True),
        'allow_remote_generation': access_control_enabled and coerce_bool(access_config.get('allow_remote_generation'), False),
        'lan_bind_enabled': coerce_bool(access_config.get('lan_bind_enabled'), True),
    }


# 加载配置
config = load_config()
_, access_config_changed = normalize_access_control_config(config)
if access_config_changed:
    save_config(config)
WORKSPACE_FOLDER = config.get('workspace_folder', DEFAULT_WORKSPACE_FOLDER)
INPUT_FOLDER = os.path.join(WORKSPACE_FOLDER, 'inputs')
OUTPUT_FOLDER = os.path.join(WORKSPACE_FOLDER, 'outputs')
THUMBNAIL_FOLDER = os.path.join(INPUT_FOLDER, '.thumbnails')
PHOTO_GALLERY_CACHE_FOLDER = os.path.join(WORKSPACE_FOLDER, '.photo-gallery-cache')
PHOTO_THUMBNAIL_FOLDER = os.path.join(PHOTO_GALLERY_CACHE_FOLDER, 'thumbnails')
PHOTO_INDEX_FILE = os.path.join(PHOTO_GALLERY_CACHE_FOLDER, 'index.json')

# 确保文件夹存在
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)
os.makedirs(PHOTO_THUMBNAIL_FOLDER, exist_ok=True)

app.config['WORKSPACE_FOLDER'] = WORKSPACE_FOLDER
app.config['INPUT_FOLDER'] = INPUT_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['THUMBNAIL_FOLDER'] = THUMBNAIL_FOLDER
app.config['PHOTO_GALLERY_CACHE_FOLDER'] = PHOTO_GALLERY_CACHE_FOLDER
app.config['PHOTO_THUMBNAIL_FOLDER'] = PHOTO_THUMBNAIL_FOLDER

photo_index_lock = threading.Lock()


def generate_thumbnail(input_path, filename):
    """生成缩略图 (200px 宽度, JPEG 80% 质量)"""
    try:
        thumb_path = os.path.join(THUMBNAIL_FOLDER, os.path.splitext(filename)[0] + '.jpg')
        with Image.open(input_path) as img:
            # 转换为 RGB (处理 PNG 透明度)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            # 计算缩放比例
            width = 200
            ratio = width / img.width
            height = int(img.height * ratio)
            # 生成缩略图
            img_resized = img.resize((width, height), Image.LANCZOS)
            img_resized.save(thumb_path, 'JPEG', quality=80)
        return thumb_path
    except Exception as e:
        print(f"⚠️ Thumbnail generation failed for {filename}: {e}")
        return None


def is_path_inside(path, root):
    """判断路径是否位于指定根目录内，兼容 Windows 跨盘符场景。"""
    try:
        abs_path = os.path.abspath(path)
        abs_root = os.path.abspath(root)
        common_path = os.path.commonpath([abs_path, abs_root])
        return os.path.normcase(common_path) == os.path.normcase(abs_root)
    except ValueError:
        return False


def to_url_path(path):
    """将本地路径片段转换为 URL 路径片段。"""
    return path.replace(os.sep, '/').replace('\\', '/')


def get_relative_files_path(path):
    """将绝对路径转换为 /files 可用的相对路径。"""
    abs_path = os.path.abspath(path)

    if is_path_inside(abs_path, BASE_DIR):
        return to_url_path(os.path.relpath(abs_path, BASE_DIR))

    if is_path_inside(abs_path, WORKSPACE_FOLDER):
        workspace_relative_path = to_url_path(os.path.relpath(abs_path, WORKSPACE_FOLDER))
        return f'{WORKSPACE_FILES_PREFIX}{workspace_relative_path}'

    raise ValueError(f'File path is outside served roots: {path}')


def get_thumbnail_path(item_id):
    """获取图库条目的缩略图路径"""
    return os.path.join(THUMBNAIL_FOLDER, item_id + '.jpg')


def find_original_image(item_id):
    """根据条目 ID 查找原图文件名和路径"""
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        filename = item_id + ext
        img_path = os.path.join(INPUT_FOLDER, filename)
        if os.path.exists(img_path):
            return filename, img_path
    return None, None


def ensure_thumbnail_for_item(item_id, allow_generation=False):
    """确保图库条目存在可用缩略图"""
    thumb_path = get_thumbnail_path(item_id)
    if os.path.exists(thumb_path):
        return thumb_path

    if not allow_generation:
        return None

    original_filename, original_path = find_original_image(item_id)
    if not original_filename or not original_path:
        return None

    return generate_thumbnail(original_path, original_filename)


def get_file_version(path):
    """获取文件版本号（基于修改时间）"""
    return int(os.path.getmtime(path) * 1000)


def get_file_timestamp(path):
    """获取 ISO 格式的文件修改时间"""
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(path),
        tz=datetime.timezone.utc,
    ).isoformat()


def build_gallery_item(ply_filename, repair_missing_thumbnail=False):
    """构建单个图库条目的响应数据"""
    name_without_ext = os.path.splitext(ply_filename)[0]
    ply_path = os.path.join(OUTPUT_FOLDER, ply_filename)

    if not os.path.exists(ply_path):
        return None

    ply_size = os.path.getsize(ply_path)
    file_timestamps = [os.path.getmtime(ply_path)]

    spz_filename = name_without_ext + '.spz'
    spz_path = os.path.join(OUTPUT_FOLDER, spz_filename)
    spz_url = None
    spz_size = None
    if os.path.exists(spz_path):
        spz_url = f'/files/{get_relative_files_path(spz_path)}'
        spz_size = os.path.getsize(spz_path)
        file_timestamps.append(os.path.getmtime(spz_path))

    original_filename, original_path = find_original_image(name_without_ext)
    image_url = None
    if original_filename and original_path:
        image_url = f'/api/original/{name_without_ext}'
        file_timestamps.append(os.path.getmtime(original_path))

    thumb_path = get_thumbnail_path(name_without_ext)
    if not os.path.exists(thumb_path) and repair_missing_thumbnail:
        thumb_path = ensure_thumbnail_for_item(name_without_ext, allow_generation=True)

    thumb_url = None
    thumb_version = None
    if thumb_path and os.path.exists(thumb_path):
        thumb_url = f'/api/thumbnail/{name_without_ext}'
        thumb_version = get_file_version(thumb_path)
        file_timestamps.append(os.path.getmtime(thumb_path))

    latest_timestamp = max(file_timestamps)

    return {
        'id': name_without_ext,
        'name': name_without_ext,
        'model_url': f'/files/{get_relative_files_path(ply_path)}',
        'spz_url': spz_url,
        'image_url': image_url,
        'thumb_url': thumb_url,
        'thumb_version': thumb_version,
        'size': ply_size,
        'spz_size': spz_size,
        'created_at': get_file_timestamp(ply_path),
        'updated_at': datetime.datetime.fromtimestamp(
            latest_timestamp,
            tz=datetime.timezone.utc,
        ).isoformat(),
    }


def make_photo_album_id(path):
    """根据目录真实路径生成稳定相册 ID。"""
    normalized = os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))
    return hashlib.sha1(normalized.encode('utf-8', 'surrogatepass')).hexdigest()[:16]


def normalize_photo_album_roots(config_data=None):
    """读取并规范化照片图库目录配置。"""
    source_config = config_data or load_config()
    raw_roots = source_config.get('photo_gallery_roots', [])
    if not isinstance(raw_roots, list):
        return []

    albums = []
    seen_ids = set()
    for raw in raw_roots:
        if isinstance(raw, str):
            raw = {'path': raw}
        if not isinstance(raw, dict):
            continue

        path = raw.get('path')
        if not isinstance(path, str) or not path.strip():
            continue

        absolute_path = os.path.abspath(os.path.expanduser(path.strip()))
        album_id = raw.get('id')
        if not isinstance(album_id, str) or not album_id.strip():
            album_id = make_photo_album_id(absolute_path)
        album_id = ''.join(ch for ch in album_id if ch.isalnum() or ch in ('-', '_'))[:64]
        if not album_id or album_id in seen_ids:
            album_id = make_photo_album_id(f'{absolute_path}-{len(seen_ids)}')
        seen_ids.add(album_id)

        default_name = os.path.basename(os.path.normpath(absolute_path)) or absolute_path
        name = raw.get('name')
        if not isinstance(name, str) or not name.strip():
            name = default_name

        albums.append({
            'id': album_id,
            'name': name.strip(),
            'path': absolute_path,
            'recursive': bool(raw.get('recursive', True)),
            'enabled': raw.get('enabled', True) is not False,
        })

    return albums


def find_photo_album(album_id):
    """根据相册 ID 查找配置。"""
    for album in normalize_photo_album_roots():
        if album['id'] == album_id:
            return album
    return None


def load_photo_index():
    """读取照片图库轻量索引。"""
    if not os.path.exists(PHOTO_INDEX_FILE):
        return {'photos': {}}

    try:
        with open(PHOTO_INDEX_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('photos'), dict):
            return data
    except Exception as e:
        print(f"⚠️ Failed to load photo index: {e}")

    return {'photos': {}}


def save_photo_index(index_data):
    """保存照片图库轻量索引。"""
    os.makedirs(PHOTO_GALLERY_CACHE_FOLDER, exist_ok=True)
    with open(PHOTO_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def is_real_path_inside(path, root):
    """判断真实路径是否在 root 内，避免符号链接逃逸。"""
    try:
        abs_path = os.path.realpath(os.path.abspath(path))
        abs_root = os.path.realpath(os.path.abspath(root))
        common_path = os.path.commonpath([abs_path, abs_root])
        return os.path.normcase(common_path) == os.path.normcase(abs_root)
    except ValueError:
        return False


def make_photo_id(album_id, relative_path):
    """根据相册与相对路径生成不暴露路径的照片 ID。"""
    normalized_relative = to_url_path(relative_path)
    payload = f'{album_id}\0{normalized_relative}'
    return hashlib.sha256(payload.encode('utf-8', 'surrogatepass')).hexdigest()[:32]


def is_supported_photo(filename):
    """判断文件是否是支持的照片格式。"""
    return filename.endswith(ALLOWED_IMAGE_EXTENSIONS)


def photo_meta_from_path(album, full_path, existing_meta=None):
    """根据文件路径构建照片索引元数据。"""
    root_path = os.path.realpath(album['path'])
    real_path = os.path.realpath(full_path)
    if not is_real_path_inside(real_path, root_path):
        return None

    try:
        stat = os.stat(real_path)
    except OSError:
        return None

    relative_path = to_url_path(os.path.relpath(real_path, root_path))
    photo_id = make_photo_id(album['id'], relative_path)

    width = None
    height = None
    if existing_meta:
        same_version = (
            existing_meta.get('mtime') == stat.st_mtime
            and existing_meta.get('size') == stat.st_size
        )
        if same_version:
            width = existing_meta.get('width')
            height = existing_meta.get('height')

    return {
        'id': photo_id,
        'album_id': album['id'],
        'relative_path': relative_path,
        'name': os.path.basename(real_path),
        'mtime': stat.st_mtime,
        'ctime': stat.st_ctime,
        'size': stat.st_size,
        'width': width,
        'height': height,
    }


def iter_album_photo_paths(album):
    """遍历相册中的图片路径。"""
    root_path = album['path']
    if not os.path.isdir(root_path):
        return

    if album.get('recursive', True):
        for current_root, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [
                dirname for dirname in dirnames
                if dirname not in {'.photo-gallery-cache', '.thumbnails', '__pycache__'}
            ]
            for filename in filenames:
                if is_supported_photo(filename):
                    yield os.path.join(current_root, filename)
    else:
        for filename in os.listdir(root_path):
            full_path = os.path.join(root_path, filename)
            if os.path.isfile(full_path) and is_supported_photo(filename):
                yield full_path


def scan_photo_album(album):
    """扫描相册并刷新轻量索引。"""
    if not album.get('enabled', True):
        return [], 'error', 'Album disabled'

    if not os.path.isdir(album['path']):
        return [], 'error', 'Album path is not available'

    with photo_index_lock:
        index_data = load_photo_index()
        photos = index_data.setdefault('photos', {})
        previous_by_key = {
            (meta.get('album_id'), meta.get('relative_path')): meta
            for meta in photos.values()
            if isinstance(meta, dict)
        }

        album_photo_ids = set()
        album_photos = []
        try:
            for full_path in iter_album_photo_paths(album):
                root_path = os.path.realpath(album['path'])
                relative_path = to_url_path(os.path.relpath(os.path.realpath(full_path), root_path))
                existing = previous_by_key.get((album['id'], relative_path))
                meta = photo_meta_from_path(album, full_path, existing_meta=existing)
                if not meta:
                    continue
                photos[meta['id']] = meta
                album_photo_ids.add(meta['id'])
                album_photos.append(meta)
        except Exception as e:
            save_photo_index(index_data)
            return [], 'error', str(e)

        stale_ids = [
            photo_id for photo_id, meta in photos.items()
            if meta.get('album_id') == album['id'] and photo_id not in album_photo_ids
        ]
        for photo_id in stale_ids:
            photos.pop(photo_id, None)

        save_photo_index(index_data)

    album_photos.sort(key=lambda item: item.get('mtime', 0), reverse=True)
    return album_photos, 'idle', None


def get_photo_dimensions(full_path):
    """读取照片尺寸。"""
    try:
        with Image.open(full_path) as img:
            return img.size
    except Exception:
        return None, None


def build_photo_item(meta):
    """构建照片条目响应。"""
    width = meta.get('width')
    height = meta.get('height')
    if not width or not height:
        resolved = resolve_photo_path(meta['id'], allow_stale=True)
        if resolved:
            _, full_path, current_meta = resolved
            width, height = get_photo_dimensions(full_path)
            if width and height:
                current_meta['width'] = width
                current_meta['height'] = height
                with photo_index_lock:
                    index_data = load_photo_index()
                    index_data.setdefault('photos', {})[meta['id']] = current_meta
                    save_photo_index(index_data)
                meta = current_meta

    updated_at = None
    if meta.get('mtime'):
        updated_at = datetime.datetime.fromtimestamp(
            meta['mtime'],
            tz=datetime.timezone.utc,
        ).isoformat()
    created_at = None
    if meta.get('ctime'):
        created_at = datetime.datetime.fromtimestamp(
            meta['ctime'],
            tz=datetime.timezone.utc,
        ).isoformat()

    return {
        'id': meta['id'],
        'album_id': meta['album_id'],
        'name': meta.get('name') or meta['id'],
        'width': width,
        'height': height,
        'thumb_url': f"/api/photo-thumbnail/{meta['id']}",
        'full_url': f"/api/photo-original/{meta['id']}",
        'preview_url': f"/api/photo-original/{meta['id']}",
        'download_url': f"/api/photo-original/{meta['id']}?download=1",
        'size': meta.get('size'),
        'created_at': created_at,
        'updated_at': updated_at,
    }


def resolve_photo_path(photo_id, allow_stale=False):
    """根据照片 ID 解析真实路径，并验证仍在配置目录内。"""
    with photo_index_lock:
        index_data = load_photo_index()
        meta = index_data.get('photos', {}).get(photo_id)

    if not isinstance(meta, dict):
        return None

    album = find_photo_album(meta.get('album_id'))
    if not album:
        return None

    root_path = os.path.realpath(album['path'])
    relative_path = str(meta.get('relative_path', '')).replace('/', os.sep)
    full_path = os.path.realpath(os.path.join(root_path, relative_path))
    if not is_real_path_inside(full_path, root_path) or not os.path.isfile(full_path):
        return None

    try:
        stat = os.stat(full_path)
    except OSError:
        return None

    current_meta = dict(meta)
    current_meta['mtime'] = stat.st_mtime
    current_meta['ctime'] = stat.st_ctime
    current_meta['size'] = stat.st_size
    current_meta['name'] = os.path.basename(full_path)

    if not allow_stale and (
        meta.get('mtime') != stat.st_mtime or meta.get('size') != stat.st_size
    ):
        current_meta['width'] = None
        current_meta['height'] = None
        with photo_index_lock:
            index_data = load_photo_index()
            index_data.setdefault('photos', {})[photo_id] = current_meta
            save_photo_index(index_data)

    return album, full_path, current_meta


def get_photo_thumbnail_filename(photo_id, meta):
    """生成与源文件版本绑定的缩略图文件名。"""
    version = f"{int(float(meta.get('mtime', 0)) * 1000)}-{int(meta.get('size', 0))}"
    return f"{photo_id}-{version}-{PHOTO_THUMBNAIL_WIDTH}.jpg"


def ensure_photo_thumbnail(photo_id):
    """确保照片缩略图存在。"""
    resolved = resolve_photo_path(photo_id)
    if not resolved:
        return None

    _, full_path, meta = resolved
    thumb_filename = get_photo_thumbnail_filename(photo_id, meta)
    thumb_path = os.path.join(PHOTO_THUMBNAIL_FOLDER, thumb_filename)
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        os.makedirs(PHOTO_THUMBNAIL_FOLDER, exist_ok=True)
        with Image.open(full_path) as img:
            img = ImageOps.exif_transpose(img)
            meta['width'], meta['height'] = img.size
            img.thumbnail((PHOTO_THUMBNAIL_WIDTH, PHOTO_THUMBNAIL_WIDTH * 3), Image.LANCZOS)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.getchannel('A'))
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(thumb_path, 'JPEG', quality=82, optimize=True)

        with photo_index_lock:
            index_data = load_photo_index()
            index_data.setdefault('photos', {})[photo_id] = meta
            save_photo_index(index_data)
        return thumb_path
    except Exception as e:
        print(f"⚠️ Photo thumbnail generation failed for {photo_id}: {e}")
        return None


def build_photo_album_response(album):
    """构建相册响应数据。"""
    photos, scan_status, error = scan_photo_album(album)
    cover = photos[0] if photos else None
    updated_at = None
    if photos:
        updated_at = datetime.datetime.fromtimestamp(
            max(photo.get('mtime', 0) for photo in photos),
            tz=datetime.timezone.utc,
        ).isoformat()

    return {
        'id': album['id'],
        'name': album['name'],
        'cover_thumb_url': f"/api/photo-thumbnail/{cover['id']}" if cover else None,
        'photo_count': len(photos) if scan_status != 'error' else None,
        'recursive': album.get('recursive', True),
        'enabled': album.get('enabled', True),
        'scan_status': scan_status,
        'updated_at': updated_at,
        'error': error,
    }


def make_unique_input_filename(filename):
    """为照片转 3D 生成唯一输入文件名。"""
    safe_name = secure_filename(filename)
    name, ext = os.path.splitext(safe_name)
    if not ext:
        _, ext = os.path.splitext(filename)
    if not name:
        name = 'photo'
    if not ext:
        ext = '.jpg'

    candidate = f"{name}{ext}"
    candidate_path = os.path.join(INPUT_FOLDER, candidate)
    if not os.path.exists(candidate_path):
        return candidate

    suffix = uuid.uuid4().hex[:8]
    return f"{name}-{suffix}{ext}"


def make_unique_archive_name(filename, used_names):
    """Create a safe unique filename for files inside the downloaded ZIP."""
    safe_name = str(filename or 'photo').replace('\\', '_').replace('/', '_').replace('\0', '').strip()
    if not safe_name:
        safe_name = 'photo'

    stem, ext = os.path.splitext(safe_name)
    if not stem:
        stem = 'photo'

    candidate = f'{stem}{ext}'
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f'{stem} ({counter}){ext}'
        counter += 1

    used_names.add(candidate.casefold())
    return candidate


def queue_generation_task_from_file(input_path, filename):
    """把已有图片文件加入现有 3D 生成队列。"""
    generate_thumbnail(input_path, filename)

    task_id = str(uuid.uuid4())
    task_info = {
        'id': task_id,
        'status': 'pending',
        'filename': filename,
        'input_path': input_path,
        'output_folder': app.config['OUTPUT_FOLDER'],
        'created_at': time.time(),
        'error': None
    }

    with task_lock:
        task_status[task_id] = task_info
    task_queue.put(task_id)
    return task_info


def ply_to_splat(ply_path):
    """将 PLY 文件转换为更紧凑的 .splat 格式
    
    PLY 格式: 每点 56 bytes (14 × float32)
    Splat 格式: 每点 32 bytes (position: 12, scales: 12, color: 4, rot: 4)
    压缩比: ~43% 节省
    """
    plydata = PlyData.read(ply_path)
    vert = plydata["vertex"]
    
    # 按重要性排序 (大且不透明的点优先)
    sorted_indices = np.argsort(
        -np.exp(vert["scale_0"] + vert["scale_1"] + vert["scale_2"])
        / (1 + np.exp(-vert["opacity"]))
    )
    
    buffer = BytesIO()
    SH_C0 = 0.28209479177387814  # 球谐函数 0 阶系数
    
    for idx in sorted_indices:
        v = vert[idx]
        
        # Position: 3 × float32 = 12 bytes
        position = np.array([v["x"], v["y"], v["z"]], dtype=np.float32)
        buffer.write(position.tobytes())
        
        # Scales: 3 × float32 = 12 bytes (已经是 exp 形式)
        scales = np.exp(np.array([v["scale_0"], v["scale_1"], v["scale_2"]], dtype=np.float32))
        buffer.write(scales.tobytes())
        
        # Color + Opacity: 4 × uint8 = 4 bytes
        color = np.array([
            0.5 + SH_C0 * v["f_dc_0"],
            0.5 + SH_C0 * v["f_dc_1"],
            0.5 + SH_C0 * v["f_dc_2"],
            1 / (1 + np.exp(-v["opacity"])),
        ])
        buffer.write((color * 255).clip(0, 255).astype(np.uint8).tobytes())
        
        # Rotation quaternion: 4 × uint8 = 4 bytes (normalized)
        rot = np.array([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], dtype=np.float32)
        rot_normalized = (rot / np.linalg.norm(rot)) * 128 + 128
        buffer.write(rot_normalized.clip(0, 255).astype(np.uint8).tobytes())
    
    return buffer.getvalue()


import struct
import math

# SPZ 常量 (与 @sparkjsdev/spark SpzReader / Niantic SPZ v3 完全对齐)
SPZ_MAGIC = 1347635022    # 0x5053474E — 字节顺序 4E 47 53 50
SPZ_VERSION = 3
SQRT1_2 = 1.0 / math.sqrt(2.0)
QUAT_VALUEMASK = (1 << 9) - 1  # 511


def ply_to_spz(ply_path, spz_path=None, fractional_bits=11):
    """将 PLY 高斯泼溅模型转换为 SPZ 格式 (Niantic v3)

    数据布局 (gzip 压缩后):
      Header 16B | Centers N×9B | Alpha N×1B | RGB N×3B | Scales N×3B | Quats N×4B
    """
    plydata = PlyData.read(ply_path)
    vert = plydata["vertex"].data
    n = len(vert)

    if spz_path is None:
        spz_path = os.path.splitext(ply_path)[0] + '.spz'

    sh_degree = 0
    scale_factor = 1 << fractional_bits
    SH_C0 = 0.28209479177387814

    # ==================== Header (16 bytes) ====================
    header = struct.pack('<IIIBBBB',
        SPZ_MAGIC,          # magic  (uint32 LE)
        SPZ_VERSION,        # version (uint32 LE)
        n,                  # numPoints (uint32 LE)
        sh_degree,          # shDegree (uint8)
        fractional_bits,    # fractionalBits (uint8)
        0,                  # flags (uint8)
        0,                  # reserved (uint8)
    )

    # ==================== Centers: N × 9 bytes ====================
    # 每个 splat: [x_lo, x_mi, x_hi, y_lo, y_mi, y_hi, z_lo, z_mi, z_hi]
    xyz = np.column_stack([
        vert['x'].astype(np.float64),
        vert['y'].astype(np.float64),
        vert['z'].astype(np.float64),
    ])
    quantized = np.round(xyz * scale_factor).astype(np.int32)
    quantized = np.clip(quantized, -(1 << 23) + 1, (1 << 23) - 1)
    unsigned = quantized.astype(np.uint32) & 0xFFFFFF
    b0 = (unsigned & 0xFF).astype(np.uint8)            # (n, 3)
    b1 = ((unsigned >> 8) & 0xFF).astype(np.uint8)
    b2 = ((unsigned >> 16) & 0xFF).astype(np.uint8)
    # 交错: [x0_b0, x0_b1, x0_b2, y0_b0, y0_b1, y0_b2, z0_b0, z0_b1, z0_b2, ...]
    centers = np.column_stack([
        b0[:, 0], b1[:, 0], b2[:, 0],
        b0[:, 1], b1[:, 1], b2[:, 1],
        b0[:, 2], b1[:, 2], b2[:, 2],
    ]).flatten().tobytes()

    # ==================== Alpha: N × 1 byte ====================
    logits = vert['opacity'].astype(np.float64)
    alphas = 1.0 / (1.0 + np.exp(-np.clip(logits, -20, 20)))
    alpha_bytes = np.round(alphas * 255).clip(0, 255).astype(np.uint8).tobytes()

    # ==================== RGB: N × 3 bytes ====================
    # SpzWriter.scaleRgb: byte = round(((color - 0.5) / (SH_C0 / 0.15) + 0.5) * 255)
    colors = np.column_stack([
        0.5 + SH_C0 * vert['f_dc_0'].astype(np.float64),
        0.5 + SH_C0 * vert['f_dc_1'].astype(np.float64),
        0.5 + SH_C0 * vert['f_dc_2'].astype(np.float64),
    ])
    rgb_scale = SH_C0 / 0.15
    rgb_encoded = np.round(((colors - 0.5) / rgb_scale + 0.5) * 255).clip(0, 255).astype(np.uint8)
    rgb_bytes = rgb_encoded.flatten().tobytes()  # 已交错 [r0,g0,b0,r1,g1,b1,...]

    # ==================== Scales: N × 3 bytes ====================
    # SpzWriter: byte = round((log(scale) + 10) * 16)
    # PLY 存储 log-scale，直接使用
    log_scales = np.column_stack([
        vert['scale_0'].astype(np.float64),
        vert['scale_1'].astype(np.float64),
        vert['scale_2'].astype(np.float64),
    ])
    scale_encoded = np.round((log_scales + 10.0) * 16.0).clip(0, 255).astype(np.uint8)
    scale_bytes = scale_encoded.flatten().tobytes()

    # ==================== Quaternions: N × 4 bytes (v3 packed) ====================
    # 顺序: [x, y, z, w] = [rot_1, rot_2, rot_3, rot_0]
    quats = np.column_stack([
        vert['rot_1'].astype(np.float64),
        vert['rot_2'].astype(np.float64),
        vert['rot_3'].astype(np.float64),
        vert['rot_0'].astype(np.float64),
    ])
    norms = np.linalg.norm(quats, axis=1, keepdims=True)
    norms[norms < 1e-10] = 1.0
    quats /= norms

    quat_packed = np.zeros(n, dtype=np.uint32)
    for i in range(n):
        q = quats[i]
        il = int(np.argmax(np.abs(q)))
        negate = 1 if q[il] < 0 else 0
        comp = il
        for j in range(4):
            if j != il:
                negbit = (1 if q[j] < 0 else 0) ^ negate
                mag = int(QUAT_VALUEMASK * (abs(q[j]) / SQRT1_2) + 0.5)
                mag = min(QUAT_VALUEMASK, mag)
                comp = (comp << 10) | (negbit << 9) | mag
        quat_packed[i] = comp & 0xFFFFFFFF
    quat_bytes = quat_packed.astype('<u4').tobytes()

    # ==================== 组装 & gzip ====================
    raw = header + centers + alpha_bytes + rgb_bytes + scale_bytes + quat_bytes
    compressed = gzip.compress(raw, compresslevel=6)

    with open(spz_path, 'wb') as f:
        f.write(compressed)

    return spz_path


# --- 后台任务队列系统 (线程安全版) ---
task_queue = queue.Queue()
task_status = {}
task_lock = threading.Lock()  # 线程锁保护 task_status
running_processes = {}  # 存储运行中的进程，用于取消任务

# 任务清理配置
TASK_RETENTION_SECONDS = 3600  # 已完成任务保留1小时
CLEANUP_INTERVAL = 300  # 每5分钟清理一次


def verify_torch_cuda_device(require_hip=False):
    """Verify the torch CUDA namespace can execute CUDA or ROCm kernels."""
    try:
        import torch
    except Exception as exc:
        return False, f"Unable to import torch: {exc}"

    torch_version = getattr(torch, "version", None)
    torch_hip = getattr(torch_version, "hip", None)
    backend = "ROCm" if torch_hip else "CUDA"

    if require_hip and not torch_hip:
        return False, "SHARP_DEVICE=rocm requested but this PyTorch build has no HIP runtime"

    if not torch.cuda.is_available():
        return False, f"{backend} is not available through torch.cuda"

    try:
        x = torch.ones((4, 4), device="cuda")
        _ = (x @ x).sum().cpu()
        torch.cuda.synchronize()
    except Exception as exc:
        msg = str(exc).splitlines()[0] if str(exc) else repr(exc)
        return False, f"{backend} is visible but unusable: {msg}"

    return True, f"{backend} via torch.cuda"


def select_sharp_device():
    """Return a device that can actually execute kernels."""
    configured = os.environ.get("SHARP_DEVICE", "").strip().lower()
    if configured in {"cpu", "mps"}:
        return configured

    if configured in {"cuda", "rocm"}:
        ok, detail = verify_torch_cuda_device(require_hip=(configured == "rocm"))
        if ok:
            if configured == "rocm":
                print("[INFO] SHARP_DEVICE=rocm maps to ml-sharp --device cuda (ROCm/HIP)")
            return "cuda"
        print(f"[WARN] {detail}, falling back to CPU")
        return "cpu"

    try:
        import torch
    except Exception as exc:
        print(f"[WARN] Unable to import torch, falling back to CPU: {exc}")
        return "cpu"

    ok, detail = verify_torch_cuda_device()
    if ok:
        print(f"[INFO] Using {detail}")
        return "cuda"
    if "not available" not in detail:
        print(f"[WARN] {detail}, falling back to CPU")

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"

    return "cpu"


def resolve_sharp_command():
    """Return an executable Sharp CLI path that subprocess can launch."""
    if os.name == "nt":
        bundled_cmd = os.path.join(BASE_DIR, "sharp.cmd")
        if os.path.exists(bundled_cmd):
            return bundled_cmd

        for candidate in ("sharp.cmd", "sharp.exe", "sharp"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

    resolved = shutil.which("sharp")
    return resolved or "sharp"


def verbose_log(message):
    if SHARP_VERBOSE:
        print(f"[DEBUG] {message}", flush=True)


class TeeStream:
    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary

    def write(self, data):
        self.primary.write(data)
        self.secondary.write(data)
        return len(data)

    def flush(self):
        self.primary.flush()
        self.secondary.flush()


def enable_verbose_log_file():
    if not SHARP_VERBOSE:
        return

    try:
        log_dir = os.path.dirname(SHARP_LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        log_file = open(SHARP_LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception as exc:
        print(f"[WARN] Unable to open verbose log file: {exc}", flush=True)
        return

    sys.stdout = TeeStream(sys.stdout, log_file)
    sys.stderr = TeeStream(sys.stderr, log_file)
    print(f"[DEBUG] verbose_log_file={SHARP_LOG_FILE}", flush=True)


def format_command_for_log(cmd):
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in cmd)


def print_runtime_diagnostics(protocol=None, local_ip=None):
    if not SHARP_VERBOSE:
        return

    print("[DEBUG] Sharp GUI verbose diagnostics", flush=True)
    print(f"[DEBUG]   log_level={SHARP_LOG_LEVEL}", flush=True)
    print(f"[DEBUG]   base_dir={BASE_DIR}", flush=True)
    print(f"[DEBUG]   cwd={os.getcwd()}", flush=True)
    print(f"[DEBUG]   python={sys.executable}", flush=True)
    print(f"[DEBUG]   verbose_log_file={SHARP_LOG_FILE}", flush=True)
    print(f"[DEBUG]   python_version={sys.version.split()[0]}", flush=True)
    print(f"[DEBUG]   platform={platform.platform()}", flush=True)
    print(f"[DEBUG]   frontend_mode={FRONTEND_MODE}", flush=True)
    if protocol and local_ip:
        print(f"[DEBUG]   url_local={protocol}://127.0.0.1:5050", flush=True)
        print(f"[DEBUG]   url_lan={protocol}://{local_ip}:5050", flush=True)
    print(f"[DEBUG]   sharp_cmd={resolve_sharp_command()}", flush=True)
    print(f"[DEBUG]   which_sharp={shutil.which('sharp')}", flush=True)
    print(f"[DEBUG]   which_sharp_cmd={shutil.which('sharp.cmd')}", flush=True)
    print(f"[DEBUG]   path={os.environ.get('PATH', '')}", flush=True)


def cleanup_old_tasks():
    """定期清理已完成的旧任务，防止内存泄漏"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cutoff = time.time() - TASK_RETENTION_SECONDS
        with task_lock:
            old_ids = [
                k for k, v in task_status.items()
                if v['created_at'] < cutoff and v['status'] in ('completed', 'failed')
            ]
            for task_id in old_ids:
                del task_status[task_id]
            if old_ids:
                print(f"🧹 Cleaned up {len(old_ids)} old tasks")


def worker():
    """后台工作线程，持续处理队列中的任务"""
    print("👷 Worker thread started...")
    while True:
        task_id = task_queue.get()
        if task_id is None:
            break
        
        with task_lock:
            task = task_status.get(task_id)
            if not task or task['status'] == 'cancelled':
                # 任务被取消或不存在，跳过
                task_queue.task_done()
                continue
            input_path = task['input_path']
            output_folder = task['output_folder']
            filename = task['filename']
        
        print(f"🔄 Processing task {task_id}: {filename}")
        with task_lock:
            task_status[task_id]['status'] = 'processing'
            task_status[task_id]['progress'] = 0
            task_status[task_id]['stage'] = 'starting'
        
        # 构建命令
        device = select_sharp_device()
        print(f"Using Sharp device: {device}")
        sharp_command = resolve_sharp_command()
        print(f"Using Sharp command: {sharp_command}")

        cmd = [
            sharp_command, "predict",
            "-i", input_path,
            "-o", output_folder,
            "--device", device
        ]
        
        process = None
        try:
            process_env = os.environ.copy()
            process_env.setdefault("PYTHONUTF8", "1")
            process_env.setdefault("PYTHONIOENCODING", "utf-8")
            verbose_log(f"Task {task_id} input_path={input_path} exists={os.path.exists(input_path)}")
            verbose_log(f"Task {task_id} output_folder={output_folder} exists={os.path.exists(output_folder)}")
            verbose_log(f"Task {task_id} command={format_command_for_log(cmd)}")
            verbose_log(f"Task {task_id} subprocess_cwd={os.getcwd()}")
            verbose_log(f"Task {task_id} subprocess_path={process_env.get('PATH', '')}")

            # 使用 Popen 异步执行，实时读取输出解析进度
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=process_env
            )
            
            # 存储进程引用，用于取消
            with task_lock:
                running_processes[task_id] = process
            
            # 实时读取输出并解析进度
            output_lines = []
            cancelled = False
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                
                # 检查是否被取消
                with task_lock:
                    if task_status.get(task_id, {}).get('status') == 'cancelled':
                        cancelled = True
                        break
                
                output_lines.append(line)
                line_lower = line.lower()
                
                # 解析进度阶段
                with task_lock:
                    if 'downloading' in line_lower or 'download' in line_lower:
                        task_status[task_id]['progress'] = 5
                        task_status[task_id]['stage'] = 'downloading'
                    elif 'loading checkpoint' in line_lower:
                        task_status[task_id]['progress'] = 10
                        task_status[task_id]['stage'] = 'loading'
                    elif 'processing' in line_lower and filename.split('.')[0].lower() in line_lower:
                        task_status[task_id]['progress'] = 15
                        task_status[task_id]['stage'] = 'processing'
                    elif 'preprocessing' in line_lower:
                        task_status[task_id]['progress'] = 25
                        task_status[task_id]['stage'] = 'preprocessing'
                    elif 'inference' in line_lower:
                        task_status[task_id]['progress'] = 50
                        task_status[task_id]['stage'] = 'inference'
                    elif 'postprocessing' in line_lower:
                        task_status[task_id]['progress'] = 80
                        task_status[task_id]['stage'] = 'postprocessing'
                    elif 'saving' in line_lower:
                        task_status[task_id]['progress'] = 95
                        task_status[task_id]['stage'] = 'saving'
            
            # 如果被取消，终止进程
            if cancelled:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except:
                    process.kill()
                print(f"🛑 Task {task_id} cancelled by user.")
                task_queue.task_done()
                continue
            
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                # 检查输出文件是否存在
                name_without_ext = os.path.splitext(filename)[0]
                expected_ply = os.path.join(output_folder, name_without_ext + ".ply")
                
                ply_exists = os.path.exists(expected_ply)
                with task_lock:
                    if ply_exists:
                        task_status[task_id]['status'] = 'completed'
                        task_status[task_id]['progress'] = 100
                        task_status[task_id]['stage'] = 'done'
                        print(f"✅ Task {task_id} completed successfully.")
                    else:
                        task_status[task_id]['status'] = 'failed'
                        task_status[task_id]['error'] = 'Output file not found after execution.'
                        print(f"❌ Task {task_id} failed: Output missing.")
                
                # 自动转换 PLY → SPZ (在锁外执行，不阻塞其他任务)
                if ply_exists:
                    try:
                        spz_result = ply_to_spz(expected_ply)
                        if spz_result:
                            ply_size = os.path.getsize(expected_ply)
                            spz_size = os.path.getsize(spz_result)
                            ratio = 100 - spz_size * 100 // ply_size if ply_size > 0 else 0
                            print(f"📦 SPZ converted: {ply_size/1024:.0f}KB → {spz_size/1024:.0f}KB ({ratio}% smaller)")
                    except Exception as e:
                        print(f"⚠️ SPZ auto-convert failed for {name_without_ext}: {e}")
            else:
                stderr_output = ''.join(output_lines)
                with task_lock:
                    # 检查是否是因为取消而失败
                    if task_status.get(task_id, {}).get('status') != 'cancelled':
                        task_status[task_id]['status'] = 'failed'
                        task_status[task_id]['error'] = stderr_output if stderr_output else "Unknown error"
                print(f"❌ Task {task_id} failed with return code {return_code}")
                if stderr_output:
                    print(f"   Error output:\n{stderr_output}")

        except Exception as e:
            error_text = traceback.format_exc() if SHARP_VERBOSE else str(e)
            with task_lock:
                if task_status.get(task_id, {}).get('status') != 'cancelled':
                    task_status[task_id]['status'] = 'failed'
                    task_status[task_id]['error'] = error_text
            print(f"❌ Task {task_id} exception: {e}")
            if SHARP_VERBOSE:
                print("[DEBUG] Full task exception traceback:", flush=True)
                print(error_text, flush=True)
        finally:
            # 清理进程引用
            with task_lock:
                running_processes.pop(task_id, None)
        
        task_queue.task_done()


enable_verbose_log_file()

# 启动后台线程
threading.Thread(target=worker, daemon=True).start()
# 启动清理线程
threading.Thread(target=cleanup_old_tasks, daemon=True).start()


# --- 路由 ---

@app.before_request
def enforce_lan_access_control():
    access_config = get_access_control_config()
    g.access_control = access_config
    g.is_owner = is_owner_request(access_config)
    g.is_authenticated = is_authenticated_request(access_config)
    required_access = get_required_access_level(access_config)
    g.required_access = required_access

    if not is_allowed_request_host():
        return make_auth_error('Request Host is not allowed', 400, 'INVALID_HOST')

    if required_access != ACCESS_PUBLIC and not is_request_origin_allowed():
        return make_auth_error('Cross-origin private request is not allowed', 403, 'ORIGIN_FORBIDDEN')

    if request.path == '/api/auth/login' and request.method.upper() != 'OPTIONS' and not is_request_origin_allowed():
        return make_auth_error('Cross-origin login request is not allowed', 403, 'ORIGIN_FORBIDDEN')

    if required_access == ACCESS_PUBLIC:
        return None

    if required_access == ACCESS_OWNER:
        if not g.is_owner:
            return make_auth_error('Only localhost can perform this action', 403, 'OWNER_REQUIRED')
        return None

    if not is_access_control_enabled(access_config):
        return None

    if not g.is_authenticated:
        if not has_access_code(access_config):
            return make_auth_error(
                'Access code is not configured. Open Settings from localhost first.',
                401,
                'ACCESS_SETUP_REQUIRED',
                setup_required=True,
            )
        return make_auth_error('Authentication required', 401, 'AUTH_REQUIRED')

    return None


@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    if origin and is_origin_allowed(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers.add('Vary', 'Origin')
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response


@app.route('/api/auth/status')
def auth_status():
    return jsonify(build_auth_status(g.access_control))


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    access_config = g.access_control

    if not is_access_control_enabled(access_config):
        return jsonify(build_auth_status(access_config, authenticated_override=True))

    if g.is_owner:
        return jsonify(build_auth_status(access_config, authenticated_override=True))

    if not has_access_code(access_config):
        return make_auth_error(
            'Access code is not configured. Open Settings from localhost first.',
            403,
            'ACCESS_SETUP_REQUIRED',
            setup_required=True,
        )

    delay_seconds = get_login_delay_seconds()
    if delay_seconds:
        time.sleep(delay_seconds)

    data = request.get_json(silent=True) or {}
    password = data.get('password') or data.get('access_code') or data.get('accessCode')
    if not isinstance(password, str) or not check_password_hash(access_config['password_hash'], password):
        record_login_failure()
        return make_auth_error('Invalid access code', 401, 'INVALID_ACCESS_CODE')

    clear_login_failures()
    token, expires_at = create_access_session_token(access_config)
    response = jsonify(build_auth_status(access_config, authenticated_override=True))
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        max_age=coerce_int(access_config.get('session_days'), 30, 1, 365) * 86400,
        expires=datetime.datetime.utcfromtimestamp(expires_at),
        httponly=True,
        secure=request.is_secure,
        samesite='Strict',
        path='/',
    )
    return response


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    response = jsonify(build_auth_status(g.access_control, authenticated_override=g.is_owner))
    response.delete_cookie(ACCESS_COOKIE_NAME, path='/')
    return response


@app.route('/api/auth/access-code', methods=['POST'])
def auth_set_access_code():
    data = request.get_json(silent=True) or {}
    password = data.get('password') or data.get('access_code') or data.get('accessCode')
    if not isinstance(password, str) or len(password) < 8:
        return make_auth_error('Access code must be at least 8 characters', 400, 'ACCESS_CODE_TOO_SHORT')

    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)
    access_config['enabled'] = True
    access_config['password_hash'] = generate_password_hash(password)
    if 'session_days' in data:
        access_config['session_days'] = coerce_int(data.get('session_days'), access_config['session_days'], 1, 365)
    if 'allow_remote_generation' in data and access_config['enabled']:
        access_config['allow_remote_generation'] = coerce_bool(
            data.get('allow_remote_generation'),
            access_config['allow_remote_generation'],
        )
    if not access_config['enabled']:
        access_config['allow_remote_generation'] = False
    access_config['session_version'] = coerce_int(access_config.get('session_version'), 1, 1) + 1
    current_config['access_control'] = access_config
    save_config(current_config)

    return jsonify(build_auth_status(access_config, authenticated_override=True))


@app.route('/api/auth/revoke', methods=['POST'])
def auth_revoke_sessions():
    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)
    access_config['session_version'] = coerce_int(access_config.get('session_version'), 1, 1) + 1
    current_config['access_control'] = access_config
    save_config(current_config)
    return jsonify(build_auth_status(access_config, authenticated_override=True))


@app.route('/api/auth/settings', methods=['POST'])
def auth_update_settings():
    data = request.get_json(silent=True) or {}
    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)

    if 'enabled' in data:
        access_config['enabled'] = coerce_bool(data.get('enabled'), access_config['enabled'])
        if not access_config['enabled']:
            access_config['allow_remote_generation'] = False
    if 'session_days' in data:
        access_config['session_days'] = coerce_int(data.get('session_days'), access_config['session_days'], 1, 365)
    if 'allow_remote_generation' in data and access_config['enabled']:
        access_config['allow_remote_generation'] = coerce_bool(
            data.get('allow_remote_generation'),
            access_config['allow_remote_generation'],
        )
    if not access_config['enabled']:
        access_config['allow_remote_generation'] = False
    if 'allow_localhost_bypass' in data:
        next_bypass = coerce_bool(data.get('allow_localhost_bypass'), access_config['allow_localhost_bypass'])
        if not next_bypass and not has_access_code(access_config):
            return make_auth_error('Set an access code before disabling localhost bypass', 400, 'ACCESS_CODE_REQUIRED')
        access_config['allow_localhost_bypass'] = next_bypass
    if 'lan_bind_enabled' in data:
        access_config['lan_bind_enabled'] = coerce_bool(data.get('lan_bind_enabled'), access_config['lan_bind_enabled'])

    current_config['access_control'] = access_config
    save_config(current_config)
    return jsonify(build_auth_status(access_config, authenticated_override=True))


@app.route('/')
def index():
    """根据模式返回前端页面"""
    # Legacy 模式强制使用原始模板
    if FRONTEND_MODE == 'legacy':
        return render_template('index.html')
    
    # React 模式: 检查构建是否存在
    react_index = os.path.join(REACT_BUILD_DIR, 'index.html')
    if os.path.exists(react_index):
        return send_from_directory(REACT_BUILD_DIR, 'index.html')
    
    # 回退到原始模板
    return render_template('index.html')


@app.route('/assets/<path:filename>')
def react_assets(filename):
    """服务 React 静态资源"""
    return send_from_directory(
        os.path.join(REACT_BUILD_DIR, 'assets'), 
        filename,
        max_age=31536000  # 1 year cache
    )


# React 前端根目录静态文件 (favicon, manifest 等)
REACT_ROOT_STATIC_FILES = {
    'favicon.ico', 'favicon.svg', 'favicon-96x96.png',
    'apple-touch-icon.png', 'site.webmanifest',
    'web-app-manifest-192x192.png', 'web-app-manifest-512x512.png',
    'logo.png'
}

@app.route('/<path:filename>')
def react_root_static(filename):
    """服务 React 根目录静态文件 (favicon, manifest 等)"""
    if filename in REACT_ROOT_STATIC_FILES:
        return send_from_directory(REACT_BUILD_DIR, filename)
    # 非静态文件返回 404，让其他路由处理
    from flask import abort
    abort(404)


@app.route('/api/gallery')
def get_gallery():
    """获取图库列表"""
    items = []
    if os.path.exists(OUTPUT_FOLDER):
        files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.ply')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_FOLDER, x)), reverse=True)
        remaining_thumbnail_repairs = MAX_THUMBNAIL_REPAIRS_PER_REQUEST

        for ply_filename in files:
            item_id = os.path.splitext(ply_filename)[0]
            thumb_missing = not os.path.exists(get_thumbnail_path(item_id))
            repair_thumbnail = thumb_missing and remaining_thumbnail_repairs > 0
            gallery_item = build_gallery_item(
                ply_filename,
                repair_missing_thumbnail=repair_thumbnail,
            )
            if gallery_item:
                items.append(gallery_item)
            if repair_thumbnail:
                remaining_thumbnail_repairs -= 1
    return jsonify(items)


@app.route('/api/photo-albums', methods=['GET', 'POST'])
def photo_albums():
    """照片相册列表与新增配置。"""
    if request.method == 'GET':
        albums = [build_photo_album_response(album) for album in normalize_photo_album_roots()]
        return jsonify({'albums': albums, 'is_local': g.is_owner})

    if not g.is_owner:
        return jsonify({'error': 'Photo albums can only be modified from localhost'}), 403

    data = request.get_json() or {}
    path = data.get('path')
    if not isinstance(path, str) or not path.strip():
        return jsonify({'error': 'Photo album path is required'}), 400

    absolute_path = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.isdir(absolute_path):
        return jsonify({'error': 'Photo album path is not available'}), 400

    current_config = load_config()
    albums = normalize_photo_album_roots(current_config)
    album_id = make_photo_album_id(absolute_path)
    existing = next((album for album in albums if album['id'] == album_id), None)
    if existing:
        return jsonify({'success': True, 'album': build_photo_album_response(existing), 'duplicate': True})

    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        name = os.path.basename(os.path.normpath(absolute_path)) or absolute_path

    recursive = data.get('recursive', True) is not False
    new_album = {
        'id': album_id,
        'name': name.strip(),
        'path': absolute_path,
        'recursive': recursive,
        'enabled': True,
    }

    current_config['photo_gallery_roots'] = [
        {
            'id': album['id'],
            'name': album['name'],
            'path': album['path'],
            'recursive': album['recursive'],
            'enabled': album['enabled'],
        }
        for album in albums
    ] + [new_album]
    save_config(current_config)

    return jsonify({'success': True, 'album': build_photo_album_response(new_album)})


@app.route('/api/photo-albums/<album_id>', methods=['DELETE'])
def delete_photo_album(album_id):
    """移除照片相册配置，不删除原始照片。"""
    if not g.is_owner:
        return jsonify({'error': 'Photo albums can only be modified from localhost'}), 403

    current_config = load_config()
    albums = normalize_photo_album_roots(current_config)
    next_albums = [album for album in albums if album['id'] != album_id]
    if len(next_albums) == len(albums):
        return jsonify({'error': 'Album not found'}), 404

    current_config['photo_gallery_roots'] = next_albums
    save_config(current_config)

    with photo_index_lock:
        index_data = load_photo_index()
        photos = index_data.setdefault('photos', {})
        stale_ids = [
            photo_id for photo_id, meta in photos.items()
            if isinstance(meta, dict) and meta.get('album_id') == album_id
        ]
        for photo_id in stale_ids:
            photos.pop(photo_id, None)
        save_photo_index(index_data)

    return jsonify({'success': True})


@app.route('/api/photo-albums/<album_id>/scan', methods=['POST'])
def scan_photo_album_endpoint(album_id):
    """重新扫描照片相册。"""
    if not g.is_owner:
        return jsonify({'error': 'Photo albums can only be rescanned from localhost'}), 403

    album = find_photo_album(album_id)
    if not album:
        return jsonify({'error': 'Album not found'}), 404

    return jsonify({'success': True, 'album': build_photo_album_response(album)})


@app.route('/api/photo-albums/<album_id>/photos')
def get_photo_album_photos(album_id):
    """分页获取相册照片。"""
    album = find_photo_album(album_id)
    if not album:
        return jsonify({'error': 'Album not found'}), 404

    photos, scan_status, error = scan_photo_album(album)
    if scan_status == 'error':
        return jsonify({
            'items': [],
            'next_cursor': None,
            'total': 0,
            'scan_status': scan_status,
            'error': error,
        })

    sort = request.args.get('sort', 'mtime_desc')
    if sort == 'mtime_asc':
        photos.sort(key=lambda item: item.get('mtime', 0))
    elif sort == 'ctime_desc':
        photos.sort(key=lambda item: item.get('ctime', item.get('mtime', 0)), reverse=True)
    elif sort == 'ctime_asc':
        photos.sort(key=lambda item: item.get('ctime', item.get('mtime', 0)))
    elif sort == 'name_asc':
        photos.sort(key=lambda item: item.get('name', '').lower())
    elif sort == 'name_desc':
        photos.sort(key=lambda item: item.get('name', '').lower(), reverse=True)
    elif sort == 'size_desc':
        photos.sort(key=lambda item: item.get('size', 0), reverse=True)
    elif sort == 'size_asc':
        photos.sort(key=lambda item: item.get('size', 0))
    else:
        photos.sort(key=lambda item: item.get('mtime', 0), reverse=True)

    try:
        cursor = max(0, int(request.args.get('cursor', '0')))
    except ValueError:
        cursor = 0

    try:
        limit = int(request.args.get('limit', str(PHOTO_DEFAULT_PAGE_SIZE)))
    except ValueError:
        limit = PHOTO_DEFAULT_PAGE_SIZE
    limit = max(1, min(limit, PHOTO_MAX_PAGE_SIZE))

    page = photos[cursor:cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(photos) else None

    return jsonify({
        'items': [build_photo_item(meta) for meta in page],
        'next_cursor': str(next_cursor) if next_cursor is not None else None,
        'total': len(photos),
        'scan_status': scan_status,
        'error': error,
    })


@app.route('/api/photo-thumbnail/<photo_id>')
def get_photo_thumbnail(photo_id):
    """获取照片缩略图。"""
    thumb_path = ensure_photo_thumbnail(photo_id)
    if not thumb_path or not os.path.exists(thumb_path):
        return jsonify({'error': 'Thumbnail not found'}), 404

    filename = os.path.basename(thumb_path)
    response = send_from_directory(
        PHOTO_THUMBNAIL_FOLDER,
        filename,
        conditional=True,
        max_age=THUMBNAIL_CACHE_SECONDS,
    )
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    response.cache_control.public = True
    response.cache_control.max_age = THUMBNAIL_CACHE_SECONDS
    return response


@app.route('/api/photo-original/<photo_id>')
def get_photo_original(photo_id):
    """获取照片原图，支持 inline 预览和附件下载。"""
    resolved = resolve_photo_path(photo_id)
    if not resolved:
        return jsonify({'error': 'Photo not found'}), 404

    _, full_path, meta = resolved
    download = request.args.get('download', '0').lower() in ('1', 'true', 'yes')
    filename = os.path.basename(full_path)
    response = send_from_directory(
        os.path.dirname(full_path),
        filename,
        as_attachment=download,
        download_name=meta.get('name') or filename,
        conditional=True,
        max_age=DEFAULT_FILE_CACHE_SECONDS,
    )

    return response


@app.route('/api/photo-downloads', methods=['POST'])
def download_photos():
    """Download selected original photos as a ZIP archive."""
    data = request.get_json() or {}
    photo_ids = data.get('photo_ids')
    if not isinstance(photo_ids, list) or not photo_ids:
        return jsonify({'error': 'photo_ids is required'}), 400

    photo_ids = [str(photo_id) for photo_id in photo_ids[:PHOTO_MAX_DOWNLOAD_BATCH]]
    os.makedirs(PHOTO_GALLERY_CACHE_FOLDER, exist_ok=True)
    fd, zip_path = tempfile.mkstemp(
        prefix='photo-gallery-',
        suffix='.zip',
        dir=PHOTO_GALLERY_CACHE_FOLDER,
    )
    os.close(fd)

    added_count = 0
    failed = []
    used_names = set()

    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for photo_id in photo_ids:
                resolved = resolve_photo_path(photo_id)
                if not resolved:
                    failed.append({'id': photo_id, 'error': 'Photo not found'})
                    continue

                _, full_path, meta = resolved
                archive_name = make_unique_archive_name(meta.get('name') or os.path.basename(full_path), used_names)
                archive.write(full_path, archive_name)
                added_count += 1

        if added_count == 0:
            try:
                os.remove(zip_path)
            except OSError:
                pass
            return jsonify({'error': 'No downloadable photos found', 'failed': failed}), 404

        download_name = f"sharp-gui-photos-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        response = send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/zip',
            max_age=0,
            conditional=False,
        )
        response.headers['X-Photo-Download-Count'] = str(added_count)
        response.headers['X-Photo-Download-Failed'] = str(len(failed))

        @response.call_on_close
        def cleanup_zip():
            try:
                os.remove(zip_path)
            except OSError:
                pass

        return response
    except Exception as e:
        try:
            os.remove(zip_path)
        except OSError:
            pass
        return jsonify({'error': str(e)}), 500


@app.route('/api/photo-conversions', methods=['POST'])
def convert_photos_to_models():
    """将照片图库中的照片加入现有 3D 生成队列。"""
    data = request.get_json() or {}
    photo_ids = data.get('photo_ids')
    if not isinstance(photo_ids, list) or not photo_ids:
        return jsonify({'error': 'photo_ids is required'}), 400

    photo_ids = [str(photo_id) for photo_id in photo_ids[:PHOTO_MAX_CONVERSION_BATCH]]
    created_tasks = []
    failed = []

    for photo_id in photo_ids:
        resolved = resolve_photo_path(photo_id)
        if not resolved:
            failed.append({'id': photo_id, 'error': 'Photo not found'})
            continue

        _, full_path, meta = resolved
        filename = make_unique_input_filename(meta.get('name') or os.path.basename(full_path))
        input_path = os.path.join(app.config['INPUT_FOLDER'], filename)

        try:
            shutil.copy2(full_path, input_path)
            task_info = queue_generation_task_from_file(input_path, filename)
            created_tasks.append(task_info)
            print(f"📥 Photo conversion task added: {filename} (ID: {task_info['id']})")
        except Exception as e:
            failed.append({'id': photo_id, 'error': str(e)})

    return jsonify({
        'success': len(created_tasks) > 0,
        'tasks': created_tasks,
        'failed': failed,
    })


@app.route('/api/generate', methods=['POST'])
def generate():
    """批量接收文件并加入队列"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No selected file'}), 400

    created_tasks = []

    for file in files:
        if file:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['INPUT_FOLDER'], filename)
            file.save(input_path)
            
            # 生成缩略图
            generate_thumbnail(input_path, filename)
            
            task_id = str(uuid.uuid4())
            task_info = {
                'id': task_id,
                'status': 'pending',
                'filename': filename,
                'input_path': input_path,
                'output_folder': app.config['OUTPUT_FOLDER'],
                'created_at': time.time(),
                'error': None
            }
            
            with task_lock:
                task_status[task_id] = task_info
            task_queue.put(task_id)
            created_tasks.append(task_info)
            print(f"📥 Task added: {filename} (ID: {task_id})")

    return jsonify({
        'success': True,
        'message': f'{len(created_tasks)} tasks queued',
        'tasks': created_tasks
    })


@app.route('/api/tasks')
def get_tasks():
    """获取所有任务状态，支持智能轮询"""
    with task_lock:
        tasks = list(task_status.values())
    tasks.sort(key=lambda x: x['created_at'], reverse=True)
    
    # 计算是否有活跃任务，前端用于智能轮询
    has_active = any(t['status'] in ('pending', 'processing') for t in tasks)
    
    return jsonify({
        'tasks': tasks,
        'has_active': has_active  # 新增：告知前端是否需要频繁轮询
    })


@app.route('/api/task/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消队列中的任务（包括运行中的任务）"""
    with task_lock:
        task = task_status.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        if task['status'] == 'pending':
            task['status'] = 'cancelled'
            return jsonify({'success': True, 'message': 'Task cancelled'})
        elif task['status'] == 'processing':
            # 标记为取消状态，worker 会检测到并终止进程
            task['status'] = 'cancelled'
            # 尝试立即终止进程
            process = running_processes.get(task_id)
            if process:
                try:
                    process.terminate()
                except:
                    pass
            return jsonify({'success': True, 'message': 'Task cancellation requested'})
        else:
            return jsonify({'success': False, 'error': f"Task already {task['status']}"}), 400



@app.route('/api/delete/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    """删除图库项目 (包括原图、PLY、SPZ 模型)"""
    try:
        # 删除 PLY 模型
        ply_path = os.path.join(OUTPUT_FOLDER, item_id + ".ply")
        if os.path.exists(ply_path):
            os.remove(ply_path)
        
        # 删除 SPZ 模型
        spz_path = os.path.join(OUTPUT_FOLDER, item_id + ".spz")
        if os.path.exists(spz_path):
            os.remove(spz_path)
        
        # 删除缩略图
        thumb_path = os.path.join(THUMBNAIL_FOLDER, item_id + '.jpg')
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # 删除原图 (尝试所有可能的扩展名)
        for ext in ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.PNG']:
            img_path = os.path.join(INPUT_FOLDER, item_id + ext)
            if os.path.exists(img_path):
                os.remove(img_path)
                
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<item_id>')
def download_model(item_id):
    """下载模型文件，支持 ?format=spz|ply 参数"""
    fmt = request.args.get('format', 'spz')
    
    # 优先尝试请求的格式
    if fmt == 'spz':
        spz_path = os.path.join(OUTPUT_FOLDER, item_id + ".spz")
        if os.path.exists(spz_path):
            return send_from_directory(
                OUTPUT_FOLDER,
                item_id + ".spz",
                as_attachment=True,
                download_name=f"{item_id}.spz"
            )
    
    # 回退到 PLY
    ply_path = os.path.join(OUTPUT_FOLDER, item_id + ".ply")
    if not os.path.exists(ply_path):
        return jsonify({'error': 'File not found'}), 404
    
    return send_from_directory(
        OUTPUT_FOLDER, 
        item_id + ".ply",
        as_attachment=True,
        download_name=f"{item_id}.ply"
    )


def find_original_image_filename(item_id):
    """根据 item_id 查找原图文件名（保留真实扩展名）"""
    filename, _ = find_original_image(item_id)
    return filename


@app.route('/api/original/<item_id>')
def get_original_image(item_id):
    """按图库条目 ID 获取原图，支持 inline 预览和附件下载。"""
    filename = find_original_image_filename(item_id)
    if not filename:
        return jsonify({'error': 'Image not found'}), 404

    download = request.args.get('download', '0').lower() in ('1', 'true', 'yes')
    response = send_from_directory(
        INPUT_FOLDER,
        filename,
        as_attachment=download,
        download_name=filename,
        conditional=True,
        max_age=DEFAULT_FILE_CACHE_SECONDS,
    )

    return response


@app.route('/api/thumbnail/<item_id>')
def get_thumbnail(item_id):
    """按图库条目 ID 获取缩略图"""
    thumb_path = ensure_thumbnail_for_item(item_id, allow_generation=True)
    if not thumb_path or not os.path.exists(thumb_path):
        return jsonify({'error': 'Thumbnail not found'}), 404

    filename = os.path.basename(thumb_path)
    response = send_from_directory(
        THUMBNAIL_FOLDER,
        filename,
        conditional=True,
        max_age=THUMBNAIL_CACHE_SECONDS,
    )
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    response.cache_control.public = True
    response.cache_control.max_age = THUMBNAIL_CACHE_SECONDS
    return response


@app.route('/api/convert-all', methods=['POST'])
def convert_all_to_spz():
    """批量将所有现有 PLY 模型转换为 SPZ 格式 (仅本机可用)"""
    if not g.is_owner:
        return jsonify({'error': 'Only available from localhost'}), 403
    
    if not os.path.exists(OUTPUT_FOLDER):
        return jsonify({'success': True, 'converted': 0, 'skipped': 0, 'failed': 0})
    
    ply_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.ply')]
    converted = 0
    skipped = 0
    failed = 0
    
    for ply_filename in ply_files:
        name_without_ext = os.path.splitext(ply_filename)[0]
        ply_path = os.path.join(OUTPUT_FOLDER, ply_filename)
        spz_path = os.path.join(OUTPUT_FOLDER, name_without_ext + '.spz')
        
        # 跳过已有 SPZ 的
        if os.path.exists(spz_path):
            skipped += 1
            continue
        
        try:
            ply_to_spz(ply_path, spz_path)
            ply_size = os.path.getsize(ply_path)
            spz_size = os.path.getsize(spz_path)
            ratio = 100 - spz_size * 100 // ply_size if ply_size > 0 else 0
            print(f"📦 Converted {name_without_ext}: {ply_size/1024:.0f}KB → {spz_size/1024:.0f}KB ({ratio}% smaller)")
            converted += 1
        except Exception as e:
            print(f"⚠️ Failed to convert {name_without_ext}: {e}")
            failed += 1
    
    return jsonify({
        'success': True,
        'converted': converted,
        'skipped': skipped,
        'failed': failed,
        'total': len(ply_files)
    })


@app.route('/files/<path:filename>')
def serve_files(filename):
    normalized_filename = filename.replace('\\', '/')
    served_root = BASE_DIR
    served_filename = filename
    if normalized_filename.startswith(WORKSPACE_FILES_PREFIX):
        served_root = WORKSPACE_FOLDER
        served_filename = normalized_filename[len(WORKSPACE_FILES_PREFIX):]

    thumbnail_prefix = get_relative_files_path(THUMBNAIL_FOLDER) + '/'
    cache_timeout = THUMBNAIL_CACHE_SECONDS if normalized_filename.startswith(thumbnail_prefix) else DEFAULT_FILE_CACHE_SECONDS
    return send_from_directory(
        served_root,
        served_filename,
        conditional=True,
        max_age=cache_timeout,
    )


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """设置接口 - 仅本机可访问 (model_format 对所有客户端可读)"""
    is_local = g.is_owner
    config = load_config()
    
    if request.method == 'GET':
        # model_format 对所有客户端可读（作为服务器默认偏好）
        return jsonify({
            'is_local': is_local,
            'workspace_folder': WORKSPACE_FOLDER if is_local else None,
            'model_format': config.get('model_format', 'spz'),
            # 也返回实际路径供显示
            'input_folder': INPUT_FOLDER if is_local else None,
            'output_folder': OUTPUT_FOLDER if is_local else None
        })
    
    elif request.method == 'POST':
        if not is_local:
            return jsonify({'error': 'Settings can only be modified from localhost'}), 403
        
        data = request.get_json()
        new_config = load_config()
        
        if 'workspace_folder' in data:
            new_config['workspace_folder'] = data['workspace_folder']
            # 清除旧格式的配置
            new_config.pop('input_folder', None)
            new_config.pop('output_folder', None)
        
        # model_format 修改无需重启
        if 'model_format' in data:
            fmt = data['model_format']
            if fmt in ('ply', 'spz'):
                new_config['model_format'] = fmt
        
        save_config(new_config)
        
        # 判断是否需要重启 (仅 workspace_folder 变更需要重启)
        needs_restart = 'workspace_folder' in data
        
        return jsonify({
            'success': True,
            'needs_restart': needs_restart,
            'message': 'Settings saved.' + (' Restart server to apply changes.' if needs_restart else '')
        })


@app.route('/api/restart', methods=['POST'])
def restart_server():
    """重启服务器 - 仅本机可访问"""
    if not g.is_owner:
        return jsonify({'error': 'Restart can only be triggered from localhost'}), 403
    
    def do_restart():
        time.sleep(1)  # 等待响应发送完成
        print("🔄 Restarting server...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    # 在后台线程中执行重启，确保响应能先返回
    threading.Thread(target=do_restart, daemon=True).start()
    
    return jsonify({
        'success': True,
        'message': 'Server will restart in 1 second...'
    })


@app.route('/api/browse-folder', methods=['POST'])
def browse_folder():
    """调用系统原生文件夹选择对话框 (仅本机可用)
    
    使用系统原生工具：
    - Linux: zenity (GTK) 或 kdialog (KDE)
    - macOS: osascript (AppleScript)
    - Windows: PowerShell
    """
    if not g.is_owner:
        return jsonify({'error': 'Only available from localhost'}), 403
    
    import subprocess
    import platform
    
    data = request.get_json() or {}
    title = data.get('title', 'Select Folder')
    initial_dir = data.get('initial_dir', os.path.expanduser('~'))
    if not os.path.isdir(initial_dir):
        initial_dir = os.path.expanduser('~')
    
    system = platform.system()
    
    try:
        if system == 'Linux':
            # 优先使用 zenity (GTK，大多数 Linux 发行版都有)
            # 如果是 KDE，可以尝试 kdialog
            try:
                result = subprocess.run(
                    ['zenity', '--file-selection', '--directory', 
                     '--title=' + title, '--filename=' + initial_dir + '/'],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and result.stdout.strip():
                    return jsonify({'success': True, 'path': result.stdout.strip()})
                elif result.returncode == 1:  # 用户取消
                    return jsonify({'success': False, 'cancelled': True})
            except FileNotFoundError:
                # zenity 不可用，尝试 kdialog
                try:
                    result = subprocess.run(
                        ['kdialog', '--getexistingdirectory', initial_dir, '--title', title],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        return jsonify({'success': True, 'path': result.stdout.strip()})
                except FileNotFoundError:
                    pass
                    
        elif system == 'Darwin':  # macOS
            script = f'''
            tell application "System Events"
                activate
                set folderPath to choose folder with prompt "{title}" default location POSIX file "{initial_dir}"
                return POSIX path of folderPath
            end tell
            '''
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                return jsonify({'success': True, 'path': result.stdout.strip().rstrip('/')})
            elif result.returncode != 0:
                return jsonify({'success': False, 'cancelled': True})
                
        elif system == 'Windows':
            # 使用 PowerShell 调用 Windows 文件夹选择器
            script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $browser = New-Object System.Windows.Forms.FolderBrowserDialog
            $browser.Description = "{title}"
            $browser.SelectedPath = "{initial_dir}"
            $browser.ShowNewFolderButton = $true
            if ($browser.ShowDialog() -eq "OK") {{
                Write-Output $browser.SelectedPath
            }}
            '''
            result = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                return jsonify({'success': True, 'path': result.stdout.strip()})
        
        # 如果上面都失败了，返回错误
        return jsonify({
            'success': False, 
            'error': 'No dialog tool available. Please enter path manually.'
        }), 500
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'cancelled': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/export/<model_id>')
def export_model(model_id):
    """导出模型为独立 HTML 文件（完全离线）。

    支持 query 参数: ?format=spz|ply
    - spz: 直接嵌入 SPZ 数据（体积更小）
    - ply: 为兼容历史行为，先转换为 .splat 后嵌入
    """
    fmt = request.args.get('format', 'spz').lower()
    if fmt not in ('spz', 'ply'):
        fmt = 'spz'

    # 查找 .ply 文件
    ply_filename = f"{model_id}.ply"
    ply_path = os.path.join(OUTPUT_FOLDER, ply_filename)
    
    if not os.path.exists(ply_path):
        return jsonify({'error': 'Model not found'}), 404
    
    try:
        print(f"📦 Exporting {model_id} as {fmt.upper()}...")

        ply_size = os.path.getsize(ply_path)

        if fmt == 'spz':
            spz_path = os.path.join(OUTPUT_FOLDER, f"{model_id}.spz")
            if not os.path.exists(spz_path):
                # 兜底：若缺失 SPZ，按需从 PLY 生成
                spz_path = ply_to_spz(ply_path, spz_path)

            with open(spz_path, 'rb') as f:
                model_bytes = f.read()

            model_size = len(model_bytes)
            model_data = base64.b64encode(model_bytes).decode('utf-8')
            scene_format = 'Spz'
            print(
                f"   PLY: {ply_size / 1024 / 1024:.1f}MB → SPZ: {model_size / 1024 / 1024:.1f}MB "
                f"({100 - model_size * 100 // ply_size}% smaller)"
            )
        else:
            # 兼容历史行为：PLY 导出路径仍使用更紧凑的 .splat 数据
            splat_data = ply_to_splat(ply_path)
            model_size = len(splat_data)
            model_data = base64.b64encode(splat_data).decode('utf-8')
            scene_format = 'Splat'
            print(
                f"   PLY: {ply_size / 1024 / 1024:.1f}MB → Splat: {model_size / 1024 / 1024:.1f}MB "
                f"({100 - model_size * 100 // ply_size}% smaller)"
            )
        
        # 读取库文件并转 Base64 data URL（迁移到 Spark 2.0）
        three_js_candidates = [
            os.path.join(BASE_DIR, 'frontend', 'node_modules', 'three', 'build', 'three.module.js'),
            os.path.join(BASE_DIR, 'static', 'lib', 'three.module.js'),
        ]
        orbit_controls_candidates = [
            os.path.join(BASE_DIR, 'frontend', 'node_modules', 'three', 'examples', 'jsm', 'controls', 'OrbitControls.js'),
        ]
        spark_js_candidates = [
            os.path.join(BASE_DIR, 'frontend', 'node_modules', '@sparkjsdev', 'spark', 'dist', 'spark.module.js'),
        ]

        def _pick_existing_path(candidates):
            for p in candidates:
                if os.path.exists(p):
                    return p
            raise FileNotFoundError(f"No available asset found in candidates: {candidates}")

        three_js_path = _pick_existing_path(three_js_candidates)
        orbit_controls_path = _pick_existing_path(orbit_controls_candidates)
        spark_js_path = _pick_existing_path(spark_js_candidates)

        # three r18x 的 three.module.js 内部会相对导入 ./three.core.js。
        # data URL 模块无法解析相对路径，因此将其改写为 bare specifier（three-core），
        # 再通过 import map 映射到独立 data URL。这样可避免把 three.core 二次嵌套进
        # three.module 的 base64，显著降低导出体积。
        with open(three_js_path, 'r', encoding='utf-8') as f:
            three_module_text = f.read()

        three_core_path = os.path.join(os.path.dirname(three_js_path), 'three.core.js')
        three_core_data_url = 'data:text/javascript,export%20{};'
        if os.path.exists(three_core_path):
            with open(three_core_path, 'rb') as f:
                three_core_b64 = base64.b64encode(f.read()).decode('utf-8')
            three_core_data_url = f"data:text/javascript;base64,{three_core_b64}"
            three_module_text = three_module_text.replace("'./three.core.js'", "'three-core'")
            three_module_text = three_module_text.replace('"./three.core.js"', '"three-core"')

        three_js_b64 = base64.b64encode(three_module_text.encode('utf-8')).decode('utf-8')
        with open(orbit_controls_path, 'rb') as f:
            orbit_controls_b64 = base64.b64encode(f.read()).decode('utf-8')
        with open(spark_js_path, 'rb') as f:
            spark_js_b64 = base64.b64encode(f.read()).decode('utf-8')

        three_data_url = f"data:text/javascript;base64,{three_js_b64}"
        orbit_controls_data_url = f"data:text/javascript;base64,{orbit_controls_b64}"
        spark_data_url = f"data:text/javascript;base64,{spark_js_b64}"
        
        # 读取分享模板
        template_path = os.path.join(BASE_DIR, 'templates', 'share_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # 替换占位符
        html_content = template.replace('{{MODEL_DATA}}', model_data)
        html_content = html_content.replace('{{MODEL_NAME}}', model_id)
        html_content = html_content.replace('{{SCENE_FORMAT}}', scene_format)
        html_content = html_content.replace('{{THREE_DATA_URL}}', three_data_url)
        html_content = html_content.replace('{{THREE_CORE_DATA_URL}}', three_core_data_url)
        html_content = html_content.replace('{{ORBIT_CONTROLS_DATA_URL}}', orbit_controls_data_url)
        html_content = html_content.replace('{{SPARK_DATA_URL}}', spark_data_url)
        
        html_size = len(html_content.encode('utf-8'))
        print(f"   ✅ 导出完成: {ply_size / 1024 / 1024:.1f}MB → {html_size / 1024 / 1024:.1f}MB (原始 HTML 约 {100 * ply_size // html_size}% 大小)")
        
        # 返回 HTML 文件 (可直接在浏览器打开)
        response = Response(html_content, mimetype='text/html')
        response.headers['Content-Disposition'] = f'attachment; filename="{model_id}_share.html"'
        # 暴露导出元信息，供前端展示提示
        response.headers['X-Export-Format'] = fmt
        response.headers['X-Export-Model-Bytes'] = str(model_size)
        response.headers['X-Export-Html-Bytes'] = str(html_size)
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import socket
    
    # 获取本机局域网 IP (跨平台通用)
    def get_local_ip():
        """通过 hostname 解析获取所有本机 IP，返回第一个私有网络地址"""
        try:
            hostname = socket.gethostname()
            # 获取所有 IPv4 地址
            addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
            ips = list(set(ip[4][0] for ip in addrs))
            
            # 过滤：优先返回私有网络 IP
            for ip in ips:
                if ip.startswith('127.'):
                    continue
                # 排除 VPN/容器 常见网段
                if ip.startswith('28.0.') or ip.startswith('172.17.'):
                    continue
                # 私有网络地址: 192.168.x.x, 10.x.x.x, 172.16-31.x.x
                if ip.startswith('192.168.') or ip.startswith('10.'):
                    return ip
                if ip.startswith('172.'):
                    parts = ip.split('.')
                    if 16 <= int(parts[1]) <= 31:
                        return ip
            
            # 没有找到私有 IP，返回第一个非 127 的
            for ip in ips:
                if not ip.startswith('127.'):
                    return ip
        except:
            pass
        return '127.0.0.1'
    
    local_ip = os.environ.get('SHARP_LAN_IP') or get_local_ip()
    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')
    
    # 自定义启动日志，只显示正确的 IP 地址
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.DEBUG if SHARP_VERBOSE else logging.WARNING)
    
    # 检查是否存在 SSL 证书
    if os.path.exists(cert_file) and os.path.exists(key_file):
        protocol = 'https'
        ssl_ctx = (cert_file, key_file)
    else:
        protocol = 'http'
        ssl_ctx = None
    
    # 输出简洁的启动信息（只在 reloader 子进程中输出，避免重复）
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        print(f' * Running on {protocol}://127.0.0.1:5050')
        print(f' * Running on {protocol}://{local_ip}:5050')
        print('Press CTRL+C to quit')
        print_runtime_diagnostics(protocol, local_ip)
    
    if ssl_ctx:
        app.run(debug=True, port=5050, host='0.0.0.0', ssl_context=ssl_ctx)
    else:
        app.run(debug=True, port=5050, host='0.0.0.0')

"""用户级配置存储：平台路径、首次迁移、原子写入及并发修订保护。"""

import copy
import errno
import hashlib
import json
import os
import platform
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from backend.services.workspace_lock import WorkspaceInstanceLock

_THREAD_LOCK = threading.RLock()


class ConfigStorageError(RuntimeError):
    def __init__(self, code='config_unavailable', status_code=503):
        super().__init__('Configuration could not be loaded or saved. Check its location and backup.')
        self.code = code
        self.status_code = status_code


class ConfigData(dict):
    """修订信息放在属性中，不写入用户 JSON 或 API。"""

    def __init__(self, data, path, revision):
        super().__init__(data)
        self.source_path = os.path.abspath(path)
        self.revision = revision


def user_config_dir(system=None, environ=None, home=None):
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    override = env.get('SHARP_CONFIG_HOME', '').strip()
    system = system or platform.system()
    if override:
        root = Path(override).expanduser()
    elif system == 'Windows':
        root = Path(env.get('LOCALAPPDATA') or user_home / 'AppData' / 'Local') / 'SharpGUI'
    elif system == 'Darwin':
        root = user_home / 'Library' / 'Application Support' / 'SharpGUI'
    else:
        root = Path(env.get('XDG_CONFIG_HOME') or user_home / '.config') / 'sharp-gui'
    if not root.is_absolute():
        raise ConfigStorageError('config_invalid', 400)
    return root


def default_workspace_dir():
    if os.environ.get('SHARP_CONFIG_HOME', '').strip() or platform.system() != 'Linux':
        return str(user_config_dir() / 'workspace')
    root = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    if not root.is_absolute():
        raise ConfigStorageError('config_invalid', 400)
    return str(root / 'sharp-gui' / 'workspace')


def _validate(data, status_code=503):
    if not isinstance(data, dict) or ('workspace_folder' in data and (
            not isinstance(data['workspace_folder'], str) or not data['workspace_folder'].strip())):
        raise ConfigStorageError('config_invalid', status_code)
    if 'access_control' in data and not isinstance(data['access_control'], dict):
        raise ConfigStorageError('config_invalid', status_code)
    if ('photo_gallery_roots_by_workspace' in data and not isinstance(data['photo_gallery_roots_by_workspace'], dict)) or (
            'photo_gallery_roots' in data and not isinstance(data['photo_gallery_roots'], list)):
        raise ConfigStorageError('config_invalid', status_code)


def _read(path):
    try:
        raw = Path(path).read_bytes()
        data = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ConfigStorageError('config_invalid', 503) from exc
    _validate(data)
    return ConfigData(data, path, hashlib.sha256(raw).hexdigest())


def read_legacy_config(path):
    """只读旧配置，按它所在目录解释相对路径，保留未知字段。"""
    try:
        original = _read(path)
        data = copy.deepcopy(dict(original))
        base = os.path.dirname(os.path.abspath(path))
        def absolute(value):
            if not isinstance(value, str) or not value.strip():
                raise ConfigStorageError('config_invalid', 400)
            return os.path.abspath(os.path.join(base, os.path.expanduser(value)))
        workspace = data.get('workspace_folder')
        if not workspace:
            old_input = data.get('input_folder')
            workspace = os.path.dirname(absolute(old_input)) if old_input and os.path.basename(old_input.rstrip('/\\')) == 'inputs' else base
        data['workspace_folder'] = absolute(workspace)
        for key in ('input_folder', 'output_folder'):
            if key in data:
                data[key] = absolute(data[key])
        def normalize_roots(roots):
            if isinstance(roots, list):
                for root in roots:
                    if isinstance(root, dict) and root.get('path'):
                        root['path'] = absolute(root['path'])
            return roots
        if 'photo_gallery_roots' in data:
            normalize_roots(data['photo_gallery_roots'])
        buckets = data.get('photo_gallery_roots_by_workspace')
        if isinstance(buckets, dict):
            data['photo_gallery_roots_by_workspace'] = {
                os.path.normcase(absolute(key)): normalize_roots(roots) for key, roots in buckets.items()
            }
        return data, original.revision
    except OSError as exc:
        raise ConfigStorageError('config_source_unavailable', 400) from exc


@contextmanager
def _locked(path):
    """复用现有内核锁原语；锁由进程退出释放，标记不等于持锁。"""
    with _THREAD_LOCK:
        try:
            parent = Path(path).parent
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_path = parent / (Path(path).name + '.lock')
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(descriptor, 'r+b') as handle:
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b'0')
                    handle.flush()
                deadline = time.monotonic() + 3
                while True:
                    handle.seek(0)
                    try:
                        WorkspaceInstanceLock._lock_handle(handle)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        if time.monotonic() >= deadline:
                            raise ConfigStorageError('config_busy', 409) from exc
                        time.sleep(.05)
                try:
                    yield handle
                finally:
                    handle.seek(0)
                    WorkspaceInstanceLock._unlock_handle(handle)
        except OSError as exc:
            raise ConfigStorageError() from exc


def _mark_initialized(handle):
    handle.seek(0)
    if handle.read(1) == b'1':
        return
    handle.seek(0)
    handle.write(b'1')
    handle.flush()
    os.fsync(handle.fileno())


def _atomic_write(path, data):
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=Path(path).parent, prefix='.config-', suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return hashlib.sha256(payload).hexdigest()


def load_stored_config(path, *, legacy_path=None, default_workspace=None):
    path = os.path.abspath(path)
    with _locked(path) as handle:
        if not os.path.lexists(path):
            handle.seek(0)
            if handle.read(1) == b'1':
                raise ConfigStorageError('config_missing', 503)
            if legacy_path and os.path.lexists(legacy_path):
                data, _ = read_legacy_config(legacy_path)
            else:
                # 旧配置被移除但本包仍有用户数据时，只探测已知目录的首项。
                # 不扫描其它安装，也不把空包里的预建目录当作旧工作区。
                if legacy_path:
                    root = Path(legacy_path).parent
                    for name in ('outputs', 'inputs', 'model-assets', '.model-asset-library', '.photo-gallery-cache'):
                        try:
                            with os.scandir(root / name) as entries:
                                if next(entries, None) is not None:
                                    default_workspace = str(root)
                                    break
                        except FileNotFoundError:
                            pass
                data = {'workspace_folder': default_workspace}
            _atomic_write(path, data)
        data = _read(path)
        if legacy_path and 'workspace_folder' not in data:
            raise ConfigStorageError('config_invalid', 503)
        _mark_initialized(handle)
        return data


def save_stored_config(path, config, *, backup=False):
    path = os.path.abspath(path)
    _validate(config, 400)
    with _locked(path) as handle:
        current = _read(path) if os.path.exists(path) else None
        if isinstance(config, ConfigData) and (config.source_path != path or current is None or config.revision != current.revision):
            raise ConfigStorageError('config_conflict', 409)
        if current is None:
            handle.seek(0)
            if handle.read(1) == b'1':
                raise ConfigStorageError('config_missing', 503)
        if backup and current is not None:
            _atomic_write(path + '.before-restore-' + uuid.uuid4().hex + '.bak', dict(current))
        revision = _atomic_write(path, config)
        _mark_initialized(handle)
        if isinstance(config, ConfigData):
            config.revision = revision

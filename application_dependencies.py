"""标准库实现的应用依赖准备与只读加载，不修改基础 Python 环境。"""

from __future__ import annotations

import email
import hashlib
import importlib
import json
import os
import re
import shutil
import ssl
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener


LOCK_FILE = 'app-dependencies.lock.json'
MAX_WHEEL_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
PROTECTED_IMPORTS = {'torch', 'numpy', 'scipy', 'flask', 'PIL', 'sharp', 'backend',
                     'application_dependencies', 'sitecustomize', 'usercustomize'}
_active_paths = set()


class DependencyError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def descriptor(manifest):
    value = manifest.get('applicationDependencies')
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'lockFile', 'sha256'}
            or value.get('lockFile') != LOCK_FILE
            or not re.fullmatch('[0-9a-f]{64}', str(value.get('sha256', '')))):
        raise DependencyError('update_dependency_lock_invalid')
    return value


def validate_lock(lock, expected_digest):
    if (not isinstance(lock, dict) or lock.get('schemaVersion') != 1
            or digest(lock) != expected_digest or not isinstance(lock.get('packages'), list)):
        raise DependencyError('update_dependency_lock_invalid')
    names, roots = set(), set()
    for package in lock['packages']:
        if not isinstance(package, dict):
            raise DependencyError('update_dependency_lock_invalid')
        name, version = package.get('name', ''), package.get('version', '')
        imports = package.get('imports')
        filename = package.get('filename', '')
        if not all(isinstance(value, str) for value in (name, version, filename, package.get('url'))):
            raise DependencyError('update_dependency_lock_invalid')
        try:
            parsed = urlsplit(package['url'])
            port = parsed.port
        except ValueError as exc:
            raise DependencyError('update_dependency_lock_invalid') from exc
        minimum = package.get('pythonMinimum')
        if (not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', name) or name in names
                or not re.fullmatch(r'\d+(?:\.\d+){1,3}', version)
                or filename != f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
                or parsed.scheme != 'https' or parsed.hostname != 'files.pythonhosted.org'
                or parsed.username or parsed.password or port not in (None, 443)
                or parsed.query or parsed.fragment or parsed.path.rsplit('/', 1)[-1] != filename
                or not re.fullmatch('[0-9a-f]{64}', str(package.get('sha256', '')))
                or not isinstance(imports, list) or not imports
                or not all(isinstance(root, str) and root.isidentifier() for root in imports)
                or len(set(imports)) != len(imports)
                or set(imports) & (PROTECTED_IMPORTS | set(sys.stdlib_module_names) | roots)
                or not isinstance(package.get('requires'), list)
                or not all(isinstance(item, str) for item in package['requires'])
                or not isinstance(minimum, list) or len(minimum) != 2
                or not all(type(part) is int for part in minimum) or minimum < [3, 10]):
            raise DependencyError('update_dependency_lock_invalid')
        if tuple(sys.version_info[:2]) < tuple(minimum):
            raise DependencyError('update_base_environment_incompatible')
        names.add(name)
        roots.update(imports)
    if any(set(package['requires']) - names for package in lock['packages']):
        raise DependencyError('update_dependency_lock_invalid')
    return lock


def load_contract(base_dir):
    root = Path(base_dir)
    try:
        manifest = json.loads((root / 'update-manifest.json').read_text(encoding='utf-8-sig'))
        value = descriptor(manifest)
        if value is None:
            return None
        lock = json.loads((root / LOCK_FILE).read_text(encoding='utf-8-sig'))
        return validate_lock(lock, value['sha256'])
    except (OSError, ValueError, TypeError) as exc:
        raise DependencyError('update_dependency_lock_invalid') from exc


def _safe_root(base_dir):
    root = Path(base_dir).resolve()
    directory = root / '.sharp-gui-update' / 'dependencies'
    for part in (directory.parent, directory, directory / 'sets'):
        if part.resolve() != part.absolute():
            raise DependencyError('update_dependency_integrity_failed')
    return directory


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DependencyError('update_dependency_download_failed')


def download(package):
    """仅下载清单中经过验证 TLS 的固定 PyPI wheel，不接受重定向。"""
    try:
        with build_opener(_NoRedirect, HTTPSHandler(context=ssl.create_default_context())).open(
                package['url'], timeout=30) as response:
            data = response.read(MAX_WHEEL_BYTES + 1)
    except DependencyError:
        raise
    except (OSError, ValueError) as exc:
        raise DependencyError('update_dependency_download_failed') from exc
    if len(data) > MAX_WHEEL_BYTES or hashlib.sha256(data).hexdigest() != package['sha256']:
        raise DependencyError('update_dependency_integrity_failed')
    return data


def validate_wheel(path, package):
    """验证整包和导入根，zipimport 直接加载 wheel，无解压安装脚本。"""
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
        raise DependencyError('update_dependency_integrity_failed')
    info_root = f"{package['name'].replace('-', '_')}-{package['version']}.dist-info"
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) > 5000 or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES
                    or len({item.filename.casefold() for item in entries}) != len(entries)):
                raise DependencyError('update_dependency_integrity_failed')
            for item in entries:
                parts = PurePosixPath(item.filename).parts
                if (not parts or '\\' in item.filename or ':' in item.filename
                        or item.filename.startswith('/') or '..' in parts
                        or any(part.endswith(('.', ' ')) for part in parts)
                        or parts[0] not in {*package['imports'], info_root}
                        or item.orig_filename != item.filename
                        or stat.S_ISLNK(item.external_attr >> 16)
                        or (not item.is_dir() and Path(item.filename).suffix.lower()
                            in {'.pth', '.pyd', '.dll', '.so', '.exe', '.bat', '.cmd', '.pyc'})):
                    raise DependencyError('update_dependency_integrity_failed')
            wheel = email.message_from_bytes(archive.read(f'{info_root}/WHEEL'))
            metadata = email.message_from_bytes(archive.read(f'{info_root}/METADATA'))
            if (wheel.get('Root-Is-Purelib', '').lower() != 'true'
                    or wheel.get_all('Tag') != ['py3-none-any']
                    or metadata.get('Name', '').lower().replace('_', '-') != package['name']
                    or metadata.get('Version') != package['version']):
                raise DependencyError('update_dependency_integrity_failed')
            actual_requires = set()
            for requirement in metadata.get_all('Requires-Dist', []):
                if re.search(r";\s*extra\s*==\s*(['\"])[A-Za-z0-9_-]+\1\s*$", requirement):
                    continue
                # 保守支持无环境 marker 的依赖；未知表达式需要先扩展并验证协议。
                if ';' in requirement:
                    raise DependencyError('update_dependency_lock_invalid')
                match = re.match(r'([A-Za-z0-9_-]+)', requirement)
                if not match:
                    raise DependencyError('update_dependency_lock_invalid')
                actual_requires.add(match[1].lower().replace('_', '-'))
            if actual_requires != set(package['requires']):
                raise DependencyError('update_dependency_lock_invalid')
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise DependencyError('update_dependency_integrity_failed') from exc


def verified_paths(base_dir, lock):
    directory = _safe_root(base_dir) / 'sets' / digest(lock)
    if directory.resolve() != directory.absolute():
        raise DependencyError('update_dependency_integrity_failed')
    try:
        marker = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
        if marker != {'lockSha256': digest(lock)}:
            raise DependencyError('update_dependencies_not_ready')
        paths = []
        for package in lock['packages']:
            path = directory / package['filename']
            validate_wheel(path, package)
            paths.append(str(path))
        return paths
    except FileNotFoundError as exc:
        raise DependencyError('update_dependencies_not_ready') from exc
    except (OSError, ValueError) as exc:
        raise DependencyError('update_dependency_integrity_failed') from exc


def prepare(base_dir, lock, *, downloader=None):
    """发布完整依赖集合前完成校验；失败不改变任何已发布集合。"""
    validate_lock(lock, digest(lock))
    try:
        return verified_paths(base_dir, lock)
    except DependencyError as exc:
        if exc.code != 'update_dependencies_not_ready':
            raise
    sets = _safe_root(base_dir) / 'sets'
    sets.mkdir(parents=True, exist_ok=True)
    destination = sets / digest(lock)
    if destination.exists():
        raise DependencyError('update_dependency_integrity_failed')
    temporary = Path(tempfile.mkdtemp(prefix='.preparing-', dir=sets))
    try:
        for package in lock['packages']:
            payload = (downloader or download)(package)
            if len(payload) > MAX_WHEEL_BYTES:
                raise DependencyError('update_dependency_integrity_failed')
            path = temporary / package['filename']
            with path.open('wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            validate_wheel(path, package)
        with (temporary / 'complete.json').open('w', encoding='utf-8') as handle:
            json.dump({'lockSha256': digest(lock)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(temporary, destination)
        except FileExistsError:
            # 安装器和另一个幂等准备者同时完成时仍验证已发布集合。
            pass
        return verified_paths(base_dir, lock)
    except OSError as exc:
        raise DependencyError('update_dependency_prepare_failed') from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def activate(base_dir):
    """只读选择当前提交声明的完整依赖集合，绝不联网或安装。"""
    lock = load_contract(base_dir)
    paths = verified_paths(base_dir, lock) if lock is not None else []
    for package in (lock or {}).get('packages', []):
        for root in package['imports']:
            imported = sys.modules.get(root)
            if imported is not None and not any(str(getattr(imported, '__file__', '')).startswith(path + os.sep)
                                               for path in paths):
                raise DependencyError('update_dependency_integrity_failed')
    sys.path[:] = [path for path in sys.path if path not in _active_paths]
    sys.path[:0] = paths
    _active_paths.clear()
    _active_paths.update(paths)
    importlib.invalidate_caches()
    return digest(lock) if lock is not None else None

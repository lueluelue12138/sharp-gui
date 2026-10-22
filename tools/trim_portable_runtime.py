"""按明确清单与已验证组件指纹裁剪便携包副本。"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat


LAYOUT_REVISION = 2
REMOVABLE_PATHS = (
    ('frontend/node_modules', 'frontend_build_dependencies'),
    ('python/Lib/site-packages/torch/lib/dnnl.lib', 'unused_onednn_static_library'),
    ('tools/ffmpeg/bin/ffplay.exe', 'unused_media_player'),
)

# 原生 DLL 只裁剪经过实际推理/配准验证的固定组件；未知版本完整保留。
# 指纹覆盖保留的 Python 源码与原生文件，避免只按文件名误裁新依赖。
NATIVE_TRIM_PROFILES = (
    {
        'name': 'torch-2.8.0-cu128',
        'directory': 'python/Lib/site-packages/torch',
        'fingerprint': '9d893e80526a586a04bb0443a2b723e9404cacf734073aee025e11909f24baa2',
        'remove': {
            'lib/kineto.lib': '89aa9136395576077d1898d232ca69cd01718ab91882e06ae4466bb282ed3d4b',
            'lib/libprotobuf.lib': 'f2d648c3ffc28604cda5fc7a70b31326c750b8df85c9286d62147773b7dbb6a5',
            'lib/libprotoc.lib': '82b847f70317a0fe40309d13b9395888c4112e1ad2d424ddbeaeeaaa31dfc00d',
            'lib/curand64_10.dll': '3465fd1b46e551339b8f44c455756a0f2cba8bd846562eb659040d48edb7aaac',
            'lib/cusolverMg64_11.dll': 'c3377f10606ff0606be2f08401d54aff6c37f137b78d6b6e21be356a5b4d6cc2',
        },
    },
    {
        'name': 'torch-2.8.0-cu126',
        'directory': 'python/Lib/site-packages/torch',
        'fingerprint': 'ca8649c63a8167bd1b3cd664a79d780199cabb0f178251b352ed9764821dd263',
        'remove': {
            'lib/kineto.lib': '444ffbd0b9d494c46a525141d448d9781cf5340de0ce90d6e4db05bda84cbc48',
            'lib/libprotobuf.lib': 'cfcf20a5cdd8baab70b87565286ba1525060710af8a4af749b5393e6ebcba2cd',
            'lib/libprotoc.lib': '240458d9417a3b0ef9f386292ba6cc8d5fa3aac7208aa5a93ade2e8b801e29cc',
            'lib/curand64_10.dll': '0704875170e99155d74d533b50ade32ead16bc62f1b86e35c10640eaac4e08c9',
            'lib/cusolverMg64_11.dll': 'e4131f30f911e19ab4afc3a65cc6aba52d0be16e1a52d0ff4e10432d70e30114',
        },
    },
    {
        'name': 'colmap-sift-verified',
        'directory': '.sharp-gui-tools/colmap',
        'fingerprint': '0b8286b3189486bf34c85ffcb7a827fbad75a77ff902f0ad87c9ae8984a15125',
        'remove': {
            'bin/onnxruntime_providers_cuda.dll': 'ce1c698cae708fd4ed9ab36eddf256213df40779d0806d20f32132c5d422da72',
            'bin/curand64_10.dll': '4d6d16c9941c4f7a7e49d5c43df25d408a2a8503d8cc1eb9808e0e0c2cde36d4',
        },
    },
)


def _assert_regular_tree(root, path, *, recursive=True):
    """在任何删除之前拒绝越界、符号链接和 Windows junction。"""
    path.relative_to(root)
    for ancestor in (path, *path.parents):
        if ancestor == root.parent:
            break
        metadata = ancestor.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Links and reparse points are not allowed in package cleanup paths')
    if path == root:
        return
    if path.is_dir():
        if recursive:
            with os.scandir(path) as entries:
                for entry in entries:
                    _assert_regular_tree(root, Path(entry.path))
    elif not path.is_file():
        raise ValueError('Only regular files and directories may be trimmed')


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _native_fingerprint(component, excluded):
    """为保留的可执行文件与 Python 源码生成稳定指纹，忽略字节码缓存。"""
    digest = hashlib.sha256()
    for path in sorted(component.rglob('*')):
        relative = path.relative_to(component).as_posix()
        if (not path.is_file() or relative in excluded or path.name.endswith('_test.exe')
                or path.suffix.lower() not in ('.dll', '.exe', '.pyd', '.py')):
            continue
        digest.update(relative.encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(_file_sha256(path)))
    return digest.hexdigest()


def _native_candidates(root):
    """组件及候选库均匹配时才裁剪，版本变化或文件改动时保留全部候选。"""
    fingerprints = {}
    for profile in NATIVE_TRIM_PROFILES:
        component = root / profile['directory']
        if not any(os.path.lexists(component / name) for name in profile['remove']):
            continue
        _assert_regular_tree(root, component)
        if component not in fingerprints:
            excluded = {name for item in NATIVE_TRIM_PROFILES
                        if item['directory'] == profile['directory'] for name in item['remove']}
            fingerprints[component] = _native_fingerprint(component, excluded)
        if fingerprints[component] != profile['fingerprint']:
            continue
        if any((component / name).exists() and _file_sha256(component / name) != expected
               for name, expected in profile['remove'].items()):
            continue
        for name in profile['remove']:
            yield component / name, 'verified_unused_native_library', profile['name']


def plan_trim(package_root):
    """只接受具有运行时标识的独立包目录，不接受源码根或虚拟环境。"""
    root = Path(os.path.abspath(package_root))
    _assert_regular_tree(root, root)
    for name in ('portable-package.json', 'python/python.exe', 'frontend/dist/index.html'):
        if not (root / name).is_file():
            raise ValueError('A complete portable staging directory is required')
    if (root / 'venv').exists():
        raise ValueError('Refusing to trim a development workspace')
    candidates = [(root / relative, reason, None) for relative, reason in REMOVABLE_PATHS]
    colmap_bin = root / '.sharp-gui-tools/colmap/bin'
    # COLMAP 的独立单元测试程序不参与命令行重建。
    if colmap_bin.is_dir():
        candidates.extend((path, 'colmap_unit_test_executable', None)
                          for path in sorted(colmap_bin.glob('*_test.exe')))
    candidates.extend(_native_candidates(root))
    result = []
    for path, reason, profile in candidates:
        if not os.path.lexists(path):
            continue
        _assert_regular_tree(root, path)
        files = list(path.rglob('*')) if path.is_dir() else [path]
        size = sum(item.stat().st_size for item in files if item.is_file())
        entry = {'path': path.relative_to(root).as_posix(), 'reason': reason, 'bytes': size}
        if profile:
            entry['native_profile'] = profile
        result.append(entry)
    return root, result


def preserve_frontend_licenses(root, source, *, apply=False):
    """只复制开发依赖中的许可证和组件标识，不复制 JS 构建工具。"""
    source = Path(os.path.abspath(source))
    if not source.is_dir():
        raise ValueError('Frontend dependencies are required to preserve license inventory')
    _assert_regular_tree(source, source)
    destination = root / '.sharp-gui-tools/frontend-licenses'
    if destination.parent.exists():
        _assert_regular_tree(root, destination.parent, recursive=False)
    if destination.exists():
        _assert_regular_tree(root, destination)
    files = []
    for directory, folders, names in os.walk(source, followlinks=False):
        for folder in folders:
            _assert_regular_tree(source, Path(directory) / folder, recursive=False)
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(source)
            if (name == 'package.json' or any(fnmatch.fnmatch(name.lower(), pattern)
                                            for pattern in ('license*', 'copying*', 'notice*'))
                    or any(part.lower() in ('licenses', 'license') for part in relative.parts[:-1])):
                _assert_regular_tree(source, path)
                files.append((path, destination / relative))
    if not any(path.name.lower().startswith(('license', 'copying')) for path, _ in files):
        raise ValueError('Frontend dependency license inventory is empty')
    if apply:
        for path, target in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return len(files)


def trim_runtime(package_root, *, apply=False, frontend_dependencies=None):
    root, entries = plan_trim(package_root)
    license_count = (preserve_frontend_licenses(root, frontend_dependencies, apply=apply)
                     if frontend_dependencies is not None else 0)
    if apply:
        for entry in entries:
            path = root / entry['path']
            _assert_regular_tree(root, path)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    profiles = sorted({entry['native_profile'] for entry in entries if 'native_profile' in entry})
    return {'layout_revision': LAYOUT_REVISION, 'applied': apply, 'frontend_license_files': license_count,
            'native_profiles': profiles,
            'removed_bytes': sum(entry['bytes'] for entry in entries), 'entries': entries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Delete listed files in the package copy')
    parser.add_argument('--frontend-dependencies', type=Path,
                        help='Preserve license files from the frontend dependency tree')
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(trim_runtime(arguments.package_root, apply=arguments.apply,
                                     frontend_dependencies=arguments.frontend_dependencies), indent=2))
    except (OSError, ValueError) as error:
        print(json.dumps({'complete': False, 'error': type(error).__name__}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

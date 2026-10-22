"""按明确清单裁剪便携包副本，保留模型、运行库、编译头文件和许可资料。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil
import stat


LAYOUT_REVISION = 1
REMOVABLE_PATHS = (
    ('frontend/node_modules', 'frontend_build_dependencies'),
    ('python/Lib/site-packages/torch/lib/dnnl.lib', 'unused_onednn_static_library'),
    ('tools/ffmpeg/bin/ffplay.exe', 'unused_media_player'),
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


def plan_trim(package_root):
    """只接受具有运行时标识的独立包目录，不接受源码根或虚拟环境。"""
    root = Path(os.path.abspath(package_root))
    _assert_regular_tree(root, root)
    for name in ('portable-package.json', 'python/python.exe', 'frontend/dist/index.html'):
        if not (root / name).is_file():
            raise ValueError('A complete portable staging directory is required')
    if (root / 'venv').exists():
        raise ValueError('Refusing to trim a development workspace')
    candidates = [(root / relative, reason) for relative, reason in REMOVABLE_PATHS]
    colmap_bin = root / '.sharp-gui-tools/colmap/bin'
    # COLMAP 的独立单元测试程序不参与命令行重建。
    if colmap_bin.is_dir():
        candidates.extend((path, 'colmap_unit_test_executable')
                          for path in sorted(colmap_bin.glob('*_test.exe')))
    result = []
    for path, reason in candidates:
        if not os.path.lexists(path):
            continue
        _assert_regular_tree(root, path)
        files = list(path.rglob('*')) if path.is_dir() else [path]
        size = sum(item.stat().st_size for item in files if item.is_file())
        result.append({'path': path.relative_to(root).as_posix(), 'reason': reason, 'bytes': size})
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
    return {'layout_revision': LAYOUT_REVISION, 'applied': apply, 'frontend_license_files': license_count,
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

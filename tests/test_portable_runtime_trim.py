"""便携运行时裁剪仅作用于包副本，保留原生运行库与模型精度。"""

from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from tools.trim_portable_runtime import trim_runtime


def package(tmp_path):
    root = tmp_path / 'portable'
    for name in ('portable-package.json', 'python/python.exe', 'frontend/dist/index.html'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'package marker')
    return root


def write(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(name.encode())
    return path


def test_dry_run_and_apply_preserve_runtime_headers_weights_and_licenses(tmp_path):
    root = package(tmp_path)
    removed = [write(root, name) for name in (
        'frontend/node_modules/typescript/lib/typescript.js',
        'python/Lib/site-packages/torch/lib/dnnl.lib',
        '.sharp-gui-tools/colmap/bin/automatic_reconstruction_test.exe',
        'tools/ffmpeg/bin/ffplay.exe',
    )]
    retained = [write(root, name) for name in (
        'python/Lib/site-packages/torch/lib/torch_cuda.dll',
        'python/Lib/site-packages/torch/lib/torch.lib',
        'python/Lib/site-packages/torch/include/torch/extension.h',
        '.cache/torch/hub/checkpoints/sharp_2572gikvuh.pt',
        '.sharp-gui-tools/brush/ooo-v1.0.0/upstream-release/brush-cli.exe',
        '.sharp-gui-tools/colmap/bin/colmap.exe',
        '.sharp-gui-tools/colmap/bin/LICENSE.txt',
        'tools/ffmpeg/bin/ffmpeg.exe',
        'tools/ffmpeg/bin/ffprobe.exe',
    )]
    before = {path: path.read_bytes() for path in retained}
    dry = trim_runtime(root)
    assert not dry['applied'] and len(dry['entries']) == 4
    assert all(path.exists() for path in removed)
    assert trim_runtime(root, apply=True)['removed_bytes'] > 0
    assert not any(path.exists() for path in removed)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert trim_runtime(root, apply=True)['removed_bytes'] == 0


def test_rejects_source_workspace_or_missing_package_markers(tmp_path):
    with pytest.raises(ValueError, match='complete portable'):
        trim_runtime(tmp_path, apply=True)
    root = package(tmp_path)
    (root / 'venv').mkdir()
    with pytest.raises(ValueError, match='development workspace'):
        trim_runtime(root, apply=True)


def test_rejects_link_before_deleting_anything(tmp_path):
    root = package(tmp_path)
    static_library = write(root, 'python/Lib/site-packages/torch/lib/dnnl.lib')
    outside = tmp_path / 'outside'
    outside.mkdir()
    secret = write(outside, 'keep.txt')
    link = root / 'frontend/node_modules'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks requires OS permission')
    with pytest.raises(ValueError, match='Links'):
        trim_runtime(root, apply=True)
    assert static_library.exists() and secret.exists()


def test_rejects_windows_junction_before_any_deletion(tmp_path, monkeypatch):
    root = package(tmp_path)
    library = write(root, 'python/Lib/site-packages/torch/lib/dnnl.lib')
    nested = write(root, 'frontend/node_modules/junction/keep.txt')
    original = Path.lstat

    def metadata(path, *args, **kwargs):
        if path == nested.parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(ValueError, match='reparse'):
        trim_runtime(root, apply=True)
    assert library.exists() and nested.exists()


def test_frontend_licenses_survive_removal_of_build_dependencies(tmp_path):
    root = package(tmp_path)
    source = root / 'frontend/node_modules'
    license_file = write(source, 'react/LICENSE')
    identity = write(source, 'react/package.json')
    nested = write(source, 'dependency/licenses/MIT.txt')
    write(source, 'react/build/runtime.js')
    originals = {path.relative_to(source): path.read_bytes() for path in (license_file, identity, nested)}
    assert trim_runtime(root, frontend_dependencies=source)['frontend_license_files'] == 3
    assert source.exists()
    trim_runtime(root, apply=True, frontend_dependencies=source)
    assert not source.exists()
    destination = root / '.sharp-gui-tools/frontend-licenses'
    for relative, content in originals.items():
        assert (destination / relative).read_bytes() == content
    assert not (destination / 'react/build/runtime.js').exists()

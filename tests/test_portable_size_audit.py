"""体积盘点的只读、无解压、路径与错误边界。"""

import json
import os
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools.audit_portable_size import audit_archive, audit_components, main


def test_components_are_read_only_and_do_not_double_count(tmp_path):
    folder = tmp_path / 'runtime'
    folder.mkdir()
    data = folder / 'runtime.bin'
    data.write_bytes(b'abc')
    before = data.stat().st_mtime_ns
    report = audit_components([('python', folder)])
    assert report['complete'] and report['logical_bytes'] == 3
    assert report['scope'] == 'selected_components_only'
    assert data.stat().st_mtime_ns == before
    assert data.read_bytes() == b'abc'
    with pytest.raises(ValueError, match='overlap'):
        audit_components([('parent', folder), ('child', data)])
    with pytest.raises(ValueError, match='unique'):
        audit_components([('python', data), ('python', folder)])


def test_directory_links_are_not_followed(tmp_path):
    folder, outside = tmp_path / 'runtime', tmp_path / 'outside'
    folder.mkdir()
    outside.mkdir()
    (outside / 'private.txt').write_bytes(b'do not count')
    link = folder / 'link'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating a symlink requires OS permission')
    report = audit_components([('runtime', folder)])
    assert report['logical_bytes'] == 0
    assert report['components']['runtime']['skipped_links'] == 1
    with pytest.raises(ValueError, match='not links'):
        audit_components([('link', link)])


def test_unreadable_directory_marks_report_incomplete(tmp_path, monkeypatch):
    def denied(*_args):
        raise PermissionError('simulated permission failure')
    monkeypatch.setattr(os, 'scandir', denied)
    report = audit_components([('blocked', tmp_path)])
    assert not report['complete']
    assert report['components']['blocked']['errors'] == 1


def test_windows_reparse_attributes_prevent_traversal(tmp_path, monkeypatch):
    folder = tmp_path / 'runtime'
    reparse = folder / 'junction'
    reparse.mkdir(parents=True)
    (reparse / 'outside-private-file').write_bytes(b'must not count')
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        if path == reparse:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', metadata)
    report = audit_components([('runtime', folder)])
    assert report['logical_bytes'] == 0
    assert report['components']['runtime']['skipped_links'] == 1


@pytest.mark.parametrize('wrapper', ['', 'sharp-gui/'])
def test_zip_totals_and_classification_never_read_or_extract_members(tmp_path, monkeypatch, wrapper):
    archive = tmp_path / 'runtime.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr(wrapper + 'python/Lib/site-packages/torch/lib/cuda.dll', b'0' * 100000)
        stream.writestr(wrapper + 'frontend/node_modules/three/build/three.module.js', b'abc')
        stream.writestr(wrapper + 'outputs/private-filename.ply', b'private')
        stream.writestr(wrapper + '.video-reconstruction-env/old-runtime.dll', b'old')
    def forbidden(*_args, **_kwargs):
        pytest.fail('ZIP payload must not be read or extracted')
    monkeypatch.setattr(zipfile.ZipFile, 'open', forbidden)
    report = audit_archive(archive)
    assert report['complete']
    assert report['archive_bytes'] == archive.stat().st_size
    assert report['logical_bytes'] == 100013
    assert report['compressed_payload_bytes'] < report['logical_bytes']
    assert report['components']['pytorch']['logical_bytes'] == 100000
    assert report['components']['user_data']['logical_bytes'] == 7
    assert report['components']['legacy_video_environment']['logical_bytes'] == 3
    assert 'private-filename' not in json.dumps(report)
    assert report['stripped_wrapper_directory'] == bool(wrapper)
    assert not (tmp_path / 'sharp-gui').exists()


@pytest.mark.parametrize('name', ['../escape.txt', '/absolute.txt', 'C:/absolute.txt', '..\\escape.txt'])
def test_zip_unsafe_paths_are_flagged_without_creating_files(tmp_path, name):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr(name, 'data')
    before = sorted(path.name for path in tmp_path.iterdir())
    report = audit_archive(archive)
    assert not report['complete'] and report['unsafe_paths'] == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_zip_directory_entries_are_audited_and_payload_bytes_are_included(tmp_path):
    archive = tmp_path / 'directories.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr('../escape/', b'')
        stream.writestr('package/python/', b'')
        compressed = sum(item.compress_size for item in stream.infolist())
    report = audit_archive(archive)
    assert not report['complete'] and report['unsafe_paths'] == 1
    assert report['files'] == 0 and report['directories'] == 2
    assert report['compressed_payload_bytes'] == compressed


@pytest.mark.parametrize('kind', ['missing', 'bad-zip', 'invalid-component'])
def test_cli_failure_is_nonzero_and_has_no_private_path(tmp_path, capsys, kind):
    private = tmp_path / 'private-name.zip'
    if kind == 'bad-zip':
        private.write_bytes(b'not a zip')
    args = ['--component', 'invalid'] if kind == 'invalid-component' else ['--archive', str(private)]
    assert main(args) == 2
    output = json.loads(capsys.readouterr().out)
    assert not output['complete'] and 'private-name' not in json.dumps(output)

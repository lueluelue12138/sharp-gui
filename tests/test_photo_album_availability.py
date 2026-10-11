import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.app_factory import create_app
from backend.services import photo_gallery


@pytest.fixture
def indexed_album(config_file, workspace, monkeypatch):
    monkeypatch.setattr(photo_gallery, 'album_index_cache', {})
    monkeypatch.setattr(photo_gallery, 'album_snapshot_cache', {})
    root = workspace / 'removable-album'
    root.mkdir()
    Image.new('RGB', (8, 8), 'red').save(root / 'photo.jpg')
    album = {'id': 'offline-album', 'name': 'Removable album', 'path': str(root), 'enabled': True}
    config = json.loads(config_file.read_text(encoding='utf-8'))
    config['photo_gallery_roots'] = [album]
    config_file.write_text(json.dumps(config), encoding='utf-8')
    app = create_app()
    app.config['TESTING'] = True
    paths = app.config['PATH_CONTEXT']
    media, status, _ = photo_gallery.scan_photo_album(paths, album)
    assert status == 'idle'
    return app, paths, album, root, media[0]['id']


def test_missing_indexed_album_keeps_record_but_cannot_browse_or_upload(indexed_album, config_file):
    app, paths, album, root, media_id = indexed_album
    client = app.test_client()
    page = client.get(f"/api/photo-albums/{album['id']}/photos").get_json()
    index_path = photo_gallery.get_album_index_path(paths, album['id'])
    index_before = Path(index_path).read_bytes()
    catalog_before = Path(paths.photo_catalog_file).read_bytes()
    config_before = config_file.read_bytes()
    moved = root.with_name('moved-album')
    root.rename(moved)

    response = client.get('/api/photo-albums')
    assert response.status_code == 200
    summary = response.get_json()['albums'][1]
    assert summary['id'] == album['id']
    assert summary['available'] is False
    assert summary['code'] == 'photo_album_path_missing'
    assert summary['photo_count'] == 1
    assert summary['cover_thumb_url'] is None
    offline = client.get(f"/api/photo-albums/{album['id']}/photos?snapshot={page['snapshot']}").get_json()
    assert offline['items'] == []
    assert offline['next_cursor'] is None
    assert offline['available'] is False
    assert offline['code'] == 'photo_album_path_missing'
    assert client.get(f'/api/photo-original/{media_id}').status_code == 404
    assert client.get(f'/api/photo-thumbnail/{media_id}').status_code == 404
    upload, status = photo_gallery.upload_photos_to_album(paths, album['id'], [])
    assert status == 400
    assert upload['code'] == 'photo_album_path_missing'
    scan = client.post(f"/api/photo-albums/{album['id']}/scan").get_json()
    assert scan['success'] is False
    assert scan['code'] == 'photo_album_path_missing'
    assert Path(index_path).read_bytes() == index_before
    assert Path(paths.photo_catalog_file).read_bytes() == catalog_before
    assert config_file.read_bytes() == config_before

    moved.rename(root)
    assert client.get('/api/photo-albums').get_json()['albums'][1]['available'] is True
    recovered = client.get(f"/api/photo-albums/{album['id']}/photos").get_json()
    assert [item['id'] for item in recovered['items']] == [media_id]


def test_restart_with_offline_album_still_starts_application(indexed_album):
    _, _, album, root, _ = indexed_album
    root.rename(root.with_name('disconnected-album'))
    restarted = create_app()
    manager = restarted.config['TASK_MANAGER']
    try:
        manager.start_workers()
        client = restarted.test_client()
        assert client.get('/').status_code == 200
        assert client.get('/api/settings').status_code == 200
        assert client.get('/api/tasks').status_code == 200
        assert client.get('/api/model-assets').status_code == 200
        summary = client.get('/api/photo-albums').get_json()['albums'][1]
        assert summary['id'] == album['id']
        assert summary['available'] is False
    finally:
        manager.release_workspace_lock()


@pytest.mark.parametrize('path', ['Z:/offline/albums', '/Volumes/Offline/albums', '/media/user/Offline/albums'])
def test_missing_legacy_paths_and_realpath_errors_do_not_break_boot(config_file, workspace, monkeypatch, path):
    config = json.loads(config_file.read_text(encoding='utf-8'))
    config['photo_gallery_roots'] = [path]
    config_file.write_text(json.dumps(config), encoding='utf-8')
    original_realpath = os.path.realpath
    original_stat = os.stat
    absolute_path = os.path.abspath(path)

    def offline_realpath(candidate, *args, **kwargs):
        if os.fspath(candidate) == absolute_path:
            raise OSError('Disconnected volume')
        return original_realpath(candidate, *args, **kwargs)

    def offline_stat(candidate, *args, **kwargs):
        if os.fspath(candidate) == absolute_path:
            raise FileNotFoundError('Disconnected volume')
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(os.path, 'realpath', offline_realpath)
    monkeypatch.setattr(os, 'stat', offline_stat)
    app = create_app()
    response = app.test_client().get('/api/photo-albums')
    assert response.status_code == 200
    assert response.get_json()['albums'][1]['available'] is False
    assert response.get_json()['albums'][1]['code'] == 'photo_album_path_missing'


@pytest.mark.parametrize('failure', [PermissionError('Denied'), OSError('Device not ready')])
def test_unreadable_album_is_a_local_error_and_preserves_index(indexed_album, monkeypatch, failure):
    app, paths, album, root, _ = indexed_album
    original_scandir = os.scandir

    def unreadable_scandir(candidate):
        if os.fspath(candidate) == str(root):
            raise failure
        return original_scandir(candidate)

    monkeypatch.setattr(os, 'scandir', unreadable_scandir)
    expected_code = 'photo_album_permission_denied' if isinstance(failure, PermissionError) else 'photo_album_unavailable'
    client = app.test_client()
    assert client.get('/api/photo-albums').get_json()['albums'][1]['code'] == expected_code
    assert client.get(f"/api/photo-albums/{album['id']}/photos").get_json()['items'] == []
    assert len(photo_gallery.load_album_index(paths, album['id'])['media']) == 1


@pytest.mark.parametrize('catalog_missing', [False, True])
def test_unmounted_directory_still_exists_but_storage_changed(indexed_album, monkeypatch, catalog_missing):
    app, paths, album, root, _ = indexed_album
    if catalog_missing:
        photo_gallery.save_catalog(paths, {'albums': {}})
    original_stat = os.stat
    root_stat = original_stat(root)

    def changed_device(candidate, *args, **kwargs):
        if os.fspath(candidate) == str(root):
            return SimpleNamespace(st_mode=root_stat.st_mode, st_dev=root_stat.st_dev + 1)
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(os, 'stat', changed_device)
    client = app.test_client()
    assert client.get('/api/photo-albums').get_json()['albums'][1]['code'] == 'photo_album_storage_changed'
    assert client.get(f"/api/photo-albums/{album['id']}/photos").get_json()['available'] is False
    assert len(photo_gallery.load_album_index(paths, album['id'])['media']) == 1


def test_disconnect_during_scan_does_not_replace_good_index_with_empty(indexed_album, monkeypatch):
    _, paths, album, root, _ = indexed_album
    index_path = photo_gallery.get_album_index_path(paths, album['id'])
    before = Path(index_path).read_bytes()

    def disconnect_during_walk(_album):
        root.rename(root.with_name('removed-during-scan'))
        return iter(())

    monkeypatch.setattr(photo_gallery, 'iter_album_photo_paths', disconnect_during_walk)
    _, status, _ = photo_gallery.scan_photo_album(paths, album)
    assert status == 'error'
    assert Path(index_path).read_bytes() == before


def test_directory_replaced_by_file_is_unavailable(indexed_album):
    app, _, _, root, _ = indexed_album
    root.rename(root.with_name('moved-away'))
    root.write_text('Not an album', encoding='utf-8')
    summary = app.test_client().get('/api/photo-albums').get_json()['albums'][1]
    assert summary['code'] == 'photo_album_path_missing'


def test_all_media_moved_out_of_existing_directory_is_unavailable(indexed_album):
    app, paths, album, root, _ = indexed_album
    (root / 'photo.jpg').rename(root.parent / 'moved-photo.jpg')
    assert root.is_dir()
    client = app.test_client()
    summary = client.get('/api/photo-albums').get_json()['albums'][1]
    assert summary['available'] is False
    assert summary['code'] == 'photo_album_media_missing'
    assert summary['photo_count'] == 1
    assert client.get(f"/api/photo-albums/{album['id']}/photos").get_json()['items'] == []
    assert len(photo_gallery.load_album_index(paths, album['id'])['media']) == 1
    # 显式扫描后用户确认当前空目录，正常显示真正的空相册。
    assert client.post(f"/api/photo-albums/{album['id']}/scan").get_json()['success'] is True
    summary = client.get('/api/photo-albums').get_json()['albums'][1]
    assert summary['available'] is True
    assert summary['photo_count'] == 0

import base64
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from plyfile import PlyData, PlyElement

from backend.services import model_assets, model_editor, model_gallery, model_sources, photo_gallery


@pytest.fixture
def sources(app, config_file, workspace, monkeypatch):
    monkeypatch.setattr(model_sources, '_REPAIRS', {})
    monkeypatch.setattr(model_sources, '_SNAPSHOTS', {})
    monkeypatch.setattr(model_sources, '_AVAILABILITY', {})
    monkeypatch.setattr(model_sources, 'schedule_repair', lambda paths: None)
    monkeypatch.setattr(photo_gallery, 'album_index_cache', {})
    monkeypatch.setattr(photo_gallery, 'album_snapshot_cache', {})
    root = workspace / 'album'
    root.mkdir()
    Image.new('RGB', (12, 8), 'red').save(root / 'photo.png')
    album = {'id': 'source-test', 'name': 'Source test', 'path': str(root), 'enabled': True}
    config = json.loads(config_file.read_text(encoding='utf-8'))
    photo_gallery.set_photo_gallery_roots_for_config(config, [album])
    config_file.write_text(json.dumps(config), encoding='utf-8')
    paths = app.config['PATH_CONTEXT']
    media, status, _ = photo_gallery.scan_photo_album(paths, album)
    assert status == 'idle'
    return paths, album, root, media[0]


def publish(paths, source, model_id, *, meta=None, legacy=False, video=False):
    vertices = np.zeros(4, dtype=model_editor.gaussian_dtype(0))
    vertices['rot_0'], vertices['opacity'] = 1, 2
    vertices['x'] = np.arange(4)
    for axis in range(3):
        vertices[f'scale_{axis}'] = -2
    path = Path(paths.output_folder) / (model_id + '.ply')
    path.parent.mkdir(exist_ok=True)
    PlyData([PlyElement.describe(vertices, 'vertex')]).write(path)
    if not video:
        original = Path(paths.input_folder) / (model_id + '.png')
        original.parent.mkdir(exist_ok=True)
        shutil.copy2(source, original)
    metadata = {'source_media_type': 'video' if video else 'image', 'source_name': source.name}
    if video:
        metadata['source_video_path'] = str(source)
    if meta:
        metadata.update({'source_media_id': meta['id'], 'source_media_version': model_sources.media_version(meta)})
    if not legacy:
        metadata['source_identity'] = model_sources.capture_source(str(source), source.name, metadata['source_media_type'], meta)
    model_gallery.write_model_metadata(paths, model_id, metadata)
    model_assets.sync_generated_model_asset(paths, model_id)
    return metadata


def test_repeated_sources_formats_defaults_and_deletion(sources, client):
    paths, _, root, meta = sources
    first = publish(paths, root / 'photo.png', 'first', meta=meta)
    publish(paths, root / 'photo.png', 'second', meta=meta)
    Path(paths.output_folder, 'first.spz').write_bytes(b'companion-format')
    model_assets.sync_generated_model_asset(paths, 'first')
    response = client.get('/api/photo-models/' + meta['id']).get_json()
    assert response['model_count'] == 2
    assert response['source_id'] == first['source_identity']['id']
    assert response['default_model_id'] is None
    endpoint = '/api/model-sources/' + response['source_id'] + '/default'
    assert client.post(endpoint, json={'asset_id': 'first'}).status_code == 200
    assert client.get('/api/photo-models/' + meta['id']).get_json()['default_model_id'] == 'first'
    # Unrelated catalog mutations must preserve the saved default.
    model_assets.sync_generated_model_asset(paths, 'second')
    assert model_assets.read_asset_index(paths)['source_defaults'][response['source_id']] == 'first'
    assert client.post(endpoint, json={'asset_id': 'foreign'}).status_code == 400
    assert model_assets.delete_model_asset(paths, 'first')
    assert client.get('/api/photo-models/' + meta['id']).get_json()['default_model_id'] is None
    assert model_assets.delete_model_asset(paths, 'second')
    assert client.get('/api/photo-albums/model-sources/photos').get_json()['items'] == []
    assert (root / 'photo.png').is_file()


def test_gallery_conversion_records_source_and_live_task(sources, app, client):
    paths, _, root, meta = sources
    result = client.post('/api/photo-conversions', json={'photo_ids': [meta['id']]}).get_json()
    task = result['tasks'][0]
    assert result['failed'] == []
    assert task['source_media_id'] == meta['id']
    assert task['source_id'] == model_sources.capture_source(str(root / 'photo.png'), 'photo.png', 'image')['id']
    stored = app.config['TASK_MANAGER'].task_status[task['id']]
    sidecar = model_gallery.read_model_metadata(paths, stored['model_id'])
    assert sidecar['source_identity']['id'] == task['source_id']
    assert 'input_path' not in task


def test_content_match_and_same_path_replacement(sources):
    paths, album, root, meta = sources
    publish(paths, root / 'photo.png', 'uploaded', legacy=True)
    # Recover an uploaded original by contents, despite a different internal name.
    assert model_sources.repair_sources(paths) is False
    assert model_sources.query_links(paths, [meta['id']])['links'][meta['id']]['model_count'] == 1
    Image.new('RGB', (12, 8), 'blue').save(root / 'photo.png')
    stat = os.stat(root / 'photo.png')
    os.utime(root / 'photo.png', (stat.st_atime, stat.st_mtime + 5))
    media, _, _ = photo_gallery.scan_photo_album(paths, album)
    assert 'model_source_hash' not in media[0]
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 0
    model_sources.repair_sources(paths)
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 0


def test_same_name_different_contents_are_distinct(sources):
    paths, _, root, meta = sources
    first = publish(paths, root / 'photo.png', 'red', meta=meta)
    other = root / 'other'
    other.mkdir()
    Image.new('RGB', (12, 8), 'blue').save(other / 'photo.png')
    second = publish(paths, other / 'photo.png', 'blue')
    assert first['source_identity']['id'] != second['source_identity']['id']
    page = model_sources.list_source_media(paths, 'name_asc', 0, 60, 'image')
    assert page['total'] == 2
    assert all(item['name'] == 'photo.png' for item in page['items'])
    assert all(item['model_link']['model_count'] == 1 for item in page['items'])


def test_editor_copy_and_overwrite_keep_source_after_parent_deleted(sources):
    paths, _, root, meta = sources
    identity = publish(paths, root / 'photo.png', 'parent', meta=meta)['source_identity']
    descriptor = model_editor.get_editor_descriptor(paths, 'parent')
    payload = {'fingerprint': descriptor['fingerprint'], 'point_count': 4,
               'deleted_mask': base64.b64encode(b'\x00').decode(),
               'camera': {'position': [0, 0, 8], 'target': [0, 0, 0], 'up': [0, 1, 0],
                          'fov_y_degrees': 50, 'aspect': 1.5},
               'matrix': np.eye(4).reshape(-1, order='F').tolist(), 'name': 'Edited'}
    copy = model_editor.save_edited_copy(paths, 'parent', payload)
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 2
    assert model_gallery.read_model_metadata(paths, copy['id'])['source_identity'] == identity
    descriptor = model_editor.get_editor_descriptor(paths, copy['id'])
    payload['fingerprint'] = descriptor['fingerprint']
    model_editor.save_edited_model(paths, copy['id'], {**payload, 'save_mode': 'overwrite'})
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 2
    model_assets.delete_model_asset(paths, 'parent')
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 1
    media_id = 'model-sources_' + identity['id']
    assert model_sources.resolve_source_media(paths, media_id)[2]['media_type'] == 'image'


def test_offline_album_keeps_cached_image_and_model_entry(sources, client):
    paths, _, root, meta = sources
    metadata = publish(paths, root / 'photo.png', 'cached', meta=meta)
    root.rename(root.with_name('offline'))
    source_id = 'model-sources_' + metadata['source_identity']['id']
    assert client.get('/api/photo-original/' + source_id).status_code == 200
    assert client.get('/api/photo-models/' + source_id).get_json()['model_count'] == 1
    assert client.get('/api/photo-models/' + meta['id']).get_json()['model_count'] == 1


def test_system_thumbnail_reuses_album_cache_without_generation(sources, client, monkeypatch):
    paths, album, root, meta = sources
    Image.new('RGB', (1200, 800), 'red').save(root / 'photo.png')
    media, _, _ = photo_gallery.scan_photo_album(paths, album)
    meta = media[0]
    metadata = publish(paths, root / 'photo.png', 'cached-cover', meta=meta)
    model_gallery.generate_thumbnail(paths, str(root / 'photo.png'), 'cached-cover.png')
    model_assets.sync_generated_model_asset(paths, 'cached-cover')
    cached = Path(photo_gallery.ensure_photo_thumbnail(paths, meta['id']))
    original_bytes, original_mtime = cached.read_bytes(), cached.stat().st_mtime_ns
    assert Image.open(cached).width == 480
    assert Image.open(model_gallery.get_thumbnail_path(paths, 'cached-cover')).width == 200

    def forbidden(*args, **kwargs):
        raise AssertionError('Model Sources must reuse cache without reading or generating originals')

    monkeypatch.setattr(photo_gallery, 'ensure_photo_thumbnail', forbidden)
    monkeypatch.setattr(photo_gallery, 'resolve_media_path', forbidden)
    monkeypatch.setattr(model_sources, 'capture_source', forbidden)
    root.rename(root.with_name('detached'))
    page = client.get('/api/photo-albums/model-sources/photos').get_json()
    response = client.get(page['items'][0]['thumb_url'])
    assert response.status_code == 200
    assert response.data == original_bytes
    response.close()
    assert cached.stat().st_mtime_ns == original_mtime
    # Clearing just the thumbnail falls back to the existing model cover, without recreation.
    cached.unlink()
    response = client.get(page['items'][0]['thumb_url'])
    assert response.status_code == 302
    assert response.location == '/api/thumbnail/cached-cover'
    assert response.cache_control.no_store
    assert not cached.exists()
    assert metadata['source_identity']['id'] in page['items'][0]['thumb_url']


def test_system_video_poster_reuses_verified_cache_and_rejects_replaced_source(sources, client, monkeypatch):
    paths, album, root, _ = sources
    video = root / 'video.mp4'
    video.write_bytes(b'original-video')
    monkeypatch.setattr(photo_gallery, 'probe_video_metadata', lambda *args, **kwargs: {})
    media, _, _ = photo_gallery.scan_photo_album(paths, album)
    meta = next(item for item in media if item['media_type'] == 'video')
    metadata = publish(paths, video, 'cached-video', meta=meta, video=True)
    model_cover = Path(model_gallery.get_thumbnail_path(paths, 'cached-video'))
    model_cover.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (200, 120), 'red').save(model_cover)
    model_assets.sync_generated_model_asset(paths, 'cached-video')
    poster = Path(paths.video_poster_folder) / photo_gallery.get_video_poster_filename(meta['id'], meta)
    poster.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (640, 360), 'red').save(poster)
    original_bytes = poster.read_bytes()
    monkeypatch.setattr(photo_gallery, 'ensure_video_poster', lambda *args: pytest.fail('Unexpected poster generation'))
    url = '/api/video-poster/model-sources_' + metadata['source_identity']['id']
    response = client.get(url)
    assert response.status_code == 200
    assert response.data == original_bytes
    response.close()
    video.write_bytes(b'replaced-video-with-other-content')
    photo_gallery.scan_photo_album(paths, album)
    response = client.get(url)
    assert response.status_code == 302
    assert response.location == '/api/thumbnail/cached-video'


def test_historical_content_match_reuses_album_thumbnail_without_explicit_reference(sources, client):
    paths, _, root, meta = sources
    publish(paths, root / 'photo.png', 'uploaded-no-reference', legacy=True)
    assert model_sources.repair_sources(paths) is False
    cached = Path(photo_gallery.ensure_photo_thumbnail(paths, meta['id']))
    page = client.get('/api/photo-albums/model-sources/photos').get_json()
    response = client.get(page['items'][0]['thumb_url'])
    assert response.status_code == 200
    assert response.data == cached.read_bytes()
    response.close()


@pytest.mark.parametrize('stored_type', [None, ''])
def test_historical_image_with_empty_type_keeps_cover_counts_and_original(sources, client, monkeypatch, stored_type):
    paths, album, root, meta = sources
    metadata = publish(paths, root / 'photo.png', 'historical-photo', meta=meta)
    metadata['source_media_type'] = stored_type
    metadata['source_identity']['media_type'] = stored_type
    model_gallery.write_model_metadata(paths, 'historical-photo', metadata)
    model_gallery.generate_thumbnail(paths, str(root / 'photo.png'), 'historical-photo.png')
    model_assets.sync_generated_model_asset(paths, 'historical-photo')
    cover = Path(model_gallery.get_thumbnail_path(paths, 'historical-photo')).read_bytes()
    cached = Path(photo_gallery.ensure_photo_thumbnail(paths, meta['id']))
    assert client.delete('/api/photo-albums/' + album['id']).status_code == 200
    assert not cached.exists()

    def forbidden(*args, **kwargs):
        raise AssertionError('Missing album cache must not trigger thumbnail generation')

    monkeypatch.setattr(photo_gallery, 'ensure_photo_thumbnail', forbidden)
    monkeypatch.setattr(model_gallery, 'generate_thumbnail', forbidden)
    page = client.get('/api/photo-albums/model-sources/photos').get_json()
    assert page['media_counts']['image'] == page['media_counts']['all'] == 1
    assert page['items'][0]['media_type'] == 'image'
    photos = client.get('/api/photo-albums/model-sources/photos?type=image').get_json()
    assert photos['total'] == 1
    assert client.get('/api/photo-albums/model-sources/photos?type=video').get_json()['total'] == 0
    response = client.get(page['items'][0]['thumb_url'], follow_redirects=True)
    assert response.status_code == 200
    assert response.data == cover
    response.close()
    assert client.get(page['items'][0]['preview_url']).status_code == 200
    assert model_gallery.read_model_metadata(paths, 'historical-photo')['source_identity']['id'] == metadata['source_identity']['id']


def test_legacy_source_repair_records_image_type_and_dimensions(sources):
    paths, _, root, _ = sources
    publish(paths, root / 'photo.png', 'legacy-no-type', legacy=True)
    metadata = model_gallery.read_model_metadata(paths, 'legacy-no-type')
    metadata.pop('source_media_type')
    model_gallery.write_model_metadata(paths, 'legacy-no-type', metadata)
    model_assets.sync_generated_model_asset(paths, 'legacy-no-type')
    model_sources.repair_sources(paths)
    identity = model_gallery.read_model_metadata(paths, 'legacy-no-type')['source_identity']
    assert identity['media_type'] == 'image'
    assert (identity['width'], identity['height']) == (12, 8)


def test_source_repair_keeps_model_dates_and_default_is_newest_created(sources, client):
    paths, _, root, meta = sources
    publish(paths, root / 'photo.png', 'older', meta=meta, legacy=True)
    publish(paths, root / 'photo.png', 'newer', meta=meta, legacy=True)
    index = model_assets.read_asset_index(paths)
    for asset_id, created in [('older', '2025-01-01T00:00:00+00:00'), ('newer', '2026-01-01T00:00:00+00:00')]:
        index.setdefault('assets', {}).setdefault(asset_id, {})['created_at'] = created
    model_assets.write_asset_index(paths, index)
    for asset_id in ('older', 'newer'):
        model_assets.sync_generated_model_asset(paths, asset_id)
    before = model_assets.get_model_asset(paths, 'older')
    sidecar = Path(model_gallery.get_model_metadata_path(paths, 'older'))
    previous_mtime = sidecar.stat().st_mtime_ns
    previous_date = model_gallery.read_model_metadata(paths, 'older')['updated_at']
    model_sources.repair_sources(paths)
    after = model_assets.get_model_asset(paths, 'older')
    assert after['source_identity']['id']
    assert after['updated_at'] == before['updated_at']
    assert after['created_at'] == before['created_at']
    assert sidecar.stat().st_mtime_ns == previous_mtime
    assert model_gallery.read_model_metadata(paths, 'older')['updated_at'] == previous_date
    response = client.get('/api/model-assets').get_json()
    assert response['sort'] == 'created_desc'
    assert [asset['id'] for asset in response['items']] == ['newer', 'older']


def test_virtual_video_range_offline_and_regeneration_resolution(sources, client):
    paths, _, _, _ = sources
    source = Path(model_gallery.get_video_uploads_folder(paths)) / 'one' / 'video.mp4'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'fake-video-for-range')
    metadata = publish(paths, source, 'video-model', video=True)
    media_id = 'model-sources_' + metadata['source_identity']['id']
    response = client.get('/api/video-original/' + media_id, headers={'Range': 'bytes=0-3'})
    assert response.status_code == 206
    assert response.data == b'fake'
    response.close()
    resolved = photo_gallery.resolve_media_path(paths, media_id, expected_type='video')
    assert resolved[2]['source_media_id'] is None
    source.rename(source.with_suffix('.offline'))
    assert client.get('/api/video-original/' + media_id).status_code == 404
    page = client.get('/api/photo-albums/model-sources/photos?type=video').get_json()
    assert page['items'][0]['source_available'] is False
    assert page['items'][0]['model_link']['model_count'] == 1
    assert client.get('/api/photo-models/' + media_id).get_json()['source_available'] is False
    source.with_suffix('.offline').rename(source)
    response = client.get('/api/video-original/' + media_id)
    assert response.status_code == 200
    response.close()
    assert client.get('/api/photo-models/' + media_id).get_json()['source_available'] is True


def test_warm_queries_do_not_hash_or_scan_and_snapshots_are_stable(sources, monkeypatch):
    paths, _, root, meta = sources
    publish(paths, root / 'photo.png', 'one', meta=meta)
    first = model_sources.list_source_media(paths, 'name_asc', 0, 1, 'all')
    other = root / 'other.png'
    Image.new('RGB', (8, 8), 'blue').save(other)
    publish(paths, other, 'two')
    def forbidden(*args, **kwargs):
        raise AssertionError('Warm source queries must not scan or hash media')
    monkeypatch.setattr(model_sources, 'capture_source', forbidden)
    monkeypatch.setattr(os, 'walk', forbidden)
    assert model_sources.query_models(paths, meta['id'])['model_count'] == 1
    assert model_sources.list_source_media(paths, 'name_asc', 0, 60, 'all', first['snapshot'])['total'] == 1
    assert model_sources.list_source_media(paths, 'name_asc', 0, 60, 'all')['total'] == 2


def test_system_album_keeps_standard_filters_and_created_sort(sources, client):
    paths, _, root, _ = sources
    publish(paths, root / 'photo.png', 'image')
    video = Path(model_gallery.get_video_uploads_folder(paths)) / 'sorted' / 'video.mp4'
    video.parent.mkdir(parents=True)
    video.write_bytes(b'sorted-video')
    metadata = publish(paths, video, 'video', video=True)
    # File creation and modification times may differ after copying media.
    metadata['source_identity'].update({'ctime': 1, 'mtime': 9999999999})
    model_gallery.write_model_metadata(paths, 'video', metadata)
    model_assets.sync_generated_model_asset(paths, 'video')
    endpoint = '/api/photo-albums/model-sources/photos'
    assert client.get(endpoint + '?type=photos').get_json()['total'] == 1
    assert client.get(endpoint + '?type=videos').get_json()['items'][0]['name'] == 'video.mp4'
    assert client.get(endpoint + '?sort=ctime_asc').get_json()['items'][0]['name'] == 'video.mp4'
    assert client.get(endpoint + '?sort=ctime_desc').get_json()['items'][0]['name'] == 'photo.png'


def test_source_preference_permissions_and_input_validation(sources, client):
    paths, _, root, meta = sources
    metadata = publish(paths, root / 'photo.png', 'private', meta=meta)
    endpoint = '/api/model-sources/' + metadata['source_identity']['id'] + '/default'
    assert client.post(endpoint, json={'asset_id': 'private'}, environ_overrides={'REMOTE_ADDR': '192.168.1.50'}).status_code == 403
    assert client.post('/api/photo-models', json={'media_ids': 'path'}).status_code == 400
    assert client.post('/api/photo-models', json={'media_ids': ['id'] * 201}).status_code == 400
    assert client.post('/api/photo-models', json=['invalid']).status_code == 400
    assert client.post(endpoint, json=['invalid']).status_code == 400
    response = client.get('/api/photo-models/' + meta['id'])
    assert str(paths.workspace_folder).encode() not in response.data


def test_historical_source_retries_after_disk_returns(sources, monkeypatch):
    paths, _, _, _ = sources
    source = Path(model_gallery.get_video_uploads_folder(paths)) / 'retry' / 'video.mp4'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'retry-original')
    publish(paths, source, 'offline-video', video=True, legacy=True)
    source.rename(source.with_suffix('.detached'))
    assert model_sources.repair_sources(paths) is False
    assert not model_gallery.read_model_metadata(paths, 'offline-video').get('source_identity')
    source.with_suffix('.detached').rename(source)
    # Background repair has a bounded retry interval, even without a catalog mutation.
    now = model_sources.time.monotonic()
    monkeypatch.setattr(model_sources.time, 'monotonic', lambda: now + model_sources.REPAIR_RETRY_SECONDS + 1)
    assert model_sources.repair_sources(paths) is False
    assert model_gallery.read_model_metadata(paths, 'offline-video')['source_identity']['id']


def test_source_queries_report_catalog_errors_as_json(sources, client, monkeypatch):
    def corrupt_catalog(*args, **kwargs):
        raise model_assets.ModelAssetServiceError('Catalog unavailable', code='model_asset_index_invalid', status_code=503)
    monkeypatch.setattr(model_assets, 'get_catalog_items', corrupt_catalog)
    response = client.post('/api/photo-models', json={'media_ids': []})
    assert response.status_code == 503
    assert response.get_json()['code'] == 'model_asset_index_invalid'


def test_guessed_legacy_video_name_does_not_create_verified_source(sources):
    paths, _, root, _ = sources
    publish(paths, root / 'photo.png', 'guessed')
    metadata = {'source_media_type': 'video', 'source_media_id': 'random_id', 'recovered_from': 'gallery-video-stem'}
    model_gallery.write_model_metadata(paths, 'guessed', metadata)
    model_assets.sync_generated_model_asset(paths, 'guessed')
    assert model_sources.source_groups(paths)[0] == {}

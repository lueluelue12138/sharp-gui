import base64
import hashlib
import gzip
import struct
from pathlib import Path

import numpy as np
import pytest
from plyfile import PlyData, PlyElement

from backend.paths import build_path_context
from backend.services import model_assets, model_convert, model_editor, model_gallery


def make_model(paths, degree=3, big_endian=False):
    import os
    os.makedirs(paths.output_folder, exist_ok=True)
    vertices = np.zeros(9, dtype=model_editor.gaussian_dtype(degree))
    vertices['x'] = np.arange(9)
    vertices['y'] = 0.3
    vertices['z'] = 2
    vertices['rot_0'] = 1
    vertices['opacity'] = 2
    for axis in range(3):
        vertices[f'scale_{axis}'] = -2
        vertices[f'f_dc_{axis}'] = axis * 0.2
    for index in range(3 * ((degree+1)**2-1)):
        vertices[f'f_rest_{index}'] = (index - 20) * 0.01
    path = os.path.join(paths.output_folder, 'source.ply')
    PlyData([PlyElement.describe(vertices, 'vertex')], byte_order='>' if big_endian else '<').write(path)
    model_assets.sync_generated_model_asset(paths, 'source')
    return path, vertices


def edit_payload(paths):
    descriptor = model_editor.get_editor_descriptor(paths, 'source')
    return {'fingerprint': descriptor['fingerprint'], 'point_count': descriptor['point_count'],
            'deleted_mask': base64.b64encode(bytes([0b00000101, 0])).decode(),
            'matrix': np.eye(4).reshape(-1, order='F').tolist(),
            'camera': {'position': [0, 0, 8], 'target': [0, 0, 0], 'up': [0, 1, 0],
                       'fov_y_degrees': 50, 'aspect': 1.5}, 'name': 'Cropped camera'}


@pytest.mark.parametrize('big_endian', [False, True])
def test_save_filters_vertices_preserves_sh_and_never_changes_source(workspace, big_endian):
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, original = make_model(paths, big_endian=big_endian)
    fingerprint = hashlib.sha256(open(source, 'rb').read()).hexdigest()
    result = model_editor.save_edited_copy(paths, 'source', edit_payload(paths))
    output = model_assets.resolve_download_file(paths, result['id'], 'ply')[0]
    vertices = PlyData.read(output)['vertex'].data
    np.testing.assert_allclose(vertices['x'], original['x'][[1, 3, 4, 5, 6, 7, 8]])
    np.testing.assert_allclose(vertices['f_rest_44'], original['f_rest_44'][[1, 3, 4, 5, 6, 7, 8]])
    assert hashlib.sha256(open(source, 'rb').read()).hexdigest() == fingerprint
    assert result['point_count'] == 7
    assert result['viewer_transform'] is None
    assert set(result['formats']) == {'ply', 'spz'}
    metadata = model_gallery.read_model_metadata(paths, result['id'])
    assert metadata['viewer_camera'] == edit_payload(paths)['camera']
    assert metadata['viewer_transform'] is None


def test_editor_does_not_infer_origin_from_camera_or_private_metadata(app, client):
    paths = app.config['PATH_CONTEXT']
    source, _ = make_model(paths)
    before = Path(source).read_bytes()
    camera = edit_payload(paths)['camera']
    camera['target'] = [-.524963886, -.014037667, -2.288947147]
    for editing in (None, {'origin_rebased': True}, {'origin_rebased': False}):
        model_gallery.write_model_metadata(paths, 'source', {'viewer_camera': camera, 'editing': editing})
        descriptor = client.get('/api/model-assets/source/editor').get_json()
        assert 'initial_origin' not in descriptor
        assert 'origin_rebased' not in descriptor
        assert descriptor['point_count'] == 9
        assert Path(source).read_bytes() == before


def test_calibration_is_baked_in_ply_and_survives_import_without_sidecar(workspace):
    from werkzeug.datastructures import FileStorage
    from scipy.spatial.transform import Rotation

    paths = build_path_context({'workspace_folder': str(workspace)})
    source, original = make_model(paths)
    source_bytes = Path(source).read_bytes()
    # 独立按坐标基底计算：视频预览 X=-90°，普通 PLY 预览 X=180°，倍率均为 2。
    video_basis = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    ply_basis = np.diag([1, -1, -1])
    angle = .37
    calibration = np.array([[np.cos(angle), -np.sin(angle), 0],
                            [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    raw_origin = np.array([4., .3, 2.])
    origin = 2 * video_basis @ raw_origin
    file_rotation = ply_basis.T @ calibration @ video_basis
    file_matrix = np.eye(4)
    file_matrix[:3, :3] = file_rotation
    file_matrix[:3, 3] = -.5 * ply_basis.T @ calibration @ origin
    payload = {**edit_payload(paths), 'matrix': file_matrix.reshape(-1, order='F').tolist()}
    edited = model_editor.save_edited_model(paths, 'source', payload)
    output = model_assets.resolve_download_file(paths, edited['id'], 'ply')[0]
    # plyfile 独立读取实际文件，不经过本项目编辑源解码或任何元数据修正。
    saved = PlyData.read(output, mmap=False)['vertex'].data
    kept = original[[1, 3, 4, 5, 6, 7, 8]]
    xyz = np.column_stack([kept[key] for key in ('x', 'y', 'z')])
    expected = (xyz - raw_origin) @ video_basis.T @ calibration.T @ ply_basis
    actual = np.column_stack([saved[key] for key in ('x', 'y', 'z')])
    np.testing.assert_allclose(actual, expected, atol=2e-6)
    np.testing.assert_allclose(actual[2], 0, atol=2e-6)
    for key in ('scale_0', 'scale_1', 'scale_2'):
        np.testing.assert_array_equal(saved[key], kept[key])
    quaternions = np.column_stack([saved[key] for key in ('rot_1', 'rot_2', 'rot_3', 'rot_0')])
    np.testing.assert_allclose(Rotation.from_quat(quaternions).as_matrix(),
                               np.repeat(file_rotation[None], len(saved), axis=0), atol=1e-6)
    # 独立的一阶 SH 基检查方向颜色；更高阶由已有 SH0～SH3 测试覆盖。
    direction = np.array([.3, .4, np.sqrt(.75)])
    def first_band(value):
        return .4886025119029199 * np.array([-value[1], value[2], -value[0]])
    for channel in range(3):
        old = np.column_stack([kept[f'f_rest_{channel * 15 + i}'] for i in range(3)])
        new = np.column_stack([saved[f'f_rest_{channel * 15 + i}'] for i in range(3)])
        np.testing.assert_allclose(new @ first_band(direction),
                                   old @ first_band(file_rotation.T @ direction), atol=1e-7)
    with open(output, 'rb') as file:
        imported = model_assets.import_model_assets(paths, [FileStorage(stream=file, filename='Plain calibrated.ply')])['assets'][0]
    assert imported['viewer_transform'] is None
    assert imported['viewer_camera'] is None
    imported_path = model_assets.resolve_download_file(paths, imported['id'], 'ply')[0]
    assert Path(imported_path).read_bytes() == Path(output).read_bytes()
    assert Path(source).read_bytes() == source_bytes


def test_edited_video_copies_keep_metadata_playback_and_shared_source_until_last_delete(app, client):
    paths = app.config['PATH_CONTEXT']
    make_model(paths)
    uploads = Path(model_gallery.get_video_uploads_folder(paths)) / 'test-source'
    uploads.mkdir(parents=True)
    video = uploads / 'source.mp4'
    video.write_bytes(b'non-sensitive-test-video')
    model_gallery.write_model_metadata(paths, 'source', {
        'source_media_type': 'video', 'source_name': 'Original video.mp4',
        'source_video_path': str(video), 'source_mime_type': 'video/mp4',
        'generator': 'video_3dgs', 'quality': 'high', 'engine': 'brush',
        'reconstruction': {'geometry': {'registered_frames': 180}},
        'point_count': 9, 'bounding_box': [0, 0, 0, 8, 1, 2],
    })
    model_assets.sync_generated_model_asset(paths, 'source')
    model_assets.update_model_asset_profile(paths, 'source', {'tags': ['camera'], 'note': 'keep this note'})
    edited = client.post('/api/model-assets/source/editor', json=edit_payload(paths)).get_json()
    assert edited['source_media_type'] == 'video'
    assert edited['source_video_url']
    assert edited['tags'] == ['camera']
    assert edited['note'] == 'keep this note'
    metadata = model_gallery.read_model_metadata(paths, edited['id'])
    assert metadata['quality'] == 'high'
    assert metadata['reconstruction']['geometry']['registered_frames'] == 180
    assert metadata['point_count'] == 7
    assert 'bounding_box' not in metadata
    assert 'source_video_path' not in client.get(f"/api/model-assets/{edited['id']}").get_json()['metadata']
    assert client.get(edited['source_video_url'], headers={'Range': 'bytes=0-3'}).status_code == 206
    descriptor = model_editor.get_editor_descriptor(paths, edited['id'])
    payload = {**edit_payload(paths), 'fingerprint': descriptor['fingerprint'], 'point_count': 7,
               'deleted_mask': base64.b64encode(bytes([0])).decode()}
    second = model_editor.save_edited_copy(paths, edited['id'], payload)
    model_gallery.delete_gallery_item(paths, 'source')
    assert video.exists()
    assert client.get(edited['source_video_url']).status_code == 200
    model_gallery.delete_gallery_item(paths, edited['id'])
    assert video.exists()
    assert client.get(second['source_video_url']).status_code == 200
    model_gallery.delete_gallery_item(paths, second['id'])
    assert not video.exists()


def test_edited_image_model_keeps_original_preview_after_source_model_delete(app, client):
    from PIL import Image
    paths = app.config['PATH_CONTEXT']
    make_model(paths)
    Path(paths.input_folder).mkdir(parents=True, exist_ok=True)
    original = Path(paths.input_folder) / 'source.jpg'
    Image.new('RGB', (8, 8), 'blue').save(original)
    model_gallery.write_model_metadata(paths, 'source', {'source_media_type': 'image', 'source_name': 'Original.jpg'})
    model_assets.sync_generated_model_asset(paths, 'source')
    result = model_editor.save_edited_copy(paths, 'source', edit_payload(paths))
    copied = Path(paths.input_folder) / (result['id'] + '.jpg')
    assert copied.read_bytes() == original.read_bytes()
    assert result['image_url']
    model_gallery.delete_gallery_item(paths, 'source')
    assert client.get(result['image_url']).status_code == 200
    assert copied.exists()


def test_overwrite_keeps_id_source_profile_and_replaces_all_generated_variants(app, client):
    paths = app.config['PATH_CONTEXT']
    source, original = make_model(paths)
    model_convert.ply_to_spz(source)
    obsolete = Path(paths.output_folder) / 'source.rad'
    obsolete.write_bytes(b'old-render-variant')
    image = Path(paths.input_folder) / 'source.jpg'
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b'original-image-cache')
    model_gallery.write_model_metadata(paths, 'source', {
        'source_media_type': 'video', 'source_media_id': 'album-video', 'source_name': 'Original.mp4',
        'generator': 'video_3dgs', 'quality': 'high', 'reconstruction': {'frames': 180},
        'custom_source_info': {'keep': True}, 'bounding_box': [1, 2, 3],
    })
    model_assets.update_model_asset_profile(paths, 'source', {'display_name': 'Camera', 'tags': ['keep'], 'note': 'original note'})
    previous = model_assets.get_model_asset(paths, 'source')
    payload = {**edit_payload(paths), 'save_mode': 'overwrite', 'name': ''}
    payload['matrix'][12] = 1.5
    response = client.post('/api/model-assets/source/editor', json=payload)
    assert response.status_code == 200
    edited = response.get_json()
    assert edited['id'] == 'source'
    assert edited['created_at'] == previous['created_at']
    assert edited['name'] == 'Camera'
    assert edited['tags'] == ['keep'] and edited['note'] == 'original note'
    assert edited['point_count'] == 7 and set(edited['formats']) == {'ply', 'spz'}
    assert edited['default_open_url'] != previous['default_open_url']
    assert '?v=' in edited['default_open_url']
    assert client.get(edited['default_open_url']).status_code == 200
    assert edited['viewer_camera'] == payload['camera']
    assert edited['viewer_transform'] is None
    metadata = model_gallery.read_model_metadata(paths, 'source')
    assert metadata['id'] == 'source'
    assert metadata['source_media_id'] == 'album-video'
    assert metadata['custom_source_info'] == {'keep': True}
    assert metadata['reconstruction']['frames'] == 180
    assert 'bounding_box' not in metadata
    assert image.read_bytes() == b'original-image-cache'
    assert not obsolete.exists()
    vertices = PlyData.read(source)['vertex'].data
    np.testing.assert_allclose(vertices['x'], original['x'][[1, 3, 4, 5, 6, 7, 8]] + 1.5)
    assert len(model_editor.decode_vertices(str(Path(source).with_suffix('.spz')), 'spz')) == 7
    assert client.get('/api/model-assets').get_json()['total'] == 1
    assert client.post('/api/model-assets/source/editor', json=payload).status_code == 409
    assert not list(Path(paths.output_folder).glob('edit-*'))
    assert not list(Path(paths.output_folder).glob('.model-edit-*'))


@pytest.mark.parametrize('fmt', ['ply', 'spz', 'splat'])
def test_overwrite_imported_model_keeps_format_id_and_user_original(workspace, fmt):
    from werkzeug.datastructures import FileStorage
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, _ = make_model(paths, degree=0)
    original_file = Path(source)
    if fmt == 'spz':
        original_file = Path(model_convert.ply_to_spz(source))
    elif fmt == 'splat':
        original_file = original_file.with_suffix('.splat')
        original_file.write_bytes(model_convert.ply_to_splat(source))
    original_bytes = original_file.read_bytes()
    with original_file.open('rb') as stream:
        imported = model_assets.import_model_assets(paths, [FileStorage(stream=stream, filename='User model.' + fmt)])['assets'][0]
    asset_id = imported['id']
    controlled = model_assets.resolve_download_file(paths, asset_id, fmt)[0]
    model_assets.update_model_asset_profile(paths, asset_id, {'tags': ['import'], 'note': 'keep'})
    descriptor = model_editor.get_editor_descriptor(paths, asset_id)
    payload = {**edit_payload(paths), 'fingerprint': descriptor['fingerprint'], 'save_mode': 'overwrite'}
    result = model_editor.save_edited_model(paths, asset_id, payload)
    assert result['id'] == asset_id and result['is_imported']
    assert result['formats'] == [fmt]
    assert result['name'] == payload['name']
    assert result['tags'] == ['import'] and result['note'] == 'keep'
    assert result['point_count'] == 7
    assert result['viewer_camera'] == payload['camera']
    assert result['viewer_transform'] is None
    assert model_assets.resolve_download_file(paths, asset_id, fmt)[0] == controlled
    assert len(model_editor.decode_vertices(controlled, fmt)) == 7
    assert original_file.read_bytes() == original_bytes
    assert '?v=' in result['default_open_url']
    model_assets.refresh_model_asset_catalog(paths)
    assert model_assets.get_model_asset(paths, asset_id)['viewer_camera'] == payload['camera']
    assert 'initial_origin' not in model_editor.get_editor_descriptor(paths, asset_id)


@pytest.mark.parametrize('failure', ['conversion', 'replacement', 'index'])
def test_overwrite_failure_restores_files_metadata_and_index(workspace, monkeypatch, failure):
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, _ = make_model(paths)
    model_convert.ply_to_spz(source)
    model_gallery.write_model_metadata(paths, 'source', {'source_name': 'original', 'point_count': 9})
    model_assets.update_model_asset_profile(paths, 'source', {'tags': ['keep'], 'note': 'keep'})
    snapshots = {path: path.read_bytes() for path in workspace.rglob('*') if path.is_file()}
    payload = {**edit_payload(paths), 'save_mode': 'overwrite'}
    if failure == 'conversion':
        def broken_conversion(*args, **kwargs):
            raise OSError('conversion failed')
        monkeypatch.setattr(model_convert, 'ply_to_spz', broken_conversion)
    elif failure == 'replacement':
        replace = model_assets.os.replace
        def broken_replace(src, dst):
            if '.model-edit-' in str(Path(src).parent.name) and str(dst) == str(Path(source).with_suffix('.spz')):
                raise OSError('replacement failed')
            return replace(src, dst)
        monkeypatch.setattr(model_assets.os, 'replace', broken_replace)
    else:
        def broken_index(*args, **kwargs):
            raise model_assets.ModelAssetIndexError('index failed', 'model_asset_index_write_failed')
        monkeypatch.setattr(model_assets, 'write_asset_index', broken_index)
    with pytest.raises((OSError, model_assets.ModelAssetServiceError)):
        model_editor.save_edited_model(paths, 'source', payload)
    for path, content in snapshots.items():
        assert path.read_bytes() == content
    assert {path for path in workspace.rglob('*') if path.is_file()} == set(snapshots)
    assert not list(workspace.rglob('.model-edit-*'))
    assert not model_editor.SAVE_LOCK.locked()


def test_overwrite_rechecks_source_after_conversion(workspace, monkeypatch):
    import os
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, _ = make_model(paths)
    original_bytes = Path(source).read_bytes()
    convert = model_convert.ply_to_spz
    def concurrent_change(*args, **kwargs):
        result = convert(*args, **kwargs)
        stat = os.stat(source)
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        return result
    monkeypatch.setattr(model_convert, 'ply_to_spz', concurrent_change)
    with pytest.raises(model_assets.ModelAssetServiceError) as error:
        model_editor.save_edited_model(paths, 'source', {**edit_payload(paths), 'save_mode': 'overwrite'})
    assert error.value.code == 'model_editor_source_changed'
    assert Path(source).read_bytes() == original_bytes
    assert not list(Path(paths.output_folder).glob('.model-edit-*'))


@pytest.mark.parametrize('degree', [1, 2, 3])
def test_rotated_harmonics_preserve_directional_color(degree):
    angle = 0.7
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    rng = np.random.default_rng(7)
    directions = rng.normal(size=(100, 3))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    coefficients = rng.normal(size=((degree+1)**2-1, 3))
    rotated = model_editor.sh_rotation(rotation, degree) @ coefficients
    np.testing.assert_allclose(model_editor.sh_basis(directions, degree) @ rotated,
                               model_editor.sh_basis(directions @ rotation, degree) @ coefficients, atol=1e-12)


def test_transform_rotates_center_covariance_and_scale():
    vertices = np.zeros(1, dtype=model_editor.gaussian_dtype(0))
    vertices['x'], vertices['rot_0'] = 1, 1
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * 2
    matrix[:3, 3] = [3, 4, 5]
    output = model_editor.transform_chunk(vertices, matrix, rotation, 2, None)
    assert tuple(output[name][0] for name in ('x', 'y', 'z')) == (3, 6, 5)
    assert abs(output['rot_0'][0]) == pytest.approx(np.sqrt(0.5))
    assert output['rot_3'][0] / output['rot_0'][0] == pytest.approx(1)
    assert output['scale_0'][0] == pytest.approx(np.log(2))


@pytest.mark.parametrize('degree', [0, 1, 2, 3])
def test_spz_edit_source_decodes_full_sh_and_rotation(workspace, degree):
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, original = make_model(paths, degree)
    original['x'] -= 4
    rotations = np.random.default_rng(42).normal(size=(len(original), 4))
    rotations /= np.linalg.norm(rotations, axis=1, keepdims=True)
    for index in range(4):
        original[f'rot_{index}'] = rotations[:, index]
    PlyData([PlyElement.describe(original, 'vertex')]).write(source)
    spz = model_convert.ply_to_spz(source)
    decoded = model_editor.decode_vertices(spz, 'spz')
    assert decoded.dtype.names == original.dtype.names
    np.testing.assert_allclose(decoded['x'], original['x'], atol=1/2048)
    np.testing.assert_allclose(decoded['f_dc_1'], original['f_dc_1'], atol=0.014)
    decoded_rotations = np.column_stack([decoded[f'rot_{i}'] for i in range(4)])
    assert np.min(np.abs(np.sum(decoded_rotations * rotations, axis=1))) > 0.99999
    if degree:
        last = f'f_rest_{3*((degree+1)**2-1)-1}'
        np.testing.assert_allclose(decoded[last], original[last], atol=0.064)


def test_spz_v2_rotation_and_negative_position(tmp_path):
    header = struct.pack('<IIIBBBB', model_convert.SPZ_MAGIC, 2, 1, 0, 11, 0, 0)
    xyz = b''.join((int(v * 2048) & 0xffffff).to_bytes(3, 'little') for v in (-2, 0.5, 3))
    quaternion = np.array([np.sin(0.4), 0, 0])
    encoded_quaternion = np.round((quaternion + 1) * 127.5).astype(np.uint8).tobytes()
    path = tmp_path / 'version2.spz'
    path.write_bytes(gzip.compress(header + xyz + bytes([200]) + bytes([128, 128, 128]) + bytes([128, 128, 128]) + encoded_quaternion))
    decoded = model_editor.decode_vertices(str(path), 'spz')
    assert tuple(decoded[name][0] for name in ('x', 'y', 'z')) == (-2, 0.5, 3)
    assert abs(float(decoded['rot_0'][0]) - np.cos(0.4)) < 0.005


@pytest.mark.parametrize('save_mode', ['copy', 'overwrite'])
def test_editor_api_source_save_and_owner_permission(client, app, save_mode):
    paths = app.config['PATH_CONTEXT']
    make_model(paths)
    descriptor = client.get('/api/model-assets/source/editor')
    assert descriptor.status_code == 200
    assert 'source_video_path' not in descriptor.get_json()
    source = client.get(descriptor.get_json()['source_url'], headers={'Range': 'bytes=0-15'})
    assert source.status_code == 206
    source.close()
    payload = edit_payload(paths)
    payload['save_mode'] = save_mode
    remote = client.post('/api/model-assets/source/editor', json=payload, environ_base={'REMOTE_ADDR': '192.168.1.4'})
    assert remote.status_code == 403
    result = client.post('/api/model-assets/source/editor', json=payload)
    assert result.status_code == 200
    assert result.get_json()['available']
    assert client.get('/api/model-assets/source/editor/source?v=stale').status_code == 409


def test_save_conversion_failure_rolls_back_new_files(workspace, monkeypatch):
    paths = build_path_context({'workspace_folder': str(workspace)})
    source, _ = make_model(paths)
    def broken_conversion(*args, **kwargs):
        raise RuntimeError('conversion failed')
    monkeypatch.setattr(model_convert, 'ply_to_spz', broken_conversion)
    with pytest.raises(RuntimeError):
        model_editor.save_edited_copy(paths, 'source', edit_payload(paths))
    assert not list(workspace.glob('outputs/edit-*'))
    assert not list(workspace.glob('outputs/.model-edit-*'))
    assert model_assets.get_model_asset(paths, 'source')['available']
    assert PlyData.read(source)['vertex'].count == 9
    assert not model_editor.SAVE_LOCK.locked()


def test_large_translation_spz_does_not_clip_positions(workspace):
    paths = build_path_context({'workspace_folder': str(workspace)})
    make_model(paths)
    payload = edit_payload(paths)
    payload['matrix'][12] = 10000
    asset = model_editor.save_edited_copy(paths, 'source', payload)
    ply = model_assets.resolve_download_file(paths, asset['id'], 'ply')[0]
    spz = model_assets.resolve_download_file(paths, asset['id'], 'spz')[0]
    np.testing.assert_allclose(model_editor.decode_vertices(spz, 'spz')['x'], PlyData.read(ply)['vertex'].data['x'], atol=0.002)


def test_busy_save_and_oversize_request_are_rejected(client, app):
    paths = app.config['PATH_CONTEXT']
    make_model(paths)
    payload = edit_payload(paths)
    model_editor.SAVE_LOCK.acquire()
    try:
        assert client.post('/api/model-assets/source/editor', json=payload).status_code == 409
    finally:
        model_editor.SAVE_LOCK.release()
    oversized = client.post('/api/model-assets/source/editor', data=b' ' * (model_editor.MAX_REQUEST_BYTES+1), content_type='application/json')
    assert oversized.status_code == 413
    assert oversized.get_json()['code'] == 'model_editor_too_large'


@pytest.mark.parametrize('field,value,code', [
    ('fingerprint', 'outdated', 'model_editor_source_changed'),
    ('deleted_mask', 'AA==', 'model_editor_invalid'),
    ('deleted_mask', base64.b64encode(bytes([255, 255])).decode(), 'model_editor_invalid'),
    ('deleted_mask', base64.b64encode(bytes([255, 1])).decode(), 'model_editor_empty'),
    ('point_count', True, 'model_editor_source_changed'),
    ('camera', None, 'model_editor_invalid'),
    ('matrix', [0]*16, 'model_editor_invalid'),
    ('save_mode', 'invalid', 'model_editor_invalid'),
    ('save_mode', None, 'model_editor_invalid'),
])
def test_bad_edit_has_no_partial_published_model(workspace, field, value, code):
    paths = build_path_context({'workspace_folder': str(workspace)})
    make_model(paths)
    payload = edit_payload(paths)
    payload[field] = value
    with pytest.raises(model_editor.ModelEditorError) as error:
        model_editor.save_edited_copy(paths, 'source', payload)
    assert error.value.code == code
    assert not list(workspace.glob('outputs/edit-*'))

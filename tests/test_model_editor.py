import base64
import hashlib
import gzip
import struct

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
    assert result['viewer_transform'] == model_editor.IDENTITY_VIEWER_TRANSFORM
    assert set(result['formats']) == {'ply', 'spz'}
    metadata = model_gallery.read_model_metadata(paths, result['id'])
    assert metadata['viewer_camera'] == edit_payload(paths)['camera']
    assert metadata['viewer_transform'] == model_editor.IDENTITY_VIEWER_TRANSFORM


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


def test_editor_api_source_save_and_owner_permission(client, app):
    paths = app.config['PATH_CONTEXT']
    make_model(paths)
    descriptor = client.get('/api/model-assets/source/editor')
    assert descriptor.status_code == 200
    assert 'source_video_path' not in descriptor.get_json()
    source = client.get(descriptor.get_json()['source_url'], headers={'Range': 'bytes=0-15'})
    assert source.status_code == 206
    payload = edit_payload(paths)
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

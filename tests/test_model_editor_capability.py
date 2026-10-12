"""编辑入口与实际文件结构一致，不按模型来源推断支持范围。"""

import base64
import json
from pathlib import Path

import numpy as np
import pytest
from plyfile import PlyData, PlyElement
from werkzeug.datastructures import FileStorage

from backend.services import model_assets, model_convert, model_editor, model_gallery


def make_ply(paths, *, sharp=False, text=False, byte_order='<'):
    root = Path(paths.output_folder)
    root.mkdir(parents=True, exist_ok=True)
    vertices = np.zeros(9, dtype=model_editor.gaussian_dtype(0))
    vertices['x'] = np.arange(9) * .1
    vertices['z'] = 2
    vertices['rot_0'] = 1
    vertices['opacity'] = 2
    for axis in range(3):
        vertices[f'scale_{axis}'] = -2
    elements = [PlyElement.describe(vertices, 'vertex')]
    if sharp:
        # 与 ml-sharp save_ply 的八个元素及标量类型一致。
        for name, dtype, values in (
            ('extrinsic', 'f4', np.eye(4).ravel()),
            ('intrinsic', 'f4', [1200, 0, 640, 0, 1200, 360, 0, 0, 1]),
            ('image_size', 'u4', [1280, 720]),
            ('frame', 'i4', [1, len(vertices)]),
            ('disparity', 'f4', [.5, .5]),
            ('color_space', 'u1', [0]),
            ('version', 'u1', [1, 5, 0]),
        ):
            array = np.zeros(len(values), dtype=[(name, dtype)])
            array[name] = values
            elements.append(PlyElement.describe(array, name))
    path = root / 'source.ply'
    PlyData(elements, text=text, byte_order=byte_order).write(path)
    return path


@pytest.mark.parametrize('label', ['image', 'video'])
def test_sharp_ply_is_uneditable_in_list_detail_and_editor(app, client, label):
    paths = app.config['PATH_CONTEXT']
    path = make_ply(paths, sharp=True)
    before = path.read_bytes()
    model_gallery.write_model_metadata(paths, 'source', {'source_media_type': label})
    # 已有 SPZ 不应绕过原始 PLY，悄悄丢掉相机等元数据。
    model_convert.ply_to_spz(str(path), str(path.with_suffix('.spz')))
    model_assets.sync_generated_model_asset(paths, 'source')
    for asset in (client.get('/api/model-assets').get_json()['items'][0],
                  client.get('/api/model-assets/source').get_json()):
        assert asset['available'] is True
        assert asset['editor_supported'] is False
        assert asset['editor_error'] == 'model_editor_unsupported'
        assert set(asset['formats']) == {'ply', 'spz'}
    response = client.get('/api/model-assets/source/editor')
    assert response.status_code == 415
    payload = {
        'fingerprint': model_editor.source_fingerprint(str(path)), 'point_count': 9,
        'deleted_mask': base64.b64encode(bytes([0, 0])).decode(), 'save_mode': 'overwrite',
        'matrix': np.eye(4).reshape(-1, order='F').tolist(),
        'camera': {'position': [0, 0, 8], 'target': [0, 0, 0], 'up': [0, 1, 0],
                   'fov_y_degrees': 50, 'aspect': 1.5},
    }
    assert client.post('/api/model-assets/source/editor', json=payload).status_code == 415
    assert path.read_bytes() == before
    assert client.get('/api/model-assets/source/download?format=ply').data == before


@pytest.mark.parametrize('text,byte_order', [(False, '<'), (False, '>'), (True, '<')])
def test_standard_image_gaussian_ply_still_supports_editor(app, client, text, byte_order):
    paths = app.config['PATH_CONTEXT']
    path = make_ply(paths, text=text, byte_order=byte_order)
    model_gallery.write_model_metadata(paths, 'source', {'source_media_type': 'image', 'generator': 'ml-sharp'})
    model_assets.sync_generated_model_asset(paths, 'source')
    asset = client.get('/api/model-assets').get_json()['items'][0]
    assert asset['editor_supported'] is True
    assert asset['editor_error'] is None
    assert client.get('/api/model-assets/source/editor').get_json()['point_count'] == 9
    assert model_editor.inspect_source_header(str(path), 'ply') == 9


@pytest.mark.parametrize('sharp', [False, True])
def test_imported_models_use_actual_structure(app, client, sharp):
    paths = app.config['PATH_CONTEXT']
    path = make_ply(paths, sharp=sharp)
    with path.open('rb') as stream:
        imported = model_assets.import_model_assets(paths, [FileStorage(stream=stream, filename='import.ply')])
    asset = imported['assets'][0]
    assert asset['editor_supported'] is (not sharp)
    response = client.get(f'/api/model-assets/{asset["id"]}/editor')
    assert response.status_code == (415 if sharp else 200)


@pytest.mark.parametrize('fmt', ['spz', 'splat'])
def test_standalone_supported_formats_remain_editable(app, client, fmt):
    paths = app.config['PATH_CONTEXT']
    path = make_ply(paths)
    destination = path.with_suffix('.' + fmt)
    if fmt == 'spz':
        model_convert.ply_to_spz(str(path), str(destination))
    else:
        destination.write_bytes(model_convert.ply_to_splat(str(path)))
    path.unlink()
    model_assets.sync_generated_model_asset(paths, 'source')
    assert client.get('/api/model-assets').get_json()['items'][0]['editor_supported'] is True
    assert client.get('/api/model-assets/source/editor').get_json()['point_count'] == 9


def test_capability_is_cached_in_warm_lists_and_old_catalog_is_rebuilt(app, client, monkeypatch):
    paths = app.config['PATH_CONTEXT']
    make_ply(paths, sharp=True)
    model_assets.sync_generated_model_asset(paths, 'source')
    index_path = Path(paths.model_asset_index_file)
    index = json.loads(index_path.read_text(encoding='utf-8'))
    index['version'] = 4
    index['catalog']['items']['source'].pop('editor_supported')
    index['source_defaults'] = {'content-identity': 'source'}
    index_path.write_text(json.dumps(index), encoding='utf-8')
    first = client.get('/api/model-assets').get_json()['items'][0]
    assert first['editor_supported'] is False
    rebuilt = json.loads(index_path.read_text(encoding='utf-8'))
    assert rebuilt['version'] == model_assets.INDEX_VERSION
    assert rebuilt['source_defaults'] == {'content-identity': 'source'}
    def forbidden(*args, **kwargs):
        raise AssertionError('Warm list must not read model headers or full point data')
    monkeypatch.setattr(model_assets, 'parse_ply_header_metadata', forbidden)
    monkeypatch.setattr(PlyData, 'read', forbidden)
    assert client.get('/api/model-assets?sort=created_desc').get_json()['items'][0]['editor_supported'] is False


def test_invalid_pointcloud_truncated_source_and_limits_are_uneditable(app, monkeypatch):
    paths = app.config['PATH_CONTEXT']
    path = make_ply(paths)
    monkeypatch.setattr(model_editor, 'MAX_POINTS', 8)
    assert model_editor.get_editor_capability({'ply': str(path)})['editor_error'] == 'model_editor_too_large'
    monkeypatch.setattr(model_editor, 'MAX_POINTS', 8_000_000)
    path.write_bytes(path.read_bytes()[:-4])
    assert model_editor.get_editor_capability({'ply': str(path)})['editor_supported'] is False
    vertices = np.zeros(9, dtype=[('x', 'f4'), ('y', 'f4'), ('z', 'f4')])
    PlyData([PlyElement.describe(vertices, 'vertex')]).write(path)
    assert model_editor.get_editor_capability({'ply': str(path)})['editor_supported'] is False
    assert model_editor.get_editor_capability({'rad': str(path)})['editor_supported'] is False

import base64
import json
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from backend import runtime
from backend.paths import build_path_context, ensure_runtime_directories
from backend.services import export_html, model_gallery
from tests.conftest import write_config


@pytest.fixture
def export_workspace(workspace, tmp_path, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    base = tmp_path / 'application'
    assets = base / 'frontend/dist/share'
    assets.mkdir(parents=True)
    (assets / 'share-viewer.js').write_text('console.log("</script><b>must stay in JS</b>");', encoding='utf-8')
    (assets / 'share-viewer.css').write_text('body{margin:0}', encoding='utf-8')
    (assets / 'LICENSES.txt').write_text('MIT <license>', encoding='utf-8')
    (base / 'templates').mkdir()
    (base / 'templates/share_template.html').write_text(
        (Path(runtime.BASE_DIR) / 'templates/share_template.html').read_text(encoding='utf-8'), encoding='utf-8')
    monkeypatch.setattr(runtime, 'BASE_DIR', str(base))
    return paths, base


def manifest_from(page):
    value = re.search(r'<script type="application/json" id="share-manifest">(.*?)</script>', page, re.S)[1]
    return json.loads(value)


@pytest.mark.parametrize('format_name', ['ply', 'spz', 'splat', 'rad'])
def test_export_only_needs_dist_and_preserves_model_bytes(export_workspace, format_name):
    paths, base = export_workspace
    payload = b'original-model-bytes'
    Path(paths.output_folder, f'example.{format_name}').write_bytes(payload)
    result, error, status = export_html.build_export_html(paths, 'example', format_name)
    assert status == 200 and error is None
    assert not (base / 'frontend/node_modules').exists()
    assert manifest_from(result['html'])['format'] == format_name
    assert result['model_size'] == len(payload)
    assert base64.b64encode(payload).decode('ascii') in result['html']
    assert result['html_size'] == len(result['html'].encode('utf-8'))
    assert 'console.log("<\\/script>' in result['html']
    assert 'MIT &lt;license&gt;' in result['html']


def test_export_only_embeds_normalized_preview_metadata(export_workspace):
    paths, _ = export_workspace
    Path(paths.output_folder, 'video.ply').write_bytes(b'ply')
    camera = {'position': [1, 2, 3], 'target': [1, 2, 5], 'up': [0, 1, 0], 'fov_y_degrees': 55, 'aspect': 1.8}
    transform = {'positionX': 1, 'positionY': 2, 'positionZ': 3, 'rotationX': 0, 'rotationY': 0.2, 'rotationZ': 0, 'scale': 1}
    model_gallery.write_model_metadata(paths, 'video', {
        'source_media_type': 'video', 'source_video_path': 'Z:/private/movie.mp4',
        'workspace_folder': 'Z:/secret', 'viewer_camera': camera, 'viewer_transform': transform,
        'password_hash': 'DO-NOT-EXPORT', 'display_name': '</script><img src=x onerror=alert(1)> {{MODEL_DATA}}',
    })
    result, _, status = export_html.build_export_html(paths, 'video', 'ply')
    assert status == 200
    page = result['html']
    manifest = manifest_from(page)
    assert manifest['viewerOrientation'] == 'y-front'
    assert manifest['viewerCamera'] == camera
    assert manifest['viewerTransform'] == transform
    assert set(manifest) == {'version', 'format', 'sourceMediaType', 'viewerOrientation', 'viewerCamera', 'viewerTransform'}
    assert 'Z:/private' not in page and 'Z:/secret' not in page and 'DO-NOT-EXPORT' not in page
    assert '&lt;/script&gt;&lt;img' in page
    assert '{{MODEL_DATA}}' in page  # User-provided placeholder is literal, never expanded again.


def test_invalid_camera_and_transform_are_not_exported(export_workspace):
    paths, _ = export_workspace
    Path(paths.output_folder, 'invalid.ply').write_bytes(b'ply')
    model_gallery.write_model_metadata(paths, 'invalid', {'viewer_camera': {'position': [float('nan'), 0, 0]}, 'viewer_transform': {'scale': float('inf')}})
    result, _, _ = export_html.build_export_html(paths, 'invalid', 'ply')
    manifest = manifest_from(result['html'])
    assert manifest['viewerCamera'] is None and manifest['viewerTransform'] is None
    assert manifest['viewerOrientation'] == 'unknown'


def test_missing_built_viewer_has_explicit_error(export_workspace, monkeypatch):
    paths, base = export_workspace
    Path(paths.output_folder, 'model.ply').write_bytes(b'ply')
    (base / 'frontend/dist/share/share-viewer.js').unlink()
    def unexpected_conversion(*args):
        pytest.fail('Missing viewer must not trigger model conversion')
    monkeypatch.setattr(export_html, 'ply_to_spz', unexpected_conversion)
    result, error, status = export_html.build_export_html(paths, 'model', 'spz')
    assert result is None and status == 503 and error['code'] == 'share_viewer_unavailable'


def test_export_keeps_existing_private_read_permission(client, config_file, workspace, monkeypatch):
    write_config(config_file, {'workspace_folder': str(workspace), 'access_control': {
        'enabled': True, 'password_hash': generate_password_hash('test-password'),
        'session_secret': 'test-only', 'allow_localhost_bypass': True,
    }})
    calls = []
    def build(*args):
        calls.append(args)
        return {'html': '<!doctype html>safe', 'download_name': 'test.html', 'format': 'ply', 'model_size': 3, 'html_size': 18}, None, 200
    monkeypatch.setattr('backend.routes.export.build_export_html', build)
    remote = {'base_url': 'http://192.168.1.2', 'environ_overrides': {'REMOTE_ADDR': '192.168.1.9'}}
    response = client.get('/api/export/model', **remote)
    assert response.status_code == 401 and not calls
    assert client.post('/api/auth/login', json={'password': 'test-password'}, **remote).status_code == 200
    response = client.get('/api/export/model', **remote)
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers['X-Export-Format'] == 'ply'

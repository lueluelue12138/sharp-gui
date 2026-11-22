import json
from io import BytesIO

import pytest
from flask import g
from PIL import Image

from backend.config import get_access_control_config
from backend.routes import portrait
from backend.security.access_control import create_access_session_token
from backend.services import portrait_progress
from backend.services import portrait_workflow as workflow

SOURCE = {'filename': 'source.png', 'subfolder': 'sharp_gui_portrait', 'type': 'input'}


def signed(app, *entries):
    with app.test_request_context():
        g.access_control = get_access_control_config(persist_missing=False)
        return [portrait.sign(kind, value) for kind, value in entries]


def test_build_uses_only_trusted_graph(app, client, monkeypatch):
    [source] = signed(app, ('source', SOURCE))
    capture = {}

    def submit(path, body, **_kwargs):
        capture.update(body)
        return {'prompt_id': '00000000-0000-4000-8000-000000000001'}

    monkeypatch.setattr(workflow, 'comfy_json', submit)
    monkeypatch.setattr(portrait_progress, 'connect', lambda _url: None)
    response = client.post('/api/portrait/jobs/build', json={
        'source': source, 'lens': 36, 'prompt': {'1': {'class_type': 'ForeignNode'}},
    })
    assert response.status_code == 202
    assert capture['partial_execution_targets'] == ['3']
    assert capture['prompt']['1']['inputs']['image'] == 'sharp_gui_portrait/source.png'
    assert capture['prompt']['2']['inputs']['lens_mm'] == 36
    assert capture['prompt']['3']['inputs']['camera'] == ''
    assert all(node['class_type'] != 'ForeignNode' for node in capture['prompt'].values())


def test_repeated_job_request_reuses_one_comfy_prompt(app, client, monkeypatch):
    [source] = signed(app, ('source', SOURCE))
    request_id = '00000000-0000-4000-8000-000000000001'
    queue = []
    submissions = []

    def comfy(path, body=None, **_kwargs):
        if path == '/queue':
            return {'queue_running': queue, 'queue_pending': []}
        if path == f'/history/{request_id}':
            return {}
        assert path == '/prompt'
        submissions.append(body)
        queue.append([1, body['prompt_id'], body['prompt'], body['extra_data'], ['3']])
        return {'prompt_id': body['prompt_id']}

    monkeypatch.setattr(workflow, 'comfy_json', comfy)
    monkeypatch.setattr(portrait_progress, 'connect', lambda _url: None)
    options = {'source': source, 'request_id': request_id, 'lens': 30}
    first = client.post('/api/portrait/jobs/build', json=options)
    again = client.post('/api/portrait/jobs/build', json=options)
    mismatch = client.post('/api/portrait/jobs/build', json={**options, 'lens': 40})
    assert first.status_code == again.status_code == 202
    assert mismatch.status_code == 409
    assert len(submissions) == 1
    with app.test_request_context():
        g.access_control = get_access_control_config(persist_missing=False)
        assert portrait.read_token('job', first.json['job']) == portrait.read_token('job', again.json['job'])


def test_cancel_addresses_only_the_signed_job(app, client, monkeypatch):
    job_id = '00000000-0000-4000-8000-000000000002'
    [job] = signed(app, ('job', {'id': job_id, 'stage': 'repair', 'source': SOURCE['filename']}))
    calls = []

    def comfy(path, body=None):
        calls.append((path, body))
        return {'cancelled': False}  # A completed or already cancelled task can be closed too.

    monkeypatch.setattr(workflow, 'comfy_json', comfy)
    monkeypatch.setattr(workflow, '_cancelled_requests', {})
    assert client.post('/api/portrait/jobs/cancel', json={'job': job + 'x'}).status_code == 404
    assert client.post('/api/portrait/jobs/cancel', json={'job': job}, base_url='http://192.168.1.2',
                       environ_overrides={'REMOTE_ADDR': '192.168.1.9'}).status_code == 403
    response = client.post('/api/portrait/jobs/cancel', json={'job': job})
    assert response.status_code == 200
    assert response.json == {'ok': True}
    assert calls == [(f'/api/jobs/{job_id}/cancel', {})]


def test_cancel_before_submit_blocks_the_late_request_for_the_same_source(app, client, monkeypatch):
    other = {**SOURCE, 'filename': 'other.png'}
    source, other_source = signed(app, ('source', SOURCE), ('source', other))
    request_id = '00000000-0000-4000-8000-000000000003'
    monkeypatch.setattr(workflow, '_cancelled_requests', {})
    monkeypatch.setattr(workflow, 'find_comfy_prompt', lambda _id: None)
    monkeypatch.setattr(portrait_progress, 'connect', lambda _url: None)
    calls = []

    def comfy(path, body, **_kwargs):
        calls.append((path, body['prompt']['1']['inputs']['image']))
        return {'prompt_id': request_id}

    monkeypatch.setattr(workflow, 'comfy_json', comfy)
    options = {'source': source, 'request_id': request_id}
    assert client.post('/api/portrait/jobs/cancel', json=options).status_code == 200
    response = client.post('/api/portrait/jobs/build', json=options)
    assert response.status_code == 409
    assert response.json['code'] == 'portraitCancelled'
    assert client.post('/api/portrait/jobs/build', json={**options, 'source': other_source}).status_code == 202
    assert calls == [('/prompt', 'sharp_gui_portrait/other.png')]


def test_cancel_after_submit_with_lost_response_requires_a_matching_source(app, client, monkeypatch):
    source, other_source = signed(app, ('source', SOURCE), ('source', {**SOURCE, 'filename': 'other.png'}))
    request_id = '00000000-0000-4000-8000-000000000004'
    entry = [1, request_id, {'1': {'inputs': {'image': 'sharp_gui_portrait/source.png'}}},
             {'sharp_gui_portrait_request': 'fingerprint'}, ['3']]
    monkeypatch.setattr(workflow, '_cancelled_requests', {})
    monkeypatch.setattr(workflow, 'find_comfy_prompt', lambda _id: entry)
    calls = []

    def comfy(path, body):
        calls.append((path, body))
        return {'cancelled': True}

    monkeypatch.setattr(workflow, 'comfy_json', comfy)
    assert client.post('/api/portrait/jobs/cancel', json={'source': other_source, 'request_id': request_id}).status_code == 409
    assert client.post('/api/portrait/jobs/cancel', json={'source': source, 'request_id': request_id}).status_code == 200
    assert calls == [(f'/api/jobs/{request_id}/cancel', {})]


def test_legacy_job_recovery_is_available_only_to_the_host(client, monkeypatch):
    monkeypatch.setattr(workflow, 'recent_legacy_jobs', lambda: [{
        'context': {'stage': 'build', 'source': SOURCE['filename'], 'lens': 30, 'id': '00000000-0000-4000-8000-000000000001'},
        'model': None, 'started_at': 1795278245811, 'edge': 1920,
    }])
    result = client.get('/api/portrait/recent')
    assert result.status_code == 200
    assert result.json[0]['source']['url'].startswith('/api/portrait/media/')
    assert result.json[0]['stage'] == 'build'
    assert client.get('/api/portrait/recent', base_url='http://192.168.1.2',
                      environ_overrides={'REMOTE_ADDR': '192.168.1.9'}).status_code == 403


def test_closeup_only_changes_the_original_reference_input():
    graph = {**workflow.workflow_template(), '12': {'inputs': {'image_1': ['6', 0], 'image_2': ['3', 3], 'start_from_image': False}}}
    workflow.match_reference_crop(graph, {'width': 2730, 'height': 1535, 'bounds': [0.17, 0.35, 0.77, 0.94]}, 1920)
    assert graph['10001'] == {'class_type': 'ImageCrop', 'inputs': {
        'image': ['3', 3], 'x': 326, 'y': 381, 'width': 1152, 'height': 642,
    }}
    assert graph['12']['inputs'] == {'image_1': ['6', 0], 'image_2': ['10001', 0], 'start_from_image': False}


@pytest.mark.parametrize(('stage', 'custom', 'edge'), [
    ('repair', '', None),
    ('repair', 'Keep the original colors.', 1280),
    ('frame', 'Keep the original colors.', None),
])
def test_repair_preserves_native_comfy_sampling(monkeypatch, stage, custom, edge):
    default = workflow.workflow_template()['12']['inputs']['prompt']
    submitted = {}

    def submit(_path, body, **_kwargs):
        submitted.update(body)
        return {'prompt_id': '00000000-0000-4000-8000-000000000001'}

    monkeypatch.setattr(workflow, 'comfy_json', submit)
    monkeypatch.setattr(portrait_progress, 'connect', lambda _url: None)
    options = {
        'repair_prompt': custom,
        'camera': {'width': 768, 'height': 512, 'w2c': [[int(a == b) for b in range(4)] for a in range(4)],
                   'K': [[640, 0, 384], [0, 640, 256], [0, 0, 1]]},
        'sequence': '20261121-123456-123abcd0', 'mode': 'repair', 'count': 1, 'index': 1,
    }
    if edge is not None:
        options['edge'] = edge
    workflow.submit(stage, SOURCE, options, model_token='a' * 64, capture='capture.png')
    graph = submitted['prompt']
    assert graph['12']['inputs']['prompt'] == (custom or default)
    assert workflow.workflow_template()['12']['inputs']['prompt'] == default
    assert graph['12']['inputs']['image_1'] == ['6', 0]
    assert graph['12']['inputs']['image_2'] == ['3', 3]
    assert graph['6']['inputs']['image'] == ['3', 4]
    assert json.loads(graph['3']['inputs']['camera'])['capture'] == 'capture.png'
    assert graph['3']['inputs']['long_edge'] == (edge or 1920)
    assert graph['3']['inputs']['reference_edge'] == 1920
    assert graph['12']['inputs']['start_from_image'] is False
    assert 'noise_mask' not in graph['12']['inputs']
    assert graph['13']['inputs'] == {'model': ['11', 0], 'conditioning': ['12', 0]}
    assert graph['10']['inputs']['lora_name'] == 'splat_repair_human_qwen21_e23.safetensors'
    assert graph['10']['inputs']['strength_model'] == 1.0
    assert graph['14']['inputs']['noise_seed'] == 1
    assert graph['15']['inputs']['sampler_name'] == 'euler'
    assert graph['17']['inputs']['latent_image'] == ['12', 1]
    schedule_id, _ = graph['17']['inputs']['sigmas']
    sigmas = [float(sigma) for sigma in graph[schedule_id]['inputs']['sigmas'].split(',')]
    assert sigmas == [1.0, 0.978453, 0.954180, 0.926626, 0.895080, 0.845148, 0.704534, 0.414568, 0.15, 0.0]


def test_repair_rejects_other_photos_model(app, client):
    source, model = signed(app, ('source', SOURCE), ('model', {'source': 'other.png', 'lens': 30}))
    response = client.post('/api/portrait/jobs/repair', json={'source': source, 'model': model})
    assert response.status_code == 400
    assert response.json['code'] == 'portraitInvalid'


def test_media_rejects_arbitrary_path(client):
    assert client.get('/api/portrait/media/untrusted-filename').status_code == 404
    assert client.get('/api/portrait/renderer/portrait_save.js').status_code == 404


@pytest.mark.parametrize('kind', ['capture', 'mask'])
def test_render_upload_requires_alpha(client, kind):
    photo = BytesIO()
    Image.new('RGB', (64, 64)).save(photo, 'PNG')
    photo.seek(0)
    response = client.post(f'/api/portrait/uploads/{kind}', data={'image': (photo, 'photo.png')})
    assert response.status_code == 400
    assert response.json['code'] == 'portraitInvalidImage'


def test_local_comfy_address_rejects_remote_targets(monkeypatch):
    monkeypatch.setenv('SHARP_PORTRAIT_COMFY_URL', 'http://127.0.0.1:8188')
    assert workflow.comfy_url() == 'http://127.0.0.1:8188'
    monkeypatch.setenv('SHARP_PORTRAIT_COMFY_URL', 'http://127.0.0.1:8188@192.168.1.2')
    with pytest.raises(workflow.PortraitError):
        workflow.comfy_url()


def test_start_comfy_uses_local_shortcut_once_then_reports_connection(client, monkeypatch, tmp_path):
    shortcut = tmp_path / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Comfy Desktop.lnk'
    shortcut.parent.mkdir(parents=True)
    shortcut.touch()
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.delenv('SHARP_PORTRAIT_COMFY_EXE', raising=False)
    monkeypatch.setattr(workflow, '_comfy_launch_deadline', None)
    launched = []
    monkeypatch.setattr(workflow.os, 'startfile', launched.append, raising=False)
    now = [0]
    connected = [False]
    monkeypatch.setattr(workflow, 'time', type('Clock', (), {'monotonic': lambda: now[0]}))

    def query_comfy(path, **_kwargs):
        if not connected[0]:
            raise workflow.PortraitError('portraitOffline', 'Unavailable', 503)
        assert path == '/queue'
        return {'queue_running': [], 'queue_pending': []}

    monkeypatch.setattr(workflow, 'comfy_json', query_comfy)
    first = client.post('/api/portrait/start', json={'path': 'ignore-client-supplied-path.exe'})
    assert first.status_code == 202 and first.json == {'state': 'starting'}
    assert client.post('/api/portrait/start').status_code == 202
    assert client.get('/api/portrait/status').json['code'] == 'portraitStarting'
    assert launched == [str(shortcut)]

    now[0] = workflow.COMFY_START_TIMEOUT
    assert client.get('/api/portrait/status').json['code'] == 'portraitStartTimeout'
    connected[0] = True
    assert client.post('/api/portrait/start').json == {'state': 'online'}
    assert launched == [str(shortcut)]


def test_lan_start_comfy_respects_generation_permission(app, client, monkeypatch):
    access = get_access_control_config(persist_missing=False)
    access.update(enabled=True, allow_remote_generation=True, password_hash='configured')
    monkeypatch.setattr('backend.security.hooks.get_access_control_config', lambda: access)
    launches = []
    monkeypatch.setattr(workflow, 'start_comfy', lambda: launches.append(True) or 'starting')
    remote = {'base_url': 'http://192.168.1.2', 'environ_overrides': {'REMOTE_ADDR': '192.168.1.9'}}
    assert client.post('/api/portrait/start', **remote).status_code == 401
    session, _ = create_access_session_token(access)
    client.set_cookie('sharp_gui_access', session, domain='192.168.1.2')
    assert client.post('/api/portrait/start', **remote).status_code == 202
    access['allow_remote_generation'] = False
    assert client.post('/api/portrait/start', **remote).status_code == 403
    assert launches == [True]


def test_lan_requires_unlocked_generation_access(app, client, monkeypatch):
    access = get_access_control_config(persist_missing=False)
    access.update(enabled=True, allow_remote_generation=True, password_hash='configured')
    monkeypatch.setattr('backend.security.hooks.get_access_control_config', lambda: access)
    remote = {'REMOTE_ADDR': '192.168.1.9'}
    request = {'base_url': 'http://192.168.1.2', 'environ_overrides': remote, 'json': {}}
    assert client.post('/api/portrait/jobs/build', **request).status_code == 401
    session, _ = create_access_session_token(access)
    client.set_cookie('sharp_gui_access', session, domain='192.168.1.2')
    assert client.post('/api/portrait/jobs/build', **request).status_code == 400
    access['allow_remote_generation'] = False
    assert client.post('/api/portrait/jobs/build', **request).status_code == 403


def test_progress_uses_real_node_steps_and_ignores_other_jobs():
    previous = {'node': '17'}
    update = {'type': 'progress', 'data': {'prompt_id': 'ours', 'node': '17', 'value': 5, 'max': 9}}
    assert portrait_progress.update_progress(previous, update, 'other') is previous
    result = portrait_progress.update_progress(previous, update, 'ours')
    assert result == {'node': '17', 'value': 5, 'max': 9}
    next_node = {'type': 'executing', 'data': {'prompt_id': 'ours', 'node': '18'}}
    assert portrait_progress.update_progress(result, next_node, 'ours') == {'node': '18'}


def test_memory_release_waits_for_comfy_queue(client, monkeypatch):
    monkeypatch.setattr(workflow, 'comfy_json', lambda _path: {'queue_pending': ['another job']})
    assert client.post('/api/portrait/memory/release').status_code == 409


def test_memory_release_clears_only_preview_models_and_requests_both_comfy_flags(client, monkeypatch, tmp_path):
    monkeypatch.delenv('SHARP_PORTRAIT_COMFY_TEMP', raising=False)
    preview = tmp_path / 'temp' / 'portrait_sharp'
    preview.mkdir(parents=True)
    cached = preview / f'{"f" * 64}.ply'
    cached.touch()
    unrelated = preview / 'manual-export.ply'
    unrelated.touch()
    render = preview.parent / 'result.png'
    render.touch()

    def comfy_json(path):
        if path == '/system_stats':
            return {'system': {'argv': ['ComfyUI/main.py', '--base-directory', str(tmp_path)]}}
        assert path == '/queue'
        return {'queue_pending': [], 'queue_running': []}

    monkeypatch.setattr(workflow, 'comfy_json', comfy_json)

    def open_comfy(path, body, content_type):
        assert path == '/free'
        assert content_type == 'application/json'
        assert json.loads(body) == {'unload_models': True, 'free_memory': True}
        return BytesIO()

    monkeypatch.setattr(workflow, 'comfy_open', open_comfy)
    assert client.post('/api/portrait/memory/release').json == {'requested': True, 'removed': 1, 'failed': 0}
    assert not cached.exists()
    assert unrelated.exists() and render.exists()


def test_gallery_import_resolves_photo_id(client, monkeypatch, tmp_path):
    photo = tmp_path / 'test.png'
    photo.write_bytes(b'test photo')
    monkeypatch.setattr(portrait.photo_gallery, 'resolve_photo_path', lambda _paths, photo_id: (None, photo, {}) if photo_id == 'valid-photo' else None)

    def upload(kind, stream):
        assert kind == 'source'
        assert stream.read() == b'test photo'
        return SOURCE

    monkeypatch.setattr(workflow, 'upload_image_stream', upload)
    result = client.post('/api/portrait/gallery-source/valid-photo')
    assert result.status_code == 200
    assert result.json['url'].startswith('/api/portrait/media/')
    assert client.post('/api/portrait/gallery-source/another-photo').status_code == 404

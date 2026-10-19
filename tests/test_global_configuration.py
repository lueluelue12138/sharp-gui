"""配置换包、恢复、并发与损坏保护；全部使用隔离目录。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from plyfile import PlyData, PlyElement

from backend import config, config_storage, runtime
from backend.app_factory import create_app
from backend.routes import settings as settings_routes
from backend.services import model_editor, video_reconstruction


@pytest.fixture
def global_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv('SHARP_CONFIG_FILE', raising=False)
    package = tmp_path / 'old-package'
    package.mkdir()
    monkeypatch.setattr(runtime, 'CONFIG_FILE', str(package / 'config.json'))
    monkeypatch.setattr(video_reconstruction, 'start_dependency_warmup', lambda: None)
    return package, Path(runtime.get_config_file())


def write_legacy(folder, workspace=None, **extra):
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'config.json'
    source.write_text(json.dumps({
        'workspace_folder': str(workspace or folder),
        'access_control': {'enabled': False, 'session_secret': 'private-session-secret'},
        **extra,
    }, ensure_ascii=False), encoding='utf-8')
    return source


@pytest.mark.parametrize('system,expected', [
    ('Windows', ('local', 'SharpGUI')), ('Darwin', ('home', 'Library', 'Application Support', 'SharpGUI')),
    ('Linux', ('xdg', 'sharp-gui')),
])
def test_platform_config_locations(tmp_path, system, expected):
    actual = config_storage.user_config_dir(system, {
        'LOCALAPPDATA': str(tmp_path / 'local'), 'XDG_CONFIG_HOME': str(tmp_path / 'xdg'),
    }, tmp_path / 'home')
    assert actual == tmp_path.joinpath(*expected)


def test_custom_profile_and_explicit_file_are_isolated(global_configuration, monkeypatch, tmp_path):
    old, global_path = global_configuration
    write_legacy(old, model_format='ply')
    explicit = tmp_path / 'explicit' / 'custom.json'
    monkeypatch.setenv('SHARP_CONFIG_FILE', str(explicit))
    data = config.load_config()
    assert data['workspace_folder'] == runtime.DEFAULT_WORKSPACE_FOLDER
    assert 'model_format' not in data
    data['model_format'] = 'spz'
    config.save_config(data)
    assert explicit.exists()
    assert not global_path.exists()


def test_new_profile_has_stable_default_workspace(global_configuration, monkeypatch, tmp_path):
    _, global_path = global_configuration
    first = config.load_config()
    monkeypatch.setattr(runtime, 'CONFIG_FILE', str(tmp_path / 'new-package' / 'config.json'))
    second = config.load_config()
    assert first == second
    assert Path(first['workspace_folder']).parent == global_path.parent
    assert global_path.exists()
    assert json.loads(json.dumps(first)) == dict(first)
    assert 'source_path' not in first


def test_migration_preserves_relative_paths_unknown_fields_and_source(global_configuration):
    old, _ = global_configuration
    source = write_legacy(old, workspace='library', custom_future={'unchanged': True},
                          photo_gallery_roots_by_workspace={'library': [{'id': 'album-id', 'path': '../媒体'}]})
    before = source.read_bytes()
    migrated = config.load_config()
    assert migrated['workspace_folder'] == str(old / 'library')
    bucket = migrated['photo_gallery_roots_by_workspace'][os.path.normcase(str(old / 'library'))]
    assert bucket[0]['id'] == 'album-id'
    assert bucket[0]['path'] == os.path.abspath(old / '../媒体')
    assert migrated['custom_future'] == {'unchanged': True}
    assert migrated['access_control']['session_secret'] == 'private-session-secret'
    assert source.read_bytes() == before


def test_old_input_only_config_uses_old_package_not_new_default(global_configuration):
    old, _ = global_configuration
    (old / 'config.json').write_text(json.dumps({'input_folder': 'inputs', 'model_format': 'ply'}), encoding='utf-8')
    assert config.load_config()['workspace_folder'] == str(old)


def test_package_data_without_config_is_retained_as_legacy_workspace(global_configuration):
    old, _ = global_configuration
    (old / 'outputs').mkdir()
    (old / 'outputs' / 'existing.ply').write_bytes(b'existing model')
    assert config.load_config()['workspace_folder'] == str(old)


def test_unwritable_profile_does_not_fall_back_to_package(global_configuration, monkeypatch):
    old, path = global_configuration
    source = write_legacy(old)
    before = source.read_bytes()
    def denied(*_args):
        raise PermissionError('read-only storage')
    monkeypatch.setattr(config_storage, '_atomic_write', denied)
    with pytest.raises(config_storage.ConfigStorageError) as error:
        config.load_config()
    assert error.value.code == 'config_unavailable'
    assert source.read_bytes() == before
    assert not path.exists()


def test_new_package_reuses_same_models_album_ids_and_index(global_configuration, monkeypatch, tmp_path):
    old, _ = global_configuration
    workspace = old / 'library'
    media = tmp_path / '媒体'
    media.mkdir()
    Image.new('RGB', (32, 20), 'red').save(media / '照片.jpg')
    source = write_legacy(old, workspace, photo_gallery_roots=[{
        'id': 'stable-album', 'name': '测试相册', 'path': str(media), 'enabled': True, 'recursive': True,
    }])
    before = source.read_bytes()
    (workspace / 'outputs').mkdir(parents=True)
    vertices = np.zeros(3, dtype=model_editor.gaussian_dtype(0))
    vertices['z'] = 2
    vertices['rot_0'] = 1
    PlyData([PlyElement.describe(vertices, 'vertex')]).write(workspace / 'outputs' / 'model.ply')
    first = create_app().test_client()
    assert first.post('/api/photo-albums/stable-album/scan').status_code == 200
    models = first.get('/api/model-assets').get_json()['items']
    photos = first.get('/api/photo-albums/stable-album/photos').get_json()['items']
    assert models and photos
    new_package = tmp_path / 'new-package'
    write_legacy(new_package, tmp_path / 'wrong-new-workspace', model_format='spz')
    monkeypatch.setattr(runtime, 'CONFIG_FILE', str(new_package / 'config.json'))
    second = create_app().test_client()
    assert second.get('/api/settings').get_json()['workspace_folder'] == str(workspace)
    assert [item['id'] for item in second.get('/api/model-assets').get_json()['items']] == [item['id'] for item in models]
    assert [item['id'] for item in second.get('/api/photo-albums/stable-album/photos').get_json()['items']] == [item['id'] for item in photos]
    assert source.read_bytes() == before


@pytest.mark.parametrize('bad', ['{broken', '[]', '{}', '{"workspace_folder": null}'])
def test_corrupt_config_is_not_reset(global_configuration, bad):
    _, path = global_configuration
    config.load_config()
    path.write_text(bad, encoding='utf-8')
    with pytest.raises(config_storage.ConfigStorageError, match='Configuration'):
        config.load_config()
    assert path.read_text(encoding='utf-8') == bad


def test_deleted_initialized_config_is_not_recreated_even_in_fresh_process(global_configuration):
    old, path = global_configuration
    config.load_config()
    path.unlink()
    code = 'from backend import runtime; from backend.config import load_config; runtime.CONFIG_FILE=' + repr(str(old / 'config.json')) + '; load_config()'
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'ConfigStorageError' in result.stderr
    assert not path.exists()


def test_stale_write_and_failed_replace_keep_current_config(global_configuration, monkeypatch):
    _, path = global_configuration
    first, stale = config.load_config(), config.load_config()
    first['model_format'] = 'ply'
    config.save_config(first)
    with pytest.raises(config_storage.ConfigStorageError) as error:
        config.save_config(stale)
    assert error.value.code == 'config_conflict'
    before = path.read_bytes()
    first['model_format'] = 'spz'
    def disk_full(*_args):
        raise OSError('disk full')
    monkeypatch.setattr(config_storage.os, 'replace', disk_full)
    with pytest.raises(config_storage.ConfigStorageError):
        config.save_config(first)
    assert path.read_bytes() == before
    assert not list(path.parent.glob('.config-*.tmp'))


def test_invalid_save_keeps_valid_config(global_configuration):
    _, path = global_configuration
    data = config.load_config()
    before = path.read_bytes()
    data['workspace_folder'] = None
    with pytest.raises(config_storage.ConfigStorageError) as error:
        config.save_config(data)
    assert error.value.code == 'config_invalid'
    assert path.read_bytes() == before


def test_two_processes_initialize_one_profile_without_overwriting(global_configuration):
    old, path = global_configuration
    write_legacy(old, model_format='ply')
    code = ('from backend import runtime; from backend.config import load_config; runtime.CONFIG_FILE=' +
            repr(str(old / 'config.json')) + '; print(load_config()["model_format"])')
    processes = [subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    for process in processes:
        output, error = process.communicate(timeout=20)
        assert process.returncode == 0, error
        assert output.strip() == 'ply'
    assert json.loads(path.read_text(encoding='utf-8'))['model_format'] == 'ply'


@pytest.fixture
def restore_case(app, client, tmp_path, monkeypatch):
    old = tmp_path / 'restore-old'
    workspace = tmp_path / 'restored-workspace'
    workspace.mkdir()
    source = write_legacy(old, workspace, model_format='ply', photo_gallery_roots=[{
        'id': 'old-album', 'name': '旧相册', 'path': str(tmp_path / 'offline-media'),
    }])
    restarted = []
    monkeypatch.setattr(settings_routes, 'restart_process_later', lambda: restarted.append(True))
    preview = client.post('/api/settings/restore', json={'folder': str(old)})
    assert preview.status_code == 200
    return old, source, preview.get_json(), restarted


def test_restore_previews_without_secrets_then_backs_up_and_preserves_old_source(app, client, restore_case):
    _, source, preview, restarted = restore_case
    active = Path(runtime.get_config_file())
    before = json.loads(active.read_text(encoding='utf-8'))
    original_source = source.read_bytes()
    assert 'session_secret' not in str(preview)
    assert 'password_hash' not in str(preview)
    assert preview['album_count'] == 1
    assert not restarted
    response = client.post('/api/settings/restore', json={**preview, 'confirm': True})
    assert response.status_code == 200
    assert restarted == [True]
    assert config.load_config()['workspace_folder'] == preview['workspace_folder']
    assert source.read_bytes() == original_source
    backup = list(active.parent.glob(active.name + '.before-restore-*.bak'))
    assert len(backup) == 1
    assert json.loads(backup[0].read_text(encoding='utf-8')) == before
    assert client.post('/api/generate').status_code == 409
    with pytest.raises(config_storage.ConfigStorageError):
        app.config['TASK_MANAGER'].enqueue_video_reconstruction({})


@pytest.mark.parametrize('change', ['source', 'target', 'active', 'admission'])
def test_restore_conflicts_and_active_work_leave_target_intact(app, client, restore_case, change):
    _, source, preview, restarted = restore_case
    active = Path(runtime.get_config_file())
    if change == 'source':
        source.write_text(source.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    elif change == 'target':
        config_data = config.load_config()
        config_data['changed_after_preview'] = True
        config.save_config(config_data)
    elif change == 'active':
        app.config['TASK_MANAGER'].task_status['busy'] = {'status': 'running'}
    else:
        app.config['TASK_MANAGER']._configuration_enqueuing = 1
    before = active.read_bytes()
    response = client.post('/api/settings/restore', json={**preview, 'confirm': True})
    assert response.status_code == 409
    assert active.read_bytes() == before
    assert not restarted


def test_restore_is_owner_only_and_settings_never_reveal_config_location_to_remote(client, restore_case):
    old, _, _, _ = restore_case
    assert client.post('/api/settings/restore', json={'folder': str(old)}, environ_base={'REMOTE_ADDR': '10.0.0.5'}).status_code == 403
    remote = client.get('/api/settings', environ_base={'REMOTE_ADDR': '10.0.0.5'}).get_json()
    assert remote['config_file'] is None
    assert remote['config_scope'] is None


def test_restore_rejects_occupied_workspace(app, client, restore_case):
    _, _, preview, restarted = restore_case
    from backend.services.workspace_lock import WorkspaceInstanceLock
    lock = WorkspaceInstanceLock(preview['workspace_folder'])
    lock.acquire()
    before = Path(runtime.get_config_file()).read_bytes()
    try:
        response = client.post('/api/settings/restore', json={**preview, 'confirm': True})
        assert response.status_code == 409
        assert response.get_json()['code'] == 'config_workspace_unavailable'
        assert Path(runtime.get_config_file()).read_bytes() == before
        assert not restarted
    finally:
        lock.release()


def test_restored_access_settings_can_require_login_without_blocking_public_restart_probe(client, restore_case):
    _, source, _, _ = restore_case
    data = json.loads(source.read_text(encoding='utf-8'))
    data['access_control'].update({'enabled': True, 'password_hash': 'test-hash', 'allow_localhost_bypass': False})
    source.write_text(json.dumps(data), encoding='utf-8')
    preview = client.post('/api/settings/restore', json={'folder': str(source.parent)}).get_json()
    old_instance = client.get('/api/auth/status').get_json()['server_instance_id']
    assert client.post('/api/settings/restore', json={**preview, 'confirm': True}).status_code == 200
    new = create_app().test_client()
    status = new.get('/api/auth/status')
    assert status.status_code == 200
    assert status.get_json()['server_instance_id'] != old_instance
    assert status.get_json()['authenticated'] is False
    assert new.get('/api/settings').status_code == 401


def test_config_corruption_fails_closed_for_public_requests_with_origin(app, client):
    path = Path(runtime.get_config_file())
    path.write_text('{broken', encoding='utf-8')
    response = client.get('/api/auth/status', headers={'Origin': 'http://localhost'})
    assert response.status_code == 503
    assert response.get_json()['code'] == 'config_invalid'
    assert 'session_secret' not in response.get_data(as_text=True)
    assert path.read_text(encoding='utf-8') == '{broken'


def test_config_backup_and_temporary_files_cannot_be_served(app, client, monkeypatch):
    outputs = Path(app.config['PATH_CONTEXT'].output_folder)
    data = dict(config.load_config())
    custom = outputs / 'custom-settings.json'
    custom.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setenv('SHARP_CONFIG_FILE', str(custom))
    for name in ('custom-settings.json', 'config.json.lock', 'custom.json.before-restore-test.bak', '.config-secret.tmp'):
        if name != custom.name:
            (outputs / name).write_text('private', encoding='utf-8')
        assert client.get('/files/workspace/outputs/' + name).status_code in (403, 404)

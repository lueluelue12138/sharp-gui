import zipfile

import pytest

from backend.config import normalize_video_reconstruction_config
from backend.services import video_reconstruction
from tools import install_video_reconstruction as installer


@pytest.mark.parametrize('engine', ['auto', 'stable', 'splatfacto'])
def test_saved_engine_preferences_migrate_without_losing_quality(engine):
    config = {'video_reconstruction': {'default_engine': engine, 'default_quality': 'extreme',
                                        'vram_budget': '12gb', 'keep_intermediate_files': True}}
    normalized, changed = normalize_video_reconstruction_config(config)
    assert changed
    assert normalized == {'default_engine': 'brush', 'default_quality': 'extreme',
                          'vram_budget': '12gb', 'keep_intermediate_files': True}


@pytest.mark.parametrize('engine', ['stable', 'splatfacto'])
def test_explicit_retired_engine_requests_fail_before_dependency_probe(engine, monkeypatch):
    monkeypatch.setattr(video_reconstruction, 'get_video_reconstruction_config',
                        lambda: {'default_quality': 'high', 'default_engine': 'brush'})
    options, error, status = video_reconstruction.validate_reconstruction_options({'engine': engine})
    assert options is None
    assert (status, error['field']) == (400, 'engine')


def test_dependency_scan_only_probes_current_route(monkeypatch):
    commands = []
    monkeypatch.setattr(video_reconstruction, 'ensure_local_video_reconstruction_path', lambda: None)
    def fake_version(command, *args, **kwargs):
        commands.append(command)
        return {'name': command, 'available': True, 'version': 'synthetic'}
    monkeypatch.setattr(video_reconstruction, 'command_version', fake_version)
    monkeypatch.setattr(video_reconstruction.brush_engine, 'find_brush_executable', lambda: 'brush_app')
    status = video_reconstruction._scan_dependencies()
    assert commands == ['ffmpeg', 'ffprobe', 'colmap', 'brush_app']
    assert set(status) == {'required', 'brush', 'summary'}
    assert status['summary'] == {'available': True, 'brush_available': True}


def test_installer_migrates_native_files_without_old_python(tmp_path, monkeypatch):
    old = tmp_path / '.video-reconstruction-env'
    (old / 'colmap' / 'bin').mkdir(parents=True)
    (old / 'colmap' / 'bin' / 'colmap.exe').write_bytes(b'native')
    (old / 'colmap' / 'bin' / 'dependency.dll').write_bytes(b'dll')
    (old / 'Scripts').mkdir()
    (old / 'Scripts' / 'ns-train.exe').write_bytes(b'old')
    tools = tmp_path / '.sharp-gui-tools'
    monkeypatch.setattr(installer, 'ROOT', tmp_path)
    monkeypatch.setattr(installer, 'TOOLS_DIR', tools)
    monkeypatch.setattr(installer, 'COLMAP_DIR', tools / 'colmap')
    monkeypatch.setattr(installer, 'verify_colmap', lambda _: 'COLMAP synthetic')
    destination = installer.ensure_colmap()
    assert (destination / 'bin' / 'dependency.dll').read_bytes() == b'dll'
    assert not (tools / 'Scripts').exists()
    assert (old / 'Scripts' / 'ns-train.exe').read_bytes() == b'old'


def test_colmap_archive_cannot_escape_installation_directory(tmp_path):
    archive = tmp_path / 'colmap.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('../outside.txt', 'escape')
    with pytest.raises(ValueError, match='outside'):
        installer.extract_colmap(archive, tmp_path / 'native')
    assert not (tmp_path / 'outside.txt').exists()

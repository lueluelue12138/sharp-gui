from types import SimpleNamespace

import pytest

from backend.services import portable_compatibility as compatibility


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setattr(compatibility, 'sys', SimpleNamespace(platform='win32', version_info=(3, 12, 14)))
    monkeypatch.setattr(compatibility, 'platform', SimpleNamespace(machine=lambda: 'AMD64'))
    monkeypatch.setattr(compatibility.importlib.metadata, 'version', lambda _: '2.8.0+cu128')
    return {'schemaVersion': 1, 'targets': {'cu128-rtx50': {
        'runtimeRevisions': [6, 7], 'pythonMinor': [3, 12], 'torchVersion': '2.8.0+cu128'}}}


@pytest.mark.parametrize('revision', [6, 7])
def test_explicit_supported_original_and_future_packaged_base(policy, tmp_path, revision):
    assert compatibility.validate_policy(policy, ['cu128-rtx50'])
    assert compatibility.compatible(tmp_path, {'target': 'cu128-rtx50', 'portableRuntimeRevision': revision}, policy)


@pytest.mark.parametrize('revision', [4, 5, 8, None])
def test_unverified_or_unknown_baseline_is_not_silently_allowed(policy, tmp_path, revision):
    assert not compatibility.compatible(tmp_path, {'target': 'cu128-rtx50', 'portableRuntimeRevision': revision}, policy)


def test_required_python_and_torch_versions_are_checked(policy, tmp_path, monkeypatch):
    metadata = {'target': 'cu128-rtx50', 'portableRuntimeRevision': 6}
    monkeypatch.setattr(compatibility.importlib.metadata, 'version', lambda _: '2.7.0+cu128')
    assert not compatibility.compatible(tmp_path, metadata, policy)
    monkeypatch.setattr(compatibility.importlib.metadata, 'version', lambda _: '2.8.0+cu128')
    monkeypatch.setattr(compatibility, 'sys', SimpleNamespace(platform='win32', version_info=(3, 13, 0)))
    assert not compatibility.compatible(tmp_path, metadata, policy)


def test_video_base_requires_the_fixed_native_tools(policy, tmp_path):
    profile = policy['targets'].pop('cu128-rtx50')
    policy['targets']['cu128-rtx50-video-recon'] = profile
    metadata = {'target': 'cu128-rtx50-video-recon', 'portableRuntimeRevision': 6}
    assert not compatibility.compatible(tmp_path, metadata, policy)
    for name in ('.sharp-gui-tools/brush/ooo-v1.0.0/brush-cli.exe',
                 '.sharp-gui-tools/colmap/bin/colmap.exe', 'tools/ffmpeg/bin/ffmpeg.exe'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'native marker')
    assert compatibility.compatible(tmp_path, metadata, policy)

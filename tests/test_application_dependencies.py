import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import application_dependencies as deps


def wheel_contract(version='1.0', extra=None):
    payload = io.BytesIO()
    info = f'example_dep-{version}.dist-info'
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr(zipfile.ZipInfo('example_dep/__init__.py'), f"__version__ = '{version}'\n")
        archive.writestr(zipfile.ZipInfo(f'{info}/WHEEL'), 'Root-Is-Purelib: true\nTag: py3-none-any\n')
        archive.writestr(zipfile.ZipInfo(f'{info}/METADATA'), f'Name: example-dep\nVersion: {version}\n')
        for name, contents in (extra or {}).items():
            entry = zipfile.ZipInfo()
            entry.filename = name
            archive.writestr(entry, contents)
    data = payload.getvalue()
    filename = f'example_dep-{version}-py3-none-any.whl'
    lock = {'schemaVersion': 1, 'packages': [{
        'name': 'example-dep', 'version': version, 'filename': filename,
        'url': f'https://files.pythonhosted.org/packages/test/{filename}',
        'sha256': hashlib.sha256(data).hexdigest(), 'imports': ['example_dep'],
        'requires': [], 'pythonMinimum': [3, 10],
    }]}
    return lock, data


def install_contract(root, lock):
    (root / 'update-manifest.json').write_text(json.dumps({'applicationDependencies': {
        'lockFile': deps.LOCK_FILE, 'sha256': deps.digest(lock)}}), encoding='utf-8')
    (root / deps.LOCK_FILE).write_text(json.dumps(lock), encoding='utf-8')


def test_prepare_activate_and_consecutive_versions_without_system_package(tmp_path):
    base_marker = tmp_path / 'python' / 'base-marker'
    base_marker.parent.mkdir()
    base_marker.write_bytes(b'unchanged base')
    results = []
    for version in ('1.0', '2.0', '1.0'):
        lock, data = wheel_contract(version)
        install_contract(tmp_path, lock)
        paths = deps.prepare(tmp_path, lock, downloader=lambda package: data)
        assert len(paths) == 1
        # 全新解释器与只读加载器验证升级、降级，不借用测试进程已导入的模块。
        root = str(Path(deps.__file__).parent)
        script = ('import sys; sys.path.insert(0,sys.argv[1]); '
                  'import application_dependencies as d; d.activate(sys.argv[2]); '
                  'import example_dep; print(example_dep.__version__)')
        result = subprocess.run([sys.executable, '-I', '-c', script, root, str(tmp_path)],
                                capture_output=True, text=True, check=True)
        results.append(result.stdout.strip())
    assert results == ['1.0', '2.0', '1.0']
    assert base_marker.read_bytes() == b'unchanged base'
    assert len(list((tmp_path / '.sharp-gui-update/dependencies/sets').iterdir())) == 2


def test_exact_verified_cache_is_reused_without_network(tmp_path):
    lock, data = wheel_contract()
    first = deps.prepare(tmp_path, lock, downloader=lambda _: data)
    assert deps.prepare(tmp_path, lock, downloader=lambda _: pytest.fail('downloaded cached wheel')) == first


@pytest.mark.parametrize('path', ['../outside.py', '/outside.py', 'example_dep/a.pth',
                                  'example_dep/a.dll', 'sitecustomize.py', 'example_dep/a\\b.py'])
def test_unsafe_wheel_never_becomes_importable(tmp_path, path):
    lock, data = wheel_contract(extra={path: 'bad'})
    with pytest.raises(deps.DependencyError, match='integrity'):
        deps.prepare(tmp_path, lock, downloader=lambda _: data)
    assert not (tmp_path / 'outside.py').exists()
    assert list((tmp_path / '.sharp-gui-update/dependencies/sets').iterdir()) == []


def test_failed_download_preserves_previous_dependency_set(tmp_path):
    previous, data = wheel_contract()
    deps.prepare(tmp_path, previous, downloader=lambda _: data)
    target, _ = wheel_contract('2.0')
    with pytest.raises(deps.DependencyError):
        deps.prepare(tmp_path, target, downloader=lambda _: b'incorrect digest')
    assert deps.verified_paths(tmp_path, previous)
    with pytest.raises(deps.DependencyError, match='not_ready'):
        deps.verified_paths(tmp_path, target)


@pytest.mark.parametrize('field,value', [('imports', ['sys']), ('imports', ['torch']),
                                        ('version', '>=1.0'), ('requires', ['missing-package']),
                                        ('filename', '../outside.whl'), ('url', 'http://files.pythonhosted.org/a')])
def test_invalid_or_unlocked_dependency_is_rejected(field, value):
    lock, _ = wheel_contract()
    lock['packages'][0][field] = value
    with pytest.raises(deps.DependencyError):
        deps.validate_lock(lock, deps.digest(lock))


def test_loading_is_read_only_and_missing_set_does_not_fall_back(tmp_path, monkeypatch):
    lock, _ = wheel_contract()
    install_contract(tmp_path, lock)
    monkeypatch.setattr(deps, 'download', lambda _: pytest.fail('import downloaded a package'))
    with pytest.raises(deps.DependencyError, match='not_ready'):
        deps.activate(tmp_path)
    assert not (tmp_path / '.sharp-gui-update').exists()


def test_hash_and_completeness_marker_are_checked_on_every_load(tmp_path):
    lock, data = wheel_contract()
    path = Path(deps.prepare(tmp_path, lock, downloader=lambda _: data)[0])
    path.write_bytes(data + b'tampered')
    with pytest.raises(deps.DependencyError, match='integrity'):
        deps.verified_paths(tmp_path, lock)


def test_repository_lock_is_exact_and_matches_manifest():
    root = Path(deps.__file__).parent
    lock = deps.load_contract(root)
    assert lock['packages'][0]['version'] == '1.8.0'
    assert lock['packages'][0]['requires'] == []


def test_download_uses_explicit_verified_tls_context(monkeypatch):
    contexts = []
    monkeypatch.setattr(deps.ssl, '_create_default_https_context', deps.ssl._create_unverified_context)

    def inspect_opener(*handlers):
        contexts.append(handlers[1]._context)
        raise OSError('test avoids network')

    monkeypatch.setattr(deps, 'build_opener', inspect_opener)
    lock, _ = wheel_contract()
    with pytest.raises(deps.DependencyError, match='download_failed'):
        deps.download(lock['packages'][0])
    assert contexts[0].verify_mode == deps.ssl.CERT_REQUIRED
    assert contexts[0].check_hostname


def test_unconditional_transitive_dependency_must_match_lock(tmp_path):
    lock, data = wheel_contract()
    modified = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(modified, 'w') as target:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith('/METADATA'):
                content += b'Requires-Dist: undeclared-dependency>=1\n'
            target.writestr(name, content)
    payload = modified.getvalue()
    lock['packages'][0]['sha256'] = hashlib.sha256(payload).hexdigest()
    with pytest.raises(deps.DependencyError, match='lock_invalid'):
        deps.prepare(tmp_path, lock, downloader=lambda _: payload)

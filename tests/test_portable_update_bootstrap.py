import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import application_dependencies as deps
from backend.services import self_update
from tools import build_update_bootstrap, portable_update_bootstrap
from test_application_dependencies import wheel_contract


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], check=True,
                            capture_output=True, text=True, encoding='utf-8')
    return result.stdout.strip()


def commit(root, message):
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')


@pytest.fixture
def installation(tmp_path, monkeypatch):
    source, bare, install = (tmp_path / name for name in ('source', 'remote.git', 'install'))
    source.mkdir()
    git(source, 'init', '-q', '--initial-branch=main')
    git(source, 'config', 'user.name', 'Update Tests')
    git(source, 'config', 'user.email', 'tests@example.invalid')
    git(source, 'config', 'core.autocrlf', 'false')
    git(source, 'config', 'commit.gpgSign', 'false')
    for folder in ('backend/routes', 'backend/services', 'tools', 'frontend/dist'):
        (source / folder).mkdir(parents=True, exist_ok=True)
    for filename in ('backend/__init__.py', 'backend/services/__init__.py'):
        (source / filename).write_text('')
    for filename in ('app.py', 'backend/app_factory.py', 'backend/routes/__init__.py', 'tools/update.py'):
        (source / filename).write_text("VALUE = 'base'\n")
    (source / 'frontend/dist/index.html').write_text('<html>base</html>')
    (source / 'version.txt').write_text('v1.0.0\n')
    (source / '.gitignore').write_text('.sharp-gui-update/\n.sharp-gui-upgrade/\npython/\nportable-package.json\n__pycache__/\n')
    manifest = {
        'schemaVersion': 1, 'application': 'sharp-gui',
        'repository': {'slug': self_update.CANONICAL_REPOSITORY_SLUG},
        'defaultBranch': 'main', 'updateProtocolRevision': 1, 'portableRuntimeRevision': 6,
        'minimumGitVersion': '2.30.0', 'supportedPortableTargets': ['cu128-rtx50'],
        'frontend': {'builtAssetsRequired': True, 'entrypoint': 'frontend/dist/index.html'},
    }
    (source / 'update-manifest.json').write_text(json.dumps(manifest))
    base_sha = commit(source, 'base')
    git(source, 'tag', 'v1.0.0')
    subprocess.run(['git', 'clone', '--bare', str(source), str(bare)], check=True, capture_output=True)
    subprocess.run(['git', 'clone', str(bare), str(install)], check=True, capture_output=True)
    (install / 'python').mkdir()
    (install / 'python/python.exe').write_bytes(b'portable interpreter marker')
    metadata = {'target': 'cu128-rtx50', 'portableRuntimeRevision': 6, 'updateProtocolRevision': 1,
                'sourceRevision': base_sha}
    (install / 'portable-package.json').write_text(json.dumps(metadata))
    monkeypatch.setattr(self_update, 'CANONICAL_REPOSITORY_URL', str(bare))
    monkeypatch.setattr(self_update, 'resolve_git_executable', lambda _: shutil.which('git'))
    # 此处为合成环境的事务测试；真实 Python/Torch/三 target 的验证独立记录。
    monkeypatch.setattr(self_update.portable_compatibility, 'compatible', lambda *_: True)
    payloads = {}
    monkeypatch.setattr(deps, 'download', lambda package: payloads[package['sha256']])

    def publish(version, *, broken=False, remove=False):
        target = dict(manifest, portableRuntimeRevision=7)
        target['portableCompatibility'] = {'schemaVersion': 1, 'targets': {'cu128-rtx50': {
            'runtimeRevisions': [6], 'pythonMinor': [3, 12], 'torchVersion': '2.8.0+cu128'}}}
        shutil.copyfile(deps.__file__, source / 'application_dependencies.py')
        if not remove:
            lock, data = wheel_contract(version)
            payloads[lock['packages'][0]['sha256']] = data
            target['applicationDependencies'] = {'lockFile': deps.LOCK_FILE, 'sha256': deps.digest(lock)}
            (source / deps.LOCK_FILE).write_text(json.dumps(lock))
            code = ('from application_dependencies import activate\nfrom pathlib import Path\n'
                    'activate(Path(__file__).resolve().parents[1])\nimport example_dep\n')
        else:
            code = "VALUE = 'no overlay'\n"
        if broken:
            code += "raise RuntimeError('injected failure')\n"
        (source / 'backend/app_factory.py').write_text(code)
        (source / 'update-manifest.json').write_text(json.dumps(target))
        sha = commit(source, f'target {version} {broken} {remove}')
        git(source, 'push', str(bare), 'main')
        return sha, target

    def apply():
        manager = self_update.SelfUpdateManager(base_dir=install)
        manager.check('latest', is_owner=True)
        candidate = self_update.load_update_state(install)['channels']['latest']
        operation = self_update.prepare_cli_operation(install, 'latest', candidate)
        success = self_update.run_update_operation(install, operation['id'], wait_for_server=False, relaunch=False)
        return success, self_update.load_update_state(install)['operation']

    return source, install, manifest, publish, apply


def test_old_gate_then_multiple_dependency_updates_rollback_removal_and_downgrade(installation):
    source, install, original, publish, apply = installation
    provenance = (install / 'portable-package.json').read_bytes()
    sha_a, target = publish('1.0')
    old_contract = dict(target)
    old_contract.pop('portableCompatibility')
    assert self_update.compare_manifest_compatibility(install, old_contract) == (False, 'update_full_package_required')
    assert apply()[0]
    assert git(install, 'rev-parse', 'HEAD') == sha_a
    sha_b, _ = publish('2.0')
    assert apply()[0]
    broken, _ = publish('3.0', broken=True)
    success, operation = apply()
    assert not success and operation['rolled_back']
    assert git(install, 'rev-parse', 'HEAD') == sha_b
    assert deps.load_contract(install)['packages'][0]['version'] == '2.0'
    removed, _ = publish('4.0', remove=True)
    assert apply()[0]
    assert deps.load_contract(install) is None
    git(source, 'reset', '--hard', sha_a)
    git(source, 'push', '--force', str(self_update.CANONICAL_REPOSITORY_URL), 'main')
    assert apply()[0]
    assert deps.load_contract(install)['packages'][0]['version'] == '1.0'
    assert (install / 'portable-package.json').read_bytes() == provenance
    assert len(list((install / '.sharp-gui-update/dependencies/sets').iterdir())) == 3


def test_failed_preparation_does_not_stop_or_replace_working_application(installation, monkeypatch):
    _, install, _, publish, _ = installation
    previous = git(install, 'rev-parse', 'HEAD')
    publish('1.0')
    manager = self_update.SelfUpdateManager(base_dir=install)
    manager.check('latest')
    candidate = self_update.load_update_state(install)['channels']['latest']
    operation = self_update.prepare_cli_operation(install, 'latest', candidate)
    state = self_update.load_update_state(install)
    state['operation'].update(_defer_stop=True, _server_pid=123456)
    self_update.save_update_state(install, state)
    monkeypatch.setattr(deps, 'download', lambda _: (_ for _ in ()).throw(deps.DependencyError('update_dependency_download_failed')))
    monkeypatch.setattr(self_update, 'wait_for_process_exit', lambda *_: pytest.fail('stopped service before dependencies ready'))
    monkeypatch.setattr(self_update, 'launch_application', lambda *_: pytest.fail('restarted working service'))
    assert not self_update.run_update_operation(install, operation['id'])
    assert git(install, 'rev-parse', 'HEAD') == previous
    assert self_update.load_update_state(install)['operation']['error_code'] == 'update_dependency_download_failed'


def test_interrupted_broken_target_restores_matching_previous_set(installation):
    _, install, _, publish, apply = installation
    previous, _ = publish('1.0')
    assert apply()[0]
    target, _ = publish('2.0', broken=True)
    manager = self_update.SelfUpdateManager(base_dir=install)
    manager.check('latest')
    candidate = self_update.load_update_state(install)['channels']['latest']
    operation = self_update.prepare_cli_operation(install, 'latest', candidate)
    git(install, 'reset', '--hard', target)
    state = self_update.load_update_state(install)
    state['operation']['phase'] = 'applying'
    self_update.save_update_state(install, state)
    assert self_update.recover_interrupted_operation(install)
    assert git(install, 'rev-parse', 'HEAD') == previous
    assert deps.verified_paths(install, deps.load_contract(install))


def test_upgrade_bundle_contains_only_versioned_stdlib_helper_and_valid_digests(tmp_path):
    archive_path = build_update_bootstrap.build(tmp_path, working_tree=True)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('.sharp-gui-upgrade/tool.json'))
        for filename, checksum in manifest['files'].items():
            assert hashlib.sha256(archive.read('.sharp-gui-upgrade/' + filename)).hexdigest() == checksum
        assert 'upgrade-portable.bat' in archive.namelist()
        assert not any('/python/' in name for name in archive.namelist())
    assert archive_path.stat().st_size < 100_000


def test_interrupted_preparation_does_not_reset_later_local_edits(installation):
    _, install, _, publish, _ = installation
    publish('1.0')
    manager = self_update.SelfUpdateManager(base_dir=install)
    manager.check('latest')
    candidate = self_update.load_update_state(install)['channels']['latest']
    self_update.prepare_cli_operation(install, 'latest', candidate)
    state = self_update.load_update_state(install)
    state['operation']['phase'] = 'preparing_dependencies'
    self_update.save_update_state(install, state)
    edited = install / 'app.py'
    edited.write_text('LOCAL_WORK = True\n')
    with pytest.raises(self_update.UpdateError, match='worktree_dirty'):
        self_update.recover_interrupted_operation(install)
    assert edited.read_text() == 'LOCAL_WORK = True\n'


@pytest.mark.parametrize('active', [False, True])
def test_deferred_shutdown_rechecks_work_before_stopping(tmp_path, monkeypatch, active):
    events = []
    manager = self_update.SelfUpdateManager(base_dir=tmp_path, restart_callback=lambda: events.append('stop'),
                                           active_work_callback=lambda: active)
    state = self_update.default_update_state()
    state['operation'] = {'id': 'ready', 'phase': 'waiting_for_server', 'previous_sha': 'a' * 40}
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(self_update, 'get_installed_identity', lambda *_: {
        'commit': 'a' * 40, 'managed': True, 'dirty': False, 'installation_kind': 'source', 'branch': 'main'})
    manager._wait_for_preparation('ready')
    assert events == ([] if active else ['stop'])
    if active:
        assert self_update.load_update_state(tmp_path)['operation']['error_code'] == 'update_tasks_active'


def test_bootstrap_refuses_running_service_and_dirty_installation(monkeypatch, tmp_path):
    monkeypatch.setattr(portable_update_bootstrap, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(portable_update_bootstrap, 'verify_tool', lambda: None)
    monkeypatch.setattr(self_update, 'get_installed_identity', lambda _: {
        'installation_kind': 'portable', 'managed': True, 'dirty': False})
    monkeypatch.setattr(portable_update_bootstrap, 'server_running', lambda: True)
    assert portable_update_bootstrap.main(['--yes']) == 2
    monkeypatch.setattr(self_update, 'get_installed_identity', lambda _: {
        'installation_kind': 'portable', 'managed': True, 'dirty': True})
    assert portable_update_bootstrap.main(['--yes']) == 1

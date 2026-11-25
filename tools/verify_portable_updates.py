"""对专用临时目录中的真实旧包验证升级链，不接触工作安装或公开 Git refs。

先将三种 runtime 6 包分别解压到 %TEMP%/sharp-update-check/{core,cu126,video}。
验证使用本地 bare fixture 和包内 Python/MinGit，公开仓库和主线不变。
"""

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen
import ssl

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import application_dependencies as deps
from tools.build_update_bootstrap import build


def git(*args, env=None, data=None):
    result = subprocess.run(['git', '-C', str(ROOT), *args], input=data,
                            capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result.stdout.decode('utf-8').strip()


def commit_tree(tree, parent):
    return git('-c', 'user.name=OpenAI Codex', '-c', 'user.email=codex@openai.com',
               'commit-tree', tree, '-p', parent, data=b'test(update): isolated portable verification snapshot\n')


def make_snapshot(directory, base='HEAD', changes=None):
    env = os.environ.copy()
    env['GIT_INDEX_FILE'] = str(directory / 'index')
    git('read-tree', base, env=env)
    if changes is None:
        git('add', '-A', env=env)
    else:
        for name, content in changes.items():
            blob = git('hash-object', '-w', '--stdin', data=content)
            git('update-index', '--add', '--cacheinfo', f'100644,{blob},{name}', env=env)
    return commit_tree(git('write-tree', env=env), git('rev-parse', base))


def file_hash(path):
    checksum = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def base_markers(package):
    selected = [package / 'portable-package.json']
    for relative in ('python', '.sharp-gui-tools', '.cache', 'tools/ffmpeg', 'workspace-smoke'):
        root = package / relative
        if root.is_dir():
            selected.extend(path for path in root.rglob('*')
                            if path.is_file() and '__pycache__' not in path.parts
                            and path.suffix not in {'.pyc', '.log'})
    critical = {'portable-package.json', 'python/python.exe',
                'python/Lib/site-packages/torch/__init__.py',
                'python/Lib/site-packages/flask/__init__.py',
                'workspace-smoke/preserve-marker.txt'}
    result = {}
    for path in selected:
        name = str(path.relative_to(package)).replace('\\', '/')
        info = path.stat()
        result[name] = {'bytes': info.st_size, 'modified': info.st_mtime_ns}
        if name in critical:
            result[name]['sha256'] = file_hash(path)
    return result


def run(package, script, *args, check=True):
    env = os.environ.copy()
    env.update(PATH=str(package / 'python'), PYTHONIOENCODING='utf-8',
               SHARP_CONFIG_HOME=str(package / '.sharp-gui-update/smoke-config'),
               SHARP_CONFIG_FILE=str(package / '.sharp-gui-update/smoke-config/config.json'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    result = subprocess.run([str(package / 'python/python.exe'), '-I', str(script), *args],
                            cwd=package, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=240)
    if check and result.returncode:
        raise RuntimeError(f'{package.name} verification failed: {result.stdout}\n{result.stderr}')
    return result


def main():
    scratch = Path(tempfile.gettempdir()).resolve() / 'sharp-update-check'
    if not (scratch / '.verification-owned').is_file():
        raise RuntimeError('Refusing to modify directories without the dedicated verification ownership marker')
    artifacts = ROOT / '.sharp-gui-update/verification'
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=artifacts) as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(artifacts.resolve())
        snapshot = make_snapshot(directory)
        bundle = build(directory, snapshot)
        manifest = json.loads(git('show', f'{snapshot}:update-manifest.json'))
        lock = json.loads(git('show', f'{snapshot}:{deps.LOCK_FILE}'))
        with urlopen('https://pypi.org/pypi/websocket-client/1.9.0/json',
                     context=ssl.create_default_context(), timeout=30) as response:
            release = json.load(response)
        wheel = next(item for item in release['urls'] if item['filename'].endswith('-py3-none-any.whl'))
        upgraded_lock = json.loads(json.dumps(lock))
        upgraded_lock['packages'][0].update(version='1.9.0', filename=wheel['filename'],
                                             url=wheel['url'], sha256=wheel['digests']['sha256'])
        upgraded_manifest = dict(manifest, applicationDependencies={
            'lockFile': deps.LOCK_FILE, 'sha256': deps.digest(upgraded_lock)})
        version_a = make_snapshot(directory, snapshot, {
            deps.LOCK_FILE: json.dumps(upgraded_lock).encode(),
            'update-manifest.json': json.dumps(upgraded_manifest).encode(),
            'update-transition-fixture.txt': b'test version A\n'})
        version_b = make_snapshot(directory, snapshot, {'update-transition-fixture.txt': b'test version B\n'})
        broken = make_snapshot(directory, version_a, {'backend/app_factory.py': (
            git('show', f'{version_a}:backend/app_factory.py') +
            "\nraise RuntimeError('portable recovery verification fixture')\n").encode()})
        bare = directory / 'remote.git'
        git('init', '--bare', '--initial-branch=main', str(bare))
        git('-C', str(bare), 'config', 'receive.shallowUpdate', 'true')
        git('push', str(bare), f'{snapshot}:refs/heads/main')
        git('-C', str(bare), 'update-ref', 'refs/tags/v99.0.0', snapshot)
        driver = '''import sys
from pathlib import Path
root = Path.cwd()
phase, remote = sys.argv[1:3]
sys.path.insert(0, str(root / '.sharp-gui-upgrade') if phase == 'bootstrap' else str(root))
from backend.services import self_update
self_update.CANONICAL_REPOSITORY_URL = remote
if phase == 'bootstrap':
    import bootstrap
    # 这里只忽略其他安装占用的主机端口。此测试副本无服务，绝不停止其他实例。
    bootstrap.server_running = lambda: False
    raise SystemExit(bootstrap.main(['--channel', 'latest', '--yes']))
from tools import update
update.local_server_is_running = lambda: False
raise SystemExit(update.main(['--channel', 'stable' if phase == 'stable' else 'latest', '--yes']))
'''
        health_code = '''import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from backend.app_factory import create_app
from application_dependencies import load_contract
import importlib.metadata
app = create_app()
with app.test_client() as client:
    assert client.get('/').status_code == 200
    assert client.get('/api/updates/status').status_code == 200
    assert client.get('/api/portrait/status').status_code == 200
assert importlib.metadata.version('websocket-client') == load_contract(Path.cwd())['packages'][0]['version']
print('application and dependency health verified')
'''
        rows = []
        expected_hashes = json.loads((scratch / 'archive-checksums.json').read_text(encoding='utf-8-sig'))
        checksums = {Path(row['Path']).name: row['Hash'].lower() for row in expected_hashes}
        for folder, target in (('core', 'cu128-rtx50'), ('cu126', 'cu126-mainstream'),
                               ('video', 'cu128-rtx50-video-recon')):
            package = (scratch / folder).resolve()
            assert package.is_relative_to(scratch) and package.name == folder
            metadata = json.loads((package / 'portable-package.json').read_text(encoding='utf-8-sig'))
            assert metadata['portableRuntimeRevision'] == 6 and metadata['target'] == target
            # 专用测试副本可重复使用；每轮先恢复真实归档的原始代码基线。
            git('-C', str(package), 'reset', '--hard', metadata['sourceRevision'])
            workspace = package / 'workspace-smoke'
            workspace.mkdir(exist_ok=True)
            (workspace / 'preserve-marker.txt').write_bytes(b'workspace/model/input marker')
            config = package / '.sharp-gui-update/smoke-config'
            config.mkdir(parents=True, exist_ok=True)
            (config / 'config.json').write_text(json.dumps({'workspace_folder': str(workspace)}))
            print(f'{target}: recording base inventory', flush=True)
            before = base_markers(package)
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(package)
            script = package / '.sharp-gui-update/smoke_driver.py'
            script.write_text(driver, encoding='utf-8')
            health = package / '.sharp-gui-update/smoke_health.py'
            health.write_text(health_code, encoding='utf-8')
            git('push', '--force', str(bare), f'{snapshot}:refs/heads/main')
            print(f'{target}: bootstrap', flush=True)
            run(package, script, 'bootstrap', str(bare))
            run(package, health)
            for version in (version_a, version_b):
                git('push', '--force', str(bare), f'{version}:refs/heads/main')
                run(package, script, 'latest', str(bare))
                run(package, health)
            git('push', '--force', str(bare), f'{broken}:refs/heads/main')
            failure = run(package, script, 'latest', str(bare), check=False)
            assert failure.returncode == 1
            state = json.loads((package / '.sharp-gui-update/state.json').read_text())
            assert state['operation']['rolled_back'] is True
            run(package, health)
            run(package, script, 'stable', str(bare))
            run(package, health)
            assert base_markers(package) == before
            row = {'target': target, 'runtimeRevision': 6,
                   'archiveSha256': checksums[f'sharp-gui-v2.0.0-windows-{target}-portable.7z'],
                   'bootstrap': True, 'subsequentUpdates': True, 'downgrade': True,
                   'rollback': True, 'basePreserved': True, 'health': True,
                   'baseFilesVerified': len(before),
                   'baseVerificationMethod': 'Complete size/mtime inventory excluding bytecode; SHA256 of provenance, Python, Torch/Flask entry modules and workspace marker'}
            rows.append(row)
            (artifacts / 'portable-transition-progress.json').write_text(json.dumps(rows, indent=2))
            print(f'{target}: all transitions and {len(before)} base files verified', flush=True)
        report = json.loads((ROOT / 'docs/update-verification.json').read_text())
        report.update(status='passed', testedSnapshot=snapshot, packages=rows,
                      fixtureScope='Local bare remote and synthetic channel refs; no public branches/tags modified')
        tested = ('application_dependencies.py', 'backend/services/self_update.py',
                  'backend/services/portable_compatibility.py', 'tools/update.py',
                  'tools/portable_update_bootstrap.py', 'backend/app_factory.py',
                  'backend/routes/__init__.py', 'app.py', 'update-manifest.json')
        report['testedFiles'] = {}
        for name in tested:
            blob = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{snapshot}:{name}'])
            report['testedFiles'][name] = hashlib.sha256(blob).hexdigest()
        (ROOT / 'docs/update-verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()

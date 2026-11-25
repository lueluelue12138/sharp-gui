"""生成仅包含标准库 helper 的小型升级包，不构建 Python/CUDA 便携环境。"""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build(output_dir, revision=None, *, working_tree=False):
    revision = revision or subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    def source_file(name):
        if working_tree:
            return (ROOT / name).read_bytes()
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{revision}:{name}'])

    files = {
        'bootstrap.py': source_file('tools/portable_update_bootstrap.py'),
        'application_dependencies.py': source_file('application_dependencies.py'),
        'backend/__init__.py': b'',
        'backend/services/__init__.py': b'',
        'backend/services/self_update.py': source_file('backend/services/self_update.py'),
        'backend/services/portable_compatibility.py': source_file('backend/services/portable_compatibility.py'),
    }
    manifest = {'schemaVersion': 1, 'repository': 'lueluelue12138/sharp-gui',
                'sourceRevision': revision, 'developmentSnapshot': working_tree,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    archive_path = output_dir / 'sharp-gui-update-tool.zip'
    launcher = ('@echo off\r\nchcp 65001 >nul 2>&1\r\nsetlocal\r\nset "PYTHONIOENCODING=utf-8"\r\n'
                'if not exist "%~dp0python\\python.exe" (\r\n'
                ' echo Put these files in the existing portable folder.\r\n pause\r\n exit /b 1\r\n)\r\n'
                '"%~dp0python\\python.exe" -I "%~dp0.sharp-gui-upgrade\\bootstrap.py" %*\r\n'
                'set "UPDATE_EXIT=%ERRORLEVEL%"\r\npause\r\nexit /b %UPDATE_EXIT%\r\n')
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('upgrade-portable.bat', launcher)
        archive.writestr('UPGRADE-README.txt',
                         'Close Sharp GUI. Extract into your existing managed portable folder.\n'
                         'Run upgrade-portable.bat. Use --channel latest for main.\n'
                         'Check SHA256 against the canonical Release before use.\n'
                         'Existing Python/CUDA, models and user data are preserved.\n\n'
                         '先正常关闭 Sharp GUI，将本包解压到已有受管便携包目录。\n'
                         '运行 upgrade-portable.bat，可用 --channel latest 选择主线。\n'
                         '运行前请核对正式 Release 提供的 SHA256。保留原环境、模型与用户数据。\n')
        for name, data in files.items():
            archive.writestr(f'.sharp-gui-upgrade/{name}', data)
        archive.writestr('.sharp-gui-upgrade/tool.json', json.dumps(manifest, indent=2))
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.sha256.txt').write_text(f'{checksum}  {archive_path.name}\n', encoding='utf-8')
    return archive_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default=str(ROOT / 'portable-dist' / 'update-tool'))
    args = parser.parse_args()
    print(build(args.output_dir))

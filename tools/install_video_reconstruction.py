#!/usr/bin/env python3
"""安装 Windows 视频路线所需的原生 COLMAP 与固定版本 Brush。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.install_brush import install_brush
TOOLS_DIR = ROOT / '.sharp-gui-tools'
COLMAP_DIR = TOOLS_DIR / 'colmap'
COLMAP_VERSION = '4.0.4'
COLMAP_URL = f'https://github.com/colmap/colmap/releases/download/{COLMAP_VERSION}/colmap-x64-windows-cuda.zip'


def verify_colmap(directory: Path) -> str:
    executable = directory / 'bin' / 'colmap.exe'
    result = subprocess.run([str(executable), '-h'], check=True, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=30)
    return (result.stdout + result.stderr).splitlines()[0]


def extract_colmap(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            target = (root / entry.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError('COLMAP archive contains a path outside its destination')
        archive.extractall(root)


def ensure_colmap() -> Path:
    if (COLMAP_DIR / 'bin' / 'colmap.exe').is_file():
        print(f'[OK] {verify_colmap(COLMAP_DIR)}', flush=True)
        return COLMAP_DIR
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    # 只迁移已验证的原生程序，保持重建结果；不复制旧 Python 环境。
    legacy_native = ROOT / '.video-reconstruction-env' / 'colmap'
    with tempfile.TemporaryDirectory(prefix='colmap-install-', dir=TOOLS_DIR) as temporary:
        staging = Path(temporary) / 'colmap'
        if (legacy_native / 'bin' / 'colmap.exe').is_file():
            version = verify_colmap(legacy_native)
            shutil.copytree(legacy_native, staging)
            provenance = {'source': 'existing-native-installation', 'version': version}
        else:
            archive = Path(temporary) / 'colmap.zip'
            print(f'[INFO] Downloading COLMAP {COLMAP_VERSION}', flush=True)
            urllib.request.urlretrieve(COLMAP_URL, archive)
            staging.mkdir()
            extract_colmap(archive, staging)
            provenance = {'source': COLMAP_URL, 'version': verify_colmap(staging)}
        verify_colmap(staging)
        (staging / 'INSTALLATION.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
        if COLMAP_DIR.exists():
            raise RuntimeError(f'Incomplete installation at {COLMAP_DIR}; inspect it before retrying')
        staging.rename(COLMAP_DIR)
    return COLMAP_DIR


def main() -> int:
    if os.name != 'nt':
        print('[INFO] On Linux/macOS install COLMAP and FFmpeg with your package manager, then run tools/install_brush.py.')
        return 0
    try:
        colmap = ensure_colmap()
        brush = install_brush()
        print(f'[OK] Video reconstruction ready: COLMAP={colmap}, Brush={brush}', flush=True)
        print('[INFO] FFmpeg and ffprobe are provided by install.bat or the full video portable package.', flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f'[ERROR] Video dependencies could not be installed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

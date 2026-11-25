"""基础运行环境的显式兼容规则，读取元数据而不导入 Torch 或启动子进程。"""

import importlib.metadata
import platform
import sys
from pathlib import Path


def validate_policy(policy, targets):
    if not isinstance(policy, dict) or set(policy) != {'schemaVersion', 'targets'}:
        return False
    profiles = policy['targets']
    if policy['schemaVersion'] != 1 or not isinstance(profiles, dict) or set(profiles) != set(targets):
        return False
    for target, profile in profiles.items():
        if (not isinstance(profile, dict)
                or set(profile) != {'runtimeRevisions', 'pythonMinor', 'torchVersion'}
                or not isinstance(profile['runtimeRevisions'], list) or not profile['runtimeRevisions']
                or not all(type(value) is int and value > 0 for value in profile['runtimeRevisions'])
                or not isinstance(profile['pythonMinor'], list) or len(profile['pythonMinor']) != 2
                or not all(type(value) is int and value >= 0 for value in profile['pythonMinor'])
                or not isinstance(profile['torchVersion'], str)):
            return False
    return True


def compatible(base_dir, metadata, policy):
    profile = policy['targets'].get(metadata.get('target'))
    revision = metadata.get('portableRuntimeRevision', metadata.get('portable_runtime_revision'))
    if profile is None or revision not in profile['runtimeRevisions']:
        return False
    if (sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}
            or list(sys.version_info[:2]) != profile['pythonMinor']):
        return False
    try:
        if importlib.metadata.version('torch') != profile['torchVersion']:
            return False
    except importlib.metadata.PackageNotFoundError:
        return False
    if metadata.get('target') == 'cu128-rtx50-video-recon':
        root = Path(base_dir)
        if not all((root / relative).is_file() for relative in (
                '.sharp-gui-tools/brush/ooo-v1.0.0/brush-cli.exe',
                '.sharp-gui-tools/colmap/bin/colmap.exe', 'tools/ffmpeg/bin/ffmpeg.exe')):
            return False
    return True

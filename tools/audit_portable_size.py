"""只读盘点明确指定的组件或 ZIP 元数据；不解压、不下载、不清理。"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import zipfile
from collections import defaultdict
from pathlib import Path


def _is_link(metadata):
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, 'st_file_attributes', 0) & 0x400)


def _bucket():
    return {'files': 0, 'logical_bytes': 0, 'compressed_payload_bytes': 0}


def _add(bucket, size, compressed=0, is_file=True):
    bucket['files'] += int(is_file)
    bucket['logical_bytes'] += size
    bucket['compressed_payload_bytes'] += compressed


def audit_components(components):
    """只统计明确选择的文件/目录，不自动遍历整个安装或媒体目录。"""
    roots = []
    for label, value in components:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', label) or any(label == old[0] for old in roots):
            raise ValueError('Use unique component labels containing letters, digits, _ or -')
        path = Path(value).absolute()
        metadata = path.lstat()
        if _is_link(metadata) or not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
            raise ValueError('Component roots must be regular files or directories, not links')
        resolved = os.path.normcase(os.path.realpath(path))
        for _, _, previous in roots:
            try:
                common = os.path.commonpath([resolved, previous])
            except ValueError:
                # 不同 Windows 盘符不可能重叠。
                continue
            if common in (resolved, previous):
                raise ValueError('Component roots overlap; choose disjoint paths')
        roots.append((label, path, resolved))
    result = {'mode': 'components', 'scope': 'selected_components_only', 'complete': True, 'components': {}}
    for label, root, _ in roots:
        summary = {'files': 0, 'logical_bytes': 0, 'skipped_links': 0, 'skipped_special': 0, 'errors': 0, 'largest_files_bytes': []}
        stack = [root]
        while stack:
            path = stack.pop()
            try:
                metadata = path.lstat()
                if _is_link(metadata):
                    summary['skipped_links'] += 1
                elif stat.S_ISDIR(metadata.st_mode):
                    with os.scandir(path) as entries:
                        stack.extend(Path(entry.path) for entry in entries)
                elif stat.S_ISREG(metadata.st_mode):
                    summary['files'] += 1
                    summary['logical_bytes'] += metadata.st_size
                    summary['largest_files_bytes'] = sorted(summary['largest_files_bytes'] + [metadata.st_size], reverse=True)[:10]
                else:
                    summary['skipped_special'] += 1
            except OSError:
                summary['errors'] += 1
                result['complete'] = False
        result['components'][label] = summary
    result['logical_bytes'] = sum(item['logical_bytes'] for item in result['components'].values())
    return result


def _parts(name):
    parts = name.replace('\\', '/').split('/')
    if name.startswith(('/', '\\')) or '..' in parts or any(':' in part for part in parts):
        return None
    return [part.lower() for part in parts if part and part != '.']


def _category(parts):
    prefixes = (
        ('python/lib/site-packages/torch/', 'pytorch'),
        ('python/lib/site-packages/', 'python_packages'),
        ('python/', 'python_runtime'),
        ('frontend/node_modules/', 'frontend_dependencies'),
        ('frontend/dist/', 'frontend_dist'),
        ('.sharp-gui-tools/colmap/', 'colmap'),
        ('.sharp-gui-tools/brush/', 'brush'),
        ('.sharp-gui-tools/git/', 'mingit'),
        ('tools/ffmpeg/', 'ffmpeg'),
        ('.cache/torch/hub/checkpoints/', 'model_weights'),
        ('.video-reconstruction-env/', 'legacy_video_environment'),
    )
    name = '/'.join(parts)
    for prefix, category in prefixes:
        if name.startswith(prefix):
            return category
    if parts and parts[0] in ('inputs', 'outputs', 'workspace', 'model-assets', '.model-asset-library', '.photo-gallery-cache', '.video-reconstruction'):
        return 'user_data'
    return 'application_or_other'


def audit_archive(path):
    """仅检查 central directory；不读取成员内容，不等同 CRC 或解包校验。"""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        safe_parts = [_parts(item.filename) for item in members]
        file_parts = [parts for item, parts in zip(members, safe_parts) if not item.is_dir()]
        roots = {parts[0] for parts in file_parts if parts}
        known_roots = {'python', 'frontend', 'tools', '.sharp-gui-tools', '.cache', 'backend', 'inputs', 'outputs',
                       'workspace', 'model-assets', '.model-asset-library', '.photo-gallery-cache',
                       '.video-reconstruction', '.video-reconstruction-env', '.git', 'ml-sharp', 'static', 'templates'}
        wrapped = (len(roots) == 1 and not roots.intersection(known_roots)
                   and all(parts is None or len(parts) > 1 for parts in file_parts))
        groups = defaultdict(_bucket)
        unsafe, links = 0, 0
        for item, parts in zip(members, safe_parts):
            if parts is None or not parts:
                category = 'unsafe_paths'
                unsafe += 1
            elif item.is_dir():
                category = 'directory_entries'
            else:
                category = _category(parts[1:] if wrapped else parts)
            if stat.S_ISLNK(item.external_attr >> 16):
                links += 1
            _add(groups[category], item.file_size, item.compress_size, not item.is_dir())
        return {
            'mode': 'archive', 'scope': 'zip_metadata_only', 'complete': unsafe == 0,
            'archive_bytes': os.fstat(archive.fp.fileno()).st_size,
            'logical_bytes': sum(item['logical_bytes'] for item in groups.values()),
            'compressed_payload_bytes': sum(item['compressed_payload_bytes'] for item in groups.values()),
            'files': sum(not item.is_dir() for item in members),
            'directories': sum(item.is_dir() for item in members), 'unsafe_paths': unsafe, 'link_entries': links,
            'stripped_wrapper_directory': wrapped,
            'components': dict(sorted(groups.items())),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--archive', type=Path, help='Read ZIP metadata without extraction or CRC verification')
    mode.add_argument('--component', action='append', metavar='LABEL=PATH', help='Repeat for disjoint files/directories; logical bytes only')
    args = parser.parse_args(argv)
    try:
        if args.archive:
            result = audit_archive(args.archive)
        else:
            if any('=' not in value for value in args.component):
                raise ValueError('Components must use LABEL=PATH')
            values = [value.split('=', 1) for value in args.component]
            if any(not path.strip() for _, path in values):
                raise ValueError('Component paths must not be empty')
            result = audit_components(values)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({'complete': False, 'error': type(error).__name__}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

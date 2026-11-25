"""发布前验证可更新性证据；不把合成事务测试冒充实际便携包验证。"""

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def validate(manifest, report):
    if report.get('schemaVersion') != 1 or report.get('status') != 'passed':
        raise ValueError('Portable update verification is incomplete')
    required = {
        'application_dependencies.py', 'backend/services/self_update.py',
        'backend/services/portable_compatibility.py', 'tools/update.py',
        'tools/portable_update_bootstrap.py', 'backend/app_factory.py',
        'backend/routes/__init__.py', 'app.py', 'update-manifest.json',
    }
    checksums = report.get('testedFiles', {})
    if set(checksums) != required:
        raise ValueError('Missing tested application/helper checksums')
    for name, checksum in checksums.items():
        if hashlib.sha256((ROOT / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() != checksum:
            raise ValueError(f'Application changed since package verification: {name}')
    rows = {row['target']: row for row in report.get('packages', [])}
    for target in manifest['supportedPortableTargets']:
        row = rows.get(target, {})
        if (not row.get('archiveSha256') or len(row['archiveSha256']) != 64
                or not all(row.get(key) is True for key in (
                    'bootstrap', 'subsequentUpdates', 'downgrade', 'rollback', 'basePreserved', 'health'))):
            raise ValueError(f'Missing actual portable transition verification: {target}')
        profile = manifest['portableCompatibility']['targets'][target]
        supported_historical = set(profile['runtimeRevisions']) - {manifest['portableRuntimeRevision']}
        if supported_historical != {row.get('runtimeRevision')}:
            raise ValueError(f'Unsupported compatibility claim: {target}')
    if not all(report.get('syntheticTests', {}).values()) or not report.get('syntheticTests'):
        raise ValueError('Synthetic failure and dependency transition coverage is incomplete')


if __name__ == '__main__':
    validate(json.loads((ROOT / 'update-manifest.json').read_text(encoding='utf-8-sig')),
             json.loads((ROOT / 'docs/update-verification.json').read_text(encoding='utf-8-sig')))
    print('Update release verification passed')

import hashlib

import pytest

from tools import check_update_release


@pytest.fixture
def release_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(check_update_release, 'ROOT', tmp_path)
    filenames = ('application_dependencies.py', 'backend/services/self_update.py',
                 'backend/services/portable_compatibility.py', 'tools/update.py',
                 'tools/portable_update_bootstrap.py', 'backend/app_factory.py',
                 'backend/routes/__init__.py', 'app.py', 'update-manifest.json')
    checksums = {}
    for name in filenames:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('verified fixture\n', encoding='utf-8')
        checksums[name] = hashlib.sha256(b'verified fixture\n').hexdigest()
    manifest = {'portableRuntimeRevision': 7, 'supportedPortableTargets': ['cu128-rtx50'],
                'portableCompatibility': {'targets': {'cu128-rtx50': {'runtimeRevisions': [6, 7]}}}}
    report = {'schemaVersion': 1, 'status': 'passed', 'testedFiles': checksums,
              'syntheticTests': {'recovery': True}, 'packages': [{
                  'target': 'cu128-rtx50', 'runtimeRevision': 6, 'archiveSha256': 'a' * 64,
                  **{key: True for key in ('bootstrap', 'subsequentUpdates', 'downgrade',
                                          'rollback', 'basePreserved', 'health')}}]}
    return manifest, report, tmp_path


def test_release_requires_complete_package_evidence(release_evidence):
    manifest, report, _ = release_evidence
    check_update_release.validate(manifest, report)
    report['packages'][0]['rollback'] = False
    with pytest.raises(ValueError, match='actual portable'):
        check_update_release.validate(manifest, report)


def test_release_rejects_application_changes_after_verification(release_evidence):
    manifest, report, root = release_evidence
    (root / 'application_dependencies.py').write_text('changed\n')
    with pytest.raises(ValueError, match='changed since'):
        check_update_release.validate(manifest, report)


def test_release_does_not_infer_support_for_unverified_old_baseline(release_evidence):
    manifest, report, _ = release_evidence
    manifest['portableCompatibility']['targets']['cu128-rtx50']['runtimeRevisions'].append(4)
    with pytest.raises(ValueError, match='Unsupported compatibility'):
        check_update_release.validate(manifest, report)

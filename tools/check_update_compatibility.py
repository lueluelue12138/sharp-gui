#!/usr/bin/env python3
"""Require a portable runtime revision bump for runtime-sensitive changes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import application_dependencies as app_dependencies

APPLICATION_INTEGRATION_PATHS = {
    'install.bat', 'install.sh', 'tools/build_portable_package.ps1',
    'tools/build_portable_release.ps1',
}
LAYOUT_PATHS = {'tools/build_portable_package.ps1', 'tools/build_portable_release.ps1',
                'tools/trim_portable_runtime.py'}

RUNTIME_SENSITIVE_FILES = {
    "build_portable_release.bat",
    "install.bat",
    "install.sh",
    "tools/build_portable_package.ps1",
    "tools/build_portable_release.ps1",
    "tools/portable_update_common.ps1",
    "tools/install_torch.py",
    "tools/install_video_reconstruction.py",
    "tools/install_brush.py",
    "tools/trim_portable_runtime.py",
}

DEPENDENCY_FILENAMES = {
    "conda-lock.yml",
    "conda-lock.yaml",
    "environment.yml",
    "environment.yaml",
    "pipfile",
    "pipfile.lock",
    "poetry.lock",
    "pyproject.toml",
    "uv.lock",
}


class CompatibilityGuardError(RuntimeError):
    """CI compatibility policy violation."""


def normalize_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def is_runtime_sensitive(path: str) -> bool:
    normalized = normalize_path(path)
    filename = PurePosixPath(normalized).name.lower()
    if normalized.lower() in RUNTIME_SENSITIVE_FILES:
        return True
    if filename == "requirements-dev.txt":
        return False
    if filename.startswith("requirements") and filename.endswith(".txt"):
        return True
    return filename in DEPENDENCY_FILENAMES


def runtime_revision(manifest: dict, label: str) -> int:
    value = manifest.get("portableRuntimeRevision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CompatibilityGuardError(
            f"{label} update-manifest.json must contain a positive integer "
            "portableRuntimeRevision"
        )
    return value


def check_runtime_revision(
    changed_paths: list[str],
    base_manifest: dict,
    head_manifest: dict,
) -> tuple[list[str], int, int]:
    sensitive_paths = sorted({normalize_path(path) for path in changed_paths if is_runtime_sensitive(path)})
    base_revision = runtime_revision(base_manifest, "Base")
    head_revision = runtime_revision(head_manifest, "Head")
    if head_revision < base_revision:
        raise CompatibilityGuardError(
            "portableRuntimeRevision must not decrease "
            f"({base_revision} -> {head_revision})"
        )
    previous_protocol = base_manifest.get('updateProtocolRevision', 1)
    next_protocol = head_manifest.get('updateProtocolRevision', 1)
    if previous_protocol != next_protocol:
        coverage = head_manifest.get('bootstrapSupport') or {}
        if (not isinstance(coverage, dict) or coverage.get('toProtocol') != next_protocol
                or previous_protocol not in coverage.get('fromProtocols', [])):
            raise CompatibilityGuardError('Update protocol change requires a persistent tested bootstrap path')
    classes = head_manifest.get('updateChangeClasses')
    if classes is not None:
        if not isinstance(classes, dict) or set(classes) - {'applicationDependencies', 'packageLayout'}:
            raise CompatibilityGuardError('Invalid updateChangeClasses classification')
        application = classes.get('applicationDependencies', [])
        layout = classes.get('packageLayout', [])
        if (not isinstance(application, list) or not isinstance(layout, list)
                or not all(isinstance(path, str) for path in application + layout)
                or set(application) - APPLICATION_INTEGRATION_PATHS or set(layout) - LAYOUT_PATHS
                or set(application) & set(layout)):
            raise CompatibilityGuardError('Invalid or unclassified base-runtime input')
        if application:
            try:
                app_dependencies.descriptor(head_manifest)
                if not head_manifest.get('applicationDependencies') or not head_manifest.get('portableCompatibility'):
                    raise CompatibilityGuardError('Application dependency integration requires a lock and base compatibility')
            except app_dependencies.DependencyError as exc:
                raise CompatibilityGuardError(str(exc)) from exc
        if layout and not head_manifest.get('layoutCompatibilityEvidence'):
            raise CompatibilityGuardError('Layout changes require retained-capability evidence')
        unclassified = set(sensitive_paths) - set(application) - set(layout)
        if unclassified and head_revision <= base_revision:
            raise CompatibilityGuardError('Unclassified runtime-sensitive changes: ' + ', '.join(sorted(unclassified)))
        if not unclassified:
            return sensitive_paths, base_revision, head_revision
    if sensitive_paths and head_revision <= base_revision:
        joined = "\n".join(f"  - {path}" for path in sensitive_paths)
        raise CompatibilityGuardError(
            "Runtime-sensitive files changed without increasing portableRuntimeRevision "
            f"({base_revision} -> {head_revision}):\n{joined}\n"
            "Increase portableRuntimeRevision and publish a complete portable package, "
            "or remove the runtime-sensitive change from this update."
        )
    return sensitive_paths, base_revision, head_revision


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def resolve_base_revision(base: str, head: str) -> str | None:
    if base and set(base) != {"0"}:
        result = run_git("cat-file", "-e", f"{base}^{{commit}}", check=False)
        if result.returncode == 0:
            return base
    result = run_git("rev-parse", "--verify", f"{head}^", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def manifest_at(revision: str, *, required: bool) -> dict | None:
    result = run_git("show", f"{revision}:update-manifest.json", check=False)
    if result.returncode != 0:
        if required:
            raise CompatibilityGuardError(f"{revision} does not contain update-manifest.json")
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CompatibilityGuardError(f"{revision} contains invalid update-manifest.json") from exc
    if not isinstance(payload, dict):
        raise CompatibilityGuardError(f"{revision} update-manifest.json must contain an object")
    return payload


def changed_paths(base: str, head: str) -> list[str]:
    result = run_git(
        "diff",
        "--name-status",
        "--find-renames",
        "--diff-filter=ACDMRTUXB",
        base,
        head,
    )
    paths = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            paths.extend(part for part in parts[1:] if part)
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit or ref")
    parser.add_argument("--head", default="HEAD", help="Target commit or ref")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        head_manifest = manifest_at(args.head, required=True)
        dependency = head_manifest.get('applicationDependencies')
        if dependency:
            try:
                app_dependencies.descriptor(head_manifest)
                lock_result = run_git('show', f"{args.head}:{dependency['lockFile']}")
                app_dependencies.validate_lock(json.loads(lock_result.stdout), dependency['sha256'])
            except (ValueError, app_dependencies.DependencyError) as exc:
                raise CompatibilityGuardError('Invalid application dependency lock') from exc
            for required in ('tests/test_application_dependencies.py', 'tests/test_portable_update_bootstrap.py',
                             'tools/build_update_bootstrap.py'):
                if run_git('cat-file', '-e', f'{args.head}:{required}', check=False).returncode:
                    raise CompatibilityGuardError(f'Missing update transition evidence: {required}')
        base_manifest = None
        runtime_revision(head_manifest, "Head")
        base = resolve_base_revision(args.base, args.head)
        if not base:
            print("[update-compatibility] No base commit is available; bootstrap check skipped.")
            return 0
        base_manifest = manifest_at(base, required=False)
        if base_manifest is None:
            print("[update-compatibility] Base commit predates update-manifest.json; bootstrap check skipped.")
            return 0
        sensitive, base_revision, head_revision = check_runtime_revision(
            changed_paths(base, args.head),
            base_manifest,
            head_manifest,
        )
    except (CompatibilityGuardError, subprocess.CalledProcessError) as exc:
        print(f"[update-compatibility] ERROR: {exc}", file=sys.stderr)
        return 1

    if sensitive:
        print(
            "[update-compatibility] Classified runtime inputs verified: "
            f"{base_revision} -> {head_revision}"
        )
        for path in sensitive:
            print(f"  - {path}")
    else:
        print("[update-compatibility] No runtime-sensitive changes detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

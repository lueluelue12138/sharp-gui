"""Commit-aware, transactional Sharp GUI self-update support.

The module deliberately has no import-time network, process, or thread side
effects.  Public API payloads are built from small allowlists so installation
paths, commands, and diagnostic output never cross the HTTP boundary.
"""

from __future__ import annotations

import compileall
import contextlib
import datetime as dt
import json
import os
import re
import signal
import shutil
import ssl
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UPDATE_STATE_SCHEMA = 1
SUPPORTED_MANIFEST_SCHEMA = 1
SUPPORTED_UPDATE_PROTOCOL = 1
CANONICAL_REPOSITORY_SLUG = "lueluelue12138/sharp-gui"
CANONICAL_REPOSITORY_URL = "https://github.com/lueluelue12138/sharp-gui.git"
DEFAULT_BRANCH = "main"
STATE_DIR_NAME = ".sharp-gui-update"
STATE_FILE_NAME = "state.json"
LOCK_FILE_NAME = "operation.lock"
UPDATER_LOG_NAME = "updater.log"
RESTART_LOG_NAME = "restart.log"
UPDATER_LOG_MAX_BYTES = 2 * 1024 * 1024
CHECK_TTL_SECONDS = 30 * 60
OPERATION_STALE_SECONDS = 30 * 60
LOCK_INITIALIZATION_GRACE_SECONDS = 5
APPLICATION_HEALTH_TIMEOUT_SECONDS = 60
ACTIVE_PHASES = {
    "queued",
    "waiting_for_server",
    "fetching",
    "applying",
    "verifying",
    "rolling_back",
    "restarting",
}
PROTECTED_RUNTIME_PATHS = {
    ".cache",
    ".model-asset-library",
    ".photo-gallery-cache",
    ".sharp-gui-tools",
    ".sharp-gui-update",
    ".thumbnails",
    ".video-reconstruction",
    ".video-reconstruction-env",
    ".sharp-gui.lock",
    "config.json",
    "frontend/node_modules",
    "ml-sharp",
    "models",
    "my-video",
    "portable-package.json",
    "portable-run-verbose.bat",
    "portable-run.bat",
    "python",
    "sharp.cmd",
    "tmp",
    "tools/ffmpeg",
    "venv",
    "workspace",
    "便携包说明.md",
}
# ``.gitignore`` protects whole user-data directory families such as ``inputs/``
# and ``outputs2/``.  Only a directory may match these prefixes so an ordinary
# tracked root file like ``outputs-format.md`` never blocks every update.
PROTECTED_RUNTIME_DIR_PREFIXES = ("inputs", "outputs", "model-assets")
PROTECTED_RUNTIME_SUFFIXES = (".pem", ".log")


class UpdateError(RuntimeError):
    """Expected updater failure carrying a stable, localizable code."""

    def __init__(self, code, message=None, *, status_code=409):
        super().__init__(message or code)
        self.code = code
        self.status_code = status_code


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def open_rotating_update_log(base_dir, name):
    """Open a bounded append log inside the installation update state directory."""

    state_dir = Path(base_dir) / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / name
    if log_path.is_file() and log_path.stat().st_size >= UPDATER_LOG_MAX_BYTES:
        rotated_path = log_path.with_suffix(f"{log_path.suffix}.1")
        try:
            rotated_path.unlink(missing_ok=True)
            os.replace(log_path, rotated_path)
        except OSError:
            pass
    return log_path.open("ab")


def _read_json(path, default=None):
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else (default if default is not None else {})
    except (OSError, ValueError, TypeError):
        return default if default is not None else {}


def default_update_state():
    return {
        "schema_version": UPDATE_STATE_SCHEMA,
        "selected_channel": "stable",
        "channels": {},
        "operation": None,
        "last_check_error_code": None,
        "checked_at": None,
    }


def load_update_state(base_dir):
    state = _read_json(Path(base_dir) / STATE_DIR_NAME / STATE_FILE_NAME, default_update_state())
    if state.get("schema_version") != UPDATE_STATE_SCHEMA:
        return default_update_state()
    state.setdefault("selected_channel", "stable")
    state.setdefault("channels", {})
    state.setdefault("operation", None)
    state.setdefault("last_check_error_code", None)
    state.setdefault("checked_at", None)
    return state


def save_update_state(base_dir, state):
    state = dict(state)
    state["schema_version"] = UPDATE_STATE_SCHEMA
    _atomic_write_json(Path(base_dir) / STATE_DIR_NAME / STATE_FILE_NAME, state)


def _pick(mapping, camel_key, snake_key=None, default=None):
    if not isinstance(mapping, dict):
        return default
    if camel_key in mapping:
        return mapping[camel_key]
    if snake_key and snake_key in mapping:
        return mapping[snake_key]
    return default


def normalize_manifest(raw):
    if not isinstance(raw, dict):
        raise UpdateError("update_manifest_invalid")
    repository = raw.get("repository")
    repository_slug = repository.get("slug") if isinstance(repository, dict) else repository
    normalized = {
        "schema_version": _pick(raw, "schemaVersion", "schema_version"),
        "application": raw.get("application"),
        "repository_slug": repository_slug,
        "repository_url": repository.get("url") if isinstance(repository, dict) else None,
        "default_branch": _pick(raw, "defaultBranch", "default_branch"),
        "update_protocol_revision": _pick(raw, "updateProtocolRevision", "update_protocol_revision"),
        "portable_runtime_revision": _pick(raw, "portableRuntimeRevision", "portable_runtime_revision"),
        "minimum_git_version": _pick(raw, "minimumGitVersion", "minimum_git_version"),
        "supported_portable_targets": _pick(raw, "supportedPortableTargets", "supported_portable_targets"),
        "frontend": raw.get("frontend"),
    }
    if (
        normalized["schema_version"] != SUPPORTED_MANIFEST_SCHEMA
        or normalized["application"] != "sharp-gui"
        or normalized["repository_slug"] != CANONICAL_REPOSITORY_SLUG
        or normalized["default_branch"] != DEFAULT_BRANCH
        or not isinstance(normalized["update_protocol_revision"], int)
        or not isinstance(normalized["portable_runtime_revision"], int)
        or not isinstance(normalized["minimum_git_version"], str)
        or not isinstance(normalized["supported_portable_targets"], list)
        or not all(isinstance(item, str) and item for item in normalized["supported_portable_targets"])
        or not isinstance(normalized["frontend"], dict)
    ):
        raise UpdateError("update_manifest_invalid")
    frontend = normalized["frontend"]
    normalized["frontend_required"] = bool(
        _pick(frontend, "builtAssetsRequired", "built_assets_required", False)
    )
    normalized["frontend_entrypoint"] = _pick(
        frontend,
        "entrypoint",
        "entrypoint",
        "frontend/dist/index.html",
    )
    if not _is_safe_relative_path(normalized["frontend_entrypoint"]):
        raise UpdateError("update_manifest_invalid")
    return normalized


def load_local_manifest(base_dir):
    path = Path(base_dir) / "update-manifest.json"
    if not path.is_file():
        raise UpdateError("update_manifest_missing")
    return normalize_manifest(_read_json(path))


def load_portable_metadata(base_dir):
    return _read_json(Path(base_dir) / "portable-package.json", {})


def _is_safe_relative_path(value):
    if not isinstance(value, str) or not value or os.path.isabs(value):
        return False
    parts = Path(value.replace("\\", "/")).parts
    return ".." not in parts and not value.startswith(("/", "\\"))


def parse_version_tuple(value):
    if not isinstance(value, str):
        return None
    match = re.search(r"(?:git version\s+)?(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def version_at_least(actual, required):
    actual_tuple = parse_version_tuple(actual)
    required_tuple = parse_version_tuple(required)
    return bool(actual_tuple and required_tuple and actual_tuple >= required_tuple)


def _git_environment():
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_SSL_NO_VERIFY": "0",
        }
    )
    return environment


def resolve_git_executable(base_dir):
    root = Path(base_dir)
    portable = (root / "portable-package.json").is_file() and (
        (root / "python" / "python.exe").is_file() or (root / "python" / "python").is_file()
    )
    package_candidates = [
        root / ".sharp-gui-tools" / "git" / "cmd" / "git.exe",
        root / ".sharp-gui-tools" / "git" / "bin" / "git.exe",
    ]
    for candidate in package_candidates:
        if candidate.is_file():
            return str(candidate)
    if portable:
        return None
    return shutil.which("git")


def run_git(base_dir, args, *, git_executable=None, timeout=30, check=True, text=True):
    git_executable = git_executable or resolve_git_executable(base_dir)
    if not git_executable:
        raise UpdateError("update_git_unavailable")
    command = [
        git_executable,
        "-c",
        "credential.interactive=never",
        "-c",
        "http.sslVerify=true",
        "-C",
        str(base_dir),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(base_dir),
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("update_git_failed", str(exc), status_code=503) from exc
    if check and result.returncode != 0:
        raise UpdateError("update_git_failed", status_code=503)
    return result


def get_git_version(base_dir, git_executable=None):
    try:
        executable = git_executable or resolve_git_executable(base_dir)
        if not executable:
            return None
        result = subprocess.run(
            [executable, "--version"],
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_value(base_dir, args, *, git_executable=None):
    try:
        result = run_git(base_dir, args, git_executable=git_executable, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except UpdateError:
        return None


def is_managed_worktree(base_dir, git_executable=None):
    top = _git_value(base_dir, ["rev-parse", "--show-toplevel"], git_executable=git_executable)
    if not top:
        return False
    try:
        return os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(base_dir))
    except OSError:
        return False


def tracked_worktree_dirty(base_dir, git_executable=None):
    if not is_managed_worktree(base_dir, git_executable):
        return False
    result = run_git(
        base_dir,
        ["status", "--porcelain", "--untracked-files=no"],
        git_executable=git_executable,
    )
    return bool(result.stdout.strip())


def detect_deployment(base_dir, git_executable=None):
    root = Path(base_dir)
    portable = (root / "portable-package.json").is_file() and (
        (root / "python" / "python.exe").is_file() or (root / "python" / "python").is_file()
    )
    managed = is_managed_worktree(base_dir, git_executable)
    if portable:
        return "portable", managed
    if managed:
        return "source", True
    if (root / "version.txt").is_file():
        return "release", False
    return "unknown", False


def _read_release_version(base_dir):
    try:
        value = (Path(base_dir) / "version.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        value = ""
    return value if re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value) else None


def get_installed_identity(base_dir, state=None):
    state = state or load_update_state(base_dir)
    git_executable = resolve_git_executable(base_dir)
    installation_kind, managed = detect_deployment(base_dir, git_executable)
    package_metadata = load_portable_metadata(base_dir)
    commit = _git_value(base_dir, ["rev-parse", "HEAD"], git_executable=git_executable) if managed else None
    branch = _git_value(
        base_dir,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        git_executable=git_executable,
    ) if managed else None
    base_version = None
    commits_ahead = None
    if managed:
        base_version = _git_value(
            base_dir,
            ["describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
            git_executable=git_executable,
        )
        if base_version:
            count = _git_value(
                base_dir,
                ["rev-list", "--count", f"{base_version}..HEAD"],
                git_executable=git_executable,
            )
            try:
                commits_ahead = int(count) if count is not None else None
            except ValueError:
                commits_ahead = None
    base_version = (
        base_version
        or _pick(package_metadata, "releaseBaseline", "release_baseline")
        or package_metadata.get("version")
        or _read_release_version(base_dir)
    )
    selected_channel = state.get("selected_channel") or "stable"
    selected_candidate = (state.get("channels") or {}).get(selected_channel)
    if isinstance(selected_candidate, dict) and commit == selected_candidate.get("target_sha"):
        base_version = selected_candidate.get("base_version") or base_version
        candidate_ahead = selected_candidate.get("commits_ahead")
        if isinstance(candidate_ahead, int):
            commits_ahead = candidate_ahead
    metadata_ahead = _pick(package_metadata, "commitsAhead", "commits_ahead")
    if commits_ahead is None and isinstance(metadata_ahead, int):
        commits_ahead = metadata_ahead
    if not commit:
        metadata_commit = _pick(package_metadata, "sourceRevision", "source_revision")
        if isinstance(metadata_commit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", metadata_commit):
            commit = metadata_commit.lower()
    short_commit = commit[:8] if commit else None
    if base_version and commits_ahead is not None and commits_ahead > 0 and short_commit:
        display_version = f"{base_version} + {commits_ahead} commits ({short_commit})"
    elif base_version and commits_ahead == 0:
        display_version = base_version
    elif base_version and short_commit:
        display_version = f"{base_version} ({short_commit})"
    elif base_version:
        display_version = base_version
    elif short_commit:
        display_version = short_commit
    else:
        display_version = "unknown"
    return {
        "base_version": base_version,
        "commit": commit,
        "short_commit": short_commit,
        "commits_ahead": commits_ahead,
        "display_version": display_version,
        "channel": selected_channel,
        "installation_kind": installation_kind,
        "managed": managed,
        "dirty": tracked_worktree_dirty(base_dir, git_executable) if managed else False,
        "branch": branch,
        "git_version": get_git_version(base_dir, git_executable),
    }


def compare_manifest_compatibility(base_dir, target_manifest, *, target_frontend_present=True):
    try:
        installed_manifest = load_local_manifest(base_dir)
    except UpdateError as exc:
        return False, exc.code
    try:
        target = (
            target_manifest
            if target_manifest.get("repository_slug") == CANONICAL_REPOSITORY_SLUG
            and "frontend_required" in target_manifest
            else normalize_manifest(target_manifest)
        )
    except (UpdateError, TypeError):
        return False, "update_manifest_invalid"
    if target.get("update_protocol_revision") != SUPPORTED_UPDATE_PROTOCOL:
        return False, "update_protocol_incompatible"
    if installed_manifest.get("update_protocol_revision") != SUPPORTED_UPDATE_PROTOCOL:
        return False, "update_bootstrap_required"
    identity = get_installed_identity(base_dir)
    git_version = identity.get("git_version")
    if not git_version:
        return False, "update_git_unavailable"
    if not version_at_least(git_version, target.get("minimum_git_version")):
        return False, "update_git_too_old"
    if target.get("frontend_required") and not target_frontend_present:
        return False, "update_frontend_missing"
    if identity.get("installation_kind") == "portable":
        metadata = load_portable_metadata(base_dir)
        runtime_revision = _pick(
            metadata,
            "portableRuntimeRevision",
            "portable_runtime_revision",
            installed_manifest.get("portable_runtime_revision"),
        )
        package_target = metadata.get("target")
        protocol_revision = _pick(
            metadata,
            "updateProtocolRevision",
            "update_protocol_revision",
            installed_manifest.get("update_protocol_revision"),
        )
        if protocol_revision != target.get("update_protocol_revision"):
            return False, "update_protocol_incompatible"
        if runtime_revision != target.get("portable_runtime_revision"):
            return False, "update_full_package_required"
        if package_target not in target.get("supported_portable_targets", []):
            return False, "update_target_unsupported"
    return True, "update_compatible"


def runtime_change_advisory(base_dir, target_manifest, *, installation_kind):
    """Warn source installs when the target declares different runtime inputs.

    Portable packages are hard-blocked by the runtime revision gate.  Source
    installs stay updatable, but the same signal is the only reliable predictor
    of a post-update dependency import failure, so surface it as advice.
    """

    if installation_kind == "portable":
        return None
    try:
        installed = load_local_manifest(base_dir)
    except UpdateError:
        return None
    installed_revision = installed.get("portable_runtime_revision")
    target_revision = target_manifest.get("portable_runtime_revision")
    if (
        isinstance(installed_revision, int)
        and isinstance(target_revision, int)
        and installed_revision != target_revision
    ):
        return "update_runtime_revision_changed"
    return None


FORMAL_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class GitTargetResolver:
    """Resolve both update channels using only trusted canonical Git refs."""

    def __init__(self, base_dir, *, git_executable=None):
        self.base_dir = str(base_dir)
        self.git_executable = git_executable or resolve_git_executable(base_dir)

    def _formal_release_tags(self):
        result = run_git(
            self.base_dir,
            ["ls-remote", "--tags", "--refs", CANONICAL_REPOSITORY_URL, "refs/tags/v*"],
            git_executable=self.git_executable,
            timeout=60,
        )
        tags = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) != 2 or not fields[1].startswith("refs/tags/"):
                continue
            tag = fields[1].removeprefix("refs/tags/")
            match = FORMAL_RELEASE_TAG.fullmatch(tag)
            if match:
                tags.append((tuple(int(part) for part in match.groups()), tag))
        if not tags:
            raise UpdateError("update_release_invalid", status_code=503)
        return [tag for _, tag in sorted(tags)]

    def _fetch_ref(self, source_ref, destination_ref, *, depth):
        run_git(
            self.base_dir,
            [
                "fetch",
                "--force",
                f"--depth={depth}",
                CANONICAL_REPOSITORY_URL,
                f"{source_ref}:{destination_ref}",
            ],
            git_executable=self.git_executable,
            timeout=180,
        )
        resolved = _git_value(
            self.base_dir,
            ["rev-parse", f"{destination_ref}^{{commit}}"],
            git_executable=self.git_executable,
        )
        if not isinstance(resolved, str) or not re.fullmatch(r"[0-9a-f]{40}", resolved):
            raise UpdateError("update_target_invalid", status_code=503)
        return resolved

    def _relation(self, current_sha, target_sha):
        if current_sha == target_sha:
            return "current"
        if not isinstance(current_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_sha):
            return "unknown"
        current_is_ancestor = run_git(
            self.base_dir,
            ["merge-base", "--is-ancestor", current_sha, target_sha],
            git_executable=self.git_executable,
            check=False,
        )
        if current_is_ancestor.returncode == 0:
            return "upgrade"
        target_is_ancestor = run_git(
            self.base_dir,
            ["merge-base", "--is-ancestor", target_sha, current_sha],
            git_executable=self.git_executable,
            check=False,
        )
        if target_is_ancestor.returncode == 0:
            return "downgrade"
        return "diverged" if current_is_ancestor.returncode == 1 else "unknown"

    def resolve(self, channel, current_identity):
        if channel not in {"stable", "latest"}:
            raise UpdateError("update_channel_invalid", status_code=400)
        if not self.git_executable or not is_managed_worktree(self.base_dir, self.git_executable):
            raise UpdateError("update_installation_unsupported", status_code=409)

        release_tag = self._formal_release_tags()[-1]
        stable_ref = f"refs/tags/{release_tag}"
        stable_sha = self._fetch_ref(stable_ref, stable_ref, depth=1)
        if channel == "stable":
            target_ref = stable_ref
            target_sha = stable_sha
            commits_ahead = 0
        else:
            target_ref = f"refs/heads/{DEFAULT_BRANCH}"
            target_sha = self._fetch_ref(
                target_ref,
                f"refs/remotes/sharp-gui-update/{DEFAULT_BRANCH}",
                depth=256,
            )
            ancestry = run_git(
                self.base_dir,
                ["merge-base", "--is-ancestor", stable_sha, target_sha],
                git_executable=self.git_executable,
                check=False,
            )
            count = _git_value(
                self.base_dir,
                ["rev-list", "--count", f"{stable_sha}..{target_sha}"],
                git_executable=self.git_executable,
            ) if ancestry.returncode == 0 else None
            try:
                commits_ahead = int(count) if count is not None else None
            except ValueError:
                commits_ahead = None

        raw_manifest = manifest_from_git(
            self.base_dir,
            target_sha,
            git_executable=self.git_executable,
        )
        normalized_manifest = normalize_manifest(raw_manifest)
        frontend_present = git_path_exists(
            self.base_dir,
            target_sha,
            normalized_manifest["frontend_entrypoint"],
            git_executable=self.git_executable,
        )
        compatible, compatibility_code = compare_manifest_compatibility(
            self.base_dir,
            normalized_manifest,
            target_frontend_present=frontend_present,
        )
        # The helper repeats this before mutation, but detecting it now avoids
        # stopping the server just to refuse the target afterwards.
        if compatible and target_tracks_protected_runtime(
            self.base_dir,
            target_sha,
            git_executable=self.git_executable,
        ):
            compatible = False
            compatibility_code = "update_target_tracks_runtime"
        advisory_code = runtime_change_advisory(
            self.base_dir,
            normalized_manifest,
            installation_kind=current_identity.get("installation_kind"),
        )
        relation = self._relation(current_identity.get("commit"), target_sha)
        short_sha = target_sha[:8]
        if commits_ahead is not None and commits_ahead > 0:
            display_version = f"{release_tag} + {commits_ahead} commits ({short_sha})"
        elif commits_ahead == 0:
            display_version = release_tag
        else:
            display_version = f"{release_tag} ({short_sha})"
        return {
            "channel": channel,
            "target_sha": target_sha,
            "short_sha": short_sha,
            "target_ref": target_ref,
            "base_version": release_tag,
            "commits_ahead": commits_ahead,
            "display_version": display_version,
            "relation": relation,
            "update_available": relation != "current",
            "compatible": compatible,
            "compatibility_code": compatibility_code,
            "advisory_code": advisory_code,
            "checked_at": utc_now(),
            "_target_manifest": raw_manifest,
        }


PUBLIC_CURRENT_KEYS = {
    "base_version",
    "commit",
    "short_commit",
    "commits_ahead",
    "display_version",
    "channel",
    "installation_kind",
    "managed",
    "dirty",
    "branch",
}
PUBLIC_CANDIDATE_KEYS = {
    "channel",
    "target_sha",
    "short_sha",
    "base_version",
    "commits_ahead",
    "display_version",
    "relation",
    "update_available",
    "compatible",
    "compatibility_code",
    "advisory_code",
    "checked_at",
}
PUBLIC_OPERATION_KEYS = {
    "id",
    "action",
    "phase",
    "progress",
    "channel",
    "target_sha",
    "short_target_sha",
    "error_code",
    "rolled_back",
    "started_at",
    "updated_at",
    "completed_at",
}


def _sanitize(mapping, allowed_keys):
    if not isinstance(mapping, dict):
        return None
    return {key: mapping.get(key) for key in allowed_keys if key in mapping}


def sanitize_candidate(candidate):
    return _sanitize(candidate, PUBLIC_CANDIDATE_KEYS)


def sanitize_operation(operation):
    return _sanitize(operation, PUBLIC_OPERATION_KEYS)


def _operation_active(operation):
    return isinstance(operation, dict) and operation.get("phase") in ACTIVE_PHASES


def assert_mutation_preconditions(state, identity, *, task_manager=None, checking=False):
    """Reject mutation whenever the installed checkout is not safe to replace."""

    if checking or _operation_active(state.get("operation")):
        raise UpdateError("update_in_progress", status_code=409)
    if task_manager:
        _, has_active = task_manager.list_tasks()
        if has_active:
            raise UpdateError("update_tasks_active", status_code=409)
    if identity.get("managed") and identity.get("dirty"):
        raise UpdateError("update_worktree_dirty", status_code=409)
    if identity.get("installation_kind") == "source" and identity.get("branch") != DEFAULT_BRANCH:
        raise UpdateError("update_developer_branch", status_code=409)


def _capabilities(base_dir, identity, state, *, is_owner, task_manager=None, checking=False):
    """Collect every unmet condition so the UI can list all blockers at once.

    Reasons are ordered most-actionable first; ``reason_code`` stays the primary
    reason for callers that only handle a single code.
    """

    reasons = []
    blocks_check = set()

    def block(code, *, check=False):
        if code not in reasons:
            reasons.append(code)
        if check:
            blocks_check.add(code)

    if not is_owner:
        block("update_owner_required", check=True)
    else:
        if checking or _operation_active(state.get("operation")):
            block("update_in_progress")
        if task_manager and task_manager.list_tasks()[1]:
            block("update_tasks_active")
        if not identity.get("managed") or identity.get("installation_kind") == "unknown":
            block("update_installation_unsupported", check=True)
        if not identity.get("git_version"):
            block("update_git_unavailable", check=True)
        try:
            manifest = load_local_manifest(base_dir)
        except UpdateError as exc:
            manifest = None
            block(exc.code, check=True)
        if manifest:
            if manifest.get("update_protocol_revision") != SUPPORTED_UPDATE_PROTOCOL:
                block("update_protocol_incompatible")
            if identity.get("git_version") and not version_at_least(
                identity["git_version"],
                manifest["minimum_git_version"],
            ):
                block("update_git_too_old")
        if identity.get("installation_kind") == "source" and identity.get("branch") != DEFAULT_BRANCH:
            block("update_developer_branch")
        if identity.get("managed") and identity.get("dirty"):
            block("update_worktree_dirty")
    return {
        "can_check": not blocks_check,
        "can_apply": not reasons,
        "reason_code": reasons[0] if reasons else None,
        "reason_codes": list(reasons),
        "owner_required": True,
    }


def _process_exists(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class SelfUpdateManager:
    """Application-facing coordinator. Construction is intentionally passive."""

    def __init__(
        self,
        *,
        base_dir,
        task_manager=None,
        restart_callback=None,
        resolver_factory=None,
        process_factory=None,
    ):
        self.base_dir = os.path.realpath(str(base_dir))
        self.task_manager = task_manager
        self.restart_callback = restart_callback
        self.resolver_factory = resolver_factory or (lambda: GitTargetResolver(self.base_dir))
        self.process_factory = process_factory or subprocess.Popen
        self._lock = threading.RLock()
        self._checking = False

    def _read_state(self):
        return load_update_state(self.base_dir)

    def _write_state(self, state):
        save_update_state(self.base_dir, state)

    def _reconcile(self, state, identity):
        operation = state.get("operation")
        if not isinstance(operation, dict) or operation.get("phase") not in ACTIVE_PHASES:
            return state
        current_sha = identity.get("commit")
        target_sha = operation.get("target_sha")
        previous_sha = operation.get("previous_sha")
        if operation.get("phase") == "restarting" and current_sha == target_sha:
            try:
                verify_checked_out_revision(self.base_dir, target_sha, deep=False)
            except Exception as exc:
                operation.update(
                    {
                        "phase": "failed",
                        "progress": 100,
                        "error_code": exc.code if isinstance(exc, UpdateError) else "update_verification_failed",
                        "completed_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            else:
                operation.update(
                    {
                        "phase": "completed",
                        "progress": 100,
                        "error_code": None,
                        "completed_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
                state["selected_channel"] = operation.get("channel") or state.get("selected_channel")
            self._write_state(state)
            return state
        updated_at = parse_timestamp(operation.get("updated_at"))
        helper_pid = operation.get("_helper_pid")
        helper_alive = _process_exists(helper_pid)
        stale = updated_at is None or time.time() - updated_at > OPERATION_STALE_SECONDS
        if not helper_alive or stale:
            verified = False
            verification_code = None
            if current_sha == target_sha:
                try:
                    verify_checked_out_revision(self.base_dir, target_sha, deep=False)
                    verified = True
                except Exception as exc:
                    verification_code = exc.code if isinstance(exc, UpdateError) else "update_verification_failed"
                phase = "completed" if verified else "failed"
                error_code = None if verified else verification_code
            elif current_sha == previous_sha:
                try:
                    verify_checked_out_revision(self.base_dir, previous_sha, deep=False)
                    verified = True
                except Exception:
                    verified = False
                phase = "failed"
                error_code = "update_interrupted_rolled_back" if verified else "update_recovery_required"
            else:
                phase = "failed"
                error_code = "update_recovery_required"
            operation.update(
                {
                    "phase": phase,
                    "progress": 100,
                    "error_code": error_code,
                    "rolled_back": bool(current_sha == previous_sha and verified),
                    "updated_at": utc_now(),
                    "completed_at": utc_now(),
                }
            )
            if phase == "completed":
                state["selected_channel"] = operation.get("channel") or state.get("selected_channel")
            self._write_state(state)
        return state

    def status(self, *, is_owner=False, server_instance_id=None):
        with self._lock:
            state = self._read_state()
            identity = get_installed_identity(self.base_dir, state)
            state = self._reconcile(state, identity)
            channels = {
                channel: sanitize_candidate(candidate)
                for channel, candidate in (state.get("channels") or {}).items()
                if channel in {"stable", "latest"} and isinstance(candidate, dict)
            }
            return {
                "server_instance_id": server_instance_id,
                "is_owner": bool(is_owner),
                "current": _sanitize(identity, PUBLIC_CURRENT_KEYS),
                "capabilities": _capabilities(
                    self.base_dir,
                    identity,
                    state,
                    is_owner=bool(is_owner),
                    task_manager=self.task_manager,
                    checking=self._checking,
                ),
                "channels": channels,
                "operation": sanitize_operation(state.get("operation")),
                "checked_at": state.get("checked_at"),
                "last_check_error_code": state.get("last_check_error_code"),
            }

    def check(self, channel, *, is_owner=True, server_instance_id=None):
        if not is_owner:
            raise UpdateError("update_owner_required", status_code=403)
        if channel not in {"stable", "latest"}:
            raise UpdateError("update_channel_invalid", status_code=400)
        with self._lock:
            state = self._read_state()
            if self._checking or _operation_active(state.get("operation")):
                raise UpdateError("update_in_progress", status_code=409)
            identity = get_installed_identity(self.base_dir, state)
            capabilities = _capabilities(
                self.base_dir,
                identity,
                state,
                is_owner=True,
                task_manager=self.task_manager,
                checking=False,
            )
            if not capabilities["can_check"]:
                raise UpdateError(capabilities["reason_code"] or "update_not_supported", status_code=409)
            self._checking = True
        try:
            # Git fetches into a shared repository, so a UI check must not race a
            # CLI check or a helper transaction in another process.
            with operation_lock(self.base_dir, f"check-{uuid.uuid4().hex}"):
                candidate = self.resolver_factory().resolve(channel, identity)
        except UpdateError as exc:
            if exc.code != "update_in_progress":
                with self._lock:
                    state = self._read_state()
                    state.setdefault("channels", {}).pop(channel, None)
                    state["last_check_error_code"] = exc.code
                    state["checked_at"] = utc_now()
                    self._write_state(state)
            raise
        finally:
            with self._lock:
                self._checking = False
        with self._lock:
            state = self._read_state()
            if _operation_active(state.get("operation")):
                raise UpdateError("update_in_progress", status_code=409)
            state.setdefault("channels", {})[channel] = candidate
            state["selected_channel"] = channel
            state["checked_at"] = candidate["checked_at"]
            state["last_check_error_code"] = None
            self._write_state(state)
        return self.status(is_owner=is_owner, server_instance_id=server_instance_id)

    def _assert_mutation_preconditions(self, state, identity):
        assert_mutation_preconditions(
            state,
            identity,
            task_manager=self.task_manager,
            checking=self._checking,
        )

    def _new_operation(
        self,
        *,
        action,
        channel,
        target_sha,
        target_ref,
        target_manifest,
        previous_sha,
        base_version=None,
    ):
        now = utc_now()
        return {
            "id": uuid.uuid4().hex,
            "action": action,
            "phase": "queued",
            "progress": 0,
            "channel": channel,
            "target_sha": target_sha,
            "short_target_sha": target_sha[:8],
            "target_ref": target_ref,
            "target_manifest": target_manifest,
            "base_version": base_version,
            "previous_sha": previous_sha,
            "short_previous_sha": previous_sha[:8] if previous_sha else None,
            "error_code": None,
            "rolled_back": False,
            "started_at": now,
            "updated_at": now,
            "_server_pid": os.getpid(),
        }

    def _spawn(self, operation):
        helper = Path(self.base_dir) / "tools" / "update.py"
        if not helper.is_file():
            raise UpdateError("update_helper_missing", status_code=500)
        environment = os.environ.copy()
        environment["SHARP_UPDATE_HELPER"] = "1"
        environment.pop("WERKZEUG_RUN_MAIN", None)
        creationflags = 0
        popen_kwargs = {"cwd": self.base_dir, "env": environment, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True
        with open_rotating_update_log(self.base_dir, UPDATER_LOG_NAME) as log_handle:
            process = self.process_factory(
                [sys.executable, str(helper), "--internal-run", operation["id"]],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **popen_kwargs,
            )
        return process

    def _start_operation(self, state, operation):
        state["operation"] = operation
        self._write_state(state)
        try:
            process = self._spawn(operation)
        except (OSError, UpdateError) as exc:
            operation.update(
                {
                    "phase": "failed",
                    "progress": 100,
                    "error_code": exc.code if isinstance(exc, UpdateError) else "update_helper_start_failed",
                    "updated_at": utc_now(),
                    "completed_at": utc_now(),
                }
            )
            self._write_state(state)
            if isinstance(exc, UpdateError):
                raise
            raise UpdateError("update_helper_start_failed", status_code=500) from exc
        operation["_helper_pid"] = process.pid
        operation["phase"] = "waiting_for_server"
        operation["progress"] = 5
        operation["updated_at"] = utc_now()
        self._write_state(state)
        if self.restart_callback:
            self.restart_callback()

    def start_apply(self, channel, *, is_owner=True, server_instance_id=None):
        if not is_owner:
            raise UpdateError("update_owner_required", status_code=403)
        if channel not in {"stable", "latest"}:
            raise UpdateError("update_channel_invalid", status_code=400)
        with self._lock:
            state = self._read_state()
            identity = get_installed_identity(self.base_dir, state)
            self._assert_mutation_preconditions(state, identity)
            candidate = (state.get("channels") or {}).get(channel)
            if not isinstance(candidate, dict):
                raise UpdateError("update_target_untrusted", status_code=409)
            checked_at = parse_timestamp(candidate.get("checked_at"))
            if not checked_at or time.time() - checked_at > CHECK_TTL_SECONDS:
                raise UpdateError("update_target_expired", status_code=409)
            if not candidate.get("compatible"):
                raise UpdateError(candidate.get("compatibility_code") or "update_incompatible", status_code=409)
            if not candidate.get("update_available"):
                raise UpdateError("update_already_current", status_code=409)
            capabilities = _capabilities(
                self.base_dir,
                identity,
                state,
                is_owner=True,
                task_manager=self.task_manager,
                checking=self._checking,
            )
            if not capabilities["can_apply"]:
                raise UpdateError(capabilities["reason_code"] or "update_not_supported", status_code=409)
            operation = self._new_operation(
                action="apply",
                channel=channel,
                target_sha=candidate["target_sha"],
                target_ref=candidate["target_ref"],
                target_manifest=candidate["_target_manifest"],
                previous_sha=identity.get("commit"),
                base_version=candidate.get("base_version"),
            )
            self._start_operation(state, operation)
        return self.status(is_owner=is_owner, server_instance_id=server_instance_id)


def manifest_from_git(base_dir, revision, *, git_executable=None):
    result = run_git(
        base_dir,
        ["show", f"{revision}:update-manifest.json"],
        git_executable=git_executable,
        check=False,
    )
    if result.returncode != 0:
        raise UpdateError("update_manifest_missing")
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise UpdateError("update_manifest_invalid") from exc
    normalize_manifest(payload)
    return payload


def git_path_exists(base_dir, revision, relative_path, *, git_executable=None):
    if not _is_safe_relative_path(relative_path):
        return False
    result = run_git(
        base_dir,
        ["cat-file", "-e", f"{revision}:{relative_path.replace(os.sep, '/')}"],
        git_executable=git_executable,
        check=False,
    )
    return result.returncode == 0


def target_tracks_protected_runtime(base_dir, revision, *, git_executable=None):
    result = run_git(
        base_dir,
        ["ls-tree", "-rz", "--name-only", revision],
        git_executable=git_executable,
    )
    protected = {path.casefold() for path in PROTECTED_RUNTIME_PATHS}
    for raw_path in result.stdout.split("\0"):
        path = raw_path.strip().replace("\\", "/").casefold()
        if not path:
            continue
        if path in protected or any(path.startswith(f"{prefix}/") for prefix in protected):
            return True
        if path.endswith(PROTECTED_RUNTIME_SUFFIXES):
            return True
        head, separator, _ = path.partition("/")
        if separator and head.startswith(PROTECTED_RUNTIME_DIR_PREFIXES):
            return True
    return False


@contextlib.contextmanager
def operation_lock(base_dir, operation_id):
    lock_path = Path(base_dir) / STATE_DIR_NAME / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"operation_id": operation_id, "pid": os.getpid()})
    while True:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            break
        except FileExistsError:
            existing = _read_json(lock_path, {})
            if _process_exists(existing.get("pid")):
                raise UpdateError("update_in_progress", status_code=409)
            try:
                lock_age = max(0.0, time.time() - lock_path.stat().st_mtime)
            except OSError:
                lock_age = 0.0
            # os.open(O_EXCL) creates the file before the owner can write its
            # JSON payload. Treat a fresh empty/partial file as an active lock
            # so a racing helper cannot unlink it during that tiny window.
            if not isinstance(existing.get("pid"), int) and lock_age < LOCK_INITIALIZATION_GRACE_SECONDS:
                raise UpdateError("update_in_progress", status_code=409)
            try:
                lock_path.unlink()
            except OSError as exc:
                raise UpdateError("update_in_progress", status_code=409) from exc
    try:
        yield
    finally:
        try:
            existing = _read_json(lock_path, {})
            if existing.get("operation_id") == operation_id and existing.get("pid") == os.getpid():
                lock_path.unlink()
        except OSError:
            pass


def _update_operation(base_dir, operation_id, **changes):
    state = load_update_state(base_dir)
    operation = state.get("operation")
    if not isinstance(operation, dict) or operation.get("id") != operation_id:
        raise UpdateError("update_operation_invalid", status_code=409)
    operation.update(changes)
    operation["updated_at"] = utc_now()
    save_update_state(base_dir, state)
    return state, operation


def wait_for_process_exit(pid, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _process_exists(pid):
            return True
        time.sleep(0.2)
    return not _process_exists(pid)


def _fetch_exact_target(base_dir, operation, git_executable):
    target_ref = operation.get("target_ref")
    target_sha = operation.get("target_sha")
    channel = operation.get("channel")
    if channel == "stable" and isinstance(target_ref, str) and re.fullmatch(
        r"refs/tags/v\d+\.\d+\.\d+",
        target_ref,
    ):
        destination = target_ref
        depth = 1
    elif channel == "latest" and target_ref == f"refs/heads/{DEFAULT_BRANCH}":
        destination = f"refs/remotes/sharp-gui-update/{DEFAULT_BRANCH}"
        depth = 256
    else:
        raise UpdateError("update_target_untrusted")
    run_git(
        base_dir,
        [
            "fetch",
            "--force",
            f"--depth={depth}",
            CANONICAL_REPOSITORY_URL,
            f"{target_ref}:{destination}",
        ],
        git_executable=git_executable,
        timeout=180,
    )
    resolved = _git_value(
        base_dir,
        ["rev-parse", f"{destination}^{{commit}}"],
        git_executable=git_executable,
    )
    if resolved != target_sha:
        raise UpdateError("update_target_changed")


def verify_checked_out_revision(base_dir, expected_sha, *, git_executable=None, deep=True):
    """Verify the worktree matches ``expected_sha`` and can run.

    ``deep=False`` skips bytecode compilation and the import subprocess.  The
    serving process uses the shallow form so a status request can never trigger
    a full ``compileall`` plus interpreter spawn; the updater helper always runs
    the deep form before accepting or rolling back a revision.
    """

    current = _git_value(base_dir, ["rev-parse", "HEAD"], git_executable=git_executable)
    if current != expected_sha:
        raise UpdateError("update_verification_failed")
    manifest = load_local_manifest(base_dir)
    required_files = (
        "app.py",
        "backend/app_factory.py",
        "backend/routes/__init__.py",
        "tools/update.py",
        "version.txt",
    )
    for relative_path in required_files:
        required_path = Path(base_dir) / relative_path
        if not required_path.is_file() or required_path.stat().st_size == 0:
            raise UpdateError("update_verification_failed")
    frontend_entrypoint = Path(base_dir) / manifest["frontend_entrypoint"]
    if manifest["frontend_required"] and (not frontend_entrypoint.is_file() or frontend_entrypoint.stat().st_size == 0):
        raise UpdateError("update_frontend_missing")
    compatible, compatibility_code = compare_manifest_compatibility(
        base_dir,
        manifest,
        target_frontend_present=True,
    )
    if not compatible:
        raise UpdateError(compatibility_code)
    if not deep:
        if tracked_worktree_dirty(base_dir, git_executable):
            raise UpdateError("update_verification_failed")
        return True
    for relative in ("backend", "tools"):
        path = Path(base_dir) / relative
        if not path.is_dir() or not compileall.compile_dir(str(path), quiet=2, force=True):
            raise UpdateError("update_verification_failed")
    app_path = Path(base_dir) / "app.py"
    if not compileall.compile_file(str(app_path), quiet=2, force=True):
        raise UpdateError("update_verification_failed")
    import_environment = os.environ.copy()
    import_environment.pop("PYTHONPATH", None)
    import_environment.pop("PYTHONHOME", None)
    import_check = subprocess.run(
        [sys.executable, "-c", "import backend.app_factory; import backend.routes"],
        cwd=str(base_dir),
        env=import_environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if import_check.returncode != 0:
        raise UpdateError("update_verification_failed")
    if tracked_worktree_dirty(base_dir, git_executable):
        raise UpdateError("update_verification_failed")
    return True


def launch_application(base_dir):
    """Start the updated application detached from the finished updater helper.

    The original console belonged to the process that stopped for the update, so
    the restarted instance has nowhere interactive to write.  Its output goes to
    a bounded log under the update state directory instead of being discarded,
    which is the only record available when a restart misbehaves.
    """

    environment = os.environ.copy()
    for key in ("SHARP_UPDATE_HELPER", "SHARP_WINDOWS_SERVER_CHILD", "WERKZEUG_RUN_MAIN", "WERKZEUG_SERVER_FD"):
        environment.pop(key, None)
    kwargs = {
        "cwd": str(base_dir),
        "env": environment,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        log_handle = open_rotating_update_log(base_dir, RESTART_LOG_NAME)
    except OSError:
        log_handle = None
    try:
        return subprocess.Popen(
            [sys.executable, str(Path(base_dir) / "app.py")],
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_handle else subprocess.DEVNULL,
            **kwargs,
        )
    finally:
        if log_handle is not None:
            log_handle.close()


def terminate_application_process(process):
    """Best-effort termination of the supervised application tree we started."""

    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def _is_locked_service_response(error):
    """Recognize our own running service refusing an unauthenticated probe.

    ``GET /api/updates/status`` is an Unlocked route, so an installation that
    enables the access code *and* disables the localhost bypass answers the
    loopback probe with a structured auth error.  That response still proves the
    updated Flask application imported, registered routes, and is serving, so it
    must count as healthy instead of triggering a needless rollback.
    """

    if getattr(error, "code", None) not in {401, 403}:
        return False
    try:
        payload = json.loads(error.read(64 * 1024).decode("utf-8"))
    except (AttributeError, OSError, ValueError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("code") in {
        "ACCESS_SETUP_REQUIRED",
        "AUTH_REQUIRED",
        "OWNER_REQUIRED",
    }


def wait_for_application_health(
    process,
    expected_sha,
    *,
    timeout=APPLICATION_HEALTH_TIMEOUT_SECONDS,
    fail_on_operation_error=True,
):
    """Wait for the new localhost instance to report the exact checked-out commit."""

    deadline = time.time() + timeout
    try:
        port = int(os.environ.get("SHARP_PORT", "5050"))
    except (TypeError, ValueError):
        port = 5050
    urls = (
        f"https://127.0.0.1:{port}/api/updates/status",
        f"http://127.0.0.1:{port}/api/updates/status",
    )
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        for url in urls:
            request = Request(url, headers={"Accept": "application/json"}, method="GET")
            try:
                kwargs = {"timeout": 1.5}
                if url.startswith("https://"):
                    # This is a loopback-only health probe. Sharp GUI commonly
                    # uses its own self-signed local certificate, so trust is
                    # established by the exact Git commit reported from disk.
                    kwargs["context"] = ssl._create_unverified_context()
                with contextlib.closing(urlopen(request, **kwargs)) as response:
                    payload = response.read(1024 * 1024)
                status = json.loads(payload.decode("utf-8"))
                operation = status.get("operation") if isinstance(status, dict) else None
                if fail_on_operation_error and isinstance(operation, dict) and operation.get("error_code"):
                    return False
                current = status.get("current") if isinstance(status, dict) else None
                if isinstance(current, dict) and (
                    expected_sha is None or current.get("commit") == expected_sha
                ):
                    return True
            except HTTPError as exc:
                if _is_locked_service_response(exc):
                    return True
                continue
            except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError, UnicodeDecodeError):
                continue
        time.sleep(0.25)
    return False


def run_update_operation(base_dir, operation_id, *, wait_for_server=True, relaunch=True):
    """Execute one persisted operation. Intended for the detached helper/CLI."""

    base_dir = os.path.realpath(str(base_dir))
    state = load_update_state(base_dir)
    operation = state.get("operation")
    if not isinstance(operation, dict) or operation.get("id") != operation_id:
        raise UpdateError("update_operation_invalid", status_code=409)
    server_pid = operation.get("_server_pid")
    if wait_for_server and server_pid and not wait_for_process_exit(server_pid):
        _update_operation(
            base_dir,
            operation_id,
            phase="failed",
            progress=100,
            error_code="update_server_stop_timeout",
            completed_at=utc_now(),
        )
        if relaunch:
            launch_application(base_dir)
        return False
    previous_sha = operation.get("previous_sha")
    mutated = False
    git_executable = resolve_git_executable(base_dir)
    launched_process = None
    try:
        with operation_lock(base_dir, operation_id):
            try:
                _update_operation(base_dir, operation_id, _helper_pid=os.getpid())
                if not git_executable:
                    raise UpdateError("update_git_unavailable")
                installed_identity = get_installed_identity(base_dir, state)
                if installed_identity.get("managed") and installed_identity.get("dirty"):
                    raise UpdateError("update_worktree_dirty")
                if (
                    installed_identity.get("installation_kind") == "source"
                    and installed_identity.get("branch") != DEFAULT_BRANCH
                ):
                    raise UpdateError("update_developer_branch")
                if not is_managed_worktree(base_dir, git_executable):
                    raise UpdateError("update_installation_unsupported")
                if tracked_worktree_dirty(base_dir, git_executable):
                    raise UpdateError("update_worktree_dirty")
                actual_previous = _git_value(base_dir, ["rev-parse", "HEAD"], git_executable=git_executable)
                if previous_sha and actual_previous != previous_sha:
                    raise UpdateError("update_installed_revision_changed")
                previous_sha = actual_previous
                _update_operation(
                    base_dir,
                    operation_id,
                    phase="fetching",
                    progress=20,
                    previous_sha=previous_sha,
                    short_previous_sha=previous_sha[:8] if previous_sha else None,
                )
                state = load_update_state(base_dir)
                operation = state["operation"]
                _fetch_exact_target(base_dir, operation, git_executable)
                target_sha = operation["target_sha"]
                target_manifest = manifest_from_git(base_dir, target_sha, git_executable=git_executable)
                normalized = normalize_manifest(target_manifest)
                frontend_present = git_path_exists(
                    base_dir,
                    target_sha,
                    normalized["frontend_entrypoint"],
                    git_executable=git_executable,
                )
                compatible, compatibility_code = compare_manifest_compatibility(
                    base_dir,
                    normalized,
                    target_frontend_present=frontend_present,
                )
                if not compatible:
                    raise UpdateError(compatibility_code)
                if target_tracks_protected_runtime(
                    base_dir,
                    target_sha,
                    git_executable=git_executable,
                ):
                    raise UpdateError("update_target_tracks_runtime")
                _update_operation(base_dir, operation_id, phase="applying", progress=55)
                # A failed reset can still replace a prefix of the worktree
                # (disk full, antivirus lock, permissions). Mark mutation
                # before invoking Git so every such failure enters rollback.
                mutated = True
                run_git(base_dir, ["reset", "--hard", target_sha], git_executable=git_executable, timeout=120)
                _update_operation(base_dir, operation_id, phase="verifying", progress=78)
                verify_checked_out_revision(base_dir, target_sha, git_executable=git_executable)
                _update_operation(
                    base_dir,
                    operation_id,
                    phase="restarting" if relaunch else "completed",
                    progress=92 if relaunch else 100,
                    previous_sha=previous_sha,
                    short_previous_sha=previous_sha[:8] if previous_sha else None,
                    error_code=None,
                    rolled_back=False,
                    completed_at=None if relaunch else utc_now(),
                )
                if relaunch:
                    launched_process = launch_application(base_dir)
                    if not wait_for_application_health(launched_process, target_sha):
                        terminate_application_process(launched_process)
                        launched_process = None
                        raise UpdateError("update_restart_failed")
                    _update_operation(
                        base_dir,
                        operation_id,
                        phase="completed",
                        progress=100,
                        error_code=None,
                        rolled_back=False,
                        completed_at=utc_now(),
                    )
                return True
            except Exception as exc:
                if launched_process is not None:
                    terminate_application_process(launched_process)
                launched_process = None
                code = exc.code if isinstance(exc, UpdateError) else "update_apply_failed"
                rolled_back = False
                if mutated:
                    if previous_sha:
                        try:
                            _update_operation(
                                base_dir,
                                operation_id,
                                phase="rolling_back",
                                progress=88,
                                error_code=code,
                            )
                            run_git(
                                base_dir,
                                ["reset", "--hard", previous_sha],
                                git_executable=git_executable,
                                timeout=120,
                            )
                            verify_checked_out_revision(
                                base_dir,
                                previous_sha,
                                git_executable=git_executable,
                            )
                            rolled_back = True
                        except Exception:
                            code = "update_rollback_failed"
                    else:
                        code = "update_rollback_failed"

                should_restart_previous = relaunch and (not mutated or rolled_back)
                if should_restart_previous:
                    try:
                        launched_process = launch_application(base_dir)
                        expected_restart_sha = previous_sha if previous_sha else None
                        if not wait_for_application_health(
                            launched_process,
                            expected_restart_sha,
                            fail_on_operation_error=False,
                        ):
                            terminate_application_process(launched_process)
                            launched_process = None
                            raise UpdateError("update_restart_failed")
                    except Exception:
                        code = "update_rollback_failed" if mutated else "update_restart_failed"

                _update_operation(
                    base_dir,
                    operation_id,
                    phase="failed",
                    progress=100,
                    error_code=code,
                    rolled_back=rolled_back,
                    completed_at=utc_now(),
                )
                return False
    except UpdateError as exc:
        # A competing helper owns the installation lock. It remains the sole
        # writer of operation state; this contender must not mark it failed.
        if exc.code == "update_in_progress":
            return False
        try:
            _update_operation(
                base_dir,
                operation_id,
                phase="failed",
                progress=100,
                error_code=exc.code,
                completed_at=utc_now(),
            )
        except UpdateError:
            pass
        return False


def prepare_cli_operation(base_dir, channel, candidate):
    """Persist a trusted resolver result for an in-console transaction."""

    state = load_update_state(base_dir)
    identity = get_installed_identity(base_dir, state)
    assert_mutation_preconditions(state, identity)
    operation = {
        "id": uuid.uuid4().hex,
        "action": "apply",
        "phase": "queued",
        "progress": 0,
        "channel": channel,
        "target_sha": candidate["target_sha"],
        "short_target_sha": candidate["target_sha"][:8],
        "target_ref": candidate["target_ref"],
        "target_manifest": candidate["_target_manifest"],
        "base_version": candidate.get("base_version"),
        "previous_sha": identity.get("commit"),
        "short_previous_sha": identity.get("short_commit"),
        "error_code": None,
        "rolled_back": False,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "_server_pid": None,
    }
    state["operation"] = operation
    state.setdefault("channels", {})[channel] = candidate
    state["selected_channel"] = channel
    save_update_state(base_dir, state)
    return operation

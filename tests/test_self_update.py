import copy
import json
import os
import shutil
import subprocess
import threading
import time

import pytest

from backend.services import self_update


def _git(executable, repository, *args):
    result = subprocess.run(
        [executable, "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def _init_repository(path, executable):
    subprocess.run(
        [executable, "init", "--initial-branch=main", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _git(executable, path, "config", "user.name", "Sharp GUI Tests")
    _git(executable, path, "config", "user.email", "tests@example.invalid")
    _git(executable, path, "config", "commit.gpgSign", "false")
    _git(executable, path, "config", "core.autocrlf", "false")
    return path


def _commit_all(repository, executable, message):
    _git(executable, repository, "add", "-A")
    _git(executable, repository, "commit", "--no-gpg-sign", "-m", message)
    return _git(executable, repository, "rev-parse", "HEAD")


def _manifest(*, runtime_revision=1, minimum_git_version="2.0.0", targets=None):
    return {
        "schemaVersion": 1,
        "application": "sharp-gui",
        "repository": {
            "slug": self_update.CANONICAL_REPOSITORY_SLUG,
            "url": self_update.CANONICAL_REPOSITORY_URL,
        },
        "defaultBranch": "main",
        "updateProtocolRevision": 1,
        "portableRuntimeRevision": runtime_revision,
        "minimumGitVersion": minimum_git_version,
        "frontend": {
            "builtAssetsRequired": True,
            "entrypoint": "frontend/dist/index.html",
        },
        "supportedPortableTargets": targets or ["cu128-rtx50"],
    }


@pytest.fixture
def git_executable():
    executable = shutil.which("git")
    if not executable:
        pytest.skip("Git is required for self-update tests")
    return executable


def test_installed_identity_reports_release_and_commits_ahead(tmp_path, git_executable):
    repository = _init_repository(tmp_path / "identity-repo", git_executable)
    (repository / "tracked.txt").write_text("release\n", encoding="utf-8")
    release_sha = _commit_all(repository, git_executable, "release")
    _git(git_executable, repository, "tag", "v1.2.3", release_sha)
    (repository / "tracked.txt").write_text("hotfix\n", encoding="utf-8")
    head_sha = _commit_all(repository, git_executable, "hotfix")

    identity = self_update.get_installed_identity(repository)

    assert identity["base_version"] == "v1.2.3"
    assert identity["commit"] == head_sha
    assert identity["short_commit"] == head_sha[:8]
    assert identity["commits_ahead"] == 1
    assert identity["display_version"] == f"v1.2.3 + 1 commits ({head_sha[:8]})"
    assert identity["installation_kind"] == "source"
    assert identity["managed"] is True
    assert identity["dirty"] is False


def test_managed_worktree_supports_git_file_layout(tmp_path, git_executable):
    repository = _init_repository(tmp_path / "primary", git_executable)
    (repository / "tracked.txt").write_text("base\n", encoding="utf-8")
    _commit_all(repository, git_executable, "base")
    linked = tmp_path / "linked"
    _git(git_executable, repository, "worktree", "add", "-b", "linked-test", str(linked), "HEAD")

    assert (linked / ".git").is_file()
    assert self_update.is_managed_worktree(linked, git_executable) is True
    assert self_update.detect_deployment(linked, git_executable) == ("source", True)


def test_managed_generic_release_marker_is_not_treated_as_developer_branch(tmp_path, git_executable):
    repository = _init_repository(tmp_path / "managed-release", git_executable)
    (repository / "version.txt").write_text("v1.2.3\n", encoding="utf-8")
    _commit_all(repository, git_executable, "release snapshot")
    _git(git_executable, repository, "checkout", "--detach", "HEAD")
    _git(
        git_executable,
        repository,
        "config",
        "--local",
        "sharp-gui.installation-kind",
        "release",
    )

    assert self_update.detect_deployment(repository, git_executable) == ("release", True)
    identity = self_update.get_installed_identity(repository)
    self_update.assert_mutation_preconditions(self_update.default_update_state(), identity)


def test_portable_git_resolution_never_falls_back_to_system(tmp_path, monkeypatch):
    (tmp_path / "portable-package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "python").mkdir()
    (tmp_path / "python" / "python.exe").write_bytes(b"portable-python")
    monkeypatch.setattr(self_update.shutil, "which", lambda _name: "C:/system/git.exe")

    assert self_update.resolve_git_executable(tmp_path) is None

    bundled = tmp_path / ".sharp-gui-tools" / "git" / "cmd" / "git.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"bundled-git")
    assert self_update.resolve_git_executable(tmp_path) == str(bundled)


def test_manifest_compatibility_runtime_git_frontend_and_target_gates(tmp_path, monkeypatch):
    installed = _manifest()
    (tmp_path / "update-manifest.json").write_text(json.dumps(installed), encoding="utf-8")
    (tmp_path / "portable-package.json").write_text(
        json.dumps(
            {
                "target": "cu128-rtx50",
                "portableRuntimeRevision": 1,
                "updateProtocolRevision": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir: {
            "installation_kind": "portable",
            "git_version": "git version 2.45.1.windows.1",
        },
    )

    compatible = self_update.normalize_manifest(_manifest())
    assert self_update.compare_manifest_compatibility(tmp_path, compatible) == (
        True,
        "update_compatible",
    )

    runtime_mismatch = copy.deepcopy(compatible)
    runtime_mismatch["portable_runtime_revision"] = 2
    assert self_update.compare_manifest_compatibility(tmp_path, runtime_mismatch) == (
        False,
        "update_full_package_required",
    )

    git_too_new = self_update.normalize_manifest(_manifest(minimum_git_version="99.0.0"))
    assert self_update.compare_manifest_compatibility(tmp_path, git_too_new) == (
        False,
        "update_git_too_old",
    )

    assert self_update.compare_manifest_compatibility(
        tmp_path,
        compatible,
        target_frontend_present=False,
    ) == (False, "update_frontend_missing")

    unsupported_target = self_update.normalize_manifest(_manifest(targets=["cu126-mainstream"]))
    assert self_update.compare_manifest_compatibility(tmp_path, unsupported_target) == (
        False,
        "update_target_unsupported",
    )


def test_dirty_check_ignores_untracked_but_detects_tracked_changes(tmp_path, git_executable):
    repository = _init_repository(tmp_path / "dirty-repo", git_executable)
    tracked = repository / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    _commit_all(repository, git_executable, "base")

    assert self_update.tracked_worktree_dirty(repository, git_executable) is False
    (repository / "config.json").write_text('{"marker": true}\n', encoding="utf-8")
    assert self_update.tracked_worktree_dirty(repository, git_executable) is False
    tracked.write_text("modified\n", encoding="utf-8")
    assert self_update.tracked_worktree_dirty(repository, git_executable) is True


def test_status_sanitization_never_exposes_paths_commands_or_private_fields(tmp_path, monkeypatch):
    sentinel = str(tmp_path / "private" / "install")
    state = self_update.default_update_state()
    state["channels"] = {
        "latest": {
            "channel": "latest",
            "target_sha": "a" * 40,
            "short_sha": "a" * 8,
            "checked_at": self_update.utc_now(),
            "target_ref": sentinel,
            "_target_manifest": {"path": sentinel},
            "command": ["git", "reset", "--hard"],
        }
    }
    state["operation"] = {
        "id": "operation-id",
        "phase": "failed",
        "target_sha": "a" * 40,
        "target_manifest": {"path": sentinel},
        "_helper_pid": 123,
        "log_path": sentinel,
    }
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "base_version": "v1.2.3",
            "commit": "b" * 40,
            "short_commit": "b" * 8,
            "commits_ahead": 1,
            "display_version": "v1.2.3 + 1 commits (bbbbbbbb)",
            "channel": "latest",
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
            "git_version": "git version 2.45.1",
            "install_path": sentinel,
            "command": ["git", "status"],
        },
    )

    status = self_update.SelfUpdateManager(base_dir=tmp_path).status(is_owner=False)
    serialized = json.dumps(status)

    assert sentinel not in serialized
    assert "target_ref" not in serialized
    assert "_target_manifest" not in serialized
    assert "target_manifest" not in serialized
    assert "_helper_pid" not in serialized
    assert "log_path" not in serialized
    assert "command" not in serialized


class _FakeGithubHttp:
    release_sha = "1" * 40
    latest_sha = "2" * 40

    def __init__(self, manifest):
        self.manifest = manifest
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if url.endswith("/releases/latest"):
            return {
                "tag_name": "v1.2.3",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/example/releases/v1.2.3",
            }, False
        if url.endswith("/commits/v1.2.3"):
            return {"sha": self.release_sha, "html_url": "https://github.com/example/release"}, False
        if url.endswith("/commits/main"):
            return {"sha": self.latest_sha, "html_url": "https://github.com/example/latest"}, False
        if "/compare/v1.2.3..." in url:
            return {"ahead_by": 3}, False
        if "/compare/" in url:
            return {"status": "ahead"}, False
        raise AssertionError(f"Unexpected fake GitHub JSON URL: {url}")

    def get_bytes(self, url, *, accept="application/octet-stream"):
        self.calls.append(url)
        if url.endswith("/update-manifest.json"):
            return json.dumps(self.manifest).encode("utf-8"), False
        if url.endswith("/frontend/dist/index.html"):
            return b"<html>built</html>", False
        raise AssertionError(f"Unexpected fake GitHub bytes URL: {url} ({accept})")


@pytest.mark.parametrize(
    ("channel", "expected_sha", "expected_ref", "expected_ahead", "expected_display"),
    [
        ("stable", "1" * 40, "refs/tags/v1.2.3", 0, "v1.2.3"),
        (
            "latest",
            "2" * 40,
            "refs/heads/main",
            3,
            "v1.2.3 + 3 commits (22222222)",
        ),
    ],
)
def test_stable_and_latest_resolver_use_fake_http_exact_targets(
    tmp_path,
    monkeypatch,
    channel,
    expected_sha,
    expected_ref,
    expected_ahead,
    expected_display,
):
    fake_http = _FakeGithubHttp(_manifest())
    monkeypatch.setattr(
        self_update,
        "compare_manifest_compatibility",
        lambda *_args, **_kwargs: (True, "update_compatible"),
    )
    resolver = self_update.GithubTargetResolver(tmp_path, http_client=fake_http)

    candidate = resolver.resolve(channel, {"commit": "0" * 40})

    assert candidate["target_sha"] == expected_sha
    assert candidate["target_ref"] == expected_ref
    assert candidate["commits_ahead"] == expected_ahead
    assert candidate["display_version"] == expected_display
    assert candidate["relation"] == "upgrade"
    assert candidate["update_available"] is True
    assert candidate["compatible"] is True
    assert candidate["_target_manifest"] == _manifest()


@pytest.mark.parametrize("error_code", ["update_check_rate_limited", "update_check_failed"])
def test_check_returns_fresh_cached_candidate_when_resolver_fails(tmp_path, monkeypatch, error_code):
    candidate = {
        "channel": "latest",
        "target_sha": "2" * 40,
        "short_sha": "2" * 8,
        "target_ref": "refs/heads/main",
        "base_version": "v1.2.3",
        "commits_ahead": 3,
        "display_version": "v1.2.3 + 3 commits (22222222)",
        "relation": "upgrade",
        "update_available": True,
        "compatible": True,
        "compatibility_code": "update_compatible",
        "checked_at": self_update.utc_now(),
        "cached": False,
        "target_token": "cached-token",
        "expires_at": "2999-01-01T00:00:00Z",
        "_target_manifest": _manifest(),
    }
    state = self_update.default_update_state()
    state["channels"] = {"latest": candidate}
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "base_version": "v1.2.3",
            "commit": "0" * 40,
            "short_commit": "0" * 8,
            "commits_ahead": 0,
            "display_version": "v1.2.3",
            "channel": "stable",
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
            "git_version": "git version 2.45.1",
        },
    )

    class FailingResolver:
        def resolve(self, _channel, _identity):
            raise self_update.UpdateError(error_code, status_code=503)

    manager = self_update.SelfUpdateManager(
        base_dir=tmp_path,
        resolver_factory=lambda: FailingResolver(),
    )

    status = manager.check("latest")

    assert status["last_check_error_code"] == error_code
    assert status["channels"]["latest"]["cached"] is True
    assert status["channels"]["latest"]["check_error_code"] == error_code
    assert status["channels"]["latest"]["target_sha"] == "2" * 40


def test_concurrent_checks_are_serialized(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    first_result = []
    first_error = []
    candidate = {
        "channel": "latest",
        "target_sha": "2" * 40,
        "short_sha": "2" * 8,
        "target_ref": "refs/heads/main",
        "base_version": "v1.2.3",
        "commits_ahead": 3,
        "display_version": "v1.2.3 + 3 commits (22222222)",
        "relation": "upgrade",
        "update_available": True,
        "compatible": True,
        "compatibility_code": "update_compatible",
        "checked_at": self_update.utc_now(),
        "cached": False,
        "target_token": "token",
        "expires_at": "2999-01-01T00:00:00Z",
        "_target_manifest": _manifest(),
    }
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "base_version": "v1.2.3",
            "commit": "0" * 40,
            "short_commit": "0" * 8,
            "commits_ahead": 0,
            "display_version": "v1.2.3",
            "channel": "stable",
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
            "git_version": "git version 2.45.1",
        },
    )

    class BlockingResolver:
        def resolve(self, _channel, _identity):
            entered.set()
            assert release.wait(timeout=5)
            return candidate

    manager = self_update.SelfUpdateManager(
        base_dir=tmp_path,
        resolver_factory=lambda: BlockingResolver(),
    )

    def run_first_check():
        try:
            first_result.append(manager.check("latest"))
        except Exception as exc:  # pragma: no cover - asserted below
            first_error.append(exc)

    thread = threading.Thread(target=run_first_check)
    thread.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(self_update.UpdateError) as caught:
            manager.check("stable")
        assert caught.value.code == "update_in_progress"
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert first_error == []
    assert first_result[0]["channels"]["latest"]["target_sha"] == "2" * 40


def test_manager_constructor_has_no_network_process_thread_or_state_side_effects(tmp_path, monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("constructor performed an active side effect")

    monkeypatch.setattr(self_update, "urlopen", forbidden)
    monkeypatch.setattr(self_update.threading.Thread, "start", forbidden)

    manager = self_update.SelfUpdateManager(
        base_dir=tmp_path,
        resolver_factory=forbidden,
        process_factory=forbidden,
        restart_callback=forbidden,
    )

    assert manager.base_dir == str(tmp_path.resolve())
    assert calls == []
    assert not (tmp_path / self_update.STATE_DIR_NAME).exists()


@pytest.mark.parametrize(
    ("state_patch", "identity_patch", "checking", "has_active_tasks", "expected_code"),
    [
        ({"operation": {"phase": "queued"}}, {}, False, False, "update_in_progress"),
        ({}, {}, True, False, "update_in_progress"),
        ({}, {}, False, True, "update_tasks_active"),
        ({}, {"dirty": True}, False, False, "update_worktree_dirty"),
        ({}, {"branch": "feature/test"}, False, False, "update_developer_branch"),
    ],
)
def test_mutation_preconditions_block_unsafe_states(
    tmp_path,
    state_patch,
    identity_patch,
    checking,
    has_active_tasks,
    expected_code,
):
    class TaskManager:
        def list_tasks(self):
            return [], has_active_tasks

    manager = self_update.SelfUpdateManager(base_dir=tmp_path, task_manager=TaskManager())
    manager._checking = checking
    state = self_update.default_update_state()
    state.update(state_patch)
    identity = {
        "installation_kind": "source",
        "managed": True,
        "dirty": False,
        "branch": "main",
    }
    identity.update(identity_patch)

    with pytest.raises(self_update.UpdateError) as caught:
        manager._assert_mutation_preconditions(state, identity)

    assert caught.value.code == expected_code


def test_start_apply_rejects_expired_or_mismatched_target_token(tmp_path, monkeypatch):
    candidate = {
        "channel": "latest",
        "target_sha": "2" * 40,
        "target_ref": "refs/heads/main",
        "base_version": "v1.2.3",
        "update_available": True,
        "compatible": True,
        "target_token": "trusted-token",
        "expires_at": "2000-01-01T00:00:00Z",
        "_target_manifest": _manifest(),
    }
    state = self_update.default_update_state()
    state["channels"] = {"latest": candidate}
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "commit": "1" * 40,
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
            "git_version": "git version 2.45.1",
        },
    )
    manager = self_update.SelfUpdateManager(
        base_dir=tmp_path,
        process_factory=lambda *_args, **_kwargs: pytest.fail("expired target spawned helper"),
    )

    with pytest.raises(self_update.UpdateError) as mismatched:
        manager.start_apply("latest", "wrong-token")
    assert mismatched.value.code == "update_target_untrusted"

    with pytest.raises(self_update.UpdateError) as expired:
        manager.start_apply("latest", "trusted-token")
    assert expired.value.code == "update_target_expired"


def _trusted_cli_candidate():
    target_sha = "2" * 40
    return {
        "channel": "latest",
        "target_sha": target_sha,
        "short_sha": target_sha[:8],
        "target_ref": "refs/heads/main",
        "base_version": "v1.2.3",
        "update_available": True,
        "compatible": True,
        "target_token": "trusted-token",
        "expires_at": "2999-01-01T00:00:00Z",
        "_target_manifest": _manifest(),
    }


@pytest.mark.parametrize(
    ("identity_patch", "expected_code"),
    [
        ({"dirty": True}, "update_worktree_dirty"),
        ({"branch": "feature/unsafe"}, "update_developer_branch"),
    ],
)
def test_prepare_cli_operation_rejects_unsafe_install_identity(
    tmp_path,
    monkeypatch,
    identity_patch,
    expected_code,
):
    """CLI preparation must enforce the same worktree gate as the HTTP manager."""

    identity = {
        "commit": "1" * 40,
        "short_commit": "1" * 8,
        "installation_kind": "source",
        "managed": True,
        "dirty": False,
        "branch": "main",
    }
    identity.update(identity_patch)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: identity,
    )

    with pytest.raises(self_update.UpdateError) as caught:
        self_update.prepare_cli_operation(tmp_path, "latest", _trusted_cli_candidate())

    assert caught.value.code == expected_code
    assert self_update.load_update_state(tmp_path)["operation"] is None


def test_prepare_cli_operation_does_not_replace_active_operation(tmp_path, monkeypatch):
    """A second CLI invocation must not erase an in-flight updater operation."""

    active_operation = {
        "id": "existing-operation",
        "phase": "fetching",
        "target_sha": "3" * 40,
        "updated_at": self_update.utc_now(),
    }
    state = self_update.default_update_state()
    state["operation"] = active_operation
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "commit": "1" * 40,
            "short_commit": "1" * 8,
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
        },
    )

    with pytest.raises(self_update.UpdateError) as caught:
        self_update.prepare_cli_operation(tmp_path, "latest", _trusted_cli_candidate())

    assert caught.value.code == "update_in_progress"
    assert self_update.load_update_state(tmp_path)["operation"] == active_operation


@pytest.mark.parametrize(
    "tracked_path",
    [
        "Config.json",
        "venv/Scripts/python.exe",
        "frontend/node_modules/react/index.js",
        ".sharp-gui.lock",
    ],
)
def test_target_protected_runtime_paths_are_windows_case_insensitive(
    tmp_path,
    monkeypatch,
    tracked_path,
):
    """A target tree must never collide with portable/runtime paths on Windows."""

    monkeypatch.setattr(
        self_update,
        "run_git",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git", "ls-tree"],
            returncode=0,
            stdout=f"{tracked_path}\n",
            stderr="",
        ),
    )

    assert self_update.target_tracks_protected_runtime(tmp_path, "2" * 40) is True


@pytest.mark.parametrize("missing_path", ["app.py", "backend", "tools"])
def test_checked_out_revision_requires_complete_application_tree(
    tmp_path,
    monkeypatch,
    missing_path,
):
    expected_sha = "2" * 40
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "healthy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "healthy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text(
        "<html>healthy</html>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "update-manifest.json").write_text(
        json.dumps(_manifest()) + "\n",
        encoding="utf-8",
    )
    target = tmp_path / missing_path
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    monkeypatch.setattr(self_update, "_git_value", lambda *_args, **_kwargs: expected_sha)
    monkeypatch.setattr(
        self_update,
        "compare_manifest_compatibility",
        lambda *_args, **_kwargs: (True, "update_compatible"),
    )
    monkeypatch.setattr(self_update, "tracked_worktree_dirty", lambda *_args, **_kwargs: False)

    with pytest.raises(self_update.UpdateError):
        self_update.verify_checked_out_revision(
            tmp_path,
            expected_sha,
            git_executable="git",
        )


def test_failed_reset_after_partial_mutation_is_rolled_back(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    operation_id = "partial-reset-operation"
    marker = tmp_path / "tracked.txt"
    marker.write_text("previous\n", encoding="utf-8")
    current = {"sha": previous_sha}
    reset_targets = []
    state = self_update.default_update_state()
    state["operation"] = {
        "id": operation_id,
        "action": "apply",
        "phase": "queued",
        "progress": 0,
        "channel": "latest",
        "target_sha": target_sha,
        "short_target_sha": target_sha[:8],
        "target_ref": "refs/heads/main",
        "target_manifest": _manifest(),
        "base_version": "v1.2.3",
        "previous_sha": previous_sha,
        "short_previous_sha": previous_sha[:8],
        "error_code": None,
        "rolled_back": False,
        "rollback_available": False,
        "started_at": self_update.utc_now(),
        "updated_at": self_update.utc_now(),
        "_server_pid": None,
    }
    self_update.save_update_state(tmp_path, state)

    def fake_run_git(_base_dir, arguments, **_kwargs):
        if arguments[:2] == ["reset", "--hard"]:
            revision = arguments[2]
            reset_targets.append(revision)
            current["sha"] = revision
            marker.write_text(
                "target\n" if revision == target_sha else "previous\n",
                encoding="utf-8",
            )
            if revision == target_sha:
                raise subprocess.CalledProcessError(1, ["git", *arguments])
        return subprocess.CompletedProcess(
            args=["git", *arguments],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(self_update, "resolve_git_executable", lambda _base_dir: "git")
    monkeypatch.setattr(self_update, "is_managed_worktree", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(self_update, "tracked_worktree_dirty", lambda *_args, **_kwargs: False)
    def fake_git_value(_base_dir, arguments, **_kwargs):
        if arguments and arguments[0] == "symbolic-ref":
            return "main"
        return current["sha"]

    monkeypatch.setattr(self_update, "_git_value", fake_git_value)
    monkeypatch.setattr(self_update, "_fetch_exact_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        self_update,
        "manifest_from_git",
        lambda *_args, **_kwargs: _manifest(),
    )
    monkeypatch.setattr(self_update, "git_path_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        self_update,
        "compare_manifest_compatibility",
        lambda *_args, **_kwargs: (True, "update_compatible"),
    )
    monkeypatch.setattr(
        self_update,
        "target_tracks_protected_runtime",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        self_update,
        "verify_checked_out_revision",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(self_update, "run_git", fake_run_git)

    assert self_update.run_update_operation(
        tmp_path,
        operation_id,
        wait_for_server=False,
        relaunch=False,
    ) is False
    assert reset_targets == [target_sha, previous_sha]
    assert current["sha"] == previous_sha
    assert marker.read_text(encoding="utf-8") == "previous\n"
    failed = self_update.load_update_state(tmp_path)["operation"]
    assert failed["phase"] == "failed"
    assert failed["rolled_back"] is True


def test_frontend_network_error_is_not_reported_as_missing_build(tmp_path):
    class FrontendNetworkFailure(_FakeGithubHttp):
        def get_bytes(self, url, *, accept="application/octet-stream"):
            if url.endswith("/frontend/dist/index.html"):
                raise self_update.UpdateError("update_check_failed", status_code=503)
            return super().get_bytes(url, accept=accept)

    resolver = self_update.GithubTargetResolver(
        tmp_path,
        http_client=FrontendNetworkFailure(_manifest()),
    )

    with pytest.raises(self_update.UpdateError) as caught:
        resolver.resolve("latest", {"commit": "0" * 40})

    assert caught.value.code == "update_check_failed"


def test_reconcile_verifies_target_before_marking_restart_complete(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    state = self_update.default_update_state()
    state["operation"] = {
        "id": "restart-operation",
        "action": "apply",
        "phase": "restarting",
        "progress": 92,
        "channel": "latest",
        "target_sha": target_sha,
        "previous_sha": previous_sha,
        "updated_at": self_update.utc_now(),
    }
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda _base_dir, _state=None: {
            "base_version": "v1.2.3",
            "commit": target_sha,
            "short_commit": target_sha[:8],
            "display_version": f"v1.2.3 ({target_sha[:8]})",
            "installation_kind": "source",
            "managed": True,
            "dirty": False,
            "branch": "main",
            "git_version": "git version 2.45.1",
        },
    )
    verified = []

    def record_verification(base_dir, expected_sha, **_kwargs):
        verified.append((str(base_dir), expected_sha))
        return True

    monkeypatch.setattr(self_update, "verify_checked_out_revision", record_verification)

    status = self_update.SelfUpdateManager(base_dir=tmp_path).status(is_owner=True)

    assert verified == [(str(tmp_path.resolve()), target_sha)]
    assert status["operation"]["phase"] == "completed"


def _transaction_operation(operation_id, previous_sha, target_sha):
    return {
        "id": operation_id,
        "action": "apply",
        "phase": "queued",
        "progress": 0,
        "channel": "latest",
        "target_sha": target_sha,
        "short_target_sha": target_sha[:8],
        "target_ref": "refs/heads/main",
        "target_manifest": _manifest(),
        "base_version": "v1.2.3",
        "previous_sha": previous_sha,
        "short_previous_sha": previous_sha[:8],
        "error_code": None,
        "rolled_back": False,
        "rollback_available": False,
        "started_at": self_update.utc_now(),
        "updated_at": self_update.utc_now(),
        "_server_pid": None,
    }


def _mock_relaunch_transaction(monkeypatch, current, resets, verifications):
    monkeypatch.setattr(self_update, "resolve_git_executable", lambda _base_dir: "git")
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda *_args, **_kwargs: {
            "installation_kind": "portable",
            "managed": True,
            "dirty": False,
            "branch": None,
        },
    )
    monkeypatch.setattr(self_update, "is_managed_worktree", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(self_update, "tracked_worktree_dirty", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(self_update, "_git_value", lambda *_args, **_kwargs: current["sha"])
    monkeypatch.setattr(self_update, "_fetch_exact_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(self_update, "manifest_from_git", lambda *_args, **_kwargs: _manifest())
    monkeypatch.setattr(self_update, "git_path_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        self_update,
        "compare_manifest_compatibility",
        lambda *_args, **_kwargs: (True, "update_compatible"),
    )
    monkeypatch.setattr(self_update, "target_tracks_protected_runtime", lambda *_args, **_kwargs: False)

    def fake_run_git(_base_dir, arguments, **_kwargs):
        if arguments[:2] == ["reset", "--hard"]:
            current["sha"] = arguments[2]
            resets.append(arguments[2])
        return subprocess.CompletedProcess(["git", *arguments], 0, "", "")

    def fake_verify(_base_dir, expected_sha, **_kwargs):
        verifications.append(expected_sha)
        assert current["sha"] == expected_sha
        return True

    monkeypatch.setattr(self_update, "run_git", fake_run_git)
    monkeypatch.setattr(self_update, "verify_checked_out_revision", fake_verify)


def test_restart_health_failure_rolls_back_and_restarts_previous_revision(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    operation_id = "restart-failure"
    state = self_update.default_update_state()
    state["operation"] = _transaction_operation(operation_id, previous_sha, target_sha)
    self_update.save_update_state(tmp_path, state)
    current = {"sha": previous_sha}
    resets = []
    verifications = []
    _mock_relaunch_transaction(monkeypatch, current, resets, verifications)

    launched = []
    terminated = []
    health_checks = []

    def fake_launch(_base_dir):
        process = object()
        launched.append(process)
        return process

    def fake_health(_process, expected_sha, **kwargs):
        health_checks.append((expected_sha, kwargs.get("fail_on_operation_error", True)))
        return expected_sha == previous_sha

    monkeypatch.setattr(self_update, "launch_application", fake_launch)
    monkeypatch.setattr(self_update, "wait_for_application_health", fake_health)
    monkeypatch.setattr(self_update, "terminate_application_process", terminated.append)

    assert self_update.run_update_operation(
        tmp_path,
        operation_id,
        wait_for_server=False,
        relaunch=True,
    ) is False
    assert resets == [target_sha, previous_sha]
    assert verifications == [target_sha, previous_sha]
    assert health_checks == [(target_sha, True), (previous_sha, False)]
    assert len(launched) == 2
    assert terminated == [launched[0]]
    final = self_update.load_update_state(tmp_path)["operation"]
    assert final["phase"] == "failed"
    assert final["error_code"] == "update_restart_failed"
    assert final["rolled_back"] is True
    assert current["sha"] == previous_sha


def test_update_completes_only_after_target_health_succeeds(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    operation_id = "restart-success"
    state = self_update.default_update_state()
    state["operation"] = _transaction_operation(operation_id, previous_sha, target_sha)
    self_update.save_update_state(tmp_path, state)
    current = {"sha": previous_sha}
    resets = []
    verifications = []
    _mock_relaunch_transaction(monkeypatch, current, resets, verifications)
    process = object()
    monkeypatch.setattr(self_update, "launch_application", lambda _base_dir: process)
    monkeypatch.setattr(
        self_update,
        "wait_for_application_health",
        lambda actual_process, expected_sha, **_kwargs: actual_process is process and expected_sha == target_sha,
    )
    monkeypatch.setattr(
        self_update,
        "terminate_application_process",
        lambda _process: pytest.fail("healthy process must not be terminated"),
    )

    assert self_update.run_update_operation(
        tmp_path,
        operation_id,
        wait_for_server=False,
        relaunch=True,
    ) is True
    assert resets == [target_sha]
    assert verifications == [target_sha]
    final = self_update.load_update_state(tmp_path)["operation"]
    assert final["phase"] == "completed"
    assert final["progress"] == 100
    assert final["rollback_available"] is True


def test_operation_lock_preserves_fresh_empty_file_and_reclaims_stale_one(tmp_path):
    lock_path = tmp_path / self_update.STATE_DIR_NAME / self_update.LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True)
    lock_path.write_bytes(b"")

    with pytest.raises(self_update.UpdateError) as caught:
        with self_update.operation_lock(tmp_path, "contender"):
            pytest.fail("fresh initializing lock must not be acquired")
    assert caught.value.code == "update_in_progress"
    assert lock_path.is_file()

    stale_time = time.time() - self_update.LOCK_INITIALIZATION_GRACE_SECONDS - 1
    os.utime(lock_path, (stale_time, stale_time))
    with self_update.operation_lock(tmp_path, "recovered"):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["operation_id"] == "recovered"
    assert not lock_path.exists()


def test_reconcile_invalid_timestamp_reverifies_target_even_with_live_pid(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    state = self_update.default_update_state()
    operation = _transaction_operation("invalid-timestamp", previous_sha, target_sha)
    operation.update({"phase": "applying", "updated_at": "not-a-timestamp", "_helper_pid": os.getpid()})
    state["operation"] = operation
    self_update.save_update_state(tmp_path, state)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda *_args, **_kwargs: {
            "commit": target_sha,
            "installation_kind": "portable",
            "managed": True,
            "dirty": False,
            "git_version": "git version 2.45.1",
        },
    )
    verified = []
    monkeypatch.setattr(
        self_update,
        "verify_checked_out_revision",
        lambda _base_dir, expected_sha, **_kwargs: verified.append(expected_sha) or True,
    )

    status = self_update.SelfUpdateManager(base_dir=tmp_path).status(is_owner=True)

    assert verified == [target_sha]
    assert status["operation"]["phase"] == "completed"

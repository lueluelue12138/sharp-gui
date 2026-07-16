import json
import os
import subprocess
import time

import pytest

from backend.services import self_update


def _manifest():
    return {
        "schemaVersion": 1,
        "application": "sharp-gui",
        "repository": {
            "slug": self_update.CANONICAL_REPOSITORY_SLUG,
            "url": self_update.CANONICAL_REPOSITORY_URL,
        },
        "defaultBranch": "main",
        "updateProtocolRevision": 1,
        "portableRuntimeRevision": 1,
        "minimumGitVersion": "2.0.0",
        "frontend": {
            "builtAssetsRequired": True,
            "entrypoint": "frontend/dist/index.html",
        },
        "supportedPortableTargets": ["cu128-rtx50"],
    }


def _persist_operation(base_dir, operation_id, previous_sha, target_sha):
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
        "started_at": self_update.utc_now(),
        "updated_at": self_update.utc_now(),
        "_server_pid": None,
    }
    self_update.save_update_state(base_dir, state)


def _patch_compatible_checkout(monkeypatch, current, events):
    monkeypatch.setattr(self_update, "resolve_git_executable", lambda _base_dir: "git")
    monkeypatch.setattr(self_update, "is_managed_worktree", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(self_update, "tracked_worktree_dirty", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        self_update,
        "get_installed_identity",
        lambda *_args, **_kwargs: {
            "managed": True,
            "dirty": False,
            "installation_kind": "source",
            "branch": "main",
        },
    )
    monkeypatch.setattr(
        self_update,
        "_git_value",
        lambda *_args, **_kwargs: current["sha"],
    )
    monkeypatch.setattr(self_update, "_fetch_exact_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(self_update, "manifest_from_git", lambda *_args, **_kwargs: _manifest())
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

    def fake_run_git(_base_dir, arguments, **_kwargs):
        if arguments[:2] == ["reset", "--hard"]:
            revision = arguments[2]
            events.append(("reset", revision))
            current["sha"] = revision
        return subprocess.CompletedProcess(
            args=["git", *arguments],
            returncode=0,
            stdout="",
            stderr="",
        )

    def fake_verify(_base_dir, expected_sha, **_kwargs):
        events.append(("verify", expected_sha))
        assert current["sha"] == expected_sha
        return True

    monkeypatch.setattr(self_update, "run_git", fake_run_git)
    monkeypatch.setattr(self_update, "verify_checked_out_revision", fake_verify)


class _FakeApplicationProcess:
    def __init__(self, revision):
        self.revision = revision


def test_target_restart_health_failure_rolls_back_and_restarts_previous(
    tmp_path,
    monkeypatch,
):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    operation_id = "restart-failure-operation"
    current = {"sha": previous_sha}
    events = []
    _persist_operation(tmp_path, operation_id, previous_sha, target_sha)
    _patch_compatible_checkout(monkeypatch, current, events)

    def fake_launch(_base_dir):
        process = _FakeApplicationProcess(current["sha"])
        events.append(("launch", process.revision))
        return process

    def fake_health(process, expected_sha, **kwargs):
        events.append(("health", process.revision, expected_sha, kwargs))
        return expected_sha == previous_sha

    def fake_terminate(process):
        if process is not None:
            events.append(("terminate", process.revision))

    monkeypatch.setattr(self_update, "launch_application", fake_launch)
    monkeypatch.setattr(self_update, "wait_for_application_health", fake_health)
    monkeypatch.setattr(self_update, "terminate_application_process", fake_terminate)

    assert self_update.run_update_operation(
        tmp_path,
        operation_id,
        wait_for_server=False,
        relaunch=True,
    ) is False

    assert events == [
        ("reset", target_sha),
        ("verify", target_sha),
        ("launch", target_sha),
        ("health", target_sha, target_sha, {}),
        ("terminate", target_sha),
        ("reset", previous_sha),
        ("verify", previous_sha),
        ("launch", previous_sha),
        (
            "health",
            previous_sha,
            previous_sha,
            {"fail_on_operation_error": False},
        ),
    ]
    assert current["sha"] == previous_sha
    failed = self_update.load_update_state(tmp_path)["operation"]
    assert failed["phase"] == "failed"
    assert failed["error_code"] == "update_restart_failed"
    assert failed["rolled_back"] is True


def test_target_is_completed_only_after_restart_health_succeeds(tmp_path, monkeypatch):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    operation_id = "restart-success-operation"
    current = {"sha": previous_sha}
    events = []
    _persist_operation(tmp_path, operation_id, previous_sha, target_sha)
    _patch_compatible_checkout(monkeypatch, current, events)

    def fake_launch(_base_dir):
        process = _FakeApplicationProcess(current["sha"])
        events.append(("launch", process.revision))
        return process

    def fake_health(process, expected_sha, **kwargs):
        operation_during_probe = self_update.load_update_state(tmp_path)["operation"]
        events.append(
            (
                "health",
                process.revision,
                expected_sha,
                operation_during_probe["phase"],
                operation_during_probe.get("completed_at"),
            )
        )
        return True

    monkeypatch.setattr(self_update, "launch_application", fake_launch)
    monkeypatch.setattr(self_update, "wait_for_application_health", fake_health)

    assert self_update.run_update_operation(
        tmp_path,
        operation_id,
        wait_for_server=False,
        relaunch=True,
    ) is True

    assert events == [
        ("reset", target_sha),
        ("verify", target_sha),
        ("launch", target_sha),
        ("health", target_sha, target_sha, "restarting", None),
    ]
    completed = self_update.load_update_state(tmp_path)["operation"]
    assert completed["phase"] == "completed"
    assert completed["progress"] == 100
    assert completed["error_code"] is None
    assert completed["completed_at"] is not None
    assert completed["rolled_back"] is False


def test_operation_lock_preserves_fresh_empty_lock_and_reclaims_old_one(tmp_path):
    lock_path = (
        tmp_path
        / self_update.STATE_DIR_NAME
        / self_update.LOCK_FILE_NAME
    )
    lock_path.parent.mkdir(parents=True)
    lock_path.write_bytes(b"")

    with pytest.raises(self_update.UpdateError) as caught:
        with self_update.operation_lock(tmp_path, "contender"):
            pytest.fail("a fresh partially initialized lock must not be acquired")

    assert caught.value.code == "update_in_progress"
    assert lock_path.exists()
    assert lock_path.read_bytes() == b""

    old_timestamp = time.time() - self_update.LOCK_INITIALIZATION_GRACE_SECONDS - 1
    os.utime(lock_path, (old_timestamp, old_timestamp))
    with self_update.operation_lock(tmp_path, "replacement"):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload == {"operation_id": "replacement", "pid": os.getpid()}

    assert not lock_path.exists()


@pytest.mark.parametrize(
    (
        "updated_at",
        "current_revision",
        "expected_phase",
        "expected_error",
        "expected_rolled_back",
    ),
    [
        ("not-a-timestamp", "target", "completed", None, False),
        (None, "previous", "failed", "update_interrupted_rolled_back", True),
    ],
)
def test_reconcile_reverifies_inactive_operation_with_invalid_or_missing_timestamp(
    tmp_path,
    monkeypatch,
    updated_at,
    current_revision,
    expected_phase,
    expected_error,
    expected_rolled_back,
):
    previous_sha = "1" * 40
    target_sha = "2" * 40
    current_sha = target_sha if current_revision == "target" else previous_sha
    state = self_update.default_update_state()
    operation = {
        "id": f"reconcile-{current_revision}",
        "action": "apply",
        "phase": "verifying",
        "progress": 78,
        "channel": "latest",
        "target_sha": target_sha,
        "previous_sha": previous_sha,
        "_helper_pid": 424242,
    }
    if updated_at is not None:
        operation["updated_at"] = updated_at
    state["operation"] = operation
    verified = []

    monkeypatch.setattr(self_update, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(
        self_update,
        "verify_checked_out_revision",
        lambda _base_dir, expected_sha, **_kwargs: verified.append(expected_sha) or True,
    )

    reconciled = self_update.SelfUpdateManager(base_dir=tmp_path)._reconcile(
        state,
        {"commit": current_sha},
    )

    assert verified == [current_sha]
    assert reconciled["operation"]["phase"] == expected_phase
    assert reconciled["operation"]["error_code"] == expected_error
    assert reconciled["operation"]["rolled_back"] is expected_rolled_back
    assert reconciled["operation"]["completed_at"] is not None
    persisted = self_update.load_update_state(tmp_path)["operation"]
    assert persisted["phase"] == expected_phase
    assert persisted["error_code"] == expected_error

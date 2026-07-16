import copy
from argparse import Namespace

import pytest

from backend.services import self_update
from tools import update as update_cli


def _args(**overrides):
    values = {
        "internal_run": None,
        "pre": False,
        "channel": "stable",
        "rollback": False,
        "yes": False,
        "check": False,
    }
    values.update(overrides)
    return Namespace(**values)


@pytest.mark.parametrize(
    "reason_code",
    ["update_tasks_active", "update_worktree_dirty", "update_developer_branch"],
)
def test_run_cli_honors_status_apply_preconditions(tmp_path, monkeypatch, reason_code):
    class BlockedManager:
        def __init__(self, *, base_dir):
            assert base_dir == tmp_path

        def status(self, *, is_owner):
            assert is_owner is True
            return {
                "capabilities": {
                    "can_apply": False,
                    "reason_code": reason_code,
                }
            }

    monkeypatch.setattr(update_cli, "BASE_DIR", tmp_path)
    monkeypatch.setattr(update_cli, "SelfUpdateManager", BlockedManager)
    monkeypatch.setattr(
        update_cli,
        "get_installed_identity",
        lambda *_args, **_kwargs: {
            "display_version": "v1.2.3",
            "installation_kind": "source",
            "branch": "main",
        },
    )
    monkeypatch.setattr(
        update_cli,
        "checked_candidate",
        lambda *_args, **_kwargs: pytest.fail("unsafe CLI reached update check"),
    )

    with pytest.raises(self_update.UpdateError) as caught:
        update_cli.run_cli(_args(channel="latest"))

    assert caught.value.code == reason_code


def test_cancelled_cli_rollback_preserves_completed_update_state(tmp_path, monkeypatch):
    completed_operation = {
        "id": "completed-update",
        "action": "apply",
        "phase": "completed",
        "progress": 100,
        "channel": "latest",
        "target_sha": "2" * 40,
        "previous_sha": "1" * 40,
        "rollback_available": True,
        "rolled_back": False,
        "updated_at": self_update.utc_now(),
        "completed_at": self_update.utc_now(),
    }
    state = self_update.default_update_state()
    state["operation"] = copy.deepcopy(completed_operation)
    self_update.save_update_state(tmp_path, state)

    class PassiveManager:
        def __init__(self, *, base_dir):
            assert base_dir == tmp_path

        def status(self, *, is_owner):
            assert is_owner is True
            return {}

    def mutating_prepare(base_dir):
        queued_state = self_update.load_update_state(base_dir)
        queued_state["operation"] = {
            "id": "queued-rollback",
            "action": "rollback",
            "phase": "queued",
            "target_sha": "1" * 40,
        }
        self_update.save_update_state(base_dir, queued_state)
        return {"id": "queued-rollback", "short_target_sha": "11111111"}

    monkeypatch.setattr(update_cli, "BASE_DIR", tmp_path)
    monkeypatch.setattr(update_cli, "SelfUpdateManager", PassiveManager)
    monkeypatch.setattr(
        update_cli,
        "get_installed_identity",
        lambda *_args, **_kwargs: {
            "display_version": "v1.2.3 + 1 commits (22222222)",
            "installation_kind": "source",
            "branch": "main",
        },
    )
    monkeypatch.setattr(update_cli, "local_server_is_running", lambda: False)
    monkeypatch.setattr(update_cli, "prepare_cli_rollback", mutating_prepare)
    monkeypatch.setattr(update_cli, "confirm", lambda _prompt: False)

    assert update_cli.run_cli(_args(rollback=True)) == 0
    assert self_update.load_update_state(tmp_path)["operation"] == completed_operation

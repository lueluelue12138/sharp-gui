from argparse import Namespace

import pytest

from backend.services import self_update
from tools import update as update_cli


def _args(**overrides):
    values = {
        "internal_run": None,
        "channel": "stable",
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

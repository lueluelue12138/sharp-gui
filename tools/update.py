#!/usr/bin/env python3
"""Safe command-line entry point for Sharp GUI code updates."""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.services.self_update import (  # noqa: E402
    ACTIVE_PHASES,
    SelfUpdateManager,
    UpdateError,
    get_installed_identity,
    load_update_state,
    prepare_cli_operation,
    run_update_operation,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Check or apply a verified Sharp GUI code update.",
    )
    parser.add_argument(
        "--channel",
        choices=("stable", "latest"),
        default="stable",
        help="stable = highest formal vX.Y.Z tag; latest = current main commit",
    )
    parser.add_argument("--check", action="store_true", help="check only; do not modify files")
    parser.add_argument("--yes", "-y", action="store_true", help="apply without an interactive confirmation")
    parser.add_argument("--internal-run", metavar="OPERATION_ID", help=argparse.SUPPRESS)
    return parser


def print_identity(identity):
    print(f"Current version: {identity.get('display_version') or 'unknown'}")
    print(f"Installation:    {identity.get('installation_kind') or 'unknown'}")
    if identity.get("branch"):
        print(f"Git branch:      {identity['branch']}")


def print_candidate(candidate):
    print(f"Target channel:  {candidate['channel']}")
    print(f"Target version:  {candidate['display_version']}")
    print(f"Target commit:   {candidate['short_sha']}")
    print(f"Relationship:    {candidate['relation']}")
    print(f"Compatibility:   {candidate['compatibility_code']}")
    if candidate.get("advisory_code"):
        print(f"Advisory:        {candidate['advisory_code']}")


def local_server_is_running():
    host = os.environ.get("SHARP_BIND_HOST", "127.0.0.1")
    if host in {"", "0.0.0.0", "::"}:
        host = "127.0.0.1"
    try:
        port = int(os.environ.get("SHARP_PORT", "5050"))
    except ValueError:
        port = 5050
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def checked_candidate(manager, channel):
    status = manager.check(channel, is_owner=True)
    candidate = status.get("channels", {}).get(channel)
    if not candidate:
        raise UpdateError(status.get("last_check_error_code") or "update_check_failed", status_code=503)
    # The public response is sanitized. Read the persisted trusted record for
    # transaction-only ref/manifest data; no CLI argument supplies either.
    persisted = load_update_state(BASE_DIR).get("channels", {}).get(channel)
    if not isinstance(persisted, dict):
        raise UpdateError("update_target_untrusted")
    return persisted


def confirm(prompt):
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def run_cli(args):
    if args.internal_run:
        return 0 if run_update_operation(BASE_DIR, args.internal_run) else 1

    channel = args.channel

    manager = SelfUpdateManager(base_dir=BASE_DIR)
    # Reconcile a previously interrupted terminal/restart state before deciding
    # whether another CLI operation may start.
    manager_status = manager.status(is_owner=True)
    state = load_update_state(BASE_DIR)
    if (state.get("operation") or {}).get("phase") in ACTIVE_PHASES:
        raise UpdateError("update_in_progress")

    if not args.check:
        capabilities = manager_status.get("capabilities") or {}
        reason_codes = capabilities.get("reason_codes")
        if not isinstance(reason_codes, list):
            reason_codes = [capabilities.get("reason_code")]
        blocking = {
            "update_in_progress",
            "update_tasks_active",
            "update_worktree_dirty",
            "update_developer_branch",
        }
        for reason_code in reason_codes:
            if reason_code in blocking:
                raise UpdateError(reason_code)

    identity = get_installed_identity(BASE_DIR, state)
    print_identity(identity)

    candidate = checked_candidate(manager, channel)
    print_candidate(candidate)
    if not candidate.get("update_available"):
        print("Sharp GUI is already current for this channel.")
        return 0
    if not candidate.get("compatible"):
        print("This target cannot be applied as a code-only update.")
        print(f"Reason: {candidate.get('compatibility_code') or 'update_incompatible'}")
        return 2
    if args.check:
        print("An applicable update is available.")
        return 0
    if local_server_is_running():
        raise UpdateError("update_server_running")
    if not args.yes and not confirm(
        f"Apply {candidate['display_version']} from the {channel} channel?"
    ):
        print("Update cancelled.")
        return 0
    operation = prepare_cli_operation(BASE_DIR, channel, candidate)
    print("Applying exact verified commit; runtime and user data remain untouched...")
    success = run_update_operation(BASE_DIR, operation["id"], wait_for_server=False, relaunch=False)
    final = load_update_state(BASE_DIR).get("operation") or {}
    if success:
        print("Update completed. Start Sharp GUI normally.")
        return 0
    print(f"Update failed: {final.get('error_code') or 'update_apply_failed'}")
    if final.get("rolled_back"):
        print("The previous commit was restored and verified.")
    return 1


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except UpdateError as exc:
        print(f"Update error: {exc.code}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Update cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

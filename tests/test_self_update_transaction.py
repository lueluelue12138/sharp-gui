import json
import shutil
import subprocess

import pytest

from backend.services import self_update


def _run(command, *, cwd=None):
    return subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git(executable, repository, *args):
    return _run([executable, "-C", repository, *args]).stdout.strip()


def _commit_all(executable, repository, message):
    _git(executable, repository, "add", "-A")
    _git(executable, repository, "commit", "--no-gpg-sign", "-m", message)
    return _git(executable, repository, "rev-parse", "HEAD")


def _manifest(runtime_revision=1):
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
        "minimumGitVersion": "2.0.0",
        "frontend": {
            "builtAssetsRequired": True,
            "entrypoint": "frontend/dist/index.html",
        },
        "supportedPortableTargets": ["cu128-rtx50"],
    }


def _write_manifest(repository, runtime_revision=1):
    manifest = _manifest(runtime_revision)
    (repository / "update-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _candidate(target_sha, manifest):
    return {
        "channel": "latest",
        "target_sha": target_sha,
        "short_sha": target_sha[:8],
        "target_ref": "refs/heads/main",
        "base_version": "v1.0.0",
        "commits_ahead": None,
        "display_version": f"v1.0.0 ({target_sha[:8]})",
        "relation": "upgrade",
        "update_available": True,
        "compatible": True,
        "compatibility_code": "update_compatible",
        "checked_at": self_update.utc_now(),
        "_target_manifest": manifest,
    }


def _assert_markers(marker_contents):
    for path, expected in marker_contents.items():
        assert path.read_bytes() == expected, f"marker changed or disappeared: {path}"


@pytest.fixture
def git_executable():
    executable = shutil.which("git")
    if not executable:
        pytest.skip("Git is required for updater transaction integration")
    return executable


def test_local_bare_remote_transaction_preserves_runtime_and_auto_rolls_back_failures(
    tmp_path,
    monkeypatch,
    git_executable,
):
    bare = tmp_path / "remote.git"
    source = tmp_path / "source"
    install = tmp_path / "portable"
    _run([git_executable, "init", "--bare", "--initial-branch=main", bare])
    _run([git_executable, "init", "--initial-branch=main", source])
    _git(git_executable, source, "config", "user.name", "Sharp GUI Tests")
    _git(git_executable, source, "config", "user.email", "tests@example.invalid")
    _git(git_executable, source, "config", "commit.gpgSign", "false")
    _git(git_executable, source, "config", "core.autocrlf", "false")

    (source / "backend").mkdir()
    (source / "backend" / "routes").mkdir()
    (source / "tools").mkdir()
    (source / "frontend" / "dist").mkdir(parents=True)
    (source / ".gitignore").write_text(
        "\n".join(
            [
                "__pycache__/",
                "config.json",
                "workspace/",
                "models/",
                "python/",
                ".video-reconstruction-env/",
                ".sharp-gui-tools/",
                ".sharp-gui-update/",
                "portable-package.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (source / "app.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (source / "backend" / "app_factory.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "backend" / "routes" / "__init__.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "backend" / "healthy.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (source / "tools" / "update.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "tools" / "healthy.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (source / "frontend" / "dist" / "index.html").write_text(
        "<html>base</html>\n",
        encoding="utf-8",
    )
    (source / "version.txt").write_text("v1.0.0\n", encoding="utf-8")
    (source / "tracked-modified.txt").write_text("base\n", encoding="utf-8")
    (source / "tracked-deleted.txt").write_text("delete-me\n", encoding="utf-8")
    (source / "rename-old.txt").write_text("rename-me\n", encoding="utf-8")
    _write_manifest(source, 1)
    base_sha = _commit_all(git_executable, source, "base release")
    _git(git_executable, source, "tag", "v1.0.0", base_sha)
    _git(git_executable, source, "remote", "add", "origin", str(bare))
    _git(git_executable, source, "push", "origin", "main", "refs/tags/v1.0.0")

    _run([git_executable, "clone", "--branch", "main", "--single-branch", bare, install])
    _git(git_executable, install, "config", "core.autocrlf", "false")
    _git(git_executable, install, "reset", "--hard", base_sha)

    portable_metadata = {
        "version": "v1.0.0",
        "releaseBaseline": "v1.0.0",
        "sourceRevision": base_sha,
        "target": "cu128-rtx50",
        "portableRuntimeRevision": 1,
        "updateProtocolRevision": 1,
    }
    marker_contents = {
        install / "config.json": b'{"marker":"config"}\n',
        install / "workspace" / "inputs" / "marker.bin": b"workspace-marker",
        install / "models" / "cache.bin": b"model-marker",
        install / "python" / "python.exe": b"portable-python-marker",
        install / ".video-reconstruction-env" / "marker.bin": b"video-env-marker",
        install / ".sharp-gui-tools" / "git" / "cmd" / "git.exe": b"mingit-marker",
        install / ".sharp-gui-update" / "user-marker.bin": b"update-state-marker",
        install / "portable-package.json": (json.dumps(portable_metadata) + "\n").encode("utf-8"),
    }
    for path, content in marker_contents.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    monkeypatch.setattr(self_update, "CANONICAL_REPOSITORY_URL", str(bare))
    monkeypatch.setattr(self_update, "resolve_git_executable", lambda _base_dir: git_executable)
    assert self_update.detect_deployment(install, git_executable) == ("portable", True)
    assert self_update.tracked_worktree_dirty(install, git_executable) is False

    (source / "tracked-modified.txt").write_text("compatible-hotfix\n", encoding="utf-8")
    (source / "tracked-deleted.txt").unlink()
    _git(git_executable, source, "mv", "rename-old.txt", "rename-new.txt")
    (source / "tracked-added.txt").write_text("added-by-hotfix\n", encoding="utf-8")
    compatible_manifest = _write_manifest(source, 1)
    compatible_sha = _commit_all(git_executable, source, "compatible hotfix")
    _git(git_executable, source, "push", "origin", "main")

    operation = self_update.prepare_cli_operation(
        install,
        "latest",
        _candidate(compatible_sha, compatible_manifest),
    )
    assert self_update.run_update_operation(
        install,
        operation["id"],
        wait_for_server=False,
        relaunch=False,
    ) is True
    assert _git(git_executable, install, "rev-parse", "HEAD") == compatible_sha
    assert (install / "tracked-modified.txt").read_text(encoding="utf-8") == "compatible-hotfix\n"
    assert not (install / "tracked-deleted.txt").exists()
    assert not (install / "rename-old.txt").exists()
    assert (install / "rename-new.txt").read_text(encoding="utf-8") == "rename-me\n"
    assert (install / "tracked-added.txt").read_text(encoding="utf-8") == "added-by-hotfix\n"
    _assert_markers(marker_contents)
    completed = self_update.load_update_state(install)["operation"]
    assert completed["phase"] == "completed"
    assert completed["previous_sha"] == base_sha

    (source / "tracked-modified.txt").write_text("must-not-apply\n", encoding="utf-8")
    incompatible_manifest = _write_manifest(source, 2)
    incompatible_sha = _commit_all(git_executable, source, "incompatible runtime")
    _git(git_executable, source, "push", "origin", "main")

    incompatible = self_update.prepare_cli_operation(
        install,
        "latest",
        _candidate(incompatible_sha, incompatible_manifest),
    )
    assert self_update.run_update_operation(
        install,
        incompatible["id"],
        wait_for_server=False,
        relaunch=False,
    ) is False
    assert _git(git_executable, install, "rev-parse", "HEAD") == compatible_sha
    assert (install / "tracked-modified.txt").read_text(encoding="utf-8") == "compatible-hotfix\n"
    incompatible_state = self_update.load_update_state(install)["operation"]
    assert incompatible_state["phase"] == "failed"
    assert incompatible_state["error_code"] == "update_full_package_required"
    assert incompatible_state["rolled_back"] is False
    _assert_markers(marker_contents)

    (source / "tracked-modified.txt").write_text("syntax-target\n", encoding="utf-8")
    (source / "backend" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    syntax_manifest = _write_manifest(source, 1)
    syntax_sha = _commit_all(git_executable, source, "broken syntax")
    _git(git_executable, source, "push", "origin", "main")

    syntax_operation = self_update.prepare_cli_operation(
        install,
        "latest",
        _candidate(syntax_sha, syntax_manifest),
    )
    assert self_update.run_update_operation(
        install,
        syntax_operation["id"],
        wait_for_server=False,
        relaunch=False,
    ) is False
    assert _git(git_executable, install, "rev-parse", "HEAD") == compatible_sha
    assert (install / "tracked-modified.txt").read_text(encoding="utf-8") == "compatible-hotfix\n"
    assert not (install / "backend" / "broken.py").exists()
    failed = self_update.load_update_state(install)["operation"]
    assert failed["phase"] == "failed"
    assert failed["error_code"] == "update_verification_failed"
    assert failed["rolled_back"] is True
    _assert_markers(marker_contents)

    (source / "config.json").write_text('{"must":"never-be-tracked"}\n', encoding="utf-8")
    _git(git_executable, source, "add", "--force", "config.json")
    protected_manifest = _write_manifest(source, 1)
    protected_sha = _commit_all(git_executable, source, "invalid protected runtime target")
    _git(git_executable, source, "push", "origin", "main")

    protected_operation = self_update.prepare_cli_operation(
        install,
        "latest",
        _candidate(protected_sha, protected_manifest),
    )
    assert self_update.run_update_operation(
        install,
        protected_operation["id"],
        wait_for_server=False,
        relaunch=False,
    ) is False
    assert _git(git_executable, install, "rev-parse", "HEAD") == compatible_sha
    assert not (install / "config.json").is_file() or (install / "config.json").read_bytes() == marker_contents[
        install / "config.json"
    ]
    protected_state = self_update.load_update_state(install)["operation"]
    assert protected_state["phase"] == "failed"
    assert protected_state["error_code"] == "update_target_tracks_runtime"
    assert protected_state["rolled_back"] is False
    _assert_markers(marker_contents)

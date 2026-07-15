import os
import subprocess
import sys

import pytest

from backend.app_factory import create_app
from backend.paths import build_path_context, ensure_runtime_directories
from backend.services import model_gallery, task_queue
from backend.services.task_queue import TaskManager
from backend.services.workspace_lock import (
    WorkspaceInUseError,
    WorkspaceInstanceLock,
    WorkspaceUnavailableError,
)


class NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


def test_workspace_lock_is_exclusive_and_reusable(workspace):
    first = WorkspaceInstanceLock(str(workspace))
    second = WorkspaceInstanceLock(str(workspace))

    try:
        first.acquire()
        with pytest.raises(WorkspaceInUseError, match="Workspace is already in use"):
            second.acquire()

        first.release()
        second.acquire()
    finally:
        first.release()
        second.release()


def test_workspace_lock_rejects_regular_file_as_unavailable(tmp_path):
    target_file = tmp_path / "workspace-file"
    target_file.write_text("keep", encoding="utf-8")

    with pytest.raises(WorkspaceUnavailableError, match="not writable or is not a directory"):
        WorkspaceInstanceLock(str(target_file)).acquire()

    assert target_file.read_text(encoding="utf-8") == "keep"


def test_workspace_lock_blocks_another_process(workspace):
    child_code = (
        "import os, sys; "
        "from backend.services.workspace_lock import WorkspaceInstanceLock; "
        "lock = WorkspaceInstanceLock(sys.argv[1]); "
        "lock.acquire(); "
        "print(f'ready:{os.getpid()}', flush=True); "
        "sys.stdin.readline(); "
        "lock.release()"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(workspace)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    contender = WorkspaceInstanceLock(str(workspace))

    try:
        ready_message = process.stdout.readline().strip()
        assert ready_message.startswith("ready:")
        lock_owner_pid = int(ready_message.split(":", 1)[1])
        with pytest.raises(WorkspaceInUseError) as exc_info:
            contender.acquire()
        assert f"PID {lock_owner_pid}" in str(exc_info.value)

        process.stdin.write("\n")
        process.stdin.flush()
        assert process.wait(timeout=5) == 0

        contender.acquire()
    finally:
        contender.release()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_app_factory_does_not_cleanup_before_workspace_claim(config_file, workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    monkeypatch.setattr(
        "backend.app_factory.video_reconstruction.start_dependency_warmup",
        lambda: None,
    )

    model_id = "img-88888888888888888888888888888888"
    input_path = os.path.join(paths.input_folder, f"{model_id}.jpg")
    with open(input_path, "wb") as file:
        file.write(b"input")
    metadata_path = model_gallery.write_model_metadata(
        paths,
        model_id,
        {
            "source_media_type": "image",
            "generation_status": "processing",
        },
    )

    app = create_app()

    assert app.config["TASK_MANAGER"].workers_started is False
    assert os.path.exists(input_path)
    assert os.path.exists(metadata_path)


def test_second_service_cannot_cleanup_live_image_task(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    monkeypatch.setattr(task_queue.threading, "Thread", NoopThread)
    video_cleanup_calls = []
    monkeypatch.setattr(
        task_queue.video_reconstruction,
        "cleanup_stale_runtime_artifacts",
        lambda cleanup_paths: video_cleanup_calls.append(cleanup_paths) or {},
    )

    first = TaskManager(paths=paths)
    second = TaskManager(paths=paths)
    first.start_workers()

    model_id = "img-99999999999999999999999999999999"
    input_path = os.path.join(paths.input_folder, f"{model_id}.jpg")
    thumbnail_path = model_gallery.get_thumbnail_path(paths, model_id)
    with open(input_path, "wb") as file:
        file.write(b"input")
    with open(thumbnail_path, "wb") as file:
        file.write(b"thumbnail")
    metadata_path = model_gallery.write_model_metadata(
        paths,
        model_id,
        {
            "source_media_type": "image",
            "generation_status": "processing",
        },
    )

    try:
        with pytest.raises(WorkspaceInUseError):
            second.start_workers()

        assert os.path.exists(input_path)
        assert os.path.exists(thumbnail_path)
        assert os.path.exists(metadata_path)
        assert video_cleanup_calls == [paths]
    finally:
        first.release_workspace_lock()
        second.release_workspace_lock()

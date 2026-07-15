import threading
import time

from backend.paths import build_path_context
from backend.routes import photo_gallery as photo_gallery_routes
from backend.services import photo_gallery, workspace_storage


def _wait_for_bootstrap_idle(timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with photo_gallery.bootstrap_lock:
            if (
                not photo_gallery.bootstrap_worker_running
                and not photo_gallery.bootstrap_queue
                and not photo_gallery.bootstrap_album_ids
            ):
                return
        time.sleep(0.01)
    raise AssertionError("photo gallery bootstrap worker did not become idle")


def test_legacy_photo_cache_delete_invalidates_workspace_snapshot(client, app, monkeypatch):
    workspace_storage.reset_workspace_storage_cache_for_tests()
    invalidated_paths = []
    real_invalidate = workspace_storage.invalidate_workspace_storage_stats

    def track_invalidation(paths):
        invalidated_paths.append(paths)
        real_invalidate(paths)

    monkeypatch.setattr(
        photo_gallery_routes.workspace_storage,
        "invalidate_workspace_storage_stats",
        track_invalidation,
    )

    invalid_response = client.delete("/api/photo-gallery/cache?scope=unsupported")
    response = client.delete("/api/photo-gallery/cache?scope=generated")

    assert invalid_response.status_code == 400
    assert invalidated_paths == [app.config["PATH_CONTEXT"]]
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    workspace_storage.reset_workspace_storage_cache_for_tests()


def test_album_bootstrap_runs_multiple_albums_serially(workspace, monkeypatch):
    _wait_for_bootstrap_idle()
    paths = build_path_context({"workspace_folder": str(workspace)})
    albums = [
        {"id": "album-a", "name": "Album A", "path": str(workspace / "a")},
        {"id": "album-b", "name": "Album B", "path": str(workspace / "b")},
        {"id": "album-c", "name": "Album C", "path": str(workspace / "c")},
    ]

    first_started = threading.Event()
    release_first = threading.Event()
    all_finished = threading.Event()
    state_lock = threading.Lock()
    started_ids = []
    finished_ids = []
    active_scans = 0
    max_active_scans = 0
    created_threads = []
    real_thread_class = threading.Thread

    class CountingThread(real_thread_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_threads.append(self)

    def fake_scan(_paths, album):
        nonlocal active_scans, max_active_scans
        album_id = album["id"]
        with state_lock:
            active_scans += 1
            max_active_scans = max(max_active_scans, active_scans)
            started_ids.append(album_id)
        if album_id == "album-a":
            first_started.set()
            release_first.wait(timeout=2)
        with state_lock:
            active_scans -= 1
            finished_ids.append(album_id)
            if len(finished_ids) == len(albums):
                all_finished.set()

    monkeypatch.setattr(photo_gallery, "load_album_index", lambda _paths, _album_id: None)
    monkeypatch.setattr(photo_gallery, "scan_photo_album", fake_scan)
    monkeypatch.setattr(photo_gallery.threading, "Thread", CountingThread)

    try:
        assert photo_gallery.schedule_album_bootstrap(paths, albums[0]) is True
        assert first_started.wait(timeout=1)

        assert photo_gallery.schedule_album_bootstrap(paths, albums[1]) is True
        assert photo_gallery.schedule_album_bootstrap(paths, albums[2]) is True
        assert photo_gallery.schedule_album_bootstrap(paths, albums[1]) is False
        assert len(created_threads) == 1

        release_first.set()
        assert all_finished.wait(timeout=2)
        created_threads[0].join(timeout=2)
        assert not created_threads[0].is_alive()

        assert started_ids == [album["id"] for album in albums]
        assert finished_ids == [album["id"] for album in albums]
        assert max_active_scans == 1
        _wait_for_bootstrap_idle()
    finally:
        release_first.set()
        for thread in created_threads:
            thread.join(timeout=2)

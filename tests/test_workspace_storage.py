import io
import json
import os
import threading
import time

import pytest
from werkzeug.datastructures import FileStorage

from backend.paths import build_path_context, ensure_runtime_directories
from backend.services import model_assets, model_gallery, photo_gallery, workspace_storage


def write_bytes(path, size, byte=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(byte * size)
    return path


def create_storage_fixture(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)

    write_bytes(workspace / ".photo-gallery-cache" / "catalog.json", 10)
    write_bytes(workspace / ".photo-gallery-cache" / "albums" / "album.tmp", 3)
    write_bytes(workspace / ".photo-gallery-cache" / "thumbnails" / "photo.jpg", 5)
    write_bytes(workspace / ".photo-gallery-cache" / "video-posters" / "video.jpg", 7)
    old_download = write_bytes(workspace / ".photo-gallery-cache" / "photo-gallery-old.zip", 11)
    old_time = time.time() - workspace_storage.ACTIVE_DOWNLOAD_GRACE_SECONDS - 60
    os.utime(old_download, (old_time, old_time))
    write_bytes(
        workspace / ".photo-gallery-cache" / "leftovers" / "photo-gallery-nested.zip",
        13,
    )

    write_bytes(workspace / "inputs" / ".thumbnails" / "generated.jpg", 17)
    write_bytes(workspace / "inputs" / "source.jpg", 23)
    write_bytes(workspace / "outputs" / "generated.ply", 19)
    write_bytes(workspace / "outputs" / "generated.meta.json", 2)
    write_bytes(workspace / "model-assets" / "imports" / "imported.splat", 29)

    manual_cover = write_bytes(workspace / "model-assets" / "thumbnails" / "manual.png", 31)
    system_cover = write_bytes(workspace / "model-assets" / "thumbnails" / "system.png", 37)
    fallback_cover = write_bytes(workspace / "model-assets" / "thumbnails" / "generated.jpg", 41)
    unknown_cover = write_bytes(workspace / "model-assets" / "thumbnails" / "unknown.jpg", 43)
    model_assets.write_asset_index(paths, {
        "assets": {
            "manual-asset": {
                "cover_kind": model_assets.THUMBNAIL_MANUAL,
                "cover_path": model_assets.workspace_relative_path(paths, str(manual_cover)),
            },
            "system-asset": {
                "cover_kind": model_assets.THUMBNAIL_SYSTEM,
                "cover_status": "ready",
                "cover_path": model_assets.workspace_relative_path(paths, str(system_cover)),
            },
        },
    })

    write_bytes(
        workspace / ".video-reconstruction" / "uploads" / "upload-123" / "source.mp4",
        47,
    )
    write_bytes(workspace / ".video-reconstruction" / "jobs" / "active" / "frame.png", 53)

    return paths, {
        "manual_cover": manual_cover,
        "system_cover": system_cover,
        "fallback_cover": fallback_cover,
        "unknown_cover": unknown_cover,
        "asset_index": workspace / ".model-asset-library" / "index.json",
    }


def test_workspace_storage_snapshot_is_disjoint_and_skips_video_jobs(workspace):
    paths, files = create_storage_fixture(workspace)

    snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)
    cache = snapshot["clearable_cache"]
    protected = snapshot["protected_storage"]

    assert cache["gallery_indexes"] == {"files": 2, "bytes": 13}
    assert cache["photo_thumbnails"] == {"files": 1, "bytes": 5}
    assert cache["video_posters"] == {"files": 1, "bytes": 7}
    assert cache["temporary_downloads"] == {"files": 1, "bytes": 11}
    assert cache["other"] == {"files": 1, "bytes": 13}
    assert cache["model_previews"] == {"files": 3, "bytes": 95}
    assert cache["total"] == {"files": 9, "bytes": 144}

    assert protected["source_images"] == {"files": 1, "bytes": 23}
    assert protected["generated_models"] == {"files": 2, "bytes": 21}
    assert protected["imported_models"] == {"files": 1, "bytes": 29}
    assert protected["asset_covers"] == {"files": 2, "bytes": 74}
    assert protected["video_uploads"] == {"files": 1, "bytes": 47}
    assert protected["asset_library"] == {
        "files": 1,
        "bytes": files["asset_index"].stat().st_size,
    }
    expected_protected_bytes = 23 + 21 + 29 + 74 + 47 + files["asset_index"].stat().st_size
    assert protected["total"] == {"files": 8, "bytes": expected_protected_bytes}
    assert snapshot["managed_total"] == {
        "files": cache["total"]["files"] + protected["total"]["files"],
        "bytes": cache["total"]["bytes"] + protected["total"]["bytes"],
    }
    assert snapshot["scan"]["incomplete"] is False


def test_clear_workspace_cache_preserves_user_data_and_recent_download(workspace):
    workspace_storage.reset_workspace_storage_cache_for_tests()
    paths, files = create_storage_fixture(workspace)
    recent_download = write_bytes(
        workspace / ".photo-gallery-cache" / "photo-gallery-active.zip",
        59,
    )

    result = workspace_storage.clear_rebuildable_workspace_cache(paths)

    assert result["success"] is True
    assert result["removed"]["files"] == 9
    assert recent_download.exists()
    assert (workspace / "inputs" / "source.jpg").exists()
    assert (workspace / "outputs" / "generated.ply").exists()
    assert (workspace / "model-assets" / "imports" / "imported.splat").exists()
    assert (
        workspace / ".video-reconstruction" / "uploads" / "upload-123" / "source.mp4"
    ).exists()
    assert (workspace / ".video-reconstruction" / "jobs" / "active" / "frame.png").exists()
    assert files["manual_cover"].exists()
    assert files["unknown_cover"].exists()
    assert not files["system_cover"].exists()
    assert not files["fallback_cover"].exists()
    assert not (workspace / "inputs" / ".thumbnails" / "generated.jpg").exists()

    index = json.loads(files["asset_index"].read_text(encoding="utf-8"))
    assert index["assets"]["manual-asset"]["cover_kind"] == model_assets.THUMBNAIL_MANUAL
    assert index["assets"]["system-asset"]["cover_kind"] == model_assets.THUMBNAIL_SYSTEM
    assert index["assets"]["system-asset"]["cover_status"] == model_assets.THUMBNAIL_PENDING
    assert "cover_path" not in index["assets"]["system-asset"]


def test_workspace_storage_refresh_is_single_flight_across_invalidation(workspace, monkeypatch):
    workspace_storage.reset_workspace_storage_cache_for_tests()
    paths = build_path_context({"workspace_folder": str(workspace)})
    started = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    calls = 0
    active = 0
    max_active = 0

    def fake_collect(_paths):
        nonlocal calls, active, max_active
        with state_lock:
            calls += 1
            active += 1
            max_active = max(max_active, active)
        started.set()
        release.wait(timeout=2)
        with state_lock:
            active -= 1
        return {"computed_at": "now", "call": calls}

    monkeypatch.setattr(workspace_storage, "collect_workspace_storage_snapshot", fake_collect)

    first = workspace_storage.request_workspace_storage_stats(paths)
    assert first["status"] == "checking"
    assert started.wait(timeout=1)
    workspace_storage.request_workspace_storage_stats(paths, refresh=True)
    workspace_storage.invalidate_workspace_storage_stats(paths)
    during_invalidation = workspace_storage.request_workspace_storage_stats(paths, refresh=True)
    assert during_invalidation["refreshing"] is True
    assert calls == 1
    assert max_active == 1

    release.set()
    deadline = time.time() + 2
    response = None
    while time.time() < deadline:
        response = workspace_storage.request_workspace_storage_stats(paths)
        if response["snapshot"] is not None:
            break
        time.sleep(0.01)

    assert response is not None
    assert response["snapshot"] is not None
    assert calls == 2
    assert max_active == 1
    workspace_storage.request_workspace_storage_stats(paths)
    assert calls == 2


def test_workspace_storage_does_not_follow_file_symlinks(workspace, tmp_path):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    outside = write_bytes(tmp_path / "outside.bin", 101)
    link = workspace / ".photo-gallery-cache" / "thumbnails" / "outside-link"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("File symlinks are not available in this environment")

    snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)

    assert snapshot["clearable_cache"]["photo_thumbnails"] == {"files": 0, "bytes": 0}
    assert snapshot["scan"]["symlinks_skipped"] >= 1


@pytest.mark.parametrize("index_state", ["missing", "corrupt", "malformed-record"])
def test_unreliable_model_asset_index_protects_all_covers(workspace, index_state):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_bytes(workspace / "outputs" / "generated.ply", 13)
    fallback_cover = write_bytes(
        workspace / "model-assets" / "thumbnails" / "generated.jpg",
        17,
    )
    orphan_cover = write_bytes(
        workspace / "model-assets" / "thumbnails" / "orphan.png",
        19,
    )

    index_path = workspace / ".model-asset-library" / "index.json"
    if index_state == "corrupt":
        index_path.write_text("{not-json", encoding="utf-8")
    elif index_state == "malformed-record":
        index_path.write_text(
            json.dumps({"version": 1, "assets": {"generated": "not-an-object"}}),
            encoding="utf-8",
        )

    snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)
    removed = model_assets.clear_rebuildable_model_asset_covers(paths)

    assert snapshot["clearable_cache"]["model_previews"] == {"files": 0, "bytes": 0}
    assert snapshot["protected_storage"]["asset_covers"] == {"files": 2, "bytes": 36}
    assert removed == {"files": 0, "bytes": 0}
    assert fallback_cover.exists()
    assert orphan_cover.exists()


def test_nested_video_uploads_are_counted_as_protected_storage(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_bytes(
        workspace / ".video-reconstruction" / "uploads" / "upload-abc" / "source.mp4",
        47,
    )
    write_bytes(
        workspace / ".video-reconstruction" / "jobs" / "active-job" / "frame.png",
        53,
    )

    snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)

    assert snapshot["protected_storage"]["video_uploads"] == {"files": 1, "bytes": 47}
    assert snapshot["managed_total"] == {"files": 1, "bytes": 47}


def test_active_and_recent_downloads_are_protected_from_workspace_clear(
    workspace,
    monkeypatch,
):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    cache_root = workspace / ".photo-gallery-cache"
    old_download = write_bytes(cache_root / "photo-gallery-old.zip", 11)
    recent_download = write_bytes(cache_root / "photo-gallery-recent.zip", 13)
    active_download = write_bytes(cache_root / "photo-gallery-active.zip", 17)
    old_time = time.time() - workspace_storage.ACTIVE_DOWNLOAD_GRACE_SECONDS - 60
    os.utime(old_download, (old_time, old_time))
    os.utime(active_download, (old_time, old_time))
    photo_gallery.register_active_photo_download(str(active_download))
    monkeypatch.setattr(
        workspace_storage,
        "request_workspace_storage_stats",
        lambda _paths, refresh=False: {"refreshing": False, "snapshot": None},
    )

    try:
        snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)
        result = workspace_storage.clear_rebuildable_workspace_cache(paths)
    finally:
        photo_gallery.unregister_active_photo_download(str(active_download))

    assert snapshot["clearable_cache"]["temporary_downloads"] == {"files": 1, "bytes": 11}
    assert snapshot["protected_storage"]["active_downloads"] == {"files": 2, "bytes": 30}
    assert result["success"] is True
    assert not old_download.exists()
    assert recent_download.exists()
    assert active_download.exists()


def test_model_asset_cover_root_symlink_is_not_scanned_or_deleted(workspace, tmp_path):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_bytes(workspace / "outputs" / "generated.ply", 13)
    model_assets.write_asset_index(paths, {"assets": {}})

    thumbnail_root = workspace / "model-assets" / "thumbnails"
    thumbnail_root.rmdir()
    outside_root = tmp_path / "outside-model-covers"
    outside_cover = write_bytes(outside_root / "generated.jpg", 23)
    try:
        thumbnail_root.symlink_to(outside_root, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks are not available in this environment")

    snapshot = workspace_storage.collect_workspace_storage_snapshot(paths)
    removed = model_assets.clear_rebuildable_model_asset_covers(paths)

    assert snapshot["clearable_cache"]["model_previews"] == {"files": 0, "bytes": 0}
    assert snapshot["protected_storage"]["asset_covers"] == {"files": 0, "bytes": 0}
    assert snapshot["scan"]["symlinks_skipped"] >= 1
    assert removed == {"files": 0, "bytes": 0}
    assert outside_cover.exists()


def test_workspace_storage_thread_start_failure_can_retry(workspace, monkeypatch):
    workspace_storage.reset_workspace_storage_cache_for_tests()
    paths = build_path_context({"workspace_folder": str(workspace)})
    real_thread = workspace_storage.threading.Thread
    attempts = 0

    class FlakyThread:
        def __init__(self, *args, **kwargs):
            self._thread = real_thread(*args, **kwargs)

        def start(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("thread start failed")
            self._thread.start()

    monkeypatch.setattr(workspace_storage.threading, "Thread", FlakyThread)
    monkeypatch.setattr(
        workspace_storage,
        "collect_workspace_storage_snapshot",
        lambda _paths: {"computed_at": "retry-succeeded"},
    )

    first = workspace_storage.request_workspace_storage_stats(paths)
    second = workspace_storage.request_workspace_storage_stats(paths, refresh=True)
    deadline = time.time() + 2
    final = second
    while time.time() < deadline and final["snapshot"] is None:
        time.sleep(0.01)
        final = workspace_storage.request_workspace_storage_stats(paths)

    assert first["status"] == "error"
    assert first["refreshing"] is False
    assert attempts == 2
    assert final["status"] == "ready"
    assert final["snapshot"] == {"computed_at": "retry-succeeded"}


def test_clear_does_not_publish_snapshot_from_scan_started_before_cleanup(
    workspace,
    monkeypatch,
):
    workspace_storage.reset_workspace_storage_cache_for_tests()
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    scan_started = threading.Event()
    release_old_scan = threading.Event()
    call_lock = threading.Lock()
    calls = 0

    def fake_collect(_paths):
        nonlocal calls
        with call_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            scan_started.set()
            release_old_scan.wait(timeout=2)
            return {"computed_at": "before-clear", "marker": "partial"}
        return {"computed_at": "after-clear", "marker": "fresh"}

    monkeypatch.setattr(workspace_storage, "collect_workspace_storage_snapshot", fake_collect)

    initial = workspace_storage.request_workspace_storage_stats(paths)
    assert initial["status"] == "checking"
    assert scan_started.wait(timeout=1)

    clear_result = workspace_storage.clear_rebuildable_workspace_cache(paths)
    assert clear_result["stats"]["snapshot"] is None
    release_old_scan.set()

    observed_markers = []
    deadline = time.time() + 2
    response = None
    while time.time() < deadline:
        response = workspace_storage.request_workspace_storage_stats(paths)
        if response["snapshot"] is not None:
            observed_markers.append(response["snapshot"]["marker"])
            if not response["refreshing"]:
                break
        time.sleep(0.01)

    assert response is not None
    assert response["snapshot"] == {"computed_at": "after-clear", "marker": "fresh"}
    assert "partial" not in observed_markers
    assert calls == 2


@pytest.mark.parametrize(
    "item_id",
    ["../escape", r"..\escape", "C:\\outside\\escape", ".", ".."],
)
def test_thumbnail_lookup_rejects_item_ids_outside_managed_roots(workspace, item_id):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    escaped_thumbnail = write_bytes(workspace / "inputs" / "escape.jpg", 7)

    result = model_gallery.ensure_thumbnail_for_item(paths, item_id, allow_generation=True)

    assert result is None
    assert escaped_thumbnail.exists()


def test_cover_upload_does_not_restore_asset_deleted_during_validation(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_bytes(workspace / "outputs" / "deleted-during-upload.ply", 32)

    def delete_asset_before_commit(_temp_path):
        assert model_assets.delete_model_asset(paths, "deleted-during-upload") is True

    monkeypatch.setattr(model_assets, "validate_cover_image", delete_asset_before_commit)
    upload = FileStorage(stream=io.BytesIO(b"cover"), filename="cover.png")

    asset, error, status = model_assets.save_model_asset_cover(
        paths,
        "deleted-during-upload",
        upload,
        kind=model_assets.THUMBNAIL_SYSTEM,
    )

    assert asset is None
    assert status == 409
    assert error["code"] == "cover_cache_changed"
    assert not (workspace / "model-assets" / "thumbnails" / "deleted-during-upload.png").exists()
    index = model_assets.read_asset_index(paths)
    assert "deleted-during-upload" not in index["assets"]


def test_cover_upload_started_before_cache_clear_cannot_restore_system_cover(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_bytes(workspace / "outputs" / "clear-race.ply", 32)
    model_assets.write_asset_index(paths, {"assets": {}})

    def clear_cache_during_validation(_temp_path):
        model_assets.clear_rebuildable_model_asset_covers(paths)

    monkeypatch.setattr(model_assets, "validate_cover_image", clear_cache_during_validation)
    upload = FileStorage(stream=io.BytesIO(b"cover"), filename="cover.png")

    asset, error, status = model_assets.save_model_asset_cover(
        paths,
        "clear-race",
        upload,
        kind=model_assets.THUMBNAIL_SYSTEM,
    )

    assert asset is None
    assert status == 409
    assert error["code"] == "cover_cache_changed"
    assert not (workspace / "model-assets" / "thumbnails" / "clear-race.png").exists()


def test_workspace_storage_owner_api_returns_json(client):
    workspace_storage.reset_workspace_storage_cache_for_tests()

    get_response = client.get("/api/workspace-storage")
    delete_response = client.delete("/api/workspace-storage")

    assert get_response.status_code == 200
    assert get_response.is_json
    assert get_response.get_json()["status"] in {"checking", "ready"}
    assert delete_response.status_code == 200
    assert delete_response.is_json
    assert delete_response.get_json()["success"] is True

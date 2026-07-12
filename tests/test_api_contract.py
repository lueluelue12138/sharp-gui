import os
from io import BytesIO

from tests.conftest import make_png_bytes
from backend.services.photo_gallery import photo_meta_from_path, save_photo_index
from tests.conftest import write_config


def test_core_read_apis_return_expected_shapes(client, app):
    auth = client.get("/api/auth/status")
    assert auth.status_code == 200
    auth_payload = auth.get_json()
    assert auth_payload["authenticated"] is True
    assert auth_payload["is_owner"] is True

    paths = app.config["PATH_CONTEXT"]
    model_path = os.path.join(paths.output_folder, "demo.ply")
    with open(model_path, "wb") as f:
        f.write(b"fake-ply")

    gallery = client.get("/api/gallery")
    assert gallery.status_code == 200
    gallery_payload = gallery.get_json()
    assert gallery_payload[0]["id"] == "demo"
    assert gallery_payload[0]["model_url"].startswith("/files/")

    download = client.get("/api/download/demo?format=ply")
    assert download.status_code == 200
    assert download.data == b"fake-ply"

    albums = client.get("/api/photo-albums")
    assert albums.status_code == 200
    assert albums.get_json()["albums"] == []

    tasks = client.get("/api/tasks")
    assert tasks.status_code == 200
    assert tasks.get_json() == {"tasks": [], "has_active": False}

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    settings_payload = settings.get_json()
    assert settings_payload["model_format"] == "spz"
    assert settings_payload["server_instance_id"] == app.config["SERVER_INSTANCE_ID"]
    assert settings_payload["workspace_folder"] == paths.workspace_folder
    assert settings_payload["video_reconstruction"]["default_quality"] == "high"

    video_status = client.get("/api/video-reconstructions/status")
    assert video_status.status_code == 200
    assert "dependencies" in video_status.get_json()


def test_restart_api_returns_current_instance_id(client, app, monkeypatch):
    restart_calls = []
    monkeypatch.setattr(
        "backend.routes.settings.restart_process_later",
        lambda: restart_calls.append(True),
    )

    response = client.post("/api/restart")

    assert response.status_code == 200
    assert response.get_json()["server_instance_id"] == app.config["SERVER_INSTANCE_ID"]
    assert restart_calls == [True]


def test_model_assets_api_lists_imports_edits_covers_and_downloads(client, app):
    paths = app.config["PATH_CONTEXT"]
    model_path = os.path.join(paths.output_folder, "demo.ply")
    spz_path = os.path.join(paths.output_folder, "demo.spz")
    with open(model_path, "wb") as f:
        f.write(b"fake-ply")
    with open(spz_path, "wb") as f:
        f.write(b"fake-spz")

    list_response = client.get("/api/model-assets")
    assert list_response.status_code == 200
    payload = list_response.get_json()
    assert payload["total"] == 1
    assert payload["total_size"] == len(b"fake-ply") + len(b"fake-spz")
    assert payload["items"][0]["id"] == "demo"
    assert payload["items"][0]["formats"] == ["spz", "ply"]
    assert payload["items"][0]["default_open_url"].startswith("/files/")
    assert payload["counts"]["generated"] == 1

    detail = client.get("/api/model-assets/demo")
    assert detail.status_code == 200
    detail_payload = detail.get_json()
    assert detail_payload["files"][0]["format"] == "spz"

    imported = client.post(
        "/api/model-assets/import",
        data={"files": (BytesIO(b"imported-ply"), "../Imported Model.ply")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    imported_payload = imported.get_json()
    assert imported_payload["success"] is True
    imported_asset = imported_payload["assets"][0]
    assert imported_asset["source_type"] == "imported"
    assert imported_asset["default_open_url"].startswith("/files/workspace/model-assets/imports/")
    assert ".." not in imported_asset["default_open_url"]

    asset_id = imported_asset["id"]
    edited = client.post(
        f"/api/model-assets/{asset_id}",
        json={"display_name": "Imported Meadow", "tags": ["scan", "spz"], "note": "Ready"},
    )
    assert edited.status_code == 200
    edited_payload = edited.get_json()
    assert edited_payload["name"] == "Imported Meadow"
    assert edited_payload["tags"] == ["scan", "spz"]

    cover = client.post(
        f"/api/model-assets/{asset_id}/cover",
        data={"cover": (make_png_bytes(), "cover.png")},
        content_type="multipart/form-data",
    )
    assert cover.status_code == 200
    cover_payload = cover.get_json()
    assert cover_payload["thumbnail_state"] == "ready"
    assert cover_payload["thumb_url"].startswith("/files/workspace/model-assets/thumbnails/")

    refreshed_cover = client.post(f"/api/model-assets/{asset_id}/cover/refresh")
    assert refreshed_cover.status_code == 200
    refreshed_payload = refreshed_cover.get_json()
    assert refreshed_payload["thumbnail_state"] == "pending"
    assert refreshed_payload["thumbnail_kind"] == "system"
    assert refreshed_payload["thumb_url"] is None

    download = client.get(f"/api/model-assets/{asset_id}/download?format=ply")
    assert download.status_code == 200
    assert download.data == b"imported-ply"

    legacy_gallery = client.get("/api/gallery")
    assert legacy_gallery.status_code == 200
    assert legacy_gallery.get_json()[0]["id"] == "demo"


def test_export_missing_model_returns_json_error(client):
    response = client.get("/api/export/missing")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Model not found"}


def test_photo_album_media_api_lists_videos_and_supports_range(client, app, config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "小米办公Pro20260212-180739.mp4"
    video_path.write_bytes(b"0123456789")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "model_format": "spz",
            "access_control": {
                "enabled": False,
                "password_hash": "",
                "session_secret": "test-secret",
                "session_days": 30,
                "allow_localhost_bypass": True,
                "allow_remote_generation": False,
                "session_version": 1,
                "lan_bind_enabled": True,
            },
            "video_reconstruction": {
                "default_quality": "high",
                "default_engine": "auto",
                "vram_budget": "8gb",
                "keep_intermediate_files": False,
            },
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )

    albums = client.get("/api/photo-albums")
    assert albums.status_code == 200
    album_payload = albums.get_json()["albums"][0]
    assert album_payload["scan_status"] in {"needs_index", "idle"}

    scan = client.post("/api/photo-albums/album1/scan")
    assert scan.status_code == 200
    assert scan.get_json()["success"] is True

    albums = client.get("/api/photo-albums")
    assert albums.status_code == 200
    album_payload = albums.get_json()["albums"][0]
    assert album_payload["media_count"] == 1
    assert album_payload["video_count"] == 1
    assert album_payload["photo_count"] == 0
    assert album_payload["cover_thumb_url"].startswith("/api/video-poster/")

    list_response = client.get("/api/photo-albums/album1/photos?type=video")
    assert list_response.status_code == 200
    payload = list_response.get_json()
    assert payload["total"] == 1
    assert payload["media_counts"] == {"all": 1, "image": 0, "photo": 0, "video": 1}
    item = payload["items"][0]
    assert item["media_type"] == "video"
    assert item["name"] == "小米办公Pro20260212-180739.mp4"
    assert item["poster_url"].startswith("/api/video-poster/")
    assert item["playback_url"].startswith("/api/video-play/")
    assert item["playback_url"].endswith("%E5%B0%8F%E7%B1%B3%E5%8A%9E%E5%85%ACPro20260212-180739.mp4")
    assert item["download_url"].endswith("?download=1")

    poster = client.get(item["poster_url"])
    assert poster.status_code == 404
    assert poster.get_json() == {"error": "Video poster not available"}

    range_response = client.get(item["playback_url"], headers={"Range": "bytes=0-3"})
    assert range_response.status_code == 206
    assert range_response.data == b"0123"
    assert range_response.headers["Content-Type"].startswith("video/mp4")

    download = client.get(item["download_url"])
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]


def test_video_reconstruction_api_rejects_invalid_and_missing_dependencies(client, app, config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    image_path = album_dir / "image.jpg"
    video_path = album_dir / "clip.mp4"
    image_path.write_bytes(b"fake-image")
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "model_format": "spz",
            "access_control": {
                "enabled": False,
                "password_hash": "",
                "session_secret": "test-secret",
                "session_days": 30,
                "allow_localhost_bypass": True,
                "allow_remote_generation": False,
                "session_version": 1,
                "lan_bind_enabled": True,
            },
            "video_reconstruction": {
                "default_quality": "high",
                "default_engine": "auto",
                "vram_budget": "8gb",
                "keep_intermediate_files": False,
            },
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = app.config["PATH_CONTEXT"]
    image_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(image_path))
    video_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {image_meta["id"]: image_meta, video_meta["id"]: video_meta}})

    photo_response = client.post("/api/video-reconstructions", json={"video_id": image_meta["id"]})
    assert photo_response.status_code == 404
    assert photo_response.get_json()["code"] == "video_reconstruction_source_unavailable"

    monkeypatch.setattr("backend.services.video_reconstruction.check_dependencies", lambda: {
        "required": {"available": False, "tools": [], "message": "missing"},
        "stable": {"available": False, "tools": [], "message": "missing"},
        "summary": {
            "available": False,
            "stable_available": False,
        },
    })
    missing_response = client.post("/api/video-reconstructions", json={"video_id": video_meta["id"]})
    assert missing_response.status_code == 409
    assert missing_response.get_json()["code"] == "video_reconstruction_dependency_missing"


def test_video_reconstruction_api_queues_without_exposing_paths(client, app, config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "model_format": "spz",
            "access_control": {
                "enabled": False,
                "password_hash": "",
                "session_secret": "test-secret",
                "session_days": 30,
                "allow_localhost_bypass": True,
                "allow_remote_generation": False,
                "session_version": 1,
                "lan_bind_enabled": True,
            },
            "video_reconstruction": {
                "default_quality": "high",
                "default_engine": "auto",
                "vram_budget": "8gb",
                "keep_intermediate_files": False,
            },
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = app.config["PATH_CONTEXT"]
    video_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {video_meta["id"]: video_meta}})
    monkeypatch.setattr("backend.services.video_reconstruction.check_dependencies", lambda: {
        "required": {"available": True, "tools": [], "message": None},
        "stable": {"available": True, "tools": [], "message": None},
        "summary": {
            "available": True,
            "stable_available": True,
        },
    })

    response = client.post("/api/video-reconstructions", json={
        "video_id": video_meta["id"],
        "mode": "object",
        "quality": "custom",
        "custom_options": {
            "frame_count": 600,
            "max_num_iterations": 35000,
            "downscale_factor": 2,
            "matching_method": "sequential",
            "cache_images": "cpu",
        },
        "engine": "auto",
        "output_name": "clip",
    })

    assert response.status_code == 200
    task = response.get_json()["task"]
    assert task["kind"] == "video_3dgs"
    assert task["source_media_id"] == video_meta["id"]
    assert task["mode"] == "object"
    assert task["quality"] == "custom"
    assert task["custom_options"]["frame_count"] == 600
    assert task["custom_options"]["matching_method"] == "sequential"
    assert task["resolved_engine"] == "stable"
    assert task["vram_budget"] == "8gb"
    assert "source_video_path" not in task
    assert "output_path" not in task

    tasks = client.get("/api/tasks").get_json()["tasks"]
    assert tasks[0]["id"] == task["id"]
    assert "source_video_path" not in tasks[0]


def test_video_reconstruction_upload_queues_same_name_without_exposing_paths(client, app, monkeypatch):
    monkeypatch.setattr("backend.services.video_reconstruction.check_dependencies", lambda: {
        "required": {"available": True, "tools": [], "message": None},
        "stable": {"available": True, "tools": [], "message": None},
        "summary": {
            "available": True,
            "stable_available": True,
        },
    })

    response = client.post(
        "/api/video-reconstructions/upload",
        data={
            "file": (BytesIO(b"video"), "clip.mp4"),
            "mode": "auto",
            "quality": "high",
            "engine": "auto",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    task = response.get_json()["task"]
    assert task["kind"] == "video_3dgs"
    assert task["filename"] == "clip.ply"
    assert task["output_name"] == "clip"
    assert task["source_name"] == "clip.mp4"
    assert "source_media_id" not in task
    assert "source_video_path" not in task

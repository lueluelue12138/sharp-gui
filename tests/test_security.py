import json
import time
from io import BytesIO

from werkzeug.security import generate_password_hash

from backend.app_factory import create_app
from backend.security.access_control import create_video_play_token
from backend.services.photo_gallery import make_photo_id, photo_meta_from_path, save_photo_index
from tests.conftest import make_png_bytes, write_config


def make_access_config(**overrides):
    data = {
        "enabled": False,
        "password_hash": "",
        "session_secret": "test-secret",
        "session_days": 30,
        "allow_localhost_bypass": True,
        "allow_remote_generation": False,
        "session_version": 1,
        "lan_bind_enabled": True,
    }
    data.update(overrides)
    return data


def remote_post(client, path, **kwargs):
    return client.post(
        path,
        base_url="http://192.168.1.2",
        environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        **kwargs,
    )


def remote_get(client, path, **kwargs):
    return client.get(
        path,
        base_url="http://192.168.1.2",
        environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        **kwargs,
    )


def test_owner_only_rejects_remote_when_gate_disabled(client):
    response = remote_post(client, "/api/settings", json={"model_format": "ply"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_workspace_storage_is_owner_only(client):
    stats = remote_get(client, "/api/workspace-storage")
    clear = client.delete(
        "/api/workspace-storage",
        base_url="http://192.168.1.2",
        environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
    )

    assert stats.status_code == 403
    assert stats.get_json()["code"] == "OWNER_REQUIRED"
    assert clear.status_code == 403
    assert clear.get_json()["code"] == "OWNER_REQUIRED"


def test_forwarded_headers_do_not_grant_owner(client):
    response = remote_post(
        client,
        "/api/settings",
        json={"model_format": "ply"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
            "Forwarded": "for=127.0.0.1",
        },
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_generate_requires_explicit_gate_setting(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        response = remote_post(client, "/api/generate")
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_generate_accepts_unlocked_client_when_enabled(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=True,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        response = remote_post(
            client,
            "/api/generate",
            data={"file": (make_png_bytes(), "dragged.png")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["tasks"][0]["filename"] == "dragged.png"


def test_remote_model_asset_read_requires_auth_when_gate_enabled(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True
    paths = app.config["PATH_CONTEXT"]
    model_path = workspace / "outputs" / "demo.ply"
    model_path.write_bytes(b"ply")

    with app.test_client() as client:
        blocked = remote_get(client, "/api/model-assets")
        assert blocked.status_code == 401
        assert blocked.get_json()["code"] == "AUTH_REQUIRED"

        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200

        allowed = remote_get(client, "/api/model-assets")
        assert allowed.status_code == 200
        assert allowed.get_json()["items"][0]["id"] == "demo"
        assert paths.allowed_file_serve_roots


def test_remote_model_asset_writes_use_generation_gate(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True
    paths = app.config["PATH_CONTEXT"]

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200

        blocked = remote_post(
            client,
            "/api/model-assets/import",
            data={"files": (BytesIO(b"ply"), "remote.ply")},
            content_type="multipart/form-data",
        )
        assert blocked.status_code == 403
        assert blocked.get_json()["code"] == "OWNER_REQUIRED"
        assert not (workspace / "model-assets" / "imports" / "remote.ply").exists()


def test_remote_model_asset_write_requires_login_even_when_generation_gate_enabled(
    config_file,
    workspace,
):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=True,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        blocked = remote_post(
            client,
            "/api/model-assets/import",
            data={"files": (BytesIO(b"ply"), "remote.ply")},
            content_type="multipart/form-data",
        )
        assert blocked.status_code == 401
        assert blocked.get_json()["code"] == "AUTH_REQUIRED"


def test_remote_model_asset_write_allowed_but_delete_stays_owner_only(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=True,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200

        imported = remote_post(
            client,
            "/api/model-assets/import",
            data={"files": (BytesIO(b"ply"), "../remote.ply")},
            content_type="multipart/form-data",
        )
        assert imported.status_code == 200
        asset_id = imported.get_json()["assets"][0]["id"]

        edited = remote_post(
            client,
            f"/api/model-assets/{asset_id}",
            json={"display_name": "Remote Asset", "tags": ["lan"], "note": "ok"},
        )
        assert edited.status_code == 200
        assert edited.get_json()["name"] == "Remote Asset"

        cover = remote_post(
            client,
            f"/api/model-assets/{asset_id}/cover",
            data={"cover": (make_png_bytes(), "cover.png")},
            content_type="multipart/form-data",
        )
        assert cover.status_code == 200
        assert cover.get_json()["thumbnail_state"] == "ready"

        delete = client.delete(
            f"/api/model-assets/{asset_id}",
            base_url="http://192.168.1.2",
            environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        )
        assert delete.status_code == 403
        assert delete.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_task_cancel_requires_generation_gate(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        response = remote_post(client, "/api/task/task-id/cancel")
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_task_cancel_accepts_image_and_video_when_generation_enabled(
    config_file,
    workspace,
):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=True,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200

        generate_response = remote_post(
            client,
            "/api/generate",
            data={"file": (make_png_bytes(), "dragged.png")},
            content_type="multipart/form-data",
        )
        assert generate_response.status_code == 200
        image_task_id = generate_response.get_json()["tasks"][0]["id"]

        image_cancel = remote_post(client, f"/api/task/{image_task_id}/cancel")
        assert image_cancel.status_code == 200
        assert image_cancel.get_json()["success"] is True

        video_task = app.config["TASK_MANAGER"].enqueue_video_reconstruction({
            "filename": "clip.mp4",
            "source_video_path": str(workspace / "clip.mp4"),
        })
        video_cancel = remote_post(client, f"/api/task/{video_task['id']}/cancel")
        assert video_cancel.status_code == 200
        assert video_cancel.get_json()["success"] is True


def test_remote_video_reconstruction_uses_generation_gate(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_remote_generation=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        response = remote_post(client, "/api/video-reconstructions", json={"video_id": "album_video"})
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"

        upload_response = remote_post(
            client,
            "/api/video-reconstructions/upload",
            data={"file": (BytesIO(b"video"), "clip.mp4")},
            content_type="multipart/form-data",
        )
        assert upload_response.status_code == 403
        assert upload_response.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_photo_upload_gate_disabled_is_owner_only(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(enabled=False),
        "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = remote_post(
            client,
            "/api/photo-albums/album1/uploads",
            data={"file": (make_png_bytes(), "remote.png")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_remote_photo_upload_gate_enabled_accepts_unlocked_client(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
        ),
        "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        response = remote_post(
            client,
            "/api/photo-albums/album1/uploads",
            data={"file": (make_png_bytes(), "remote.png")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["uploaded"] == 1
        assert (album_dir / "remote.png").exists()


def test_video_play_token_allows_inline_stream_without_cookie_but_not_download(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"0123456789")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True
    paths = app.config["PATH_CONTEXT"]
    video_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {video_meta["id"]: video_meta}})
    video_id = make_photo_id("album1", "clip.mp4")
    token = create_video_play_token(video_id, config["access_control"])

    with app.test_client() as client:
        stream = remote_get(
            client,
            f"/api/video-play/{video_id}/{token}/clip.mp4",
            headers={"Range": "bytes=0-3"},
        )
        assert stream.status_code == 206
        assert stream.data == b"0123"

        download = remote_get(client, f"/api/video-original/{video_id}?download=1&play_token={token}")
        assert download.status_code == 401
        assert download.get_json()["code"] == "AUTH_REQUIRED"

        expired = create_video_play_token(video_id, config["access_control"], now=time.time() - 100000)
        expired_stream = remote_get(client, f"/api/video-play/{video_id}/{expired}/clip.mp4")
        assert expired_stream.status_code == 401
        assert expired_stream.get_json()["code"] == "AUTH_REQUIRED"


def test_remote_unlocked_client_cannot_clear_photo_gallery_cache(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200

        stats = remote_get(client, "/api/photo-gallery/cache")
        assert stats.status_code == 200

        clear = client.delete(
            "/api/photo-gallery/cache",
            base_url="http://192.168.1.2",
            environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        )
        assert clear.status_code == 403
        assert clear.get_json()["code"] == "OWNER_REQUIRED"

import json
import time

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


def test_owner_bootstrap_grants_owner_session(config_file, workspace, monkeypatch):
    monkeypatch.setenv("SHARP_DOCKER_MODE", "1")
    monkeypatch.setenv("SHARP_OWNER_TOKEN", "owner-token-123")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        before = remote_post(client, "/api/settings", json={"model_format": "ply"})
        assert before.status_code == 403
        assert before.get_json()["code"] == "OWNER_REQUIRED"

        login = remote_post(client, "/api/auth/owner-bootstrap", json={"token": "owner-token-123"})
        assert login.status_code == 200
        payload = login.get_json()
        assert payload["authenticated"] is True
        assert payload["is_owner"] is True
        assert payload["is_docker"] is True
        assert payload["owner_bootstrap_available"] is True
        assert "owner-token-123" not in login.get_data(as_text=True)

        response = remote_post(client, "/api/settings", json={"model_format": "ply"})
        assert response.status_code == 200


def test_owner_session_survives_first_access_code_setup(config_file, workspace, monkeypatch):
    monkeypatch.setenv("SHARP_DOCKER_MODE", "1")
    monkeypatch.setenv("SHARP_OWNER_TOKEN", "owner-token-123")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/owner-bootstrap", json={"token": "owner-token-123"})
        assert login.status_code == 200
        assert login.get_json()["is_owner"] is True

        setup = remote_post(client, "/api/auth/access-code", json={"password": "password123"})
        assert setup.status_code == 200
        assert setup.get_json()["is_owner"] is True

        response = remote_post(client, "/api/settings", json={"model_format": "ply"})
        assert response.status_code == 200


def test_wrong_owner_bootstrap_token_does_not_grant_owner(config_file, workspace, monkeypatch):
    monkeypatch.setenv("SHARP_DOCKER_MODE", "1")
    monkeypatch.setenv("SHARP_OWNER_TOKEN", "owner-token-123")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/owner-bootstrap", json={"token": "wrong"})
        assert login.status_code == 401
        assert login.get_json()["code"] == "INVALID_OWNER_TOKEN"

        response = remote_post(client, "/api/settings", json={"model_format": "ply"})
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_owner_bootstrap_is_disabled_outside_docker_mode(config_file, workspace, monkeypatch):
    monkeypatch.delenv("SHARP_DOCKER_MODE", raising=False)
    monkeypatch.delenv("SHARP_DOCKER_VARIANT", raising=False)
    monkeypatch.setenv("SHARP_OWNER_TOKEN", "owner-token-123")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        status = remote_get(client, "/api/auth/status")
        assert status.status_code == 200
        assert status.get_json()["is_docker"] is False
        assert status.get_json()["owner_bootstrap_available"] is False

        login = remote_post(client, "/api/auth/owner-bootstrap", json={"token": "owner-token-123"})
        assert login.status_code == 401
        assert login.get_json()["code"] == "INVALID_OWNER_TOKEN"


def test_access_code_session_does_not_grant_owner(config_file, workspace):
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=True,
            password_hash=generate_password_hash("password123"),
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        login = remote_post(client, "/api/auth/login", json={"password": "password123"})
        assert login.status_code == 200
        payload = login.get_json()
        assert payload["authenticated"] is True
        assert payload["is_owner"] is False

        response = remote_post(client, "/api/settings", json={"model_format": "ply"})
        assert response.status_code == 403
        assert response.get_json()["code"] == "OWNER_REQUIRED"


def test_forwarded_headers_do_not_grant_owner_with_docker_token_available(config_file, workspace, monkeypatch):
    monkeypatch.setenv("SHARP_DOCKER_MODE", "1")
    monkeypatch.setenv("SHARP_OWNER_TOKEN", "owner-token-123")
    config = {
        "workspace_folder": str(workspace),
        "access_control": make_access_config(
            enabled=False,
            allow_localhost_bypass=False,
        ),
        "photo_gallery_roots": [],
    }
    write_config(config_file, config)
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
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

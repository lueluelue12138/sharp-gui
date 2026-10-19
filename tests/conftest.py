import json
from io import BytesIO

import pytest
from PIL import Image

from backend.app_factory import create_app


@pytest.fixture(autouse=True)
def isolated_user_configuration(tmp_path, monkeypatch):
    """所有测试都不能读写真实用户全局配置，包括子进程。"""
    monkeypatch.setenv('SHARP_CONFIG_HOME', str(tmp_path / 'user-config'))
    default_config = tmp_path / 'isolated-config.json'
    default_config.write_text(json.dumps({'workspace_folder': str(tmp_path / 'default-workspace')}), encoding='utf-8')
    monkeypatch.setenv('SHARP_CONFIG_FILE', str(default_config))
    from backend import runtime
    monkeypatch.setattr(runtime, 'CONFIG_FILE', str(tmp_path / 'old-package' / 'config.json'))
    monkeypatch.setattr(runtime, 'DEFAULT_WORKSPACE_FOLDER', str(tmp_path / 'default-workspace'))


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def config_file(tmp_path, workspace, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_folder": str(workspace),
                "model_format": "spz",
                "photo_gallery_roots": [],
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
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SHARP_CONFIG_FILE", str(config_path))
    return config_path


@pytest.fixture
def app(config_file):
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


def write_config(config_file, data):
    config_file.write_text(json.dumps(data), encoding="utf-8")


def make_png_bytes():
    buffer = BytesIO()
    image = Image.new("RGB", (8, 8), (255, 0, 0))
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

import json

from backend.config import load_config
from backend.services.photo_gallery import (
    get_photo_gallery_roots_for_config,
    migrate_photo_gallery_roots_config,
    normalize_workspace_key,
)
from backend.services.workspace_lock import WorkspaceInstanceLock


def _album(path):
    return {"id": "album1", "name": "Album", "path": str(path), "enabled": True, "recursive": True}


def test_albums_are_remembered_per_workspace(client, config_file, workspace, tmp_path):
    # 在当前工作目录下记录一个相册
    config = load_config()
    config["photo_gallery_roots_by_workspace"] = {
        normalize_workspace_key(str(workspace)): [_album(tmp_path / "album")]
    }
    config.pop("photo_gallery_roots", None)
    config_file.write_text(json.dumps(config), encoding="utf-8")

    new_workspace = tmp_path / "new-workspace"
    new_workspace.mkdir()

    # 切换到新工作目录：新目录没有相册记录
    response = client.post("/api/settings", json={"workspace_folder": str(new_workspace)})
    assert response.status_code == 200
    assert response.get_json()["needs_restart"] is True

    config = load_config()
    config["workspace_folder"] = str(new_workspace)
    assert get_photo_gallery_roots_for_config(config) == []

    # 切回旧工作目录：之前的相册仍然记得
    config["workspace_folder"] = str(workspace)
    roots = get_photo_gallery_roots_for_config(config)
    assert len(roots) == 1
    assert roots[0]["id"] == "album1"


def test_legacy_global_roots_migrate_to_current_workspace(workspace, tmp_path):
    legacy_config = {
        "workspace_folder": str(workspace),
        "photo_gallery_roots": [_album(tmp_path / "album")],
    }

    changed = migrate_photo_gallery_roots_config(legacy_config)
    assert changed is True
    assert "photo_gallery_roots" not in legacy_config

    buckets = legacy_config["photo_gallery_roots_by_workspace"]
    key = normalize_workspace_key(str(workspace))
    assert key in buckets
    assert buckets[key][0]["id"] == "album1"


def test_migrated_legacy_roots_do_not_leak_to_other_workspace(workspace, tmp_path):
    legacy_config = {
        "workspace_folder": str(workspace),
        "photo_gallery_roots": [_album(tmp_path / "album")],
    }
    migrate_photo_gallery_roots_config(legacy_config)

    # 切换到另一个工作目录后，旧相册不再出现
    legacy_config["workspace_folder"] = str(tmp_path / "other")
    assert get_photo_gallery_roots_for_config(legacy_config) == []


def test_changing_workspace_archives_legacy_roots_before_switch(client, config_file, workspace, tmp_path):
    # 模拟仍是旧格式（仅顶层 photo_gallery_roots）的配置在切换工作目录时被正确归档
    config = {
        "workspace_folder": str(workspace),
        "model_format": "spz",
        "photo_gallery_roots": [_album(tmp_path / "album")],
    }
    config_file.write_text(json.dumps(config), encoding="utf-8")

    new_workspace = tmp_path / "new-workspace"
    new_workspace.mkdir()
    response = client.post("/api/settings", json={"workspace_folder": str(new_workspace)})
    assert response.status_code == 200

    saved = load_config()
    assert "photo_gallery_roots" not in saved
    old_key = normalize_workspace_key(str(workspace))
    assert saved["photo_gallery_roots_by_workspace"][old_key][0]["id"] == "album1"

    # 新工作目录无相册；切回旧工作目录可恢复
    saved["workspace_folder"] = str(new_workspace)
    assert get_photo_gallery_roots_for_config(saved) == []
    saved["workspace_folder"] = str(workspace)
    assert len(get_photo_gallery_roots_for_config(saved)) == 1


def test_changing_to_locked_workspace_returns_conflict_without_saving(
    client,
    config_file,
    workspace,
    tmp_path,
):
    target_workspace = tmp_path / "occupied-workspace"
    target_lock = WorkspaceInstanceLock(str(target_workspace))
    target_lock.acquire()
    config_before = config_file.read_text(encoding="utf-8")

    try:
        response = client.post(
            "/api/settings",
            json={"workspace_folder": str(target_workspace)},
        )
    finally:
        target_lock.release()

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "workspace_in_use"
    assert "Workspace is already in use" in payload["error"]
    assert config_file.read_text(encoding="utf-8") == config_before
    assert load_config()["workspace_folder"] == str(workspace)


def test_invalid_workspace_folder_is_rejected_without_saving(client, config_file, workspace):
    config_before = config_file.read_text(encoding="utf-8")

    for invalid_workspace in (None, "   ", 123, []):
        response = client.post(
            "/api/settings",
            json={"workspace_folder": invalid_workspace},
        )

        assert response.status_code == 400
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["code"] == "invalid_workspace_folder"
        assert config_file.read_text(encoding="utf-8") == config_before
        assert load_config()["workspace_folder"] == str(workspace)


def test_saving_current_workspace_does_not_conflict_with_its_live_lock(
    client,
    workspace,
):
    current_lock = WorkspaceInstanceLock(str(workspace))
    current_lock.acquire()

    try:
        response = client.post(
            "/api/settings",
            json={"workspace_folder": f"  {workspace}  "},
        )
    finally:
        current_lock.release()

    assert response.status_code == 200
    assert response.get_json()["needs_restart"] is True
    assert load_config()["workspace_folder"] == str(workspace)

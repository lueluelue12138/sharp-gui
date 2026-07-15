import os

import pytest

from backend.services.static_files import get_relative_files_path


def test_model_file_under_allowed_root_is_served(client, app):
    paths = app.config["PATH_CONTEXT"]
    model_path = paths.output_folder + "/model.ply"
    with open(model_path, "wb") as f:
        f.write(b"ply-data")

    response = client.get(f"/files/{get_relative_files_path(model_path, paths)}")
    assert response.status_code == 200
    assert response.data == b"ply-data"


def test_imported_model_and_cover_roots_are_served_but_index_is_not(client, app):
    paths = app.config["PATH_CONTEXT"]
    model_path = paths.model_asset_import_folder + "/imported.ply"
    cover_path = paths.model_asset_thumbnail_folder + "/imported.jpg"
    with open(model_path, "wb") as f:
        f.write(b"imported-ply")
    with open(cover_path, "wb") as f:
        f.write(b"cover")

    model_response = client.get(f"/files/{get_relative_files_path(model_path, paths)}")
    assert model_response.status_code == 200
    assert model_response.data == b"imported-ply"

    cover_response = client.get(f"/files/{get_relative_files_path(cover_path, paths)}")
    assert cover_response.status_code == 200
    assert cover_response.data == b"cover"

    with open(paths.model_asset_index_file, "wb") as f:
        f.write(b"secret-index")
    index_response = client.get(f"/files/{get_relative_files_path(paths.model_asset_index_file, paths)}")
    assert index_response.status_code == 404


def test_sensitive_files_are_not_served(client):
    response = client.get("/files/config.json")
    assert response.status_code == 404


def test_path_traversal_is_not_served(client):
    response = client.get("/files/%2e%2e/config.json")
    assert response.status_code == 404


def test_symlinked_file_cannot_escape_allowed_root(client, app, tmp_path):
    paths = app.config["PATH_CONTEXT"]
    outside = tmp_path / "outside.ply"
    outside.write_bytes(b"outside")
    link = os.path.join(paths.output_folder, "escape.ply")
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    response = client.get(f"/files/{get_relative_files_path(link, paths)}")

    assert response.status_code == 404


def test_symlinked_allowed_root_outside_workspace_is_not_served(client, app, tmp_path):
    paths = app.config["PATH_CONTEXT"]
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    (outside_root / "escape.ply").write_bytes(b"outside")
    os.rmdir(paths.output_folder)
    try:
        os.symlink(outside_root, paths.output_folder, target_is_directory=True)
    except OSError as exc:
        os.makedirs(paths.output_folder, exist_ok=True)
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    response = client.get("/files/workspace/outputs/escape.ply")

    assert response.status_code == 404

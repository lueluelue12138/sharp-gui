import json
import os
from io import BytesIO

from werkzeug.datastructures import FileStorage

from backend.paths import build_path_context, ensure_runtime_directories
from backend.services import model_assets, model_gallery, video_reconstruction
from backend.services.model_orientation import (
    VIEWER_ORIENTATION_DEFAULT,
    VIEWER_ORIENTATION_UNKNOWN,
    VIEWER_ORIENTATION_Y_FRONT,
    normalize_viewer_orientation,
    resolve_viewer_orientation,
)
from backend.services.photo_gallery import photo_meta_from_path, save_photo_index
from backend.services.task_queue import TaskManager
from tests.conftest import write_config


def write_model(paths, asset_id, extension, payload=b"model"):
    model_path = os.path.join(paths.output_folder, f"{asset_id}.{extension}")
    with open(model_path, "wb") as file:
        file.write(payload)
    return model_path


def test_backend_orientation_contract_is_normalized_and_conservative():
    assert normalize_viewer_orientation(" DEFAULT ") == VIEWER_ORIENTATION_DEFAULT
    assert normalize_viewer_orientation("Y-FRONT") == VIEWER_ORIENTATION_Y_FRONT
    assert normalize_viewer_orientation("unknown") == VIEWER_ORIENTATION_UNKNOWN
    assert normalize_viewer_orientation("camera-up") == VIEWER_ORIENTATION_UNKNOWN
    assert normalize_viewer_orientation(None) == VIEWER_ORIENTATION_UNKNOWN

    assert resolve_viewer_orientation(source_media_type="image") == VIEWER_ORIENTATION_DEFAULT
    assert resolve_viewer_orientation(source_media_type="video") == VIEWER_ORIENTATION_Y_FRONT
    assert resolve_viewer_orientation(source_type="video") == VIEWER_ORIENTATION_Y_FRONT
    assert resolve_viewer_orientation(source_media_type="other") == VIEWER_ORIENTATION_UNKNOWN
    assert (
        resolve_viewer_orientation("unknown", source_media_type="video")
        == VIEWER_ORIENTATION_UNKNOWN
    )
    assert (
        resolve_viewer_orientation("invalid", source_media_type="video")
        == VIEWER_ORIENTATION_UNKNOWN
    )


def test_image_and_video_tasks_write_explicit_orientation_sidecars(tmp_path):
    paths = build_path_context({"workspace_folder": str(tmp_path / "workspace")})
    ensure_runtime_directories(paths)

    manager = TaskManager(paths=paths)
    manager._write_image_metadata("image-model", "photo.jpg", "completed")
    image_metadata = model_gallery.read_model_metadata(paths, "image-model")
    assert image_metadata["source_media_type"] == "image"
    assert image_metadata["viewer_orientation"] == VIEWER_ORIENTATION_DEFAULT

    video_reconstruction.prepare_video_model_assets(
        paths,
        {
            "output_path": os.path.join(paths.output_folder, "video-model.ply"),
            "source_media_id": "album-video",
            "source_name": "clip.mp4",
            "source_video_path": os.path.join(paths.workspace_folder, "clip.mp4"),
            "source_mime_type": "video/mp4",
            "mode": "auto",
            "quality": "high",
            "engine": "auto",
            "resolved_engine": "stable",
        },
        generate_thumbnail=False,
    )
    video_metadata = model_gallery.read_model_metadata(paths, "video-model")
    assert video_metadata["source_media_type"] == "video"
    assert video_metadata["viewer_orientation"] == VIEWER_ORIENTATION_Y_FRONT


def test_model_asset_api_projects_orientation_to_details_and_companion_files(client, app):
    paths = app.config["PATH_CONTEXT"]
    for asset_id, source_media_type, orientation in (
        ("image-model", "image", VIEWER_ORIENTATION_DEFAULT),
        ("video-model", "video", VIEWER_ORIENTATION_Y_FRONT),
    ):
        write_model(paths, asset_id, "ply", b"ply")
        write_model(paths, asset_id, "spz", b"spz")
        model_gallery.write_model_metadata(
            paths,
            asset_id,
            {
                "source_media_type": source_media_type,
                "viewer_orientation": orientation,
                "coordinate_system": "opencv",
            },
        )

    list_response = client.get("/api/model-assets?refresh=1&sort=name_asc")
    assert list_response.status_code == 200
    summaries = {
        asset["id"]: asset
        for asset in list_response.get_json()["items"]
    }

    for asset_id, expected_source, expected_orientation in (
        ("image-model", "image", VIEWER_ORIENTATION_DEFAULT),
        ("video-model", "video", VIEWER_ORIENTATION_Y_FRONT),
    ):
        summary = summaries[asset_id]
        assert summary["source_media_type"] == expected_source
        assert summary["viewer_orientation"] == expected_orientation
        assert {file["format"] for file in summary["files"]} == {"ply", "spz"}
        assert all(
            file["source_media_type"] == expected_source
            and file["viewer_orientation"] == expected_orientation
            for file in summary["files"]
        )

        detail_response = client.get(f"/api/model-assets/{asset_id}")
        assert detail_response.status_code == 200
        detail = detail_response.get_json()
        assert detail["source_media_type"] == expected_source
        assert detail["viewer_orientation"] == expected_orientation
        assert detail["metadata"]["coordinate_system"] == "opencv"
        assert detail["metadata"]["viewer_orientation"] == expected_orientation
        assert all(
            file["source_media_type"] == expected_source
            and file["viewer_orientation"] == expected_orientation
            for file in detail["files"]
        )


def test_imported_asset_projects_unknown_orientation_in_all_shapes(tmp_path):
    paths = build_path_context({"workspace_folder": str(tmp_path / "workspace")})
    ensure_runtime_directories(paths)

    imported = model_assets.import_model_assets(
        paths,
        [FileStorage(stream=BytesIO(b"ply"), filename="Imported Scan.ply")],
    )["assets"][0]

    assert imported["source_media_type"] is None
    assert imported["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN
    assert imported["metadata"]["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN
    assert imported["files"][0]["source_media_type"] is None
    assert imported["files"][0]["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN

    summary = model_assets.list_model_assets(paths, {})["items"][0]
    detail = model_assets.get_model_asset(paths, imported["id"])
    for asset in (summary, detail):
        assert asset["source_media_type"] is None
        assert asset["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN
        assert asset["files"][0]["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN


def test_old_catalog_is_rebuilt_once_to_add_orientation_context(tmp_path):
    paths = build_path_context({"workspace_folder": str(tmp_path / "workspace")})
    ensure_runtime_directories(paths)
    write_model(paths, "image-model", "ply", b"ply")
    model_gallery.write_model_metadata(
        paths,
        "image-model",
        {"source_media_type": "image"},
    )
    with open(paths.model_asset_index_file, "w", encoding="utf-8") as file:
        json.dump(
            {
                "version": 2,
                "assets": {},
                "catalog": {
                    "items": {
                        "image-model": {
                            "id": "image-model",
                            "source_type": "generated",
                        }
                    }
                },
            },
            file,
        )

    rebuilt = model_assets.list_model_assets(paths, {})

    assert rebuilt["items"][0]["viewer_orientation"] == VIEWER_ORIENTATION_DEFAULT
    assert model_assets.read_asset_index(paths)["version"] == model_assets.INDEX_VERSION


def test_catalog_refresh_recovers_unique_legacy_video_without_warm_page_rescan(
    config_file,
    workspace,
    monkeypatch,
):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "photo_gallery_roots": [
                {
                    "id": "album1",
                    "name": "Album",
                    "path": str(album_dir),
                    "enabled": True,
                }
            ],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    video_meta = photo_meta_from_path(
        {"id": "album1", "path": str(album_dir)},
        str(video_path),
    )
    save_photo_index(paths, {"photos": {video_meta["id"]: video_meta}})
    write_model(paths, "clip-2", "ply", b"ply")
    write_model(paths, "clip-2", "spz", b"spz")
    monkeypatch.setattr(model_gallery, "generate_video_thumbnail", lambda *_args: None)

    refreshed = model_assets.list_model_assets(paths, {"refresh": "1"})
    recovered = refreshed["items"][0]
    assert recovered["source_type"] == "video"
    assert recovered["source_media_type"] == "video"
    assert recovered["viewer_orientation"] == VIEWER_ORIENTATION_Y_FRONT
    assert all(
        file["viewer_orientation"] == VIEWER_ORIENTATION_Y_FRONT
        for file in recovered["files"]
    )
    recovered_metadata = model_gallery.read_model_metadata(paths, "clip-2")
    assert recovered_metadata["recovered_from"] == "gallery-video-stem"
    assert recovered_metadata["viewer_orientation"] == VIEWER_ORIENTATION_Y_FRONT

    def unexpected_scan(*_args, **_kwargs):
        raise AssertionError("warm model-asset pages must not rescan source media")

    monkeypatch.setattr(model_assets, "collect_generated_file_groups", unexpected_scan)
    monkeypatch.setattr(model_gallery, "backfill_legacy_video_metadata", unexpected_scan)
    warm = model_assets.list_model_assets(
        paths,
        {
            "source": "video",
            "format": "spz",
            "sort": "name_asc",
            "limit": "1",
            "cursor": "0",
        },
    )
    assert warm["total"] == 1
    assert warm["items"][0]["id"] == "clip-2"


def test_ambiguous_legacy_video_evidence_remains_unknown(
    config_file,
    workspace,
    monkeypatch,
):
    roots = []
    photos = {}
    for index in (1, 2):
        album_dir = workspace / f"album-{index}"
        album_dir.mkdir()
        video_path = album_dir / "clip.mp4"
        video_path.write_bytes(b"video")
        root = {
            "id": f"album{index}",
            "name": f"Album {index}",
            "path": str(album_dir),
            "enabled": True,
        }
        roots.append(root)
        meta = photo_meta_from_path(root, str(video_path))
        photos[meta["id"]] = meta

    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "photo_gallery_roots": roots,
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    save_photo_index(paths, {"photos": photos})
    write_model(paths, "clip", "ply", b"ply")
    monkeypatch.setattr(model_gallery, "generate_video_thumbnail", lambda *_args: None)

    result = model_assets.list_model_assets(paths, {"refresh": "1"})

    assert result["items"][0]["source_media_type"] is None
    assert result["items"][0]["viewer_orientation"] == VIEWER_ORIENTATION_UNKNOWN
    assert model_gallery.read_model_metadata(paths, "clip") == {}

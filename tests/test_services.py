import os
import json
import zipfile
from io import BytesIO

from werkzeug.datastructures import FileStorage

from backend.config import coerce_bool, coerce_int, normalize_access_control_config
from backend.paths import build_path_context, ensure_runtime_directories
from backend.services.photo_gallery import (
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    build_photo_item,
    clear_photo_gallery_cache,
    convert_photos_to_models,
    create_photo_download_zip,
    cleanup_expired_photo_download_zips,
    delete_photo_album,
    ensure_video_poster,
    get_photo_thumbnail_filename,
    get_photo_gallery_cache_stats,
    get_video_poster_filename,
    list_album_photos,
    list_photo_album_responses,
    load_album_index,
    load_photo_index,
    make_photo_id,
    make_unique_photo_upload_filename,
    photo_meta_from_path,
    resolve_media_path,
    resolve_photo_path,
    save_photo_index,
    scan_photo_album,
    upload_photos_to_album,
)
from backend.services import model_assets, model_gallery, video_reconstruction
from backend.services.static_files import is_real_path_inside
from backend.services.task_queue import TaskManager
from tests.conftest import write_config


def test_photo_upload_filename_sanitizes_and_rejects_unsupported(tmp_path):
    target = tmp_path / "album"
    target.mkdir()
    (target / "my_photo.jpg").write_bytes(b"existing")

    filename = make_unique_photo_upload_filename("../my photo.jpg", str(target))
    assert filename.startswith("my_photo-")
    assert filename.endswith(".jpg")
    assert make_unique_photo_upload_filename("note.txt", str(target)) is None


def test_config_normalize_coerces_access_control_values():
    config = {
        "access_control": {
            "enabled": "yes",
            "session_days": "999",
            "allow_localhost_bypass": "off",
            "allow_remote_generation": "true",
            "session_version": "0",
            "lan_bind_enabled": "no",
        }
    }

    access_config, changed = normalize_access_control_config(config)

    assert access_config["enabled"] is True
    assert access_config["session_days"] == 365
    assert access_config["allow_localhost_bypass"] is False
    assert access_config["allow_remote_generation"] is True
    assert access_config["session_version"] == 1
    assert access_config["lan_bind_enabled"] is False
    assert access_config["session_secret"]
    assert changed is True
    assert coerce_bool("on") is True
    assert coerce_int("bad", 7, 1, 10) == 7


def test_video_reconstruction_config_and_paths_are_normalized(workspace):
    from backend.config import normalize_video_reconstruction_config

    config = {
        "workspace_folder": str(workspace),
        "video_reconstruction": {
            "default_quality": "bad",
            "default_engine": "unsupported",
            "vram_budget": "invalid",
            "keep_intermediate_files": "yes",
        },
    }

    video_config, changed = normalize_video_reconstruction_config(config)
    paths = build_path_context(config)

    assert video_config == {
        "default_quality": "high",
        "default_engine": "auto",
        "vram_budget": "12gb",
        "keep_intermediate_files": True,
    }
    assert changed is True
    assert os.path.normpath(paths.video_reconstruction_jobs_folder).endswith(
        os.path.normpath(".video-reconstruction/jobs")
    )

    config["video_reconstruction"]["default_quality"] = "custom"
    video_config, changed = normalize_video_reconstruction_config(config)
    assert video_config["default_quality"] == "high"
    config["video_reconstruction"]["default_quality"] = "extreme"
    video_config, changed = normalize_video_reconstruction_config(config)
    assert video_config["default_quality"] == "extreme"


def test_video_process_env_prioritizes_portable_wrappers(tmp_path, monkeypatch):
    video_env = tmp_path / ".video-reconstruction-env"
    portable_bin = video_env / "portable-bin"
    scripts_dir = video_env / "Scripts"
    colmap_bin = video_env / "colmap" / "bin"
    for path in (portable_bin, scripts_dir, colmap_bin):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        video_reconstruction,
        "_local_video_reconstruction_paths",
        lambda: (portable_bin, scripts_dir, colmap_bin),
    )
    monkeypatch.setattr(video_reconstruction, "read_vcvars_environment", lambda: {})
    monkeypatch.setattr(video_reconstruction, "find_cuda_home", lambda: None)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(scripts_dir), "system-bin", str(portable_bin))),
    )

    process_env = video_reconstruction.build_video_process_env()
    path_parts = process_env["PATH"].split(os.pathsep)

    assert path_parts[:3] == [str(portable_bin), str(scripts_dir), str(colmap_bin)]
    assert path_parts.count(str(portable_bin)) == 1
    assert path_parts.count(str(scripts_dir)) == 1


def test_model_asset_library_state_is_scoped_to_workspace(tmp_path):
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    paths_a = build_path_context({"workspace_folder": str(workspace_a)})
    paths_b = build_path_context({"workspace_folder": str(workspace_b)})
    ensure_runtime_directories(paths_a)
    ensure_runtime_directories(paths_b)

    with open(os.path.join(paths_a.output_folder, "demo.ply"), "wb") as file:
        file.write(b"workspace-a-model")
    with open(os.path.join(paths_b.output_folder, "demo.ply"), "wb") as file:
        file.write(b"workspace-b-model")

    edited_a = model_assets.update_model_asset_profile(
        paths_a,
        "demo",
        {"display_name": "Workspace A Demo", "tags": ["a"], "note": "state a"},
    )
    edited_b = model_assets.update_model_asset_profile(
        paths_b,
        "demo",
        {"display_name": "Workspace B Demo", "tags": ["b"], "note": "state b"},
    )

    assert edited_a["name"] == "Workspace A Demo"
    assert edited_b["name"] == "Workspace B Demo"
    assert paths_a.model_asset_index_file != paths_b.model_asset_index_file
    assert os.path.isfile(paths_a.model_asset_index_file)
    assert os.path.isfile(paths_b.model_asset_index_file)

    imported_a = model_assets.import_model_assets(
        paths_a,
        [FileStorage(stream=BytesIO(b"imported-a"), filename="same-name.ply")],
    )
    imported_b = model_assets.import_model_assets(
        paths_b,
        [FileStorage(stream=BytesIO(b"imported-b"), filename="same-name.ply")],
    )

    imported_a_asset = imported_a["assets"][0]
    imported_b_asset = imported_b["assets"][0]
    assert imported_a_asset["id"] != imported_b_asset["id"]
    assert os.path.isfile(os.path.join(paths_a.model_asset_import_folder, "same-name.ply"))
    assert os.path.isfile(os.path.join(paths_b.model_asset_import_folder, "same-name.ply"))

    names_a = {asset["name"] for asset in model_assets.list_model_assets(paths_a, {})["items"]}
    names_b = {asset["name"] for asset in model_assets.list_model_assets(paths_b, {})["items"]}

    assert "Workspace A Demo" in names_a
    assert "Workspace B Demo" not in names_a
    assert "Workspace B Demo" in names_b
    assert "Workspace A Demo" not in names_b


def test_real_path_inside_handles_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "file.txt"
    outside = tmp_path / "outside.txt"

    assert is_real_path_inside(str(inside), str(root)) is True
    assert is_real_path_inside(str(outside), str(root)) is False


def test_photo_id_resolves_through_index_and_album_root(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    photo_path = album_dir / "image.jpg"
    photo_path.write_bytes(b"fake")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(photo_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})

    resolved = resolve_photo_path(paths, meta["id"])

    assert make_photo_id("album1", "image.jpg") == meta["id"]
    assert resolved is not None
    assert resolved[1] == str(photo_path.resolve())


def test_media_scan_lists_images_and_videos_with_type_filter(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    image_path = album_dir / "image.jpg"
    video_path = album_dir / "clip.MP4"
    note_path = album_dir / "note.txt"
    image_path.write_bytes(b"fake-image")
    video_path.write_bytes(b"fake-video")
    note_path.write_bytes(b"ignore-me")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    monkeypatch.setattr("backend.services.photo_gallery.probe_video_metadata", lambda _path: {})
    paths = build_path_context({"workspace_folder": str(workspace)})

    media_items, status, error = scan_photo_album(paths, {"id": "album1", "path": str(album_dir), "enabled": True})
    payload_all, _ = list_album_photos(paths, "album1", "name_asc", "0", "20", "all")
    payload_photos, _ = list_album_photos(paths, "album1", "name_asc", "0", "20", "photo")
    payload_videos, _ = list_album_photos(paths, "album1", "name_asc", "0", "20", "video")

    assert status == "idle"
    assert error is None
    assert {item["media_type"] for item in media_items} == {MEDIA_TYPE_IMAGE, MEDIA_TYPE_VIDEO}
    assert payload_all["total"] == 2
    assert payload_all["media_counts"] == {"all": 2, "image": 1, "photo": 1, "video": 1}
    assert payload_photos["total"] == 1
    assert payload_photos["items"][0]["media_type"] == MEDIA_TYPE_IMAGE
    assert payload_videos["total"] == 1
    assert payload_videos["items"][0]["media_type"] == MEDIA_TYPE_VIDEO
    assert payload_videos["items"][0]["playback_url"].startswith("/api/video-play/")
    assert payload_videos["items"][0]["playback_url"].endswith("/clip.MP4")
    assert "note.txt" not in {item["name"] for item in media_items}


def test_legacy_photo_index_entries_are_migrated_to_image_type(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    save_photo_index(paths, {"photos": {"legacy": {"id": "legacy", "name": "old.jpg"}}})

    index_data = load_photo_index(paths)

    assert index_data["photos"]["legacy"]["media_type"] == MEDIA_TYPE_IMAGE


def test_video_path_resolver_rejects_album_root_escape(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    outside_path = workspace / "outside.mp4"
    outside_path.write_bytes(b"outside")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    media_id = make_photo_id("album1", "../outside.mp4")
    save_photo_index(paths, {
        "photos": {
            media_id: {
                "id": media_id,
                "album_id": "album1",
                "relative_path": "../outside.mp4",
                "name": "outside.mp4",
                "media_type": MEDIA_TYPE_VIDEO,
                "mtime": outside_path.stat().st_mtime,
                "size": outside_path.stat().st_size,
            },
        },
    })

    assert resolve_media_path(paths, media_id, expected_type=MEDIA_TYPE_VIDEO) is None


def test_video_reconstruction_output_name_is_safe_and_unique(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    os.makedirs(paths.output_folder, exist_ok=True)
    existing = os.path.join(paths.output_folder, "clip.ply")
    with open(existing, "wb") as f:
        f.write(b"exists")

    stem, ply_path, spz_path = video_reconstruction.unique_output_paths(paths, "clip.mp4", "fallback.mp4")
    chinese_stem, _, _ = video_reconstruction.unique_output_paths(paths, "中文 文件.mp4", "fallback.mp4")

    assert stem == "clip-2"
    assert ply_path.endswith("clip-2.ply")
    assert spz_path.endswith("clip-2.spz")
    assert chinese_stem


def test_video_reconstruction_quality_profile_uses_vram_budget():
    default_profile = video_reconstruction.resolve_quality_profile("high", "12gb")
    low_vram_profile = video_reconstruction.resolve_quality_profile("high", "8gb")
    large_vram_profile = video_reconstruction.resolve_quality_profile("extreme", "24gb")
    custom_profile = video_reconstruction.resolve_quality_profile("custom", "8gb", {
        "frame_count": 720,
        "max_num_iterations": 42000,
        "downscale_factor": 2,
        "matching_method": "sequential",
        "cache_images": "cpu",
    })

    assert default_profile["frame_count"] == 180
    assert default_profile["max_num_iterations"] == 30000
    assert default_profile["downscale_factor"] == 2
    assert low_vram_profile["frame_count"] < default_profile["frame_count"]
    assert low_vram_profile["max_num_iterations"] < default_profile["max_num_iterations"]
    assert low_vram_profile["max_resolution"] == 1280
    assert low_vram_profile["downscale_factor"] == 4
    assert large_vram_profile["frame_count"] > video_reconstruction.QUALITY_PROFILES["extreme"]["frame_count"]
    assert large_vram_profile["max_resolution"] == 2160
    assert large_vram_profile["downscale_factor"] == 1
    assert custom_profile["frame_count"] == 720
    assert custom_profile["max_num_iterations"] == 42000
    assert custom_profile["downscale_factor"] == 2
    assert custom_profile["matching_method"] == "sequential"
    assert custom_profile["cache_images"] == "cpu"


def test_video_reconstruction_commands_use_quality_profile():
    profile = video_reconstruction.resolve_quality_profile("high", "12gb")
    custom_profile = video_reconstruction.resolve_quality_profile("custom", "12gb", {
        "frame_count": 600,
        "max_num_iterations": 35000,
        "downscale_factor": 2,
        "matching_method": "sequential",
        "cache_images": "cpu",
    })

    process_cmd = video_reconstruction.build_process_data_command("clip.mp4", "data", profile)
    train_cmd = video_reconstruction.build_train_command("data", "train", profile)
    custom_process_cmd = video_reconstruction.build_process_data_command("clip.mp4", "data", custom_profile)
    custom_train_cmd = video_reconstruction.build_train_command("data", "train", custom_profile)

    assert process_cmd[process_cmd.index("--num-frames-target") + 1] == "180"
    assert process_cmd[process_cmd.index("--num-downscales") + 1] == "2"
    assert process_cmd[process_cmd.index("--matching-method") + 1] == "exhaustive"
    assert train_cmd[train_cmd.index("--vis") + 1] == "viewer"
    assert train_cmd[train_cmd.index("--downscale-factor") + 1] == "2"
    assert train_cmd[train_cmd.index("--pipeline.datamanager.train-cameras-sampling-strategy") + 1] == "fps"
    assert train_cmd[train_cmd.index("--pipeline.model.camera-optimizer.mode") + 1] == "SO3xR3"
    assert train_cmd[train_cmd.index("--pipeline.model.num-random") + 1] == "80000"
    assert train_cmd[-4:] == ["--data", "data", "--downscale-factor", "2"]
    assert custom_process_cmd[custom_process_cmd.index("--num-frames-target") + 1] == "600"
    assert custom_process_cmd[custom_process_cmd.index("--num-downscales") + 1] == "1"
    assert custom_process_cmd[custom_process_cmd.index("--matching-method") + 1] == "sequential"
    assert custom_train_cmd[custom_train_cmd.index("--max-num-iterations") + 1] == "35000"
    assert custom_train_cmd[custom_train_cmd.index("--pipeline.datamanager.cache-images") + 1] == "cpu"
    assert custom_train_cmd[-4:] == ["--data", "data", "--downscale-factor", "2"]


def test_video_reconstruction_custom_options_are_validated():
    valid, error = video_reconstruction.normalize_custom_quality_options({
        "frame_count": "600",
        "max_num_iterations": "35000",
        "downscale_factor": "2",
        "matching_method": "sequential",
        "cache_images": "cpu",
    })
    assert error is None
    assert valid["frame_count"] == 600

    invalid, error = video_reconstruction.normalize_custom_quality_options({
        "frame_count": 600,
        "max_num_iterations": 35000,
        "downscale_factor": 2,
        "matching_method": "exhaustive",
        "cache_images": "cpu",
    })
    assert invalid is None
    assert error["field"] == "custom_options.frame_count"


def test_video_reconstruction_train_command_can_disable_viewer():
    profile = video_reconstruction.resolve_quality_profile("high", "12gb")

    train_cmd = video_reconstruction.build_train_command(
        "data",
        "train",
        profile,
        visualizer="tensorboard",
    )

    assert train_cmd[train_cmd.index("--vis") + 1] == "tensorboard"


def test_video_reconstruction_focused_cleanup_removes_outliers(tmp_path):
    import numpy as np
    from plyfile import PlyData, PlyElement

    source_path = tmp_path / "source.ply"
    output_path = tmp_path / "focused.ply"
    dtype = [
        ("x", "f4"),
        ("y", "f4"),
        ("z", "f4"),
        ("opacity", "f4"),
        ("scale_0", "f4"),
        ("scale_1", "f4"),
        ("scale_2", "f4"),
    ]
    vertices = np.zeros(120, dtype=dtype)
    vertices["x"] = np.linspace(-1.0, 1.0, 120)
    vertices["y"] = np.linspace(-0.5, 0.5, 120)
    vertices["z"] = np.linspace(-0.25, 0.25, 120)
    vertices["opacity"] = 1.5
    vertices["scale_0"] = -4.0
    vertices["scale_1"] = -4.0
    vertices["scale_2"] = -4.0
    vertices[-1]["x"] = 50.0
    vertices[-1]["y"] = 50.0
    vertices[-1]["z"] = 50.0
    vertices[-2]["opacity"] = -10.0
    vertices[-3]["scale_0"] = 4.0
    PlyData([PlyElement.describe(vertices, "vertex")], text=False).write(source_path)

    stats = video_reconstruction.clean_gaussian_splat_ply(
        source_path,
        output_path,
        {
            **video_reconstruction.FOCUSED_CLEANUP_PROFILE,
            "min_vertices": 10,
            "min_keep_ratio": 0.2,
        },
    )
    cleaned = PlyData.read(output_path)["vertex"].data

    assert not stats["skipped"]
    assert stats["output_vertices"] < stats["input_vertices"]
    assert cleaned["x"].max() < 50.0
    assert cleaned["opacity"].min() > -10.0


def test_video_reconstruction_resolves_source_video_safely(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})

    resolved = video_reconstruction.resolve_source_video(paths, meta["id"])

    assert resolved is not None
    assert resolved[1] == str(video_path.resolve())


def test_task_manager_public_serialization_keeps_image_compatibility_and_hides_paths(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths)
    input_path = workspace / "inputs" / "photo.jpg"
    input_path.parent.mkdir()
    input_path.write_bytes(b"fake")

    created = task_manager.enqueue_file(str(input_path), "photo.jpg")
    tasks, has_active = task_manager.list_tasks()

    assert created["kind"] == "image_sharp"
    assert tasks[0]["id"] == created["id"]
    assert tasks[0]["filename"] == "photo.jpg"
    assert "input_path" not in tasks[0]
    assert "output_folder" not in tasks[0]
    assert has_active is True


def test_video_task_public_serialization_hides_source_paths(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths)
    task = task_manager.enqueue_video_reconstruction({
        "filename": "clip.ply",
        "source_media_id": "album_abc",
        "source_name": "clip.mp4",
        "source_video_path": str(workspace / "album" / "clip.mp4"),
        "mode": "auto",
        "quality": "high",
        "engine": "auto",
        "resolved_engine": "stable",
        "output_name": "clip",
        "output_path": str(workspace / "outputs" / "clip.ply"),
        "spz_path": str(workspace / "outputs" / "clip.spz"),
        "keep_intermediate_files": False,
        "details": {"warnings": [{"code": "test", "message": "ok"}], "logs": ["secret"]},
    })

    with task_manager.task_lock:
        task_manager.task_status[task["id"]]["error"] = f"failed at {workspace / 'album' / 'clip.mp4'}"
    tasks, _ = task_manager.list_tasks()

    assert "source_video_path" not in task
    assert "output_path" not in task
    assert tasks[0]["error"] == "failed at [path]"
    assert tasks[0]["details"] == {"warnings": [{"code": "test", "message": "ok"}]}


def test_video_metadata_and_poster_degrade_without_optional_tools(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.webm"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    monkeypatch.setattr("backend.services.photo_gallery.get_optional_command", lambda _name: None)
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})

    item = build_photo_item(paths, meta)

    assert item["media_type"] == MEDIA_TYPE_VIDEO
    assert item["duration"] is None
    assert item["poster_url"].startswith("/api/video-poster/")
    assert ensure_video_poster(paths, meta["id"]) is None


def test_cached_video_poster_is_reused_without_ffmpeg(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    monkeypatch.setattr("backend.services.photo_gallery.get_optional_command", lambda _name: None)
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})
    os.makedirs(paths.video_poster_folder, exist_ok=True)
    poster_path = os.path.join(paths.video_poster_folder, get_video_poster_filename(meta["id"], meta))
    with open(poster_path, "wb") as f:
        f.write(b"cached-poster")

    assert ensure_video_poster(paths, meta["id"]) == poster_path


def test_delete_photo_album_cleans_album_media_cache(config_file, workspace):
    album_dir = workspace / "album"
    other_album_dir = workspace / "other-album"
    album_dir.mkdir()
    other_album_dir.mkdir()
    image_path = album_dir / "image.jpg"
    video_path = album_dir / "clip.mp4"
    other_image_path = other_album_dir / "other.jpg"
    image_path.write_bytes(b"fake-image")
    video_path.write_bytes(b"fake-video")
    other_image_path.write_bytes(b"other-image")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [
                {"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True},
                {"id": "album2", "name": "Other", "path": str(other_album_dir), "enabled": True},
            ],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    image_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(image_path))
    video_meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    other_meta = photo_meta_from_path({"id": "album2", "path": str(other_album_dir)}, str(other_image_path))
    save_photo_index(paths, {"photos": {
        image_meta["id"]: image_meta,
        video_meta["id"]: video_meta,
        other_meta["id"]: other_meta,
    }})
    os.makedirs(paths.photo_thumbnail_folder, exist_ok=True)
    os.makedirs(paths.video_poster_folder, exist_ok=True)
    image_thumb_path = os.path.join(paths.photo_thumbnail_folder, get_photo_thumbnail_filename(image_meta["id"], image_meta))
    video_poster_path = os.path.join(paths.video_poster_folder, get_video_poster_filename(video_meta["id"], video_meta))
    other_thumb_path = os.path.join(paths.photo_thumbnail_folder, get_photo_thumbnail_filename(other_meta["id"], other_meta))
    stale_variant_path = os.path.join(paths.photo_thumbnail_folder, f"{image_meta['id']}-old-version-480.jpg")
    for path in (image_thumb_path, video_poster_path, other_thumb_path, stale_variant_path):
        with open(path, "wb") as f:
            f.write(b"cache")

    payload, status_code = delete_photo_album(paths, "album1")

    assert status_code == 200
    assert payload == {"success": True}
    index_data = load_photo_index(paths)
    assert image_meta["id"] not in index_data["photos"]
    assert video_meta["id"] not in index_data["photos"]
    assert other_meta["id"] in index_data["photos"]
    assert not os.path.exists(image_thumb_path)
    assert not os.path.exists(video_poster_path)
    assert not os.path.exists(stale_variant_path)
    assert os.path.exists(other_thumb_path)


def test_media_download_zip_can_include_videos(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})

    result, error_payload, status_code = create_photo_download_zip(paths, [meta["id"]])

    assert status_code == 200
    assert error_payload is None
    assert result["added_count"] == 1
    with zipfile.ZipFile(result["zip_path"]) as archive:
        assert archive.namelist() == ["clip.mp4"]


def test_cleanup_expired_photo_download_zips_only_removes_old_temp_archives(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    os.makedirs(paths.photo_gallery_cache_folder, exist_ok=True)
    old_zip = os.path.join(paths.photo_gallery_cache_folder, "photo-gallery-old.zip")
    fresh_zip = os.path.join(paths.photo_gallery_cache_folder, "photo-gallery-fresh.zip")
    other_zip = os.path.join(paths.photo_gallery_cache_folder, "other.zip")
    for path in (old_zip, fresh_zip, other_zip):
        with open(path, "wb") as f:
            f.write(b"zip")
    old_mtime = 1_700_000_000
    os.utime(old_zip, (old_mtime, old_mtime))

    cleanup_expired_photo_download_zips(paths, max_age_seconds=1)

    assert not os.path.exists(old_zip)
    assert os.path.exists(fresh_zip)
    assert os.path.exists(other_zip)


def test_video_ids_are_not_accepted_for_photo_conversion(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})
    task_manager = TaskManager(paths=paths)

    payload = convert_photos_to_models(paths, task_manager, [meta["id"]])

    assert payload["success"] is False
    assert payload["failed"] == [{"id": meta["id"], "error": "Only photos can be converted to 3D"}]


def test_invalid_uploaded_photo_is_cleaned_up(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    storage = FileStorage(stream=BytesIO(b"not an image"), filename="bad.jpg")

    payload, status_code = upload_photos_to_album(paths, "album1", [storage])

    assert status_code == 400
    assert payload["success"] is False
    assert not any(album_dir.iterdir())


def test_album_list_and_pagination_use_cache_without_rescan(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    photo_path = album_dir / "image.jpg"
    photo_path.write_bytes(b"fake-image")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    scan_photo_album(paths, {"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True})

    def fail_scan(*_args, **_kwargs):
        raise AssertionError("ordinary reads must not rescan albums")

    monkeypatch.setattr("backend.services.photo_gallery.scan_photo_album", fail_scan)
    payload, status_code = list_album_photos(paths, "album1", "mtime_desc", "0", "20", "all")

    assert status_code == 200
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "image.jpg"
    assert payload["scan_status"] == "idle"


def test_album_pagination_snapshot_is_stable_during_rescan(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    for index in range(3):
        (album_dir / f"image-{index}.jpg").write_bytes(f"fake-{index}".encode())
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    scan_photo_album(paths, {"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True})

    first_page, _ = list_album_photos(paths, "album1", "name_asc", "0", "2", "all")
    snapshot = first_page["snapshot"]
    (album_dir / "image-9.jpg").write_bytes(b"new")
    scan_photo_album(paths, {"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True})

    stable_second_page, _ = list_album_photos(paths, "album1", "name_asc", "2", "2", "all", snapshot)
    fresh_first_page, _ = list_album_photos(paths, "album1", "name_asc", "0", "10", "all")

    assert [item["name"] for item in stable_second_page["items"]] == ["image-2.jpg"]
    assert "image-9.jpg" in [item["name"] for item in fresh_first_page["items"]]


def test_large_warm_album_browsing_does_not_walk_directory(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    photos = {}
    for index in range(1000):
        relative_path = f"image-{index:04d}.jpg"
        media_id = make_photo_id("album1", relative_path)
        photos[media_id] = {
            "id": media_id,
            "album_id": "album1",
            "relative_path": relative_path,
            "name": relative_path,
            "media_type": MEDIA_TYPE_IMAGE,
            "mtime": float(index),
            "ctime": float(index),
            "size": index + 1,
            "width": None,
            "height": None,
        }
    save_photo_index(paths, {"photos": photos})

    def fail_walk(_path):
        raise AssertionError("warm index browsing must not call os.walk")

    monkeypatch.setattr("backend.services.photo_gallery.os.walk", fail_walk)

    first_page, _ = list_album_photos(paths, "album1", "mtime_desc", "0", "60", "all")
    sorted_page, _ = list_album_photos(paths, "album1", "size_asc", "120", "60", "all")
    filtered_page, _ = list_album_photos(paths, "album1", "name_asc", "0", "60", "photo")

    assert first_page["total"] == 1000
    assert first_page["items"][0]["name"] == "image-0999.jpg"
    assert sorted_page["items"][0]["name"] == "image-0120.jpg"
    assert filtered_page["media_counts"]["image"] == 1000


def test_first_scan_reuses_legacy_index_metadata_without_ffprobe(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    stat = video_path.stat()
    legacy_id = "legacy-video-id"
    save_photo_index(paths, {
        "photos": {
            legacy_id: {
                "id": legacy_id,
                "album_id": "album1",
                "relative_path": "clip.mp4",
                "name": "clip.mp4",
                "media_type": MEDIA_TYPE_VIDEO,
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
                "size": stat.st_size,
                "width": 1920,
                "height": 1080,
                "duration": 12.5,
                "video_codec": "h264",
                "audio_codec": "aac",
                "bitrate": 6000000,
            },
        },
    })
    os.remove(getattr(paths, "photo_album_index_folder") + "/album1.json")

    def fail_probe(_path):
        raise AssertionError("unchanged legacy video metadata should avoid ffprobe")

    monkeypatch.setattr("backend.services.photo_gallery.probe_video_metadata", fail_probe)
    media_items, status, error = scan_photo_album(paths, {"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True})
    index_data = load_album_index(paths, "album1")

    assert status == "idle"
    assert error is None
    assert len(media_items) == 1
    assert media_items[0]["id"] == make_photo_id("album1", "clip.mp4")
    assert media_items[0]["duration"] == 12.5
    assert media_items[0]["width"] == 1920
    assert index_data["media"][media_items[0]["id"]]["video_codec"] == "h264"
    assert not os.path.exists(paths.photo_index_file)
    assert os.path.exists(f"{paths.photo_index_file}.bak")


def test_scan_after_legacy_archive_does_not_rebuild_global_index(config_file, workspace, monkeypatch):
    album_one_dir = workspace / "album-one"
    album_two_dir = workspace / "album-two"
    album_one_dir.mkdir()
    album_two_dir.mkdir()
    album_one_photo = album_one_dir / "image.jpg"
    album_two_photo = album_two_dir / "fresh.jpg"
    album_one_photo.write_bytes(b"old")
    album_two_photo.write_bytes(b"new")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [
                {"id": "album1", "name": "Album One", "path": str(album_one_dir), "enabled": True},
                {"id": "album2", "name": "Album Two", "path": str(album_two_dir), "enabled": True},
            ],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    album_one_meta = photo_meta_from_path({"id": "album1", "path": str(album_one_dir)}, str(album_one_photo))
    save_photo_index(paths, {"photos": {album_one_meta["id"]: album_one_meta}})
    os.replace(paths.photo_index_file, f"{paths.photo_index_file}.bak")

    def fail_load_index(_paths):
        raise AssertionError("scan after legacy archive must not rebuild a global index")

    monkeypatch.setattr("backend.services.photo_gallery.load_photo_index", fail_load_index)
    media_items, status, error = scan_photo_album(
        paths,
        {"id": "album2", "name": "Album Two", "path": str(album_two_dir), "enabled": True},
    )

    assert status == "idle"
    assert error is None
    assert [item["id"] for item in media_items] == [make_photo_id("album2", "fresh.jpg")]
    assert os.path.exists(f"{paths.photo_index_file}.bak")
    assert not os.path.exists(paths.photo_index_file)


def test_album_list_migrates_once_and_avoids_legacy_rebuild(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    photo_path = album_dir / "image.jpg"
    photo_path.write_bytes(b"fake-image")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})

    # 模拟升级前的 workspace：仅保留旧全局 index.json，移除镜像出的每相册索引与 catalog
    stat = photo_path.stat()
    save_photo_index(paths, {
        "photos": {
            "legacy-image-id": {
                "id": "legacy-image-id",
                "album_id": "album1",
                "relative_path": "image.jpg",
                "name": "image.jpg",
                "media_type": MEDIA_TYPE_IMAGE,
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
                "size": stat.st_size,
                "width": 800,
                "height": 600,
            },
        },
    })
    os.remove(f"{paths.photo_album_index_folder}/album1.json")
    if os.path.exists(paths.photo_catalog_file):
        os.remove(paths.photo_catalog_file)

    # 首次列表触发一次性迁移：折算 catalog 并归档旧索引
    albums = list_photo_album_responses(paths)
    assert len(albums) == 1
    assert albums[0]["media_count"] == 1
    assert albums[0]["scan_status"] == "stale"
    assert not os.path.exists(paths.photo_index_file)
    assert os.path.exists(f"{paths.photo_index_file}.bak")

    # 迁移后再次请求列表不得回退去重建式读取旧索引（避免 O(N^2) 读放大）
    def fail_load_index(_paths):
        raise AssertionError("list must not rebuild from legacy index after migration")

    monkeypatch.setattr("backend.services.photo_gallery.load_photo_index", fail_load_index)
    albums_again = list_photo_album_responses(paths)
    assert len(albums_again) == 1
    assert albums_again[0]["scan_status"] == "stale"


def test_photo_gallery_cache_stats_and_clear_do_not_delete_originals(config_file, workspace):
    album_dir = workspace / "album"
    album_dir.mkdir()
    photo_path = album_dir / "image.jpg"
    photo_path.write_bytes(b"original")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
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
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(photo_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})
    os.makedirs(paths.photo_thumbnail_folder, exist_ok=True)
    thumb_path = os.path.join(paths.photo_thumbnail_folder, get_photo_thumbnail_filename(meta["id"], meta))
    with open(thumb_path, "wb") as f:
        f.write(b"thumb")

    stats = get_photo_gallery_cache_stats(paths)
    payload, status_code = clear_photo_gallery_cache(paths, "generated")

    assert stats["total"]["files"] >= 2
    assert status_code == 200
    assert payload["success"] is True
    assert payload["removed"]["files"] >= 2
    assert photo_path.exists()
    assert list(album_dir.iterdir()) == [photo_path]


def test_task_manager_enqueue_and_cancel_without_worker(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths)
    input_path = workspace / "inputs" / "photo.jpg"
    input_path.parent.mkdir()
    input_path.write_bytes(b"fake")

    task = task_manager.enqueue_file(str(input_path), "photo.jpg")
    payload, status_code = task_manager.cancel_task(task["id"])
    tasks, has_active = task_manager.list_tasks()

    assert status_code == 200
    assert payload["success"] is True
    assert tasks[0]["status"] == "cancelled"
    assert has_active is False


def test_task_manager_cancel_processing_terminates_process(workspace):
    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def terminate(self):
            self.terminated = True

    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths)
    fake_process = FakeProcess()
    task_manager.task_status["running-task"] = {
        "id": "running-task",
        "kind": "image_sharp",
        "filename": "photo.jpg",
        "status": "processing",
        "created_at": 1,
        "error": None,
    }
    task_manager.running_processes["running-task"] = fake_process

    payload, status_code = task_manager.cancel_task("running-task")

    assert status_code == 200
    assert payload["success"] is True
    assert fake_process.terminated is True
    assert task_manager.task_status["running-task"]["status"] == "cancelled"


def make_video_task(paths, workspace, **overrides):
    source_path = workspace / "album" / "clip.mp4"
    source_path.parent.mkdir(exist_ok=True)
    source_path.write_bytes(b"video")
    task = {
        "id": "video-task",
        "kind": "video_3dgs",
        "filename": "clip.ply",
        "status": "pending",
        "created_at": 1,
        "source_media_id": "album_clip",
        "source_name": "clip.mp4",
        "source_video_path": str(source_path),
        "mode": "auto",
        "quality": "preview",
        "engine": "auto",
        "resolved_engine": "stable",
        "output_name": "clip",
        "output_path": os.path.join(paths.output_folder, "clip.ply"),
        "spz_path": os.path.join(paths.output_folder, "clip.spz"),
        "keep_intermediate_files": False,
        "details": {"warnings": [], "logs": []},
        "error": None,
    }
    task.update(overrides)
    return task


def test_video_task_creation_writes_source_metadata(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})
    monkeypatch.setattr("backend.services.video_reconstruction.check_dependencies", lambda: {
        "required": {"available": True, "tools": [], "message": None},
        "stable": {"available": True, "tools": [], "message": None},
        "summary": {
            "available": True,
            "stable_available": True,
        },
    })

    task, error, status_code = video_reconstruction.build_video_task(paths, {
        "video_id": meta["id"],
        "mode": "auto",
        "quality": "high",
        "engine": "auto",
        "vram_budget": "12gb",
        "keep_intermediate_files": False,
        "output_name": "",
    })

    assert error is None
    assert status_code == 200
    metadata = model_gallery.read_model_metadata(paths, task["output_name"])
    assert metadata["source_media_type"] == "video"
    assert metadata["source_media_id"] == meta["id"]
    assert metadata["source_name"] == "clip.mp4"


def test_gallery_backfills_legacy_video_metadata_from_unique_source(config_file, workspace, monkeypatch):
    album_dir = workspace / "album"
    album_dir.mkdir()
    video_path = album_dir / "clip.mp4"
    video_path.write_bytes(b"video")
    write_config(
        config_file,
        {
            "workspace_folder": str(workspace),
            "photo_gallery_roots": [{"id": "album1", "name": "Album", "path": str(album_dir), "enabled": True}],
        },
    )
    paths = build_path_context({"workspace_folder": str(workspace)})
    meta = photo_meta_from_path({"id": "album1", "path": str(album_dir)}, str(video_path))
    save_photo_index(paths, {"photos": {meta["id"]: meta}})
    os.makedirs(paths.output_folder, exist_ok=True)
    with open(os.path.join(paths.output_folder, "clip-2.ply"), "wb") as f:
        f.write(b"ply")

    def fake_generate_video_thumbnail(paths_arg, _source_path, item_id):
        thumb_path = model_gallery.get_thumbnail_path(paths_arg, item_id)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"jpg")
        return thumb_path

    monkeypatch.setattr(
        "backend.services.model_gallery.generate_video_thumbnail",
        fake_generate_video_thumbnail,
    )

    item = model_gallery.build_gallery_item(paths, "clip-2.ply", repair_missing_thumbnail=True)

    assert item["thumb_url"] == "/api/thumbnail/clip-2"
    assert item["source_video_url"] == "/api/gallery/clip-2/source-video"
    metadata = model_gallery.read_model_metadata(paths, "clip-2")
    assert metadata["source_media_type"] == "video"
    assert metadata["source_media_id"] == meta["id"]
    assert metadata["recovered_from"] == "gallery-video-stem"


def test_video_reconstruction_service_success_and_spz_failure(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths, spz_converter=lambda *_args: (_ for _ in ()).throw(RuntimeError("spz boom")))
    task = make_video_task(paths, workspace)
    task_manager.task_status[task["id"]] = task

    def fake_generate_video_thumbnail(paths_arg, _source_path, item_id):
        thumb_path = model_gallery.get_thumbnail_path(paths_arg, item_id)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"jpg")
        return thumb_path

    def fake_run_command(_manager, _task_id, cmd, **_kwargs):
        if cmd[0] == "ns-train":
            train_dir = cmd[cmd.index("--output-dir") + 1]
            os.makedirs(train_dir, exist_ok=True)
            with open(os.path.join(train_dir, "config.yml"), "w", encoding="utf-8") as f:
                f.write("config")
        if cmd[0] == "ns-export":
            export_dir = cmd[-1]
            os.makedirs(export_dir, exist_ok=True)
            with open(os.path.join(export_dir, "model.ply"), "wb") as f:
                f.write(b"ply")
        return 0, [], False

    monkeypatch.setattr("backend.services.video_reconstruction.run_command", fake_run_command)
    monkeypatch.setattr(
        "backend.services.model_gallery.generate_video_thumbnail",
        fake_generate_video_thumbnail,
    )

    video_reconstruction.run_video_reconstruction_task(task_manager, task["id"], task)
    public_task = task_manager.list_tasks()[0][0]

    assert public_task["status"] == "completed"
    assert public_task["stage"] == "video_done"
    assert public_task["error_code"] == "video_reconstruction_spz_failed"
    assert os.path.exists(task["output_path"])
    metadata = model_gallery.read_model_metadata(paths, "clip")
    assert metadata["source_media_type"] == "video"
    assert metadata["source_media_id"] == "album_clip"
    assert metadata["source_name"] == "clip.mp4"
    item = model_gallery.build_gallery_item(paths, "clip.ply")
    assert item["thumb_url"] == "/api/thumbnail/clip"
    assert item["source_video_url"] == "/api/gallery/clip/source-video"
    assert not os.path.exists(os.path.join(paths.video_reconstruction_jobs_folder, task["id"]))


def test_video_reconstruction_retries_viewer_failure_with_tensorboard(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})

    def fake_spz_converter(_source_path, spz_path):
        with open(spz_path, "wb") as f:
            f.write(b"spz")

    task_manager = TaskManager(paths=paths, spz_converter=fake_spz_converter)
    task = make_video_task(paths, workspace, mode="environment")
    task_manager.task_status[task["id"]] = task
    visualizers = []

    def fake_generate_video_thumbnail(paths_arg, _source_path, item_id):
        thumb_path = model_gallery.get_thumbnail_path(paths_arg, item_id)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"jpg")
        return thumb_path

    def fake_run_command(_manager, _task_id, cmd, **_kwargs):
        if cmd[0] == "ns-train":
            visualizer = cmd[cmd.index("--vis") + 1]
            train_dir = cmd[cmd.index("--output-dir") + 1]
            visualizers.append(visualizer)
            stale_marker = os.path.join(train_dir, "partial-viewer-start")
            if visualizer == "viewer":
                os.makedirs(train_dir, exist_ok=True)
                with open(stale_marker, "w", encoding="utf-8") as f:
                    f.write("partial")
                return 1, [
                    "File \"nerfstudio\\viewer\\viewer.py\", line 114, in __init__\n",
                    "self.viser_server = viser.ViserServer(host=config.websocket_host, port=websocket_port)\n",
                    "File \"viser\\_client_autobuild.py\", line 41, in ensure_client_is_built\n",
                    "psutil.NoSuchProcess: process no longer exists (pid=34908)\n",
                ], False
            assert visualizer == "tensorboard"
            assert not os.path.exists(stale_marker)
            os.makedirs(train_dir, exist_ok=True)
            with open(os.path.join(train_dir, "config.yml"), "w", encoding="utf-8") as f:
                f.write("config")
        if cmd[0] == "ns-export":
            export_dir = cmd[-1]
            os.makedirs(export_dir, exist_ok=True)
            with open(os.path.join(export_dir, "model.ply"), "wb") as f:
                f.write(b"ply")
        return 0, [], False

    monkeypatch.setattr("backend.services.video_reconstruction.run_command", fake_run_command)
    monkeypatch.setattr(
        "backend.services.model_gallery.generate_video_thumbnail",
        fake_generate_video_thumbnail,
    )

    video_reconstruction.run_video_reconstruction_task(task_manager, task["id"], task)
    public_task = task_manager.list_tasks()[0][0]

    assert visualizers == ["viewer", "tensorboard"]
    assert public_task["status"] == "completed"
    assert task["details"]["train_visualizer_fallback"] == {
        "from": "viewer",
        "to": "tensorboard",
        "reason": "viser_startup_failed",
    }
    assert any(
        warning["code"] == "video_reconstruction_viewer_disabled"
        for warning in public_task["details"]["warnings"]
    )
    assert os.path.exists(task["output_path"])
    assert os.path.exists(task["spz_path"])


def test_video_reconstruction_service_oom_failure_keeps_no_output(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    task_manager = TaskManager(paths=paths)
    task = make_video_task(paths, workspace)
    task_manager.task_status[task["id"]] = task

    monkeypatch.setattr(
        "backend.services.video_reconstruction.run_command",
        lambda *_args, **_kwargs: (1, ["RuntimeError: CUDA out of memory\n"], False),
    )

    video_reconstruction.run_video_reconstruction_task(task_manager, task["id"], task)
    public_task = task_manager.list_tasks()[0][0]

    assert public_task["status"] == "failed"
    assert public_task["error_code"] == "video_reconstruction_oom"
    assert "GPU memory" in public_task["error"]
    assert not os.path.exists(task["output_path"])


def test_video_reconstruction_failure_cleans_uploaded_source_and_prepared_assets(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    upload_dir = os.path.join(model_gallery.get_video_uploads_folder(paths), "upload-failed")
    os.makedirs(upload_dir, exist_ok=True)
    uploaded_video = os.path.join(upload_dir, "clip.mp4")
    with open(uploaded_video, "wb") as f:
        f.write(b"uploaded")

    task_manager = TaskManager(paths=paths)
    task = make_video_task(
        paths,
        workspace,
        source_media_id=None,
        source_video_path=uploaded_video,
        source_mime_type="video/mp4",
    )
    task_manager.task_status[task["id"]] = task
    model_gallery.write_model_metadata(paths, task["output_name"], video_reconstruction.build_video_model_metadata(task))
    thumb_path = model_gallery.get_thumbnail_path(paths, task["output_name"])
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    with open(thumb_path, "wb") as f:
        f.write(b"jpg")
    os.makedirs(paths.output_folder, exist_ok=True)
    with open(task["output_path"], "wb") as f:
        f.write(b"partial")

    monkeypatch.setattr(
        "backend.services.video_reconstruction.run_command",
        lambda *_args, **_kwargs: (1, ["RuntimeError: CUDA out of memory\n"], False),
    )

    video_reconstruction.run_video_reconstruction_task(task_manager, task["id"], task)
    public_task = task_manager.list_tasks()[0][0]

    assert public_task["status"] == "failed"
    assert not os.path.exists(uploaded_video)
    assert not os.path.exists(upload_dir)
    assert not os.path.exists(model_gallery.get_model_metadata_path(paths, task["output_name"]))
    assert not os.path.exists(thumb_path)
    assert not os.path.exists(task["output_path"])


def test_video_reconstruction_service_cancel_cleans_job_and_uploaded_source(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    upload_dir = os.path.join(model_gallery.get_video_uploads_folder(paths), "upload-cancelled")
    os.makedirs(upload_dir, exist_ok=True)
    uploaded_video = os.path.join(upload_dir, "clip.mp4")
    with open(uploaded_video, "wb") as f:
        f.write(b"uploaded")

    task_manager = TaskManager(paths=paths)
    task = make_video_task(paths, workspace, source_media_id=None, source_video_path=uploaded_video)
    task_manager.task_status[task["id"]] = task

    def fake_cancel(_manager, _task_id, *_args, **_kwargs):
        task_manager.task_status[task["id"]]["status"] = "cancelled"
        return 143, ["terminated\n"], False

    monkeypatch.setattr("backend.services.video_reconstruction.run_command", fake_cancel)

    video_reconstruction.run_video_reconstruction_task(task_manager, task["id"], task)
    public_task = task_manager.list_tasks()[0][0]

    assert public_task["status"] == "cancelled"
    assert not os.path.exists(os.path.join(paths.video_reconstruction_jobs_folder, task["id"]))
    assert not os.path.exists(uploaded_video)
    assert not os.path.exists(upload_dir)


def test_video_reconstruction_startup_cleanup_removes_orphans_but_keeps_referenced_uploads(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    stale_job = os.path.join(paths.video_reconstruction_jobs_folder, "stale-task")
    os.makedirs(stale_job, exist_ok=True)
    with open(os.path.join(stale_job, "partial.txt"), "w", encoding="utf-8") as f:
        f.write("partial")

    upload_root = model_gallery.get_video_uploads_folder(paths)
    orphan_dir = os.path.join(upload_root, "orphan")
    referenced_dir = os.path.join(upload_root, "referenced")
    os.makedirs(orphan_dir, exist_ok=True)
    os.makedirs(referenced_dir, exist_ok=True)
    orphan_video = os.path.join(orphan_dir, "clip.mp4")
    referenced_video = os.path.join(referenced_dir, "clip.mp4")
    with open(orphan_video, "wb") as f:
        f.write(b"orphan")
    with open(referenced_video, "wb") as f:
        f.write(b"referenced")

    os.makedirs(paths.output_folder, exist_ok=True)
    with open(os.path.join(paths.output_folder, "kept.ply"), "wb") as f:
        f.write(b"ply")
    model_gallery.write_model_metadata(paths, "kept", {
        "generator": video_reconstruction.TASK_KIND_VIDEO_3DGS,
        "source_video_path": referenced_video,
    })
    model_gallery.write_model_metadata(paths, "unfinished", {
        "generator": video_reconstruction.TASK_KIND_VIDEO_3DGS,
        "source_video_path": orphan_video,
    })

    summary = video_reconstruction.cleanup_stale_runtime_artifacts(paths, terminate_processes=False)

    assert summary["jobs_removed"] == 1
    assert summary["uploads_removed"] == 1
    assert summary["sidecars_removed"] == 1
    assert not os.path.exists(stale_job)
    assert not os.path.exists(orphan_dir)
    assert os.path.exists(referenced_video)
    assert os.path.exists(model_gallery.get_model_metadata_path(paths, "kept"))
    assert not os.path.exists(model_gallery.get_model_metadata_path(paths, "unfinished"))


def test_video_reconstruction_upload_cleanup_can_keep_recent_orphans(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    upload_dir = os.path.join(model_gallery.get_video_uploads_folder(paths), "recent")
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, "clip.mp4"), "wb") as f:
        f.write(b"recent")

    removed = video_reconstruction.cleanup_orphan_video_uploads(paths, stale_age_seconds=3600)

    assert removed == 0
    assert os.path.exists(upload_dir)


def test_video_reconstruction_process_matcher_requires_tool_and_workspace(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    job_db = os.path.join(paths.video_reconstruction_jobs_folder, "task", "database.db")

    assert video_reconstruction.process_info_matches_video_runtime(
        {"name": "colmap.exe", "cmdline": ["colmap", "mapper", "--database_path", job_db], "cwd": None},
        paths.video_reconstruction_folder,
    )
    assert video_reconstruction.process_info_matches_video_runtime(
        {"name": "python.exe", "cmdline": ["python", "ns-train", "--output-dir", job_db], "cwd": None},
        paths.video_reconstruction_folder,
    )
    assert not video_reconstruction.process_info_matches_video_runtime(
        {"name": "colmap.exe", "cmdline": ["colmap", "mapper", "--database_path", r"C:\other\database.db"], "cwd": None},
        paths.video_reconstruction_folder,
    )
    assert not video_reconstruction.process_info_matches_video_runtime(
        {"name": "python.exe", "cmdline": ["python", "script.py", job_db], "cwd": None},
        paths.video_reconstruction_folder,
    )


def test_build_failure_message_detects_oom_text():
    oom_code, oom_message = video_reconstruction.build_failure_message(
        1,
        ["epoch 1\n", "RuntimeError: CUDA out of memory. Tried to allocate 2GiB\n"],
    )
    plain_code, plain_message = video_reconstruction.build_failure_message(
        2,
        ["generic failure line\n"],
    )

    assert oom_code == video_reconstruction.ERROR_OOM
    assert "GPU memory" in oom_message
    assert plain_code is None
    assert "generic failure line" in plain_message


def test_viewer_startup_failure_triggers_tensorboard_retry():
    output_lines = [
        "File \"nerfstudio\\viewer\\viewer.py\", line 114, in __init__\n",
        "self.viser_server = viser.ViserServer(host=config.websocket_host, port=websocket_port)\n",
        "File \"viser\\_client_autobuild.py\", line 41, in ensure_client_is_built\n",
        "psutil.NoSuchProcess: process no longer exists (pid=34908)\n",
    ]

    assert video_reconstruction.is_viewer_startup_failure(output_lines) is True
    assert video_reconstruction.should_retry_train_without_viewer("viewer", output_lines) is True
    assert video_reconstruction.should_retry_train_without_viewer("tensorboard", output_lines) is False


def test_contains_oom_matches_known_patterns():
    assert video_reconstruction.contains_oom("CUDA out of memory") is True
    assert video_reconstruction.contains_oom("torch.OutOfMemoryError raised") is True
    assert video_reconstruction.contains_oom("training finished cleanly") is False


def test_resolve_engine_strategy_covers_fallbacks():
    stable_only = {
        "stable": {"available": True},
    }
    none_available = {
        "stable": {"available": False},
    }

    assert video_reconstruction.resolve_engine_strategy("auto", stable_only) == ("stable", None)
    assert video_reconstruction.resolve_engine_strategy("stable", stable_only) == ("stable", None)
    assert video_reconstruction.resolve_engine_strategy("unsupported", stable_only) == (
        None,
        video_reconstruction.ERROR_INVALID_REQUEST,
    )
    assert video_reconstruction.resolve_engine_strategy("auto", none_available) == (
        None,
        video_reconstruction.ERROR_DEPENDENCY_MISSING,
    )


def test_parse_training_progress_maps_steps_into_optimize_band():
    profile = {"max_num_iterations": 30000}
    base = video_reconstruction.STAGE_PROGRESS["video_optimize"]
    ceiling = video_reconstruction.STAGE_PROGRESS["video_export"]

    midpoint = video_reconstruction.parse_training_progress("Step 15000 / 30000 ...", profile)
    percent_row = video_reconstruction.parse_training_progress("2980 (50.00%)", profile)
    near_end = video_reconstruction.parse_training_progress("progress 30000/30000 done", profile)
    unrelated = video_reconstruction.parse_training_progress("loaded 5/10 images", profile)
    no_match = video_reconstruction.parse_training_progress("starting trainer", profile)

    assert midpoint == int(base + (ceiling - base) * 0.5)
    assert percent_row == int(base + (ceiling - base) * 0.5)
    assert near_end == ceiling
    assert base < midpoint < ceiling
    assert unrelated is None
    assert no_match is None


def test_delete_uploaded_source_video_protects_album_originals(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})

    # Album-sourced model: source_media_id present, original must never be removed.
    album_dir = workspace / "album"
    album_dir.mkdir()
    album_video = album_dir / "clip.mp4"
    album_video.write_bytes(b"album-video")
    model_gallery.delete_uploaded_source_video(paths, {
        "source_media_id": "album_clip",
        "source_video_path": str(album_video),
    })
    assert album_video.exists()

    # Path outside the controlled uploads folder must be ignored.
    stray = workspace / "stray.mp4"
    stray.write_bytes(b"stray")
    model_gallery.delete_uploaded_source_video(paths, {
        "source_media_id": None,
        "source_video_path": str(stray),
    })
    assert stray.exists()

    # Uploaded cache copy must be deleted along with its now-empty job folder.
    upload_root = model_gallery.get_video_uploads_folder(paths)
    upload_dir = os.path.join(upload_root, "upload-123")
    os.makedirs(upload_dir, exist_ok=True)
    uploaded_video = os.path.join(upload_dir, "clip.mp4")
    with open(uploaded_video, "wb") as f:
        f.write(b"uploaded")
    model_gallery.delete_uploaded_source_video(paths, {
        "source_media_id": None,
        "source_video_path": uploaded_video,
    })
    assert not os.path.exists(uploaded_video)
    assert not os.path.exists(upload_dir)


def test_parse_viewer_url_extracts_local_viewer():
    assert video_reconstruction.parse_viewer_url("│   HTTP   │ http://0.0.0.0:7007 │") == (
        "http://localhost:7007",
        7007,
    )
    assert video_reconstruction.parse_viewer_url(
        "Viewer running locally at: http://localhost:7007"
    ) == ("http://localhost:7007", 7007)
    display_url, port = video_reconstruction.parse_viewer_url(
        "https://viewer.nerf.studio/?websocket_url=ws://localhost:7007"
    )
    assert display_url.startswith("https://viewer.nerf.studio")
    assert video_reconstruction.parse_viewer_url("loss=0.123 step done") == (None, None)


def test_resolve_training_profile_falls_back_to_random_when_few_cameras(tmp_path):
    data_dir = tmp_path / "nerfstudio-data"
    data_dir.mkdir()
    fps_profile = {"train_cameras_sampling_strategy": "fps"}

    # Too few registered cameras -> random sampling to avoid FPS assertion.
    (data_dir / "transforms.json").write_text(
        json.dumps({"frames": [{} for _ in range(5)]}),
        encoding="utf-8",
    )
    task = {"details": {}}
    few = video_reconstruction.resolve_training_profile(fps_profile, str(data_dir), task=task)
    assert few["train_cameras_sampling_strategy"] == "random"
    assert task["details"]["camera_sampling_fallback"]["registered_frames"] == 5

    # Enough cameras -> keep FPS unchanged.
    (data_dir / "transforms.json").write_text(
        json.dumps({"frames": [{} for _ in range(40)]}),
        encoding="utf-8",
    )
    plenty = video_reconstruction.resolve_training_profile(fps_profile, str(data_dir))
    assert plenty["train_cameras_sampling_strategy"] == "fps"

    # Missing transforms.json -> leave profile as-is (don't guess).
    missing = video_reconstruction.resolve_training_profile(fps_profile, str(tmp_path / "nope"))
    assert missing["train_cameras_sampling_strategy"] == "fps"


def test_quality_profiles_bind_matching_method_per_tier():
    assert video_reconstruction.resolve_quality_profile("preview", "12gb")["matching_method"] == "sequential"
    assert video_reconstruction.resolve_quality_profile("high", "12gb")["matching_method"] == "exhaustive"
    assert video_reconstruction.resolve_quality_profile("extreme", "24gb")["matching_method"] == "exhaustive"
    assert video_reconstruction.resolve_quality_profile(
        "custom",
        "12gb",
        {"matching_method": "sequential"},
    )["matching_method"] == "sequential"


def test_estimate_object_focus_from_orbit_geometry(tmp_path):
    import math

    import numpy as np

    data_dir = tmp_path / "nerfstudio-data"
    train_dir = tmp_path / "train"
    data_dir.mkdir()
    (train_dir / "run").mkdir(parents=True)

    # 12 cameras orbiting the origin at radius 4, all looking inward (-Z is look-at).
    frames = []
    for i in range(12):
        angle = 2 * math.pi * i / 12
        cam = np.array([4.0 * math.cos(angle), 0.0, 4.0 * math.sin(angle)])
        forward = -cam / np.linalg.norm(cam)  # look toward origin
        z_axis = -forward                      # OpenGL camera +Z points back
        up = np.array([0.0, 1.0, 0.0])
        x_axis = np.cross(up, z_axis)
        x_axis /= np.linalg.norm(x_axis)
        y_axis = np.cross(z_axis, x_axis)
        c2w = np.eye(4)
        c2w[:3, 0] = x_axis
        c2w[:3, 1] = y_axis
        c2w[:3, 2] = z_axis
        c2w[:3, 3] = cam
        frames.append({"transform_matrix": c2w.tolist()})
    (data_dir / "transforms.json").write_text(json.dumps({"frames": frames}), encoding="utf-8")

    # Identity dataparser transform (no reorientation) with unit scale.
    (train_dir / "run" / "dataparser_transforms.json").write_text(
        json.dumps({"transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], "scale": 1.0}),
        encoding="utf-8",
    )

    result = video_reconstruction.estimate_object_focus(str(train_dir), str(data_dir))

    assert result is not None
    center, radius = result
    assert np.allclose(center, [0.0, 0.0, 0.0], atol=1e-6)
    assert radius == 4.0 * video_reconstruction.OBJECT_FOCUS["radius_factor"]


def test_estimate_object_focus_returns_none_without_dataparser(tmp_path):
    data_dir = tmp_path / "nerfstudio-data"
    train_dir = tmp_path / "train"
    data_dir.mkdir()
    train_dir.mkdir()
    (data_dir / "transforms.json").write_text(
        json.dumps({"frames": [{"transform_matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}] * 12}),
        encoding="utf-8",
    )

    # No dataparser_transforms.json -> cannot align coordinates -> skip safely.
    assert video_reconstruction.estimate_object_focus(str(train_dir), str(data_dir)) is None


def test_object_focus_crop_keeps_only_subject(tmp_path):
    import numpy as np
    from plyfile import PlyData, PlyElement

    source_path = tmp_path / "source.ply"
    output_path = tmp_path / "focused.ply"
    dtype = [("x", "f4"), ("y", "f4"), ("z", "f4"), ("opacity", "f4")]
    vertices = np.zeros(400, dtype=dtype)
    # 200 subject points clustered near origin, 200 environment points far on +X.
    vertices["x"][:200] = np.linspace(-0.3, 0.3, 200)
    vertices["x"][200:] = np.linspace(8.0, 12.0, 200)
    vertices["opacity"] = 3.0
    PlyData([PlyElement.describe(vertices, "vertex")], text=False).write(source_path)

    stats = video_reconstruction.clean_gaussian_splat_ply(
        source_path,
        output_path,
        profile={**video_reconstruction.FOCUSED_CLEANUP_PROFILE, "min_vertices": 10, "min_keep_ratio": 0.25},
        object_focus=(np.array([0.0, 0.0, 0.0]), 1.0),
    )
    cleaned = PlyData.read(output_path)["vertex"].data

    assert stats["object_focus_applied"] is True
    assert cleaned["x"].max() < 1.0
    assert stats["output_vertices"] < stats["input_vertices"]

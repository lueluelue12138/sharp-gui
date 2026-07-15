import os
import re
from io import BytesIO

from backend.services import model_gallery, task_queue
from backend.services.task_queue import TaskManager


def test_generate_stages_chinese_filename_with_image_extension(client, app):
    response = client.post(
        "/api/generate",
        data={"file": (BytesIO(b"fake-jpeg"), "测试图片.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    public_task = response.get_json()["tasks"][0]
    assert public_task["filename"] == "测试图片.jpg"

    stored_task = app.config["TASK_MANAGER"].task_status[public_task["id"]]
    assert re.fullmatch(r"img-[0-9a-f]{32}\.jpg", stored_task["input_filename"])
    assert os.path.basename(stored_task["input_path"]) == stored_task["input_filename"]
    assert os.path.exists(stored_task["input_path"])
    model_id = os.path.splitext(stored_task["input_filename"])[0]
    metadata = model_gallery.read_model_metadata(app.config["PATH_CONTEXT"], model_id)
    assert metadata["display_name"] == "测试图片"
    assert metadata["source_name"] == "测试图片.jpg"
    assert metadata["generation_status"] == "pending"

    second_response = client.post(
        "/api/generate",
        data={"file": (BytesIO(b"second-jpeg"), "测试图片.jpg")},
        content_type="multipart/form-data",
    )
    second_task = app.config["TASK_MANAGER"].task_status[
        second_response.get_json()["tasks"][0]["id"]
    ]
    assert second_task["model_id"] != stored_task["model_id"]

    _, status_code = app.config["TASK_MANAGER"].cancel_task(second_task["id"])
    second_metadata = model_gallery.read_model_metadata(
        app.config["PATH_CONTEXT"], second_task["model_id"]
    )
    assert status_code == 200
    assert second_metadata["generation_status"] == "cancelled"


def test_image_worker_uses_ascii_staged_filename_for_chinese_display_name(workspace, monkeypatch):
    class FakeStdout:
        def readline(self):
            return ""

        def close(self):
            pass

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStdout()

        def wait(self):
            return 0

    paths = type("Paths", (), {
        "workspace_folder": str(workspace),
        "input_folder": str(workspace / "inputs"),
        "output_folder": str(workspace / "outputs"),
        "thumbnail_folder": str(workspace / "inputs" / ".thumbnails"),
        "video_reconstruction_folder": str(workspace / ".video-reconstruction"),
    })()
    os.makedirs(paths.input_folder)
    os.makedirs(paths.output_folder)
    model_id = "img-0123456789abcdef0123456789abcdef"
    input_filename = f"{model_id}.jpg"
    input_path = os.path.join(paths.input_folder, input_filename)
    with open(input_path, "wb") as file:
        file.write(b"fake-jpeg")
    with open(os.path.join(paths.output_folder, f"{model_id}.ply"), "wb") as file:
        file.write(b"fake-ply")

    captured_commands = []
    monkeypatch.setattr(
        task_queue.subprocess,
        "Popen",
        lambda command, **_kwargs: captured_commands.append(command) or FakeProcess(),
    )
    manager = TaskManager(
        paths=paths,
        sharp_device_selector=lambda: "cpu",
        sharp_command_resolver=lambda: "sharp",
        spz_converter=lambda _path: None,
    )
    public_task = manager.enqueue_file(
        input_path,
        input_filename,
        display_filename="测试图片.jpg",
    )
    manager.task_queue.put(None)

    manager.worker()

    assert captured_commands[0][3] == input_path
    assert manager.task_status[public_task["id"]]["status"] == "completed"
    metadata = model_gallery.read_model_metadata(paths, model_id)
    assert metadata["generation_status"] == "completed"
    gallery_item = model_gallery.build_gallery_item(paths, f"{model_id}.ply")
    assert gallery_item["id"] == model_id
    assert gallery_item["name"] == "测试图片"
    assert gallery_item["source_name"] == "测试图片.jpg"


def test_generate_rejects_unsupported_extension(client):
    response = client.post(
        "/api/generate",
        data={"file": (BytesIO(b"not-an-image"), "测试文件.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Unsupported image format"}


def test_missing_output_marks_image_metadata_failed(workspace):
    paths = type("Paths", (), {
        "workspace_folder": str(workspace),
        "input_folder": str(workspace / "inputs"),
        "output_folder": str(workspace / "outputs"),
        "thumbnail_folder": str(workspace / "inputs" / ".thumbnails"),
        "video_reconstruction_folder": str(workspace / ".video-reconstruction"),
    })()
    os.makedirs(paths.input_folder)
    os.makedirs(paths.output_folder)
    model_id = "img-cccccccccccccccccccccccccccccccc"
    input_filename = f"{model_id}.jpg"
    input_path = os.path.join(paths.input_folder, input_filename)
    with open(input_path, "wb") as file:
        file.write(b"fake-jpeg")

    manager = TaskManager(paths=paths, spz_converter=lambda _path: None)
    public_task = manager.enqueue_file(
        input_path,
        input_filename,
        display_filename="测试图片.jpg",
    )
    manager._finish_process(
        public_task["id"],
        input_filename,
        paths.output_folder,
        0,
        [],
    )

    metadata = model_gallery.read_model_metadata(paths, model_id)
    assert manager.task_status[public_task["id"]]["status"] == "failed"
    assert metadata["generation_status"] == "failed"


def test_image_task_is_published_only_after_postprocessing(workspace):
    paths = type("Paths", (), {
        "workspace_folder": str(workspace),
        "input_folder": str(workspace / "inputs"),
        "output_folder": str(workspace / "outputs"),
        "thumbnail_folder": str(workspace / "inputs" / ".thumbnails"),
        "video_reconstruction_folder": str(workspace / ".video-reconstruction"),
    })()
    os.makedirs(paths.input_folder)
    os.makedirs(paths.output_folder)

    model_id = "img-dddddddddddddddddddddddddddddddd"
    input_filename = f"{model_id}.jpg"
    input_path = os.path.join(paths.input_folder, input_filename)
    with open(input_path, "wb") as file:
        file.write(b"fake-jpeg")

    observed_states = []
    manager = None
    task_id = None

    def observe_postprocessing(_ply_path):
        observed_states.append((
            manager.task_status[task_id]["status"],
            model_gallery.read_model_metadata(paths, model_id)["generation_status"],
        ))
        return None

    manager = TaskManager(paths=paths, spz_converter=observe_postprocessing)
    public_task = manager.enqueue_file(
        input_path,
        input_filename,
        display_filename="测试图片.jpg",
    )
    task_id = public_task["id"]
    with manager.task_lock:
        manager.task_status[task_id]["status"] = "processing"
    manager._update_image_metadata_status(task_id, "processing")
    with open(os.path.join(paths.output_folder, f"{model_id}.ply"), "wb") as file:
        file.write(b"fake-ply")

    manager._finish_process(task_id, input_filename, paths.output_folder, 0, [])

    assert observed_states == [("processing", "processing")]
    assert manager.task_status[task_id]["status"] == "completed"
    assert manager.task_status[task_id]["stage"] == "done"
    assert model_gallery.read_model_metadata(paths, model_id)["generation_status"] == "completed"


def test_startup_cleanup_reconciles_only_interrupted_uuid_image_tasks(workspace):
    paths = type("Paths", (), {
        "workspace_folder": str(workspace),
        "input_folder": str(workspace / "inputs"),
        "output_folder": str(workspace / "outputs"),
        "thumbnail_folder": str(workspace / "inputs" / ".thumbnails"),
        "video_reconstruction_folder": str(workspace / ".video-reconstruction"),
    })()
    os.makedirs(paths.input_folder)
    os.makedirs(paths.output_folder)
    os.makedirs(paths.thumbnail_folder)

    orphan_id = "img-11111111111111111111111111111111"
    recovered_id = "img-22222222222222222222222222222222"
    failed_id = "img-33333333333333333333333333333333"
    video_id = "img-44444444444444444444444444444444"

    orphan_input = os.path.join(paths.input_folder, f"{orphan_id}.jpg")
    orphan_thumb = model_gallery.get_thumbnail_path(paths, orphan_id)
    with open(orphan_input, "wb") as file:
        file.write(b"input")
    with open(orphan_thumb, "wb") as file:
        file.write(b"thumb")
    model_gallery.write_model_metadata(paths, orphan_id, {
        "source_media_type": "image",
        "generation_status": "pending",
    })

    recovered_ply = os.path.join(paths.output_folder, f"{recovered_id}.ply")
    with open(recovered_ply, "wb") as file:
        file.write(b"ply")
    model_gallery.write_model_metadata(paths, recovered_id, {
        "source_media_type": "image",
        "generation_status": "processing",
    })
    model_gallery.write_model_metadata(paths, failed_id, {
        "source_media_type": "image",
        "generation_status": "failed",
    })
    model_gallery.write_model_metadata(paths, video_id, {
        "source_media_type": "video",
        "generation_status": "pending",
    })

    summary = model_gallery.cleanup_interrupted_image_tasks(paths)

    assert summary == {"removed": 1, "recovered": 1, "errors": 0}
    assert not os.path.exists(orphan_input)
    assert not os.path.exists(orphan_thumb)
    assert not os.path.exists(model_gallery.get_model_metadata_path(paths, orphan_id))
    assert os.path.exists(recovered_ply)
    assert model_gallery.read_model_metadata(paths, recovered_id)["generation_status"] == "completed"
    assert os.path.exists(model_gallery.get_model_metadata_path(paths, failed_id))
    assert os.path.exists(model_gallery.get_model_metadata_path(paths, video_id))


def test_delete_gallery_item_removes_full_uuid_image_bundle(workspace):
    paths = type("Paths", (), {
        "workspace_folder": str(workspace),
        "input_folder": str(workspace / "inputs"),
        "output_folder": str(workspace / "outputs"),
        "thumbnail_folder": str(workspace / "inputs" / ".thumbnails"),
        "video_reconstruction_folder": str(workspace / ".video-reconstruction"),
    })()
    os.makedirs(paths.input_folder)
    os.makedirs(paths.output_folder)
    os.makedirs(paths.thumbnail_folder)

    model_id = "img-55555555555555555555555555555555"
    asset_paths = [
        os.path.join(paths.input_folder, f"{model_id}.jpg"),
        os.path.join(paths.output_folder, f"{model_id}.ply"),
        os.path.join(paths.output_folder, f"{model_id}.spz"),
        model_gallery.get_thumbnail_path(paths, model_id),
    ]
    for asset_path in asset_paths:
        with open(asset_path, "wb") as file:
            file.write(b"asset")
    metadata_path = model_gallery.write_model_metadata(paths, model_id, {
        "source_media_type": "image",
        "generation_status": "completed",
    })

    model_gallery.delete_gallery_item(paths, model_id)

    assert all(not os.path.exists(asset_path) for asset_path in [*asset_paths, metadata_path])


def test_model_and_original_downloads_use_source_display_name(client, app):
    paths = app.config["PATH_CONTEXT"]
    model_id = "img-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    model_path = os.path.join(paths.output_folder, f"{model_id}.ply")
    image_path = os.path.join(paths.input_folder, f"{model_id}.jpg")
    with open(model_path, "wb") as file:
        file.write(b"fake-ply")
    with open(image_path, "wb") as file:
        file.write(b"fake-jpeg")
    model_gallery.write_model_metadata(
        paths,
        model_id,
        {
            "display_name": "测试图片",
            "source_media_type": "image",
            "source_name": "测试图片.jpg",
        },
    )

    model_response = client.get(f"/api/download/{model_id}?format=ply")
    original_response = client.get(f"/api/original/{model_id}?download=1")

    assert model_response.status_code == 200
    assert "filename*=UTF-8''%E6%B5%8B%E8%AF%95%E5%9B%BE%E7%89%87.ply" in (
        model_response.headers["Content-Disposition"]
    )
    assert original_response.status_code == 200
    assert "filename*=UTF-8''%E6%B5%8B%E8%AF%95%E5%9B%BE%E7%89%87.jpg" in (
        original_response.headers["Content-Disposition"]
    )


def test_export_uses_display_name_for_html_and_download(client, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.export.build_export_html",
        lambda _paths, _model_id, _fmt: (
            {
                "html": "<title>测试图片</title>",
                "format": "spz",
                "model_size": 10,
                "html_size": 24,
                "download_name": "测试图片_share.html",
            },
            None,
            200,
        ),
    )

    response = client.get("/api/export/img-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert response.status_code == 200
    assert response.data == "<title>测试图片</title>".encode("utf-8")
    assert "filename*=UTF-8''%E6%B5%8B%E8%AF%95%E5%9B%BE%E7%89%87_share.html" in (
        response.headers["Content-Disposition"]
    )


def test_model_suffix_id_keeps_unicode_display_and_download_name(client, app):
    paths = app.config["PATH_CONTEXT"]
    model_id = "img-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    with open(os.path.join(paths.output_folder, f"{model_id}.rad"), "wb") as file:
        file.write(b"fake-rad")
    model_gallery.write_model_metadata(
        paths,
        model_id,
        {
            "display_name": "测试图片",
            "source_media_type": "image",
            "source_name": "测试图片.jpg",
        },
    )

    assert model_gallery.get_model_display_name(paths, f"{model_id}.rad") == "测试图片"
    assert model_gallery.make_model_download_name(
        paths,
        f"{model_id}.rad",
        ".rad",
    ) == "测试图片.rad"

    response = client.get(f"/api/download/{model_id}.rad?format=rad")

    assert response.status_code == 200
    assert "filename*=UTF-8''%E6%B5%8B%E8%AF%95%E5%9B%BE%E7%89%87.rad" in (
        response.headers["Content-Disposition"]
    )

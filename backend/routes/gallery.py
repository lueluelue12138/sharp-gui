import os

from flask import Blueprint, current_app, g, jsonify, request, send_from_directory

from backend.services import model_gallery
from backend.services.model_convert import ply_to_spz

bp = Blueprint("gallery", __name__)


def get_paths():
    return current_app.config["PATH_CONTEXT"]


@bp.route("/api/gallery")
def get_gallery():
    return jsonify(model_gallery.list_gallery_items(get_paths()))


@bp.route("/api/generate", methods=["POST"])
def generate():
    """批量接收文件并加入队列。"""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    files = request.files.getlist("file")
    if not files or files[0].filename == "":
        return jsonify({"error": "No selected file"}), 400

    paths = get_paths()
    task_manager = current_app.config["TASK_MANAGER"]
    created_tasks = []

    for uploaded_file in files:
        if uploaded_file:
            original_filename = str(uploaded_file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
            filename = model_gallery.make_unique_image_input_filename(paths, original_filename)
            if not filename:
                return jsonify({"error": "Unsupported image format"}), 400

            input_path = os.path.join(paths.input_folder, filename)
            uploaded_file.save(input_path)

            task_info = task_manager.enqueue_file(
                input_path,
                filename,
                display_filename=original_filename,
            )
            created_tasks.append(task_info)
            print(f"📥 Task added: {original_filename} (ID: {task_info['id']})")

    return jsonify({
        "success": True,
        "message": f"{len(created_tasks)} tasks queued",
        "tasks": created_tasks,
    })


@bp.route("/api/delete/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    """删除图库项目。"""
    try:
        model_gallery.delete_gallery_item(get_paths(), item_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/download/<item_id>")
def download_model(item_id):
    """下载模型文件，支持 ?format=spz|ply 参数。"""
    paths = get_paths()
    fmt = request.args.get("format", "spz")
    filename = model_gallery.resolve_download_model(paths, item_id, fmt)
    if not filename:
        return jsonify({"error": "File not found"}), 404
    extension = os.path.splitext(filename)[1]
    download_name = model_gallery.make_model_download_name(paths, item_id, extension)

    return send_from_directory(
        paths.output_folder,
        filename,
        as_attachment=True,
        download_name=download_name,
    )


@bp.route("/api/original/<item_id>")
def get_original_image(item_id):
    """按图库条目 ID 获取原图，支持 inline 预览和附件下载。"""
    paths = get_paths()
    filename = model_gallery.find_original_image_filename(paths, item_id)
    if not filename:
        return jsonify({"error": "Image not found"}), 404

    download = request.args.get("download", "0").lower() in ("1", "true", "yes")
    download_name = model_gallery.get_original_image_download_name(paths, item_id, filename)
    return send_from_directory(
        paths.input_folder,
        filename,
        as_attachment=download,
        download_name=download_name,
        conditional=True,
        max_age=model_gallery.DEFAULT_FILE_CACHE_SECONDS,
    )


@bp.route("/api/gallery/<item_id>/source-video")
def get_gallery_source_video(item_id):
    """按模型图库条目获取其源视频，支持 inline 播放和附件下载。"""
    paths = get_paths()
    source_video = model_gallery.resolve_gallery_source_video(paths, item_id)
    if not source_video:
        return jsonify({"error": "Source video not found"}), 404

    download = request.args.get("download", "0").lower() in ("1", "true", "yes")
    return send_from_directory(
        os.path.dirname(source_video["path"]),
        os.path.basename(source_video["path"]),
        as_attachment=download,
        download_name=source_video["name"],
        mimetype=source_video.get("mime_type"),
        conditional=True,
        max_age=model_gallery.DEFAULT_FILE_CACHE_SECONDS,
    )


@bp.route("/api/thumbnail/<item_id>")
def get_thumbnail(item_id):
    """按图库条目 ID 获取缩略图。"""
    paths = get_paths()
    thumb_path = model_gallery.ensure_thumbnail_for_item(paths, item_id, allow_generation=True)
    if not thumb_path or not os.path.exists(thumb_path):
        return jsonify({"error": "Thumbnail not found"}), 404

    filename = os.path.basename(thumb_path)
    response = send_from_directory(
        paths.thumbnail_folder,
        filename,
        conditional=True,
        max_age=model_gallery.THUMBNAIL_CACHE_SECONDS,
    )
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.cache_control.public = True
    response.cache_control.max_age = model_gallery.THUMBNAIL_CACHE_SECONDS
    return response


@bp.route("/api/convert-all", methods=["POST"])
def convert_all_to_spz():
    """批量将所有现有 PLY 模型转换为 SPZ 格式。"""
    if not g.is_owner:
        return jsonify({"error": "Only available from localhost"}), 403

    paths = get_paths()
    if not os.path.exists(paths.output_folder):
        return jsonify({"success": True, "converted": 0, "skipped": 0, "failed": 0})

    ply_files = [f for f in os.listdir(paths.output_folder) if f.endswith(".ply")]
    converted = 0
    skipped = 0
    failed = 0

    for ply_filename in ply_files:
        name_without_ext = os.path.splitext(ply_filename)[0]
        ply_path = os.path.join(paths.output_folder, ply_filename)
        spz_path = os.path.join(paths.output_folder, name_without_ext + ".spz")

        if os.path.exists(spz_path):
            skipped += 1
            continue

        try:
            ply_to_spz(ply_path, spz_path)
            ply_size = os.path.getsize(ply_path)
            spz_size = os.path.getsize(spz_path)
            ratio = 100 - spz_size * 100 // ply_size if ply_size > 0 else 0
            print(f"📦 Converted {name_without_ext}: {ply_size/1024:.0f}KB → {spz_size/1024:.0f}KB ({ratio}% smaller)")
            converted += 1
        except Exception as exc:
            print(f"⚠️ Failed to convert {name_without_ext}: {exc}")
            failed += 1

    return jsonify({
        "success": True,
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "total": len(ply_files),
    })

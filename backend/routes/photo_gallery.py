import math
import os
import subprocess

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    request,
    send_file,
    send_from_directory,
    stream_with_context,
)

from backend.services import photo_gallery

bp = Blueprint("photo_gallery", __name__)


def get_paths():
    return current_app.config["PATH_CONTEXT"]


@bp.route("/api/photo-albums", methods=["GET", "POST"])
def photo_albums():
    """照片相册列表与新增配置。"""
    paths = get_paths()
    if request.method == "GET":
        albums = photo_gallery.list_photo_album_responses(paths)
        return jsonify({"albums": albums, "is_local": g.is_owner})

    if not g.is_owner:
        return jsonify({"error": "Photo albums can only be modified from localhost"}), 403

    payload, status_code = photo_gallery.add_photo_album(paths, request.get_json() or {})
    return jsonify(payload), status_code


@bp.route("/api/photo-albums/<album_id>", methods=["DELETE"])
def delete_photo_album(album_id):
    """移除照片相册配置，不删除原始照片。"""
    if not g.is_owner:
        return jsonify({"error": "Photo albums can only be modified from localhost"}), 403

    payload, status_code = photo_gallery.delete_photo_album(get_paths(), album_id)
    return jsonify(payload), status_code


@bp.route("/api/photo-albums/<album_id>/scan", methods=["POST"])
def scan_photo_album_endpoint(album_id):
    """重新扫描照片相册。"""
    if not g.is_owner:
        return jsonify({"error": "Photo albums can only be rescanned from localhost"}), 403

    payload, status_code = photo_gallery.rescan_photo_album(get_paths(), album_id)
    return jsonify(payload), status_code


@bp.route("/api/photo-gallery/cache", methods=["GET", "DELETE"])
def photo_gallery_cache():
    """图库生成缓存统计与清理。"""
    paths = get_paths()
    if request.method == "GET":
        return jsonify(photo_gallery.get_photo_gallery_cache_stats(paths))

    if not g.is_owner:
        return jsonify({"error": "Photo gallery cache can only be managed from localhost"}), 403

    scope = request.args.get("scope")
    if not scope:
        data = request.get_json(silent=True) or {}
        scope = data.get("scope", "generated")
    payload, status_code = photo_gallery.clear_photo_gallery_cache(paths, scope)
    return jsonify(payload), status_code


@bp.route("/api/photo-albums/<album_id>/photos")
def get_photo_album_photos(album_id):
    """分页获取相册媒体。"""
    payload, status_code = photo_gallery.list_album_photos(
        get_paths(),
        album_id,
        request.args.get("sort", "mtime_desc"),
        request.args.get("cursor", "0"),
        request.args.get("limit", str(photo_gallery.PHOTO_DEFAULT_PAGE_SIZE)),
        request.args.get("type", photo_gallery.MEDIA_TYPE_ALL),
        request.args.get("snapshot"),
    )
    return jsonify(payload), status_code


@bp.route("/api/photo-thumbnail/<photo_id>")
def get_photo_thumbnail(photo_id):
    """获取照片缩略图。"""
    paths = get_paths()
    thumb_path = photo_gallery.ensure_photo_thumbnail(paths, photo_id)
    if not thumb_path or not os.path.exists(thumb_path):
        return jsonify({"error": "Thumbnail not found"}), 404

    filename = os.path.basename(thumb_path)
    response = send_from_directory(
        paths.photo_thumbnail_folder,
        filename,
        conditional=True,
        max_age=photo_gallery.PHOTO_THUMBNAIL_CACHE_SECONDS,
    )
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.cache_control.public = True
    response.cache_control.max_age = photo_gallery.PHOTO_THUMBNAIL_CACHE_SECONDS
    return response


@bp.route("/api/photo-original/<photo_id>")
def get_photo_original(photo_id):
    """获取照片原图，支持 inline 预览和附件下载。"""
    resolved = photo_gallery.resolve_photo_path(get_paths(), photo_id)
    if not resolved:
        return jsonify({"error": "Photo not found"}), 404

    _, full_path, meta = resolved
    download = request.args.get("download", "0").lower() in ("1", "true", "yes")
    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        as_attachment=download,
        download_name=meta.get("name") or os.path.basename(full_path),
        conditional=True,
        max_age=3600,
    )


@bp.route("/api/video-poster/<video_id>")
def get_video_poster(video_id):
    """获取视频封面；不可生成时返回 404 交给前端占位降级。"""
    paths = get_paths()
    poster_path = photo_gallery.ensure_video_poster(paths, video_id)
    if not poster_path or not os.path.exists(poster_path):
        return jsonify({"error": "Video poster not available"}), 404

    filename = os.path.basename(poster_path)
    response = send_from_directory(
        paths.video_poster_folder,
        filename,
        conditional=True,
        max_age=photo_gallery.PHOTO_THUMBNAIL_CACHE_SECONDS,
    )
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.cache_control.public = True
    response.cache_control.max_age = photo_gallery.PHOTO_THUMBNAIL_CACHE_SECONDS
    return response


def send_video_file(video_id):
    paths = get_paths()
    resolved = photo_gallery.resolve_media_path(
        paths,
        video_id,
        expected_type=photo_gallery.MEDIA_TYPE_VIDEO,
    )
    if not resolved:
        return jsonify({"error": "Video not found"}), 404

    _, full_path, meta = resolved
    download = request.args.get("download", "0").lower() in ("1", "true", "yes")
    audio_stream = request.args.get("audio", "0").lower() in ("1", "true", "yes")
    if audio_stream and not download:
        try:
            start_seconds = max(0.0, float(request.args.get("start", "0")))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid audio stream start time"}), 400
        if not math.isfinite(start_seconds):
            return jsonify({"error": "Invalid audio stream start time"}), 400

        command = photo_gallery.build_browser_audio_stream_command(full_path, start_seconds)
        if not command:
            return jsonify({"error": "FFmpeg is required for compatible audio streaming"}), 503

        if not photo_gallery.browser_audio_stream_semaphore.acquire(blocking=False):
            return jsonify({"error": "Too many compatible audio streams"}), 429

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            photo_gallery.browser_audio_stream_semaphore.release()
            return jsonify({"error": "Compatible audio stream could not be started"}), 503

        def generate_audio():
            try:
                while process.stdout:
                    chunk = process.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                try:
                    if process.stdout:
                        process.stdout.close()
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=1)
                finally:
                    photo_gallery.browser_audio_stream_semaphore.release()

        response = Response(
            stream_with_context(generate_audio()),
            mimetype="audio/aac",
            direct_passthrough=True,
        )
        response.cache_control.no_store = True
        response.cache_control.no_cache = True
        response.headers["X-Accel-Buffering"] = "no"
        return response

    response = send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        as_attachment=download,
        download_name=meta.get("name") or os.path.basename(full_path),
        mimetype=meta.get("mime_type") or photo_gallery.get_video_mime_type(full_path),
        conditional=True,
        max_age=3600,
    )
    return response


@bp.route("/api/video-original/<video_id>")
def get_video_original(video_id):
    """获取视频原文件，支持 inline 播放、附件下载和 Range seek。"""
    return send_video_file(video_id)


@bp.route("/api/video-play/<video_id>/<play_token>/<path:filename>")
def play_video_original(video_id, play_token, filename):
    """为移动端原生播放器提供带文件名后缀的临时播放地址。"""
    return send_video_file(video_id)


@bp.route("/api/photo-albums/<album_id>/uploads", methods=["POST"])
def upload_photos_to_album(album_id):
    """上传图片到当前照片相册，供局域网设备添加照片。"""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    files = request.files.getlist("file")
    payload, status_code = photo_gallery.upload_photos_to_album(get_paths(), album_id, files)
    return jsonify(payload), status_code


@bp.route("/api/photo-downloads", methods=["POST"])
def download_photos():
    """Download selected original photos as a ZIP archive."""
    data = request.get_json() or {}
    photo_ids = data.get("photo_ids")
    if not isinstance(photo_ids, list) or not photo_ids:
        return jsonify({"error": "photo_ids is required"}), 400

    result, error_payload, status_code = photo_gallery.create_photo_download_zip(get_paths(), photo_ids)
    if error_payload:
        return jsonify(error_payload), status_code

    response = send_file(
        result["zip_path"],
        as_attachment=True,
        download_name=result["download_name"],
        mimetype="application/zip",
        max_age=0,
        conditional=False,
    )
    response.headers["X-Photo-Download-Count"] = str(result["added_count"])
    response.headers["X-Photo-Download-Failed"] = str(len(result["failed"]))

    @response.call_on_close
    def cleanup_zip():
        try:
            os.remove(result["zip_path"])
        except OSError:
            pass

    return response


@bp.route("/api/photo-conversions", methods=["POST"])
def convert_photos_to_models():
    """将照片图库中的照片加入现有 3D 生成队列。"""
    data = request.get_json() or {}
    photo_ids = data.get("photo_ids")
    if not isinstance(photo_ids, list) or not photo_ids:
        return jsonify({"error": "photo_ids is required"}), 400

    task_manager = current_app.config["TASK_MANAGER"]
    payload = photo_gallery.convert_photos_to_models(get_paths(), task_manager, photo_ids)
    return jsonify(payload)

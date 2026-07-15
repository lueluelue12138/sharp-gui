import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from urllib.parse import quote

from PIL import Image

from backend.services.static_files import get_relative_files_path, is_real_path_inside

ALLOWED_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".JPG",
    ".JPEG",
    ".PNG",
    ".WEBP",
)
MAX_THUMBNAIL_REPAIRS_PER_REQUEST = 6
THUMBNAIL_CACHE_SECONDS = 86400
DEFAULT_FILE_CACHE_SECONDS = 3600
MODEL_METADATA_SUFFIX = ".meta.json"
VIDEO_THUMBNAIL_WIDTH = 200
MODEL_EXTENSIONS = (".ply", ".spz", ".splat", ".rad")
MODEL_FORMAT_PRIORITY = ("ply", "spz", "splat", "rad")
IMAGE_ASSET_ID_PREFIX = "img-"
INTERRUPTED_IMAGE_TASK_STATUSES = {"pending", "processing", "cancelled"}
thumbnail_cache_lock = threading.RLock()


def normalize_model_item_id(item_id):
    """Return a safe gallery item stem, accepting an optional model suffix."""
    candidate = str(item_id or "")
    invalid_chars = '<>:"/\\|?*'
    if (
        not candidate
        or candidate != os.path.basename(candidate)
        or candidate in (".", "..")
        or any(char in invalid_chars or ord(char) < 32 for char in candidate)
    ):
        return None

    stem, ext = os.path.splitext(candidate)
    if ext.lower() in MODEL_EXTENSIONS:
        candidate = stem
    return candidate or None


def collect_model_variants(paths, item_id):
    """Return existing model filenames keyed by their normalized format."""
    stem = normalize_model_item_id(item_id)
    if not stem or not os.path.isdir(paths.output_folder):
        return {}

    variants = {}
    for filename in os.listdir(paths.output_folder):
        full_path = os.path.join(paths.output_folder, filename)
        if not os.path.isfile(full_path):
            continue
        file_stem, ext = os.path.splitext(filename)
        normalized_ext = ext.lower()
        if file_stem == stem and normalized_ext in MODEL_EXTENSIONS:
            variants[normalized_ext[1:]] = filename
    return variants


def make_unique_image_input_filename(paths, filename):
    """为 Sharp 推理分配不可复用的 UUID 输入文件名。"""
    original_name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    _, original_ext = os.path.splitext(original_name)
    extension = original_ext.lower()
    allowed_extensions = {ext.lower() for ext in ALLOWED_IMAGE_EXTENSIONS}
    if extension not in allowed_extensions:
        return None

    for _ in range(1000):
        candidate_stem = f"{IMAGE_ASSET_ID_PREFIX}{uuid.uuid4().hex}"
        candidate = f"{candidate_stem}{extension}"
        candidate_paths = (
            os.path.join(paths.input_folder, candidate),
            os.path.join(paths.thumbnail_folder, f"{candidate_stem}.jpg"),
            os.path.join(paths.output_folder, f"{candidate_stem}.ply"),
            os.path.join(paths.output_folder, f"{candidate_stem}.spz"),
            get_model_metadata_path(paths, candidate_stem),
        )
        if not any(os.path.exists(path) for path in candidate_paths):
            return candidate

    raise RuntimeError("Could not allocate a unique image input name")


def generate_thumbnail(paths, input_path, filename):
    """生成缩略图 (200px 宽度, JPEG 80% 质量)。"""
    thumb_path = os.path.join(paths.thumbnail_folder, os.path.splitext(filename)[0] + ".jpg")
    temp_path = f"{thumb_path}.tmp-{uuid.uuid4().hex[:8]}.jpg"
    try:
        os.makedirs(paths.thumbnail_folder, exist_ok=True)
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            width = 200
            ratio = width / img.width
            height = int(img.height * ratio)
            img_resized = img.resize((width, height), Image.LANCZOS)
            img_resized.save(temp_path, "JPEG", quality=80)
        with thumbnail_cache_lock:
            if os.path.exists(thumb_path):
                return thumb_path
            os.replace(temp_path, thumb_path)
        return thumb_path
    except Exception as exc:
        print(f"⚠️ Thumbnail generation failed for {filename}: {exc}")
        return None
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def get_thumbnail_path(paths, item_id):
    """获取图库条目的缩略图路径。"""
    return os.path.join(paths.thumbnail_folder, item_id + ".jpg")


def get_model_metadata_path(paths, item_id):
    """获取模型图库条目的 sidecar 元数据路径。"""
    return os.path.join(paths.output_folder, item_id + MODEL_METADATA_SUFFIX)


def get_video_uploads_folder(paths):
    """获取拖拽上传视频的持久源文件目录。"""
    return os.path.join(paths.video_reconstruction_folder, "uploads")


def read_model_metadata(paths, item_id):
    """读取模型图库条目的 sidecar 元数据。"""
    metadata_path = get_model_metadata_path(paths, item_id)
    try:
        with open(metadata_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_model_metadata(paths, item_id, metadata):
    """写入模型图库条目的 sidecar 元数据。"""
    os.makedirs(paths.output_folder, exist_ok=True)
    metadata_path = get_model_metadata_path(paths, item_id)
    payload = {
        **(metadata if isinstance(metadata, dict) else {}),
        "id": item_id,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    temp_path = f"{metadata_path}.tmp-{uuid.uuid4().hex[:8]}"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp_path, metadata_path)
    return metadata_path


def get_model_display_name(paths, item_id, metadata=None):
    """返回模型的用户可见名称，旧模型回退到内部 ID。"""
    normalized_item_id = normalize_model_item_id(item_id)
    if not normalized_item_id:
        return str(item_id or "")

    metadata = (
        metadata
        if isinstance(metadata, dict)
        else read_model_metadata(paths, normalized_item_id)
    )
    display_name = metadata.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    if metadata.get("source_media_type") == "image":
        source_name = metadata.get("source_name")
        if isinstance(source_name, str) and source_name.strip():
            source_stem = os.path.splitext(os.path.basename(source_name.strip()))[0]
            if source_stem:
                return source_stem

    return normalized_item_id


def make_model_download_name(paths, item_id, extension, suffix="", metadata=None):
    """使用展示名生成安全下载名，不改变内部模型文件路径。"""
    normalized_item_id = normalize_model_item_id(item_id)
    if not normalized_item_id:
        normalized_item_id = "model"
    display_name = get_model_display_name(paths, normalized_item_id, metadata)
    safe_stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", display_name).strip(". ")
    safe_stem = safe_stem[:120] or normalized_item_id
    return f"{safe_stem}{suffix}{extension.lower()}"


def get_original_image_download_name(paths, item_id, stored_filename):
    """返回原图下载名，优先使用上传时的原始文件名。"""
    metadata = read_model_metadata(paths, item_id)
    source_name = metadata.get("source_name")
    extension = os.path.splitext(stored_filename)[1].lower()
    if isinstance(source_name, str) and source_name.strip():
        source_stem = os.path.splitext(
            source_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        )[0]
        safe_stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", source_stem).strip(". ")
        if safe_stem:
            return f"{safe_stem[:120]}{extension}"
    return make_model_download_name(paths, item_id, extension, metadata=metadata)


def resolve_gallery_source_video(paths, item_id):
    """解析图库条目的源视频，仅允许照片图库视频或受控上传缓存。"""
    metadata = read_model_metadata(paths, item_id)
    if metadata.get("source_media_type") != "video":
        return None

    source_media_id = metadata.get("source_media_id")
    if isinstance(source_media_id, str) and source_media_id:
        from backend.services import photo_gallery

        resolved = photo_gallery.resolve_media_path(
            paths,
            source_media_id,
            expected_type=photo_gallery.MEDIA_TYPE_VIDEO,
            allow_stale=True,
        )
        if resolved:
            _, full_path, meta = resolved
            return {
                "path": full_path,
                "name": meta.get("name") or os.path.basename(full_path),
                "mime_type": meta.get("mime_type") or photo_gallery.get_video_mime_type(full_path),
            }

    source_video_path = metadata.get("source_video_path")
    if not isinstance(source_video_path, str) or not source_video_path:
        return None

    upload_root = os.path.realpath(get_video_uploads_folder(paths))
    real_path = os.path.realpath(source_video_path)
    if not is_real_path_inside(real_path, upload_root) or not os.path.isfile(real_path):
        return None

    from backend.services import photo_gallery

    return {
        "path": real_path,
        "name": metadata.get("source_name") or os.path.basename(real_path),
        "mime_type": metadata.get("source_mime_type") or photo_gallery.get_video_mime_type(real_path),
    }


def normalize_stem_for_match(value):
    """Normalize a media/model stem for conservative legacy video backfill."""
    stem = os.path.splitext(os.path.basename(str(value or "")))[0]
    stem = re.sub(r"\s+", "_", stem).strip("._ ").lower()
    return stem


def legacy_video_match_stems(item_id):
    """Return possible source video stems for old generated model names.

    NOTE: This only serves early video reconstruction outputs whose filenames
    still carried explicit quality/cleanup suffixes (produced before the
    "default to source video stem" naming policy landed). New outputs use the
    source video stem directly, so no suffix stripping is needed for them; this
    backfill is intentionally conservative and only runs when a model has no
    sidecar metadata and matches exactly one same-name gallery video.
    """
    stem = normalize_stem_for_match(item_id)
    stems = {stem}
    without_collision_suffix = re.sub(r"-\d+$", "", stem)
    if without_collision_suffix:
        stems.add(without_collision_suffix)
    legacy_suffixes = (
        "_high180_focused",
        "_preview_final_clean_focused",
        "_preview_clean_focused",
        "_preview_focused",
        "_focused",
    )
    for suffix in legacy_suffixes:
        if stem.endswith(suffix):
            stems.add(stem[: -len(suffix)])
    return {candidate for candidate in stems if candidate}


def find_unique_gallery_video_for_model(paths, item_id):
    """Find a unique same-name gallery video for legacy outputs missing sidecar metadata."""
    from backend.services import photo_gallery

    target_stems = legacy_video_match_stems(item_id)
    if not target_stems:
        return None

    matched_meta = []
    for meta in photo_gallery.load_photo_index(paths).get("photos", {}).values():
        if not isinstance(meta, dict) or meta.get("media_type") != photo_gallery.MEDIA_TYPE_VIDEO:
            continue
        name = meta.get("name") or meta.get("relative_path") or meta.get("id")
        if normalize_stem_for_match(name) in target_stems:
            matched_meta.append(meta)

    resolved_by_path = {}
    for meta in matched_meta:
        resolved = photo_gallery.resolve_media_path(
            paths,
            meta["id"],
            expected_type=photo_gallery.MEDIA_TYPE_VIDEO,
            allow_stale=True,
        )
        if not resolved:
            continue
        _, full_path, resolved_meta = resolved
        resolved_by_path[os.path.realpath(full_path)] = (full_path, resolved_meta)

    if len(resolved_by_path) != 1:
        return None

    return next(iter(resolved_by_path.values()))


def backfill_legacy_video_metadata(paths, item_id):
    """Create video sidecar metadata for old video reconstruction outputs when it is safe."""
    if read_model_metadata(paths, item_id):
        return {}

    original_filename, original_path = find_original_image(paths, item_id)
    if original_filename and original_path:
        return {}

    match = find_unique_gallery_video_for_model(paths, item_id)
    if not match:
        return {}

    from backend.services import photo_gallery

    full_path, meta = match
    metadata = {
        "source_media_type": "video",
        "source_media_id": meta.get("id"),
        "source_name": meta.get("name") or os.path.basename(full_path),
        "source_video_path": full_path,
        "source_mime_type": meta.get("mime_type") or photo_gallery.get_video_mime_type(full_path),
        "generator": "video_3dgs",
        "recovered_from": "gallery-video-stem",
    }
    try:
        write_model_metadata(paths, item_id, metadata)
        generate_video_thumbnail(paths, full_path, item_id)
        return metadata
    except Exception as exc:
        print(f"⚠️ Failed to backfill video metadata for {item_id}: {exc}")
        return {}


def find_original_image(paths, item_id):
    """根据条目 ID 查找原图文件名和路径。"""
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        filename = item_id + ext
        img_path = os.path.join(paths.input_folder, filename)
        if os.path.exists(img_path):
            return filename, img_path
    return None, None


def ensure_thumbnail_for_item(paths, item_id, allow_generation=False):
    """确保图库条目存在可用缩略图。"""
    item_id = normalize_model_item_id(item_id)
    if not item_id:
        return None
    with thumbnail_cache_lock:
        thumb_path = get_thumbnail_path(paths, item_id)
        if os.path.exists(thumb_path):
            return thumb_path

    if not allow_generation:
        return None

    original_filename, original_path = find_original_image(paths, item_id)
    if original_filename and original_path:
        return generate_thumbnail(paths, original_path, original_filename)

    source_video = resolve_gallery_source_video(paths, item_id)
    if source_video:
        return generate_video_thumbnail(paths, source_video["path"], item_id)
    return None


def generate_video_thumbnail(paths, source_video_path, item_id):
    """从源视频抽一帧生成模型缩略图。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not os.path.isfile(source_video_path):
        return None

    os.makedirs(paths.thumbnail_folder, exist_ok=True)
    thumb_path = get_thumbnail_path(paths, item_id)
    with thumbnail_cache_lock:
        if os.path.exists(thumb_path):
            return thumb_path
    temp_path = f"{thumb_path}.tmp-{uuid.uuid4().hex[:8]}.jpg"
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "0.5",
                "-i",
                source_video_path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={VIDEO_THUMBNAIL_WIDTH}:-2",
                "-q:v",
                "4",
                "-y",
                temp_path,
            ],
            check=False,
            capture_output=True,
            timeout=12,
        )
        if result.returncode != 0 or not os.path.exists(temp_path):
            return None
        with thumbnail_cache_lock:
            if os.path.exists(thumb_path):
                return thumb_path
            os.replace(temp_path, thumb_path)
        return thumb_path
    except Exception as exc:
        print(f"⚠️ Video thumbnail generation failed for {item_id}: {exc}")
        return None
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def get_file_version(path):
    """获取文件版本号（基于修改时间）。"""
    return int(os.path.getmtime(path) * 1000)


def get_file_timestamp(path):
    """获取 ISO 格式的文件修改时间。"""
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(path),
        tz=datetime.timezone.utc,
    ).isoformat()


def build_gallery_item(
    paths,
    model_filename,
    repair_missing_thumbnail=False,
    model_variants=None,
):
    """构建单个图库条目的响应数据。"""
    name_without_ext = normalize_model_item_id(model_filename)
    if not name_without_ext:
        return None

    variants = model_variants or collect_model_variants(paths, name_without_ext)
    if not variants:
        return None

    primary_format = next(
        (model_format for model_format in MODEL_FORMAT_PRIORITY if model_format in variants),
        None,
    )
    if not primary_format:
        return None

    primary_filename = variants[primary_format]
    primary_path = os.path.join(paths.output_folder, primary_filename)
    primary_size = os.path.getsize(primary_path)
    file_timestamps = [
        os.path.getmtime(os.path.join(paths.output_folder, filename))
        for filename in variants.values()
    ]
    metadata = read_model_metadata(paths, name_without_ext)
    if not metadata and repair_missing_thumbnail:
        metadata = backfill_legacy_video_metadata(paths, name_without_ext)
    metadata_path = get_model_metadata_path(paths, name_without_ext)
    if os.path.exists(metadata_path):
        file_timestamps.append(os.path.getmtime(metadata_path))

    spz_url = None
    spz_size = None
    spz_filename = variants.get("spz")
    if spz_filename:
        spz_path = os.path.join(paths.output_folder, spz_filename)
        spz_url = f"/files/{get_relative_files_path(spz_path, paths)}"
        spz_size = os.path.getsize(spz_path)

    original_filename, original_path = find_original_image(paths, name_without_ext)
    image_url = None
    if original_filename and original_path:
        image_url = f"/api/original/{name_without_ext}"
        file_timestamps.append(os.path.getmtime(original_path))

    thumb_path = get_thumbnail_path(paths, name_without_ext)
    if not os.path.exists(thumb_path) and repair_missing_thumbnail:
        if metadata.get("source_media_type") == "video":
            source_video = resolve_gallery_source_video(paths, name_without_ext)
            if source_video:
                thumb_path = generate_video_thumbnail(paths, source_video["path"], name_without_ext)
        else:
            thumb_path = ensure_thumbnail_for_item(paths, name_without_ext, allow_generation=True)

    thumb_url = None
    thumb_version = None
    if thumb_path and os.path.exists(thumb_path):
        thumb_url = f"/api/thumbnail/{name_without_ext}"
        thumb_version = get_file_version(thumb_path)
        file_timestamps.append(os.path.getmtime(thumb_path))

    latest_timestamp = max(file_timestamps)

    display_name = get_model_display_name(paths, name_without_ext, metadata)

    item = {
        "id": name_without_ext,
        "name": display_name,
        "model_url": f"/files/{get_relative_files_path(primary_path, paths)}",
        "model_format": primary_format,
        "available_formats": [
            model_format for model_format in MODEL_FORMAT_PRIORITY if model_format in variants
        ],
        "spz_url": spz_url,
        "image_url": image_url,
        "thumb_url": thumb_url,
        "thumb_version": thumb_version,
        "size": primary_size,
        "spz_size": spz_size,
        "created_at": get_file_timestamp(primary_path),
        "updated_at": datetime.datetime.fromtimestamp(
            latest_timestamp,
            tz=datetime.timezone.utc,
        ).isoformat(),
    }

    if metadata.get("source_media_type") == "video":
        item.update({
            "source_media_type": "video",
            "source_media_id": metadata.get("source_media_id"),
            "source_name": metadata.get("source_name"),
            "source_video_url": f"/api/gallery/{quote(name_without_ext, safe='')}/source-video",
        })
    elif metadata.get("source_media_type") == "image":
        item.update({
            "source_media_type": "image",
            "source_name": metadata.get("source_name"),
        })

    return item


def list_gallery_items(paths):
    """获取图库列表。"""
    items = []
    if os.path.exists(paths.output_folder):
        variants_by_id = {}
        for filename in os.listdir(paths.output_folder):
            if not os.path.isfile(os.path.join(paths.output_folder, filename)):
                continue
            item_id, ext = os.path.splitext(filename)
            normalized_ext = ext.lower()
            if normalized_ext not in MODEL_EXTENSIONS:
                continue
            variants_by_id.setdefault(item_id, {})[normalized_ext[1:]] = filename

        item_ids = sorted(
            variants_by_id,
            key=lambda item_id: max(
                os.path.getmtime(os.path.join(paths.output_folder, filename))
                for filename in variants_by_id[item_id].values()
            ),
            reverse=True,
        )
        remaining_asset_repairs = MAX_THUMBNAIL_REPAIRS_PER_REQUEST

        for item_id in item_ids:
            thumb_missing = not os.path.exists(get_thumbnail_path(paths, item_id))
            metadata_missing = not os.path.exists(get_model_metadata_path(paths, item_id))
            repair_assets = (thumb_missing or metadata_missing) and remaining_asset_repairs > 0
            gallery_item = build_gallery_item(
                paths,
                item_id,
                repair_missing_thumbnail=repair_assets,
                model_variants=variants_by_id[item_id],
            )
            if gallery_item:
                items.append(gallery_item)
            if repair_assets:
                remaining_asset_repairs -= 1
    return items


def cleanup_interrupted_image_tasks(paths):
    """Reconcile UUID image tasks left behind by a previous server process."""
    summary = {"removed": 0, "recovered": 0, "errors": 0}
    if not os.path.isdir(paths.output_folder):
        return summary

    suffix = MODEL_METADATA_SUFFIX
    asset_id_pattern = re.compile(rf"^{re.escape(IMAGE_ASSET_ID_PREFIX)}[0-9a-f]{{32}}$")

    for filename in os.listdir(paths.output_folder):
        if not filename.endswith(suffix):
            continue

        item_id = filename[:-len(suffix)]
        if not asset_id_pattern.fullmatch(item_id):
            continue

        metadata = read_model_metadata(paths, item_id)
        if (
            metadata.get("source_media_type") != "image"
            or metadata.get("generation_status") not in INTERRUPTED_IMAGE_TASK_STATUSES
        ):
            continue

        ply_path = os.path.join(paths.output_folder, item_id + ".ply")
        spz_path = os.path.join(paths.output_folder, item_id + ".spz")
        try:
            if os.path.isfile(ply_path) or os.path.isfile(spz_path):
                write_model_metadata(
                    paths,
                    item_id,
                    {**metadata, "generation_status": "completed"},
                )
                summary["recovered"] += 1
            else:
                delete_gallery_item(paths, item_id)
                summary["removed"] += 1
        except OSError:
            summary["errors"] += 1

    return summary


def delete_gallery_item(paths, item_id):
    """删除图库项目，包括所有模型格式、原图、元数据和缩略图。"""
    normalized_item_id = normalize_model_item_id(item_id)
    if not normalized_item_id:
        raise ValueError("Invalid gallery item ID")

    metadata = read_model_metadata(paths, normalized_item_id)

    for filename in collect_model_variants(paths, normalized_item_id).values():
        model_path = os.path.join(paths.output_folder, filename)
        if os.path.exists(model_path):
            os.remove(model_path)

    thumb_path = os.path.join(paths.thumbnail_folder, normalized_item_id + ".jpg")
    if os.path.exists(thumb_path):
        os.remove(thumb_path)

    for ext in ALLOWED_IMAGE_EXTENSIONS:
        img_path = os.path.join(paths.input_folder, normalized_item_id + ext)
        if os.path.exists(img_path):
            os.remove(img_path)

    delete_uploaded_source_video(paths, metadata)

    metadata_path = get_model_metadata_path(paths, normalized_item_id)
    if os.path.exists(metadata_path):
        os.remove(metadata_path)


def delete_uploaded_source_video(paths, metadata):
    """删除拖拽上传视频的源文件缓存，不触碰照片图库原视频。"""
    if not isinstance(metadata, dict) or metadata.get("source_media_id"):
        return

    source_video_path = metadata.get("source_video_path")
    if not isinstance(source_video_path, str) or not source_video_path:
        return

    upload_root = os.path.realpath(get_video_uploads_folder(paths))
    real_path = os.path.realpath(source_video_path)
    if not is_real_path_inside(real_path, upload_root):
        return

    try:
        if os.path.isfile(real_path):
            os.remove(real_path)
        parent = os.path.dirname(real_path)
        if is_real_path_inside(parent, upload_root) and not os.listdir(parent):
            os.rmdir(parent)
    except OSError:
        pass


def find_original_image_filename(paths, item_id):
    filename, _ = find_original_image(paths, item_id)
    return filename


def resolve_download_model(paths, item_id, fmt):
    """返回应下载的模型文件名，支持四种格式并安全回退。"""
    variants = collect_model_variants(paths, item_id)
    if not variants:
        return None

    requested_format = str(fmt or "").lower()
    if requested_format not in MODEL_FORMAT_PRIORITY:
        requested_format = "spz"

    format_order = [requested_format, "spz", "ply", "splat", "rad"]
    for model_format in dict.fromkeys(format_order):
        filename = variants.get(model_format)
        if filename:
            return filename
    return None

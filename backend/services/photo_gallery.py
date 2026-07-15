import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from collections import deque
from shutil import which
from urllib.parse import quote

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

from backend import runtime
from backend.config import load_config, save_config
from backend.security.access_control import create_video_play_token
from backend.services import model_gallery
from backend.services.static_files import is_real_path_inside, to_url_path

PHOTO_THUMBNAIL_WIDTH = 480
VIDEO_POSTER_WIDTH = 640
PHOTO_THUMBNAIL_CACHE_SECONDS = 86400
PHOTO_DEFAULT_PAGE_SIZE = 60
PHOTO_MAX_PAGE_SIZE = 120
PHOTO_MAX_CONVERSION_BATCH = 100
PHOTO_MAX_DOWNLOAD_BATCH = 200
PHOTO_MAX_UPLOAD_BATCH = 100
PHOTO_DOWNLOAD_ZIP_TTL_SECONDS = 24 * 60 * 60
PHOTO_INDEX_VERSION = 2
MEDIA_TYPE_ALL = "all"
MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_VIDEO = "video"
PHOTO_SCAN_STATUS_IDLE = "idle"
PHOTO_SCAN_STATUS_SCANNING = "scanning"
PHOTO_SCAN_STATUS_INDEXING = "indexing"
PHOTO_SCAN_STATUS_NEEDS_INDEX = "needs_index"
PHOTO_SCAN_STATUS_STALE = "stale"
PHOTO_SCAN_STATUS_ERROR = "error"

PHOTO_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm"}
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}

catalog_lock = threading.Lock()
album_locks_lock = threading.Lock()
album_locks = {}
album_index_cache_lock = threading.Lock()
album_index_cache = {}
album_snapshot_cache = {}
thumbnail_generation_semaphore = threading.BoundedSemaphore(2)
bootstrap_lock = threading.Lock()
bootstrap_album_ids = set()
bootstrap_queue = deque()
bootstrap_worker_running = False
photo_download_lock = threading.Lock()
active_photo_download_paths = set()


def _normalized_real_path(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _is_link_like(path):
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda _path: False)(path)


def _is_safe_workspace_cache_path(paths, path):
    return not _is_link_like(path) and is_real_path_inside(path, paths.workspace_folder)


def register_active_photo_download(path):
    with photo_download_lock:
        active_photo_download_paths.add(_normalized_real_path(path))


def unregister_active_photo_download(path):
    with photo_download_lock:
        active_photo_download_paths.discard(_normalized_real_path(path))


def is_active_photo_download(path):
    with photo_download_lock:
        return _normalized_real_path(path) in active_photo_download_paths


def get_album_lock(album_id):
    with album_locks_lock:
        if album_id not in album_locks:
            album_locks[album_id] = threading.Lock()
        return album_locks[album_id]


def build_video_playback_url(video_id, filename):
    safe_filename = quote(filename or f"{video_id}.mp4", safe="")
    return f"/api/video-play/{video_id}/{create_video_play_token(video_id)}/{safe_filename}"


def make_photo_album_id(path):
    """根据目录真实路径生成稳定相册 ID。"""
    normalized = os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))
    return hashlib.sha1(normalized.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def normalize_workspace_key(workspace_folder):
    """归一化工作目录路径，作为相册分桶的稳定键。"""
    if not isinstance(workspace_folder, str) or not workspace_folder.strip():
        workspace_folder = runtime.DEFAULT_WORKSPACE_FOLDER
    return os.path.normcase(
        os.path.realpath(os.path.abspath(os.path.expanduser(workspace_folder.strip())))
    )


def migrate_photo_gallery_roots_config(config_data):
    """把旧的全局 ``photo_gallery_roots`` 迁移到按工作目录分桶的结构。

    旧配置只有一个顶层 ``photo_gallery_roots`` 列表，它逻辑上属于配置里当前记录的
    ``workspace_folder``。迁移会把它归档到对应工作目录的分桶，并移除顶层字段。
    返回是否发生了变化（用于决定是否需要持久化）。
    """
    buckets = config_data.get("photo_gallery_roots_by_workspace")
    if not isinstance(buckets, dict):
        buckets = {}

    legacy = config_data.get("photo_gallery_roots")
    if not isinstance(legacy, list):
        # 没有可迁移的旧字段；仅在缺少分桶字段时补一个空字典。
        if "photo_gallery_roots_by_workspace" not in config_data:
            config_data["photo_gallery_roots_by_workspace"] = buckets
            return True
        return False

    key = normalize_workspace_key(config_data.get("workspace_folder"))
    # 仅当该工作目录尚无分桶记录时迁移，避免覆盖已有分桶数据。
    if key not in buckets:
        buckets[key] = legacy
    config_data["photo_gallery_roots_by_workspace"] = buckets
    config_data.pop("photo_gallery_roots", None)
    return True


def get_photo_gallery_roots_for_config(config_data):
    """读取当前工作目录对应的相册原始配置列表。"""
    buckets = config_data.get("photo_gallery_roots_by_workspace")
    if isinstance(buckets, dict):
        key = normalize_workspace_key(config_data.get("workspace_folder"))
        roots = buckets.get(key)
        if isinstance(roots, list):
            return roots
        if key in buckets:
            return []
    # 兼容尚未迁移的旧配置：顶层 photo_gallery_roots 视为属于当前工作目录。
    legacy = config_data.get("photo_gallery_roots")
    if isinstance(legacy, list):
        return legacy
    return []


def set_photo_gallery_roots_for_config(config_data, roots):
    """写入当前工作目录对应的相册配置列表，并清理旧的全局字段。"""
    key = normalize_workspace_key(config_data.get("workspace_folder"))
    buckets = config_data.get("photo_gallery_roots_by_workspace")
    if not isinstance(buckets, dict):
        buckets = {}
    buckets[key] = roots
    config_data["photo_gallery_roots_by_workspace"] = buckets
    config_data.pop("photo_gallery_roots", None)
    return config_data


def normalize_photo_album_roots(config_data=None):
    """读取并规范化照片图库目录配置。"""
    source_config = config_data or load_config()
    raw_roots = get_photo_gallery_roots_for_config(source_config)
    if not isinstance(raw_roots, list):
        raw_roots = []

    albums = []
    seen_ids = set()
    for raw in raw_roots:
        if isinstance(raw, str):
            raw = {"path": raw}
        if not isinstance(raw, dict):
            continue

        path = raw.get("path")
        if not isinstance(path, str) or not path.strip():
            continue

        absolute_path = os.path.abspath(os.path.expanduser(path.strip()))
        album_id = raw.get("id")
        if not isinstance(album_id, str) or not album_id.strip():
            album_id = make_photo_album_id(absolute_path)
        album_id = "".join(ch for ch in album_id if ch.isalnum() or ch in ("-", "_"))[:64]
        if not album_id or album_id in seen_ids:
            album_id = make_photo_album_id(f"{absolute_path}-{len(seen_ids)}")
        seen_ids.add(album_id)

        default_name = os.path.basename(os.path.normpath(absolute_path)) or absolute_path
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            name = default_name

        albums.append({
            "id": album_id,
            "name": name.strip(),
            "path": absolute_path,
            "recursive": bool(raw.get("recursive", True)),
            "enabled": raw.get("enabled", True) is not False,
        })

    return albums


def find_photo_album(album_id):
    """根据相册 ID 查找配置。"""
    for album in normalize_photo_album_roots():
        if album["id"] == album_id:
            return album
    return None


def safe_load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else fallback
    except Exception as exc:
        if os.path.exists(path):
            print(f"⚠️ Failed to load JSON cache {path}: {exc}")
    return fallback


def dump_json_stable(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def atomic_write_json_if_changed(path, data):
    """原子写 JSON；内容未变则不触盘，返回是否发生写入。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    next_payload = dump_json_stable(data)

    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == next_payload:
                return False
    except OSError:
        pass

    temp_path = f"{path}.tmp-{uuid.uuid4().hex[:8]}"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(next_payload)
    os.replace(temp_path, path)
    return True


def get_album_index_path(paths, album_id):
    safe_album_id = "".join(ch for ch in str(album_id) if ch.isalnum() or ch in ("-", "_"))[:64]
    return os.path.join(paths.photo_album_index_folder, f"{safe_album_id}.json")


def normalize_album_index(data, album_id):
    if not isinstance(data, dict):
        data = {}

    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    normalized_media = {}
    for media_id, meta in media.items():
        if not isinstance(meta, dict):
            continue
        normalized = dict(meta)
        normalized["id"] = normalized.get("id") or str(media_id)
        normalized["album_id"] = normalized.get("album_id") or album_id
        if "media_type" not in normalized:
            normalized["media_type"] = MEDIA_TYPE_IMAGE
        if normalized.get("media_type") == "photo":
            normalized["media_type"] = MEDIA_TYPE_IMAGE
        normalized_media[normalized["id"]] = normalized

    return {
        "index_version": int(data.get("index_version") or PHOTO_INDEX_VERSION),
        "album_id": data.get("album_id") or album_id,
        "media": normalized_media,
        "scan_status": data.get("scan_status") or PHOTO_SCAN_STATUS_IDLE,
        "last_scanned_at": data.get("last_scanned_at"),
        "updated_at": data.get("updated_at"),
        "error": data.get("error"),
    }


def load_album_index_from_disk(paths, album_id):
    index_path = get_album_index_path(paths, album_id)
    if not os.path.exists(index_path):
        return None
    return normalize_album_index(safe_load_json(index_path, {}), album_id)


def get_album_index_file_mtime(paths, album_id):
    try:
        return os.path.getmtime(get_album_index_path(paths, album_id))
    except OSError:
        return None


def make_snapshot_token(mtime):
    try:
        return str(int(float(mtime) * 1_000_000_000))
    except (TypeError, ValueError):
        return None


def remember_album_snapshot(album_id, token, data):
    if not token:
        return
    snapshots = album_snapshot_cache.setdefault(album_id, {})
    snapshots[token] = data
    if len(snapshots) <= 4:
        return
    for stale_token in list(snapshots.keys())[:-4]:
        snapshots.pop(stale_token, None)


def load_album_index(paths, album_id):
    """读取单相册索引，带进程内 mtime 缓存。"""
    index_path = get_album_index_path(paths, album_id)
    try:
        mtime = os.path.getmtime(index_path)
    except OSError:
        with album_index_cache_lock:
            album_index_cache.pop(album_id, None)
        return None

    with album_index_cache_lock:
        cached = album_index_cache.get(album_id)
        if cached and cached.get("mtime") == mtime:
            return cached.get("data")

    data = load_album_index_from_disk(paths, album_id)
    if data is None:
        return None
    token = make_snapshot_token(mtime)
    data["_snapshot_token"] = token

    with album_index_cache_lock:
        album_index_cache[album_id] = {"mtime": mtime, "data": data}
        remember_album_snapshot(album_id, token, data)
    return data


def save_album_index(paths, album_id, index_data):
    normalized = normalize_album_index(index_data, album_id)
    index_path = get_album_index_path(paths, album_id)
    changed = atomic_write_json_if_changed(index_path, normalized)

    with album_index_cache_lock:
        try:
            mtime = os.path.getmtime(index_path)
        except OSError:
            mtime = None
        token = make_snapshot_token(mtime)
        normalized["_snapshot_token"] = token
        album_index_cache[album_id] = {"mtime": mtime, "data": normalized}
        remember_album_snapshot(album_id, token, normalized)

    return changed


def get_album_index_snapshot(paths, album_id, snapshot_token=None):
    index_data = None
    if snapshot_token:
        with album_index_cache_lock:
            index_data = album_snapshot_cache.get(album_id, {}).get(snapshot_token)
    if index_data is None:
        index_data = load_album_index(paths, album_id)
    if not index_data:
        return None
    media = [
        dict(meta)
        for meta in index_data.get("media", {}).values()
        if isinstance(meta, dict)
    ]
    return {
        "index_version": index_data.get("index_version"),
        "scan_status": index_data.get("scan_status") or PHOTO_SCAN_STATUS_IDLE,
        "last_scanned_at": index_data.get("last_scanned_at"),
        "updated_at": index_data.get("updated_at"),
        "error": index_data.get("error"),
        "snapshot_token": index_data.get("_snapshot_token"),
        "media": media,
    }


def normalize_catalog(data):
    if not isinstance(data, dict):
        data = {}
    albums = data.get("albums") if isinstance(data.get("albums"), dict) else {}
    return {
        "index_version": int(data.get("index_version") or PHOTO_INDEX_VERSION),
        "albums": {
            str(album_id): summary
            for album_id, summary in albums.items()
            if isinstance(summary, dict)
        },
        "updated_at": data.get("updated_at"),
    }


def load_catalog(paths):
    return normalize_catalog(safe_load_json(paths.photo_catalog_file, {}))


def save_catalog(paths, catalog_data):
    normalized = normalize_catalog(catalog_data)
    normalized["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with catalog_lock:
        return atomic_write_json_if_changed(paths.photo_catalog_file, normalized)


def iso_from_timestamp(timestamp):
    if not timestamp:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            float(timestamp),
            tz=datetime.timezone.utc,
        ).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def build_catalog_summary_from_media(album, media_items, scan_status=PHOTO_SCAN_STATUS_IDLE, error=None):
    image_count = sum(1 for item in media_items if item.get("media_type") == MEDIA_TYPE_IMAGE)
    video_count = sum(1 for item in media_items if item.get("media_type") == MEDIA_TYPE_VIDEO)
    sorted_items = sorted(media_items, key=lambda item: item.get("mtime", 0), reverse=True)
    cover = sorted_items[0] if sorted_items else None
    updated_mtime = max((item.get("mtime", 0) for item in media_items), default=None)
    cover_thumb_url = None
    cover_id = None
    cover_media_type = None
    if cover:
        cover_id = cover.get("id")
        cover_media_type = cover.get("media_type") or MEDIA_TYPE_IMAGE
        if cover_media_type == MEDIA_TYPE_VIDEO:
            cover_thumb_url = f"/api/video-poster/{cover_id}"
        else:
            cover_thumb_url = f"/api/photo-thumbnail/{cover_id}"

    return {
        "id": album["id"],
        "name": album.get("name") or os.path.basename(os.path.normpath(album.get("path", ""))) or album["id"],
        "cover_id": cover_id,
        "cover_media_type": cover_media_type,
        "cover_thumb_url": cover_thumb_url,
        "photo_count": image_count if scan_status != PHOTO_SCAN_STATUS_ERROR else None,
        "media_count": len(media_items) if scan_status != PHOTO_SCAN_STATUS_ERROR else None,
        "video_count": video_count if scan_status != PHOTO_SCAN_STATUS_ERROR else None,
        "recursive": album.get("recursive", True),
        "enabled": album.get("enabled", True),
        "scan_status": scan_status,
        "updated_at": iso_from_timestamp(updated_mtime),
        "last_scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        if scan_status == PHOTO_SCAN_STATUS_IDLE
        else None,
        "error": error,
        "index_version": PHOTO_INDEX_VERSION,
    }


def build_catalog_summary_for_unindexed_album(album, scan_status=None, error=None):
    status = scan_status or (
        PHOTO_SCAN_STATUS_ERROR
        if error
        else PHOTO_SCAN_STATUS_NEEDS_INDEX
    )
    return {
        "id": album["id"],
        "name": album.get("name") or os.path.basename(os.path.normpath(album.get("path", ""))) or album["id"],
        "cover_id": None,
        "cover_media_type": None,
        "cover_thumb_url": None,
        "photo_count": None,
        "media_count": None,
        "video_count": None,
        "recursive": album.get("recursive", True),
        "enabled": album.get("enabled", True),
        "scan_status": status,
        "updated_at": None,
        "last_scanned_at": None,
        "error": error,
        "index_version": PHOTO_INDEX_VERSION,
    }


def update_catalog_album(paths, album, media_items=None, scan_status=None, error=None, summary=None):
    catalog = load_catalog(paths)
    if summary is None:
        if media_items is None:
            summary = build_catalog_summary_for_unindexed_album(album, scan_status=scan_status, error=error)
        else:
            summary = build_catalog_summary_from_media(
                album,
                media_items,
                scan_status=scan_status or PHOTO_SCAN_STATUS_IDLE,
                error=error,
            )
    summary["id"] = album["id"]
    summary["name"] = album.get("name") or os.path.basename(os.path.normpath(album.get("path", ""))) or album["id"]
    summary["recursive"] = album.get("recursive", True)
    summary["enabled"] = album.get("enabled", True)
    catalog.setdefault("albums", {})[album["id"]] = summary
    save_catalog(paths, catalog)
    return summary


def load_photo_index(paths):
    """兼容读取旧全局索引。新代码仅把它作为迁移源或测试辅助。"""
    if os.path.exists(paths.photo_index_file):
        data = safe_load_json(paths.photo_index_file, {"photos": {}})
    else:
        photos = {}
        if os.path.isdir(paths.photo_album_index_folder):
            for filename in os.listdir(paths.photo_album_index_folder):
                if not filename.endswith(".json"):
                    continue
                album_id = filename[:-5]
                index_data = load_album_index(paths, album_id)
                if index_data:
                    photos.update(index_data.get("media", {}))
        data = {"photos": photos}
    if isinstance(data, dict) and isinstance(data.get("photos"), dict):
        return migrate_index_data(data)

    return {"photos": {}}


def save_photo_index(paths, index_data):
    """兼容保存旧全局索引，同时镜像到新相册索引方便旧测试和迁移。"""
    os.makedirs(paths.photo_gallery_cache_folder, exist_ok=True)
    index_data = migrate_index_data(index_data if isinstance(index_data, dict) else {"photos": {}})
    atomic_write_json_if_changed(paths.photo_index_file, index_data)

    grouped = {}
    for meta in index_data.get("photos", {}).values():
        if not isinstance(meta, dict):
            continue
        album_id = meta.get("album_id")
        if not album_id:
            continue
        grouped.setdefault(album_id, {})[meta["id"]] = meta

    for album_id, media in grouped.items():
        existing = load_album_index(paths, album_id) or {
            "index_version": PHOTO_INDEX_VERSION,
            "album_id": album_id,
            "media": {},
            "scan_status": PHOTO_SCAN_STATUS_IDLE,
        }
        existing["media"] = media
        existing["scan_status"] = existing.get("scan_status") or PHOTO_SCAN_STATUS_IDLE
        save_album_index(paths, album_id, existing)

        album = find_photo_album(album_id)
        if album:
            update_catalog_album(paths, album, list(media.values()))


def make_photo_id(album_id, relative_path):
    """根据相册与相对路径生成不暴露路径的照片 ID。"""
    normalized_relative = to_url_path(relative_path)
    digest = hashlib.sha256(normalized_relative.encode("utf-8", "surrogatepass")).hexdigest()[:24]
    return f"{album_id}_{digest}"


def parse_media_id(media_id):
    if not isinstance(media_id, str) or "_" not in media_id:
        return None
    album_id, digest = media_id.rsplit("_", 1)
    if not album_id or not digest:
        return None
    if not all(ch.isalnum() or ch in ("-", "_") for ch in album_id):
        return None
    return album_id


def get_file_extension(filename):
    return os.path.splitext(filename)[1].lower()


def is_supported_photo(filename):
    """判断文件是否是支持的照片格式。"""
    return get_file_extension(filename) in ALLOWED_IMAGE_EXTENSIONS


def is_supported_video(filename):
    """判断文件是否是支持的视频格式。"""
    return get_file_extension(filename) in ALLOWED_VIDEO_EXTENSIONS


def get_media_type(filename):
    if is_supported_photo(filename):
        return MEDIA_TYPE_IMAGE
    if is_supported_video(filename):
        return MEDIA_TYPE_VIDEO
    return None


def normalize_media_type(value):
    normalized = str(value or "").strip().lower()
    if normalized in {MEDIA_TYPE_IMAGE, "photo", "photos"}:
        return MEDIA_TYPE_IMAGE
    if normalized in {MEDIA_TYPE_VIDEO, "videos"}:
        return MEDIA_TYPE_VIDEO
    return MEDIA_TYPE_ALL


def migrate_index_data(index_data):
    """兼容旧照片索引，为缺失字段补默认媒体类型。"""
    photos = index_data.setdefault("photos", {})
    for meta in photos.values():
        if not isinstance(meta, dict):
            continue
        if "media_type" not in meta:
            meta["media_type"] = MEDIA_TYPE_IMAGE
        if meta.get("media_type") == "photo":
            meta["media_type"] = MEDIA_TYPE_IMAGE
    return index_data


def is_same_source_version(meta, stat):
    return (
        bool(meta)
        and meta.get("mtime") == stat.st_mtime
        and meta.get("size") == stat.st_size
    )


def get_video_mime_type(filename):
    return VIDEO_MIME_TYPES.get(get_file_extension(filename), "video/mp4")


def get_optional_command(name):
    return which(name)


def parse_float(value):
    try:
        parsed = float(value)
        if parsed == parsed and parsed >= 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return None


def parse_int(value):
    try:
        parsed = int(float(value))
        if parsed >= 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return None


def probe_video_metadata(full_path):
    """使用可选 ffprobe 读取视频元数据。"""
    ffprobe = get_optional_command("ffprobe")
    if not ffprobe:
        return {}

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                full_path,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        print(f"⚠️ Video metadata probe failed for {full_path}: {exc}")
        return {}

    if result.returncode != 0:
        return {}

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}

    streams = payload.get("streams") if isinstance(payload, dict) else []
    if not isinstance(streams, list):
        streams = []

    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        {},
    )
    audio_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        {},
    )
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}

    duration = parse_float(video_stream.get("duration")) or parse_float(format_data.get("duration"))
    width = parse_int(video_stream.get("width"))
    height = parse_int(video_stream.get("height"))
    bitrate = parse_int(format_data.get("bit_rate")) or parse_int(video_stream.get("bit_rate"))

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "bitrate": bitrate,
    }


def apply_cached_video_metadata(meta, existing_meta, stat):
    if not is_same_source_version(existing_meta, stat):
        return meta

    for key in ("duration", "width", "height", "video_codec", "audio_codec", "bitrate"):
        if existing_meta.get(key) is not None:
            meta[key] = existing_meta.get(key)
    return meta


def update_index_meta(paths, meta):
    album_id = meta.get("album_id") or parse_media_id(meta.get("id"))
    if not album_id:
        return
    with get_album_lock(album_id):
        index_data = load_album_index(paths, album_id) or {
            "index_version": PHOTO_INDEX_VERSION,
            "album_id": album_id,
            "media": {},
            "scan_status": PHOTO_SCAN_STATUS_IDLE,
        }
        index_data.setdefault("media", {})[meta["id"]] = meta
        save_album_index(paths, album_id, index_data)

        album = find_photo_album(album_id)
        if album:
            update_catalog_album(paths, album, list(index_data.get("media", {}).values()))


def photo_meta_from_path(album, full_path, existing_meta=None, root_path=None):
    """根据文件路径构建媒体索引元数据。"""
    root_path = root_path or os.path.realpath(album["path"])
    real_path = os.path.realpath(full_path)
    if not is_real_path_inside(real_path, root_path):
        return None

    try:
        stat = os.stat(real_path)
    except OSError:
        return None

    relative_path = to_url_path(os.path.relpath(real_path, root_path))
    photo_id = make_photo_id(album["id"], relative_path)
    media_type = get_media_type(real_path)
    if not media_type:
        return None

    width = None
    height = None
    if is_same_source_version(existing_meta, stat):
        width = existing_meta.get("width")
        height = existing_meta.get("height")

    meta = {
        "id": photo_id,
        "album_id": album["id"],
        "relative_path": relative_path,
        "name": os.path.basename(real_path),
        "media_type": media_type,
        "mime_type": get_video_mime_type(real_path) if media_type == MEDIA_TYPE_VIDEO else None,
        "mtime": stat.st_mtime,
        "ctime": stat.st_ctime,
        "size": stat.st_size,
        "width": width,
        "height": height,
    }

    if media_type == MEDIA_TYPE_VIDEO:
        meta.update({
            "duration": None,
            "video_codec": None,
            "audio_codec": None,
            "bitrate": None,
        })
        apply_cached_video_metadata(meta, existing_meta, stat)

    return meta


def iter_album_photo_paths(album):
    """遍历相册中的媒体路径。"""
    root_path = album["path"]
    if not os.path.isdir(root_path):
        return

    if album.get("recursive", True):
        for current_root, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [
                dirname for dirname in dirnames
                if dirname not in {".photo-gallery-cache", ".thumbnails", "__pycache__"}
            ]
            for filename in filenames:
                if get_media_type(filename):
                    yield os.path.join(current_root, filename)
    else:
        for filename in os.listdir(root_path):
            full_path = os.path.join(root_path, filename)
            if os.path.isfile(full_path) and get_media_type(filename):
                yield full_path


def build_legacy_meta_lookup(paths):
    if not os.path.exists(paths.photo_index_file):
        return {}

    legacy_index = load_photo_index(paths)
    lookup = {}
    for meta in legacy_index.get("photos", {}).values():
        if not isinstance(meta, dict):
            continue
        album_id = meta.get("album_id")
        relative_path = meta.get("relative_path")
        if not album_id or not relative_path:
            continue
        lookup[(album_id, to_url_path(relative_path))] = meta
    return lookup


def archive_legacy_photo_index(paths):
    if not os.path.exists(paths.photo_index_file):
        return
    backup_path = f"{paths.photo_index_file}.bak"
    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.replace(paths.photo_index_file, backup_path)
    except OSError as exc:
        print(f"⚠️ Failed to archive legacy photo index: {exc}")


def build_catalog_from_legacy_index(paths):
    """一次性从旧全局索引折算 catalog 并归档旧索引；旧索引不存在时直接返回现有 catalog。

    迁移是一次性动作：折算完成后立即归档 ``index.json``，因此正常列表请求不会再
    走"重建式读取每相册索引"的回退路径（避免列表接口出现 O(N^2) 读放大）。
    """
    if not os.path.exists(paths.photo_index_file):
        return load_catalog(paths)

    catalog = load_catalog(paths)
    albums_by_id = {album["id"]: album for album in normalize_photo_album_roots()}
    grouped = {}
    for meta in load_photo_index(paths).get("photos", {}).values():
        if not isinstance(meta, dict):
            continue
        album_id = meta.get("album_id")
        if album_id in albums_by_id:
            grouped.setdefault(album_id, []).append(meta)

    for album_id, media_items in grouped.items():
        if album_id in catalog.get("albums", {}):
            continue
        catalog.setdefault("albums", {})[album_id] = build_catalog_summary_from_media(
            albums_by_id[album_id],
            media_items,
            scan_status=PHOTO_SCAN_STATUS_STALE,
        )

    save_catalog(paths, catalog)
    archive_legacy_photo_index(paths)
    return catalog


def scan_photo_album(paths, album):
    """扫描相册并刷新轻量索引。"""
    if not album.get("enabled", True):
        update_catalog_album(paths, album, [], scan_status=PHOTO_SCAN_STATUS_ERROR, error="Album disabled")
        return [], PHOTO_SCAN_STATUS_ERROR, "Album disabled"

    if not os.path.isdir(album["path"]):
        update_catalog_album(paths, album, [], scan_status=PHOTO_SCAN_STATUS_ERROR, error="Album path is not available")
        return [], PHOTO_SCAN_STATUS_ERROR, "Album path is not available"

    album_lock = get_album_lock(album["id"])
    with album_lock:
        existing_index = load_album_index(paths, album["id"])
        previous_by_key = {}
        if existing_index:
            previous_by_key.update({
                (meta.get("album_id"), meta.get("relative_path")): meta
                for meta in existing_index.get("media", {}).values()
                if isinstance(meta, dict)
            })
        if not existing_index:
            previous_by_key.update(build_legacy_meta_lookup(paths))

        album_photos = []
        try:
            root_path = os.path.realpath(album["path"])
            for full_path in iter_album_photo_paths(album):
                real_path = os.path.realpath(full_path)
                relative_path = to_url_path(os.path.relpath(real_path, root_path))
                existing = previous_by_key.get((album["id"], relative_path))
                meta = photo_meta_from_path(album, full_path, existing_meta=existing, root_path=root_path)
                if not meta:
                    continue
                album_photos.append(meta)
        except Exception as exc:
            update_catalog_album(paths, album, [], scan_status=PHOTO_SCAN_STATUS_ERROR, error=str(exc))
            return [], PHOTO_SCAN_STATUS_ERROR, str(exc)

        media_by_id = {meta["id"]: meta for meta in album_photos}
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated_at = iso_from_timestamp(max((meta.get("mtime", 0) for meta in album_photos), default=0))
        save_album_index(paths, album["id"], {
            "index_version": PHOTO_INDEX_VERSION,
            "album_id": album["id"],
            "media": media_by_id,
            "scan_status": PHOTO_SCAN_STATUS_IDLE,
            "last_scanned_at": now_iso,
            "updated_at": updated_at,
            "error": None,
        })
        update_catalog_album(paths, album, album_photos)
        if os.path.exists(paths.photo_index_file):
            archive_legacy_photo_index(paths)

    album_photos.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return album_photos, PHOTO_SCAN_STATUS_IDLE, None


def schedule_album_bootstrap(paths, album):
    """串行后台建立相册索引；普通读取不等待，也不会形成多盘并发扫描。"""
    global bootstrap_worker_running
    album_id = album.get("id")
    if not album_id:
        return False
    if load_album_index(paths, album_id):
        return False
    bootstrap_key = (normalize_workspace_key(paths.workspace_folder), album_id)

    with bootstrap_lock:
        if bootstrap_key in bootstrap_album_ids:
            return False
        bootstrap_album_ids.add(bootstrap_key)
        bootstrap_queue.append((bootstrap_key, paths, dict(album)))
        if bootstrap_worker_running:
            return True
        bootstrap_worker_running = True

    def worker():
        global bootstrap_worker_running
        while True:
            with bootstrap_lock:
                if not bootstrap_queue:
                    bootstrap_worker_running = False
                    return
                queued_key, queued_paths, queued_album = bootstrap_queue.popleft()
            try:
                scan_photo_album(queued_paths, queued_album)
            except Exception as exc:
                print(f"⚠️ Photo gallery bootstrap failed for {queued_album.get('id')}: {exc}")
            finally:
                with bootstrap_lock:
                    bootstrap_album_ids.discard(queued_key)

    thread = threading.Thread(
        target=worker,
        name="photo-gallery-bootstrap",
        daemon=True,
    )
    try:
        thread.start()
    except Exception:
        with bootstrap_lock:
            bootstrap_worker_running = False
            queued_keys = {item[0] for item in bootstrap_queue}
            bootstrap_queue.clear()
            bootstrap_album_ids.difference_update(queued_keys)
        raise
    return True


def get_photo_dimensions(full_path):
    """读取照片尺寸。"""
    try:
        with Image.open(full_path) as img:
            return img.size
    except Exception:
        return None, None


def get_video_metadata_for_response(paths, meta):
    if meta.get("duration") is not None and meta.get("width") and meta.get("height"):
        return meta

    resolved = resolve_media_path(
        paths,
        meta["id"],
        expected_type=MEDIA_TYPE_VIDEO,
        allow_stale=True,
    )
    if not resolved:
        return meta

    _, full_path, current_meta = resolved
    probed = probe_video_metadata(full_path)
    if not probed:
        return meta

    updated = False
    for key in ("duration", "width", "height", "video_codec", "audio_codec", "bitrate"):
        if probed.get(key) is not None and current_meta.get(key) != probed.get(key):
            current_meta[key] = probed.get(key)
            updated = True

    if updated:
        update_index_meta(paths, current_meta)
        return current_meta

    return meta


def get_video_poster_filename(video_id, meta):
    """生成与源视频版本绑定的封面文件名。"""
    version = f"{int(float(meta.get('mtime', 0)) * 1000)}-{int(meta.get('size', 0))}"
    return f"{video_id}-{version}-{VIDEO_POSTER_WIDTH}.jpg"


def ensure_video_poster(paths, video_id):
    """确保视频封面存在；ffmpeg 不可用或抽帧失败时安全返回 None。"""
    resolved = resolve_media_path(
        paths,
        video_id,
        expected_type=MEDIA_TYPE_VIDEO,
    )
    if not resolved:
        return None

    _, full_path, meta = resolved
    poster_filename = get_video_poster_filename(video_id, meta)
    poster_path = os.path.join(paths.video_poster_folder, poster_filename)
    if os.path.exists(poster_path):
        return poster_path

    ffmpeg = get_optional_command("ffmpeg")
    if not ffmpeg:
        return None

    os.makedirs(paths.video_poster_folder, exist_ok=True)
    temp_path = f"{poster_path}.tmp-{uuid.uuid4().hex[:8]}.jpg"
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
                full_path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={VIDEO_POSTER_WIDTH}:-2",
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
        os.replace(temp_path, poster_path)
        return poster_path
    except Exception as exc:
        print(f"⚠️ Video poster generation failed for {video_id}: {exc}")
        return None
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def resolve_media_path(paths, media_id, expected_type=None, allow_stale=False):
    """根据媒体 ID 解析真实路径，并验证仍在配置目录内。"""
    album_id = parse_media_id(media_id)
    if not album_id:
        return None

    index_data = load_album_index(paths, album_id)
    meta = index_data.get("media", {}).get(media_id) if index_data else None

    if not isinstance(meta, dict):
        return None
    media_type = meta.get("media_type") or MEDIA_TYPE_IMAGE
    if expected_type and media_type != expected_type:
        return None

    album = find_photo_album(album_id)
    if not album:
        return None

    root_path = os.path.realpath(album["path"])
    relative_path = str(meta.get("relative_path", "")).replace("/", os.sep)
    full_path = os.path.realpath(os.path.join(root_path, relative_path))
    if not is_real_path_inside(full_path, root_path) or not os.path.isfile(full_path):
        return None

    try:
        stat = os.stat(full_path)
    except OSError:
        return None

    current_meta = dict(meta)
    current_meta["mtime"] = stat.st_mtime
    current_meta["ctime"] = stat.st_ctime
    current_meta["size"] = stat.st_size
    current_meta["name"] = os.path.basename(full_path)
    current_meta["media_type"] = media_type

    if not allow_stale and (
        meta.get("mtime") != stat.st_mtime or meta.get("size") != stat.st_size
    ):
        current_meta["width"] = None
        current_meta["height"] = None
        if media_type == MEDIA_TYPE_VIDEO:
            current_meta["duration"] = None
            current_meta["video_codec"] = None
            current_meta["audio_codec"] = None
            current_meta["bitrate"] = None
        update_index_meta(paths, current_meta)

    return album, full_path, current_meta


def resolve_photo_path(paths, photo_id, allow_stale=False):
    """根据照片 ID 解析真实路径，并验证仍在配置目录内。"""
    return resolve_media_path(
        paths,
        photo_id,
        expected_type=MEDIA_TYPE_IMAGE,
        allow_stale=allow_stale,
    )


def build_photo_item(paths, meta):
    """构建媒体条目响应。"""
    media_type = meta.get("media_type") or MEDIA_TYPE_IMAGE
    width = meta.get("width")
    height = meta.get("height")
    if media_type == MEDIA_TYPE_VIDEO:
        meta = get_video_metadata_for_response(paths, meta)
        width = meta.get("width")
        height = meta.get("height")

    updated_at = None
    if meta.get("mtime"):
        updated_at = datetime.datetime.fromtimestamp(
            meta["mtime"],
            tz=datetime.timezone.utc,
        ).isoformat()
    created_at = None
    if meta.get("ctime"):
        created_at = datetime.datetime.fromtimestamp(
            meta["ctime"],
            tz=datetime.timezone.utc,
        ).isoformat()

    item = {
        "id": meta["id"],
        "album_id": meta["album_id"],
        "name": meta.get("name") or meta["id"],
        "media_type": media_type,
        "width": width,
        "height": height,
        "size": meta.get("size"),
        "created_at": created_at,
        "updated_at": updated_at,
    }

    if media_type == MEDIA_TYPE_VIDEO:
        item.update({
            "thumb_url": f"/api/video-poster/{meta['id']}",
            "poster_url": f"/api/video-poster/{meta['id']}",
            "preview_url": f"/api/video-original/{meta['id']}",
            "playback_url": build_video_playback_url(meta["id"], meta.get("name")),
            "download_url": f"/api/video-original/{meta['id']}?download=1",
            "duration": meta.get("duration"),
            "mime_type": meta.get("mime_type") or get_video_mime_type(meta.get("name", "")),
            "video_codec": meta.get("video_codec"),
            "audio_codec": meta.get("audio_codec"),
            "bitrate": meta.get("bitrate"),
        })
    else:
        item.update({
            "thumb_url": f"/api/photo-thumbnail/{meta['id']}",
            "full_url": f"/api/photo-original/{meta['id']}",
            "preview_url": f"/api/photo-original/{meta['id']}",
            "download_url": f"/api/photo-original/{meta['id']}?download=1",
        })

    return item


def get_photo_thumbnail_filename(photo_id, meta):
    """生成与源文件版本绑定的缩略图文件名。"""
    version = f"{int(float(meta.get('mtime', 0)) * 1000)}-{int(meta.get('size', 0))}"
    return f"{photo_id}-{version}-{PHOTO_THUMBNAIL_WIDTH}.jpg"


def ensure_photo_thumbnail(paths, photo_id):
    """确保照片缩略图存在。"""
    resolved = resolve_photo_path(paths, photo_id)
    if not resolved:
        return None

    _, full_path, meta = resolved
    thumb_filename = get_photo_thumbnail_filename(photo_id, meta)
    thumb_path = os.path.join(paths.photo_thumbnail_folder, thumb_filename)
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        os.makedirs(paths.photo_thumbnail_folder, exist_ok=True)
        with thumbnail_generation_semaphore:
            if os.path.exists(thumb_path):
                return thumb_path
            with Image.open(full_path) as img:
                img = ImageOps.exif_transpose(img)
                meta["width"], meta["height"] = img.size
                img.thumbnail((PHOTO_THUMBNAIL_WIDTH, PHOTO_THUMBNAIL_WIDTH * 3), Image.LANCZOS)
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.getchannel("A"))
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                temp_path = f"{thumb_path}.tmp-{uuid.uuid4().hex[:8]}.jpg"
                img.save(temp_path, "JPEG", quality=82, optimize=True)
                os.replace(temp_path, thumb_path)

        update_index_meta(paths, meta)
        return thumb_path
    except Exception as exc:
        print(f"⚠️ Photo thumbnail generation failed for {photo_id}: {exc}")
        return None


def build_photo_album_response(paths, album, catalog=None):
    """构建相册响应数据。"""
    if catalog is None:
        catalog = build_catalog_from_legacy_index(paths)
    summary = catalog.get("albums", {}).get(album["id"])
    if not summary:
        index_data = load_album_index(paths, album["id"])
        if index_data:
            summary = update_catalog_album(paths, album, list(index_data.get("media", {}).values()))
        else:
            error = None
            status = PHOTO_SCAN_STATUS_NEEDS_INDEX
            if not album.get("enabled", True):
                error = "Album disabled"
                status = PHOTO_SCAN_STATUS_ERROR
            elif not os.path.isdir(album["path"]):
                error = "Album path is not available"
                status = PHOTO_SCAN_STATUS_ERROR
            summary = update_catalog_album(paths, album, scan_status=status, error=error)
            if status == PHOTO_SCAN_STATUS_NEEDS_INDEX:
                schedule_album_bootstrap(paths, album)

    return {
        "id": album["id"],
        "name": album["name"],
        "cover_thumb_url": summary.get("cover_thumb_url"),
        "photo_count": summary.get("photo_count"),
        "media_count": summary.get("media_count"),
        "video_count": summary.get("video_count"),
        "recursive": album.get("recursive", True),
        "enabled": album.get("enabled", True),
        "scan_status": summary.get("scan_status") or PHOTO_SCAN_STATUS_NEEDS_INDEX,
        "updated_at": summary.get("updated_at"),
        "last_scanned_at": summary.get("last_scanned_at"),
        "error": summary.get("error"),
        "index_version": summary.get("index_version") or PHOTO_INDEX_VERSION,
    }


def list_photo_album_responses(paths):
    # 每次列表请求只折算一次 catalog（迁移在首次调用时一次性完成并归档旧索引），
    # 各相册仅从 catalog 读取摘要，避免对每个相册重复重建式读取索引。
    catalog = build_catalog_from_legacy_index(paths)
    return [
        build_photo_album_response(paths, album, catalog)
        for album in normalize_photo_album_roots()
    ]


def add_photo_album(paths, data):
    path = data.get("path")
    if not isinstance(path, str) or not path.strip():
        return {"error": "Photo album path is required"}, 400

    absolute_path = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.isdir(absolute_path):
        return {"error": "Photo album path is not available"}, 400

    current_config = load_config()
    albums = normalize_photo_album_roots(current_config)
    album_id = make_photo_album_id(absolute_path)
    existing = next((album for album in albums if album["id"] == album_id), None)
    if existing:
        return {"success": True, "album": build_photo_album_response(paths, existing), "duplicate": True}, 200

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        name = os.path.basename(os.path.normpath(absolute_path)) or absolute_path

    recursive = data.get("recursive", True) is not False
    new_album = {
        "id": album_id,
        "name": name.strip(),
        "path": absolute_path,
        "recursive": recursive,
        "enabled": True,
    }

    set_photo_gallery_roots_for_config(current_config, [
        {
            "id": album["id"],
            "name": album["name"],
            "path": album["path"],
            "recursive": album["recursive"],
            "enabled": album["enabled"],
        }
        for album in albums
    ] + [new_album])
    save_config(current_config)

    update_catalog_album(paths, new_album, scan_status=PHOTO_SCAN_STATUS_NEEDS_INDEX)
    schedule_album_bootstrap(paths, new_album)
    return {"success": True, "album": build_photo_album_response(paths, new_album)}, 200


def delete_photo_album(paths, album_id):
    current_config = load_config()
    albums = normalize_photo_album_roots(current_config)
    next_albums = [album for album in albums if album["id"] != album_id]
    if len(next_albums) == len(albums):
        return {"error": "Album not found"}, 404

    set_photo_gallery_roots_for_config(current_config, next_albums)
    save_config(current_config)

    index_data = load_album_index(paths, album_id)
    stale_items = [
        (photo_id, meta.get("media_type") or MEDIA_TYPE_IMAGE)
        for photo_id, meta in (index_data or {}).get("media", {}).items()
        if isinstance(meta, dict)
    ]

    try:
        os.remove(get_album_index_path(paths, album_id))
    except OSError:
        pass

    if os.path.exists(paths.photo_index_file):
        legacy_index = load_photo_index(paths)
        legacy_photos = legacy_index.setdefault("photos", {})
        for photo_id, meta in list(legacy_photos.items()):
            if isinstance(meta, dict) and meta.get("album_id") == album_id:
                legacy_photos.pop(photo_id, None)
        atomic_write_json_if_changed(paths.photo_index_file, legacy_index)

    with album_index_cache_lock:
        album_index_cache.pop(album_id, None)

    catalog = load_catalog(paths)
    if catalog.get("albums", {}).pop(album_id, None) is not None:
        save_catalog(paths, catalog)

    cleanup_album_media_cache(paths, stale_items)
    return {"success": True}, 200


def cleanup_album_media_cache(paths, media_items):
    """删除相册移除后不再可达的图片缩略图和视频封面缓存。"""
    for media_id, media_type in media_items:
        if media_type == MEDIA_TYPE_VIDEO:
            remove_cache_files_for_media(paths.video_poster_folder, media_id)
        else:
            remove_cache_files_for_media(paths.photo_thumbnail_folder, media_id)


def remove_cache_files_for_media(cache_folder, media_id):
    if not os.path.isdir(cache_folder):
        return

    prefix = f"{media_id}-"
    try:
        filenames = os.listdir(cache_folder)
    except OSError:
        return

    for filename in filenames:
        if not filename.startswith(prefix):
            continue
        cache_path = os.path.join(cache_folder, filename)
        try:
            if os.path.isfile(cache_path):
                os.remove(cache_path)
        except OSError:
            pass


def get_media_counts(media_items):
    image_count = sum(1 for item in media_items if item.get("media_type") == MEDIA_TYPE_IMAGE)
    video_count = sum(1 for item in media_items if item.get("media_type") == MEDIA_TYPE_VIDEO)
    return {
        "all": len(media_items),
        "image": image_count,
        "photo": image_count,
        "video": video_count,
    }


def list_album_photos(
    paths,
    album_id,
    sort,
    cursor_value,
    limit_value,
    media_type_value=MEDIA_TYPE_ALL,
    snapshot_token=None,
):
    album = find_photo_album(album_id)
    if not album:
        return {"error": "Album not found"}, 404

    snapshot = get_album_index_snapshot(paths, album_id, snapshot_token=snapshot_token)
    if snapshot is None:
        error = None
        scan_status = PHOTO_SCAN_STATUS_NEEDS_INDEX
        if not album.get("enabled", True):
            error = "Album disabled"
            scan_status = PHOTO_SCAN_STATUS_ERROR
        elif not os.path.isdir(album["path"]):
            error = "Album path is not available"
            scan_status = PHOTO_SCAN_STATUS_ERROR
        else:
            schedule_album_bootstrap(paths, album)
        summary = update_catalog_album(paths, album, scan_status=scan_status, error=error)
        return {
            "items": [],
            "next_cursor": None,
            "total": 0,
            "media_counts": get_media_counts([]),
            "scan_status": summary.get("scan_status") or scan_status,
            "index_version": summary.get("index_version") or PHOTO_INDEX_VERSION,
            "snapshot": None,
            "error": error,
        }, 200

    media_items = snapshot["media"]
    scan_status = snapshot.get("scan_status") or PHOTO_SCAN_STATUS_IDLE
    error = snapshot.get("error")
    media_counts = get_media_counts(media_items)
    if scan_status == PHOTO_SCAN_STATUS_ERROR:
        return {
            "items": [],
            "next_cursor": None,
            "total": 0,
            "media_counts": media_counts,
            "scan_status": scan_status,
            "index_version": snapshot.get("index_version") or PHOTO_INDEX_VERSION,
            "snapshot": snapshot.get("snapshot_token"),
            "error": error,
        }, 200

    requested_media_type = normalize_media_type(media_type_value)
    if requested_media_type != MEDIA_TYPE_ALL:
        media_items = [
            item for item in media_items
            if item.get("media_type") == requested_media_type
        ]

    if sort == "mtime_asc":
        media_items.sort(key=lambda item: item.get("mtime", 0))
    elif sort == "ctime_desc":
        media_items.sort(key=lambda item: item.get("ctime", item.get("mtime", 0)), reverse=True)
    elif sort == "ctime_asc":
        media_items.sort(key=lambda item: item.get("ctime", item.get("mtime", 0)))
    elif sort == "name_asc":
        media_items.sort(key=lambda item: item.get("name", "").lower())
    elif sort == "name_desc":
        media_items.sort(key=lambda item: item.get("name", "").lower(), reverse=True)
    elif sort == "size_desc":
        media_items.sort(key=lambda item: item.get("size", 0), reverse=True)
    elif sort == "size_asc":
        media_items.sort(key=lambda item: item.get("size", 0))
    else:
        media_items.sort(key=lambda item: item.get("mtime", 0), reverse=True)

    try:
        cursor = max(0, int(cursor_value))
    except ValueError:
        cursor = 0

    try:
        limit = int(limit_value)
    except ValueError:
        limit = PHOTO_DEFAULT_PAGE_SIZE
    limit = max(1, min(limit, PHOTO_MAX_PAGE_SIZE))

    page = media_items[cursor:cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(media_items) else None

    return {
        "items": [build_photo_item(paths, meta) for meta in page],
        "next_cursor": str(next_cursor) if next_cursor is not None else None,
        "total": len(media_items),
        "media_counts": media_counts,
        "scan_status": scan_status,
        "index_version": snapshot.get("index_version") or PHOTO_INDEX_VERSION,
        "snapshot": snapshot.get("snapshot_token"),
        "error": error,
    }, 200


def make_unique_photo_upload_filename(filename, target_folder):
    """为上传到照片图库的文件生成安全且不冲突的文件名。"""
    safe_name = secure_filename(filename)
    name, ext = os.path.splitext(safe_name)
    if not ext:
        _, ext = os.path.splitext(filename)

    ext = ext.lower()
    if ext not in PHOTO_UPLOAD_EXTENSIONS:
        return None

    if not name:
        name = "photo"

    candidate = f"{name}{ext}"
    candidate_path = os.path.join(target_folder, candidate)
    if not os.path.exists(candidate_path):
        return candidate

    suffix = uuid.uuid4().hex[:8]
    return f"{name}-{suffix}{ext}"


def is_valid_uploaded_photo(path):
    """验证上传文件是否为 Pillow 可识别的图片。"""
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def upload_photos_to_album(paths, album_id, files):
    """上传图片到当前照片相册。"""
    album = find_photo_album(album_id)
    if not album:
        return {"error": "Album not found"}, 404
    if not album.get("enabled", True):
        return {"error": "Album is disabled"}, 400

    album_root = os.path.realpath(os.path.abspath(album["path"]))
    if not os.path.isdir(album_root):
        return {"error": "Album folder is unavailable"}, 400

    if not files or files[0].filename == "":
        return {"error": "No selected file"}, 400

    uploaded = 0
    failed = []

    for uploaded_file in files[:PHOTO_MAX_UPLOAD_BATCH]:
        original_name = uploaded_file.filename or "photo"
        filename = make_unique_photo_upload_filename(original_name, album_root)
        if not filename:
            failed.append({"name": original_name, "error": "Unsupported image format"})
            continue

        target_path = os.path.realpath(os.path.join(album_root, filename))
        if not is_real_path_inside(target_path, album_root):
            failed.append({"name": original_name, "error": "Unsafe upload path"})
            continue

        try:
            uploaded_file.save(target_path)
            if not is_valid_uploaded_photo(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
                failed.append({"name": original_name, "error": "Invalid image file"})
                continue

            uploaded += 1
        except Exception as exc:
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
            except OSError:
                pass
            failed.append({"name": original_name, "error": str(exc)})

    if uploaded == 0:
        return {
            "success": False,
            "uploaded": uploaded,
            "failed": failed,
            "error": "No valid photos uploaded",
        }, 400

    scan_photo_album(paths, album)
    return {
        "success": True,
        "uploaded": uploaded,
        "failed": failed,
        "album": build_photo_album_response(paths, album),
    }, 200


def rescan_photo_album(paths, album_id):
    album = find_photo_album(album_id)
    if not album:
        return {"error": "Album not found"}, 404

    media_items, scan_status, error = scan_photo_album(paths, album)
    if scan_status == PHOTO_SCAN_STATUS_ERROR:
        return {
            "success": False,
            "album": build_photo_album_response(paths, album),
            "error": error,
        }, 200

    return {
        "success": True,
        "album": build_photo_album_response(paths, album),
        "media_count": len(media_items),
    }, 200


def make_unique_input_filename(paths, filename):
    """为照片转 3D 分配与上传图片一致的 UUID 输入文件名。"""
    return model_gallery.make_unique_image_input_filename(paths, filename)


def make_unique_archive_name(filename, used_names):
    """Create a safe unique filename for files inside the downloaded ZIP."""
    safe_name = str(filename or "photo").replace("\\", "_").replace("/", "_").replace("\0", "").strip()
    if not safe_name:
        safe_name = "photo"

    stem, ext = os.path.splitext(safe_name)
    if not stem:
        stem = "photo"

    candidate = f"{stem}{ext}"
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({counter}){ext}"
        counter += 1

    used_names.add(candidate.casefold())
    return candidate


def cleanup_expired_photo_download_zips(paths, max_age_seconds=PHOTO_DOWNLOAD_ZIP_TTL_SECONDS):
    """清理中断下载或异常退出遗留的临时图库 ZIP。"""
    cache_folder = paths.photo_gallery_cache_folder
    if (
        not _is_safe_workspace_cache_path(paths, cache_folder)
        or not os.path.isdir(cache_folder)
    ):
        return

    now = datetime.datetime.now().timestamp()
    try:
        filenames = os.listdir(cache_folder)
    except OSError:
        return

    for filename in filenames:
        if not filename.startswith("photo-gallery-") or not filename.endswith(".zip"):
            continue

        zip_path = os.path.join(cache_folder, filename)
        if is_active_photo_download(zip_path):
            continue
        try:
            stat = os.stat(zip_path)
        except OSError:
            continue

        if now - stat.st_mtime < max_age_seconds:
            continue

        try:
            if os.path.isfile(zip_path):
                os.remove(zip_path)
        except OSError:
            pass


def create_photo_download_zip(paths, photo_ids):
    photo_ids = [str(photo_id) for photo_id in photo_ids[:PHOTO_MAX_DOWNLOAD_BATCH]]
    if not _is_safe_workspace_cache_path(paths, paths.photo_gallery_cache_folder):
        return None, {"error": "Unsafe photo gallery cache path"}, 409
    os.makedirs(paths.photo_gallery_cache_folder, exist_ok=True)
    cleanup_expired_photo_download_zips(paths)
    fd, zip_path = tempfile.mkstemp(
        prefix="photo-gallery-",
        suffix=".zip",
        dir=paths.photo_gallery_cache_folder,
    )
    os.close(fd)
    register_active_photo_download(zip_path)

    added_count = 0
    failed = []
    used_names = set()

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for photo_id in photo_ids:
                resolved = resolve_media_path(paths, photo_id)
                if not resolved:
                    failed.append({"id": photo_id, "error": "Media not found"})
                    continue

                _, full_path, meta = resolved
                archive_name = make_unique_archive_name(meta.get("name") or os.path.basename(full_path), used_names)
                archive.write(full_path, archive_name)
                added_count += 1

        if added_count == 0:
            unregister_active_photo_download(zip_path)
            try:
                os.remove(zip_path)
            except OSError:
                pass
            return None, {"error": "No downloadable media found", "failed": failed}, 404

        download_name = f"sharp-gui-media-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        return {
            "zip_path": zip_path,
            "download_name": download_name,
            "added_count": added_count,
            "failed": failed,
        }, None, 200
    except Exception as exc:
        unregister_active_photo_download(zip_path)
        try:
            os.remove(zip_path)
        except OSError:
            pass
        return None, {"error": str(exc)}, 500


def convert_photos_to_models(paths, task_manager, photo_ids):
    photo_ids = [str(photo_id) for photo_id in photo_ids[:PHOTO_MAX_CONVERSION_BATCH]]
    created_tasks = []
    failed = []

    for photo_id in photo_ids:
        resolved = resolve_photo_path(paths, photo_id)
        if not resolved:
            media_resolved = resolve_media_path(paths, photo_id, allow_stale=True)
            if media_resolved and media_resolved[2].get("media_type") == MEDIA_TYPE_VIDEO:
                failed.append({"id": photo_id, "error": "Only photos can be converted to 3D"})
            else:
                failed.append({"id": photo_id, "error": "Photo not found"})
            continue

        _, full_path, meta = resolved
        filename = make_unique_input_filename(paths, meta.get("name") or os.path.basename(full_path))
        if not filename:
            failed.append({"id": photo_id, "error": "Unsupported image format"})
            continue
        input_path = os.path.join(paths.input_folder, filename)

        try:
            shutil.copy2(full_path, input_path)
            task_info = task_manager.enqueue_file(
                input_path,
                filename,
                display_filename=meta.get("name") or os.path.basename(full_path),
            )
            created_tasks.append(task_info)
            print(f"📥 Photo conversion task added: {filename} (ID: {task_info['id']})")
        except Exception as exc:
            failed.append({"id": photo_id, "error": str(exc)})

    return {
        "success": len(created_tasks) > 0,
        "tasks": created_tasks,
        "failed": failed,
    }


def collect_cache_folder_stats(folder, predicate=None, *, allowed_root=None):
    stats = {"files": 0, "bytes": 0}
    if (
        not os.path.isdir(folder)
        or _is_link_like(folder)
        or (allowed_root and not is_real_path_inside(folder, allowed_root))
    ):
        return stats

    for current_root, _dirnames, filenames in os.walk(folder):
        for filename in filenames:
            if predicate and not predicate(filename):
                continue
            path = os.path.join(current_root, filename)
            if _is_link_like(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            stats["files"] += 1
            stats["bytes"] += stat.st_size
    return stats


def get_photo_gallery_cache_stats(paths):
    index_stats = {"files": 0, "bytes": 0}
    if not _is_safe_workspace_cache_path(paths, paths.photo_gallery_cache_folder):
        return {
            "success": True,
            "index_version": PHOTO_INDEX_VERSION,
            "indexes": index_stats,
            "thumbnails": {"files": 0, "bytes": 0},
            "video_posters": {"files": 0, "bytes": 0},
            "downloads": {"files": 0, "bytes": 0},
            "total": {"files": 0, "bytes": 0},
        }
    for path in (paths.photo_catalog_file, paths.photo_index_file, f"{paths.photo_index_file}.bak"):
        if not _is_safe_workspace_cache_path(paths, path):
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        index_stats["files"] += 1
        index_stats["bytes"] += stat.st_size

    album_index_stats = collect_cache_folder_stats(
        paths.photo_album_index_folder,
        lambda filename: filename.endswith(".json"),
        allowed_root=paths.workspace_folder,
    )
    index_stats["files"] += album_index_stats["files"]
    index_stats["bytes"] += album_index_stats["bytes"]

    thumbnail_stats = collect_cache_folder_stats(
        paths.photo_thumbnail_folder,
        allowed_root=paths.workspace_folder,
    )
    poster_stats = collect_cache_folder_stats(
        paths.video_poster_folder,
        allowed_root=paths.workspace_folder,
    )
    download_stats = collect_cache_folder_stats(
        paths.photo_gallery_cache_folder,
        lambda filename: filename.startswith("photo-gallery-") and filename.endswith(".zip"),
        allowed_root=paths.workspace_folder,
    )
    total = {
        "files": index_stats["files"] + thumbnail_stats["files"] + poster_stats["files"] + download_stats["files"],
        "bytes": index_stats["bytes"] + thumbnail_stats["bytes"] + poster_stats["bytes"] + download_stats["bytes"],
    }
    return {
        "success": True,
        "index_version": PHOTO_INDEX_VERSION,
        "indexes": index_stats,
        "thumbnails": thumbnail_stats,
        "video_posters": poster_stats,
        "downloads": download_stats,
        "total": total,
    }


def remove_tree_contents(folder):
    removed = {"files": 0, "bytes": 0}
    if not os.path.isdir(folder):
        return removed

    for current_root, dirnames, filenames in os.walk(folder, topdown=False):
        for filename in filenames:
            path = os.path.join(current_root, filename)
            if _is_link_like(path):
                continue
            try:
                stat = os.stat(path)
                os.remove(path)
                removed["files"] += 1
                removed["bytes"] += stat.st_size
            except OSError:
                pass
        for dirname in dirnames:
            try:
                os.rmdir(os.path.join(current_root, dirname))
            except OSError:
                pass
    return removed


def remove_matching_cache_files(folder, predicate):
    removed = {"files": 0, "bytes": 0}
    if not os.path.isdir(folder):
        return removed

    try:
        filenames = os.listdir(folder)
    except OSError:
        return removed

    for filename in filenames:
        if not predicate(filename):
            continue
        path = os.path.join(folder, filename)
        if _is_link_like(path):
            continue
        try:
            stat = os.stat(path)
            if os.path.isfile(path):
                os.remove(path)
                removed["files"] += 1
                removed["bytes"] += stat.st_size
        except OSError:
            pass
    return removed


def merge_removed_stats(target, source):
    target["files"] += source["files"]
    target["bytes"] += source["bytes"]


def invalidate_photo_gallery_memory_cache():
    """清空依赖磁盘索引的进程内快照，供缓存清理流程复用。"""
    with album_index_cache_lock:
        album_index_cache.clear()
        album_snapshot_cache.clear()


def clear_photo_gallery_cache(paths, scope="generated"):
    """清理图库生成缓存；永远不删除配置相册中的原始媒体。"""
    normalized_scope = str(scope or "generated").strip().lower()
    allowed_scopes = {"generated", "indexes", "thumbnails", "posters", "downloads", "all"}
    if normalized_scope not in allowed_scopes:
        return {"success": False, "error": "Unsupported cache cleanup scope"}, 400
    managed_roots = (
        paths.photo_gallery_cache_folder,
        paths.photo_album_index_folder,
        paths.photo_thumbnail_folder,
        paths.video_poster_folder,
    )
    if any(not _is_safe_workspace_cache_path(paths, path) for path in managed_roots):
        return {"success": False, "error": "Unsafe cache path"}, 409

    removed = {"files": 0, "bytes": 0}

    if normalized_scope in {"generated", "all", "indexes"}:
        for path in (paths.photo_catalog_file, paths.photo_index_file, f"{paths.photo_index_file}.bak"):
            if not _is_safe_workspace_cache_path(paths, path):
                continue
            try:
                stat = os.stat(path)
                os.remove(path)
                removed["files"] += 1
                removed["bytes"] += stat.st_size
            except OSError:
                pass
        merge_removed_stats(removed, remove_tree_contents(paths.photo_album_index_folder))
        invalidate_photo_gallery_memory_cache()

    if normalized_scope in {"generated", "all", "thumbnails"}:
        merge_removed_stats(removed, remove_tree_contents(paths.photo_thumbnail_folder))

    if normalized_scope in {"generated", "all", "posters"}:
        merge_removed_stats(removed, remove_tree_contents(paths.video_poster_folder))

    if normalized_scope in {"generated", "all", "downloads"}:
        merge_removed_stats(
            removed,
            remove_matching_cache_files(
                paths.photo_gallery_cache_folder,
                lambda filename: filename.startswith("photo-gallery-") and filename.endswith(".zip"),
            ),
        )

    os.makedirs(paths.photo_album_index_folder, exist_ok=True)
    os.makedirs(paths.photo_thumbnail_folder, exist_ok=True)
    os.makedirs(paths.video_poster_folder, exist_ok=True)

    return {
        "success": True,
        "scope": normalized_scope,
        "removed": removed,
        "stats": get_photo_gallery_cache_stats(paths),
    }, 200

import datetime
import json
import os
import re
import threading
import uuid
from urllib.parse import quote

from PIL import Image
from werkzeug.utils import secure_filename

from backend.services import model_gallery
from backend.services.static_files import get_relative_files_path, is_real_path_inside, to_url_path

# 资产索引是单一 JSON 文件的 read-modify-write，局域网多设备可能并发导入/编辑，
# 用进程级可重入锁串行化写路径，避免相互覆盖导致记录丢失。
_INDEX_LOCK = threading.RLock()

# 导入资产在索引中的稳定身份字段，编辑封面/资料时需要原样保留。
IMPORTED_IDENTITY_KEYS = ("model_path", "format", "original_name", "imported_at", "created_at")
# 除身份字段外还需要保留的用户编辑字段（封面刷新/上传时不应清空资料）。
IMPORTED_PROFILE_KEYS = IMPORTED_IDENTITY_KEYS + ("display_name", "tags", "note")


def carry_imported_record_fields(existing, record, keys):
    """把已存在导入记录中的指定字段回填到新记录，避免写操作丢失身份或资料。"""
    for key in keys:
        if key in existing:
            record[key] = existing[key]
    return record

SUPPORTED_MODEL_EXTENSIONS = {
    ".ply": "ply",
    ".spz": "spz",
    ".splat": "splat",
    ".rad": "rad",
}
SUPPORTED_MODEL_FORMATS = tuple(sorted(set(SUPPORTED_MODEL_EXTENSIONS.values())))
VIEWER_FORMAT_PRIORITY = ("spz", "ply", "splat", "rad")
SOURCE_ALL = "all"
SOURCE_GENERATED = "generated"
SOURCE_IMPORTED = "imported"
SOURCE_VIDEO = "video"
THUMBNAIL_MANUAL = "manual"
THUMBNAIL_SYSTEM = "system"
THUMBNAIL_MISSING = "missing"
THUMBNAIL_PENDING = "pending"
DEFAULT_BATCH_SIZE = 24
MAX_BATCH_SIZE = 96
MAX_IMPORT_FILES = 64
MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_IMPORT_BATCH_BYTES = 10 * 1024 * 1024 * 1024
MAX_COVER_BYTES = 10 * 1024 * 1024
PLY_HEADER_MAX_BYTES = 512 * 1024
SPLAT_BYTES_PER_POINT = 32
ALLOWED_COVER_EXTENSIONS = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".webp": "webp",
}


def utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_timestamp(path):
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(path),
        tz=datetime.timezone.utc,
    ).isoformat()


def normalize_format(value):
    fmt = str(value or "").strip().lower().lstrip(".")
    return fmt if fmt in SUPPORTED_MODEL_FORMATS else None


def format_for_path(path):
    return SUPPORTED_MODEL_EXTENSIONS.get(os.path.splitext(path)[1].lower())


def safe_asset_filename(asset_id):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(asset_id or "")).strip(".-")
    return value or f"asset-{uuid.uuid4().hex[:10]}"


def normalize_upload_filename(filename):
    """Return the user-visible basename without trusting client path segments."""
    return str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()


def read_asset_index(paths):
    try:
        with open(paths.model_asset_index_file, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {"version": 1, "assets": {}}
    except Exception:
        return {"version": 1, "assets": {}}

    if not isinstance(data, dict):
        return {"version": 1, "assets": {}}
    assets = data.get("assets")
    if not isinstance(assets, dict):
        data["assets"] = {}
    data.setdefault("version", 1)
    return data


def write_asset_index(paths, data):
    os.makedirs(os.path.dirname(paths.model_asset_index_file), exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": utc_now_iso(),
        "assets": data.get("assets", {}) if isinstance(data, dict) else {},
    }
    temp_path = f"{paths.model_asset_index_file}.tmp-{uuid.uuid4().hex[:8]}"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp_path, paths.model_asset_index_file)
    return paths.model_asset_index_file


def workspace_relative_path(paths, path):
    real_path = os.path.realpath(os.path.abspath(path))
    if not is_real_path_inside(real_path, paths.workspace_folder):
        raise ValueError("Path is outside workspace")
    return to_url_path(os.path.relpath(real_path, paths.workspace_folder))


def resolve_workspace_relative_path(paths, relative_path):
    if not isinstance(relative_path, str) or not relative_path:
        return None
    native = relative_path.replace("/", os.sep).replace("\\", os.sep)
    candidate = os.path.realpath(os.path.join(paths.workspace_folder, native))
    if not is_real_path_inside(candidate, paths.workspace_folder):
        return None
    return candidate


def url_for_file(paths, path):
    return f"/files/{get_relative_files_path(path, paths)}"


def get_user_record(index, asset_id):
    assets = index.get("assets", {})
    record = assets.get(asset_id) if isinstance(assets, dict) else None
    return record if isinstance(record, dict) else {}


def collect_supported_files(folder, stem):
    result = {}
    normalized_stem = model_gallery.normalize_model_item_id(stem)
    if not normalized_stem or not os.path.isdir(folder):
        return result

    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue
        file_stem, extension = os.path.splitext(filename)
        fmt = SUPPORTED_MODEL_EXTENSIONS.get(extension.lower())
        if file_stem == normalized_stem and fmt:
            result[fmt] = path
    return result


def collect_generated_file_groups(paths):
    groups = {}
    if not os.path.isdir(paths.output_folder):
        return groups

    for filename in os.listdir(paths.output_folder):
        path = os.path.join(paths.output_folder, filename)
        if not os.path.isfile(path):
            continue
        fmt = format_for_path(filename)
        if not fmt:
            continue
        stem = model_gallery.normalize_model_item_id(filename)
        if not stem:
            continue
        groups.setdefault(stem, {})[fmt] = path
    return groups


def build_file_descriptor(paths, path, fmt=None, primary=False):
    resolved_format = fmt or format_for_path(path)
    if not resolved_format:
        return None
    filename = os.path.basename(path)
    return {
        "format": resolved_format,
        "filename": filename,
        "size": os.path.getsize(path),
        "url": url_for_file(paths, path),
        "download_url": None,
        "modified_at": file_timestamp(path),
        "primary": primary,
    }


def select_primary_format(files):
    for fmt in VIEWER_FORMAT_PRIORITY:
        if fmt in files:
            return fmt
    return next(iter(files.keys()), None)


def first_present(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def compression_for_format(fmt):
    if fmt == "spz":
        return "spz"
    if fmt in ("ply", "splat", "rad"):
        return "none"
    return None


def parse_ply_header_metadata(path):
    try:
        with open(path, "rb") as file:
            header = file.read(PLY_HEADER_MAX_BYTES)
    except OSError:
        return {}

    marker = b"end_header"
    marker_index = header.find(marker)
    if marker_index < 0:
        return {}

    text = header[:marker_index + len(marker)].decode("ascii", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "ply":
        return {}

    metadata = {
        "derived_format": "ply",
        "derived_from": os.path.basename(path),
        "ply_vertex_properties": [],
    }
    result = {
        "compression": "none",
        "metadata": metadata,
    }
    current_element = None

    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        keyword = parts[0]
        if keyword == "format" and len(parts) >= 3:
            metadata["ply_header_format"] = parts[1]
            result["version"] = parts[2]
        elif keyword == "element" and len(parts) >= 3:
            current_element = parts[1]
            if current_element == "vertex":
                try:
                    result["point_count"] = int(parts[2])
                except ValueError:
                    pass
        elif keyword == "property" and current_element == "vertex" and len(parts) >= 3:
            metadata["ply_vertex_properties"].append(parts[-1])

    properties = metadata.get("ply_vertex_properties") or []
    if properties:
        result["attributes"] = properties
    return result


def derive_model_metadata(files):
    if not isinstance(files, dict) or not files:
        return {}

    ply_path = files.get("ply")
    if ply_path and os.path.isfile(ply_path):
        parsed = parse_ply_header_metadata(ply_path)
        if parsed:
            parsed.setdefault("metadata", {})
            parsed["metadata"]["available_formats"] = sorted(files.keys())
            return parsed

    splat_path = files.get("splat")
    if splat_path and os.path.isfile(splat_path):
        size = os.path.getsize(splat_path)
        result = {
            "compression": "none",
            "attributes": ["position", "scale", "rotation", "color", "opacity"],
            "metadata": {
                "derived_format": "splat",
                "derived_from": os.path.basename(splat_path),
                "available_formats": sorted(files.keys()),
                "splat_record_bytes": SPLAT_BYTES_PER_POINT,
            },
        }
        if size > 0 and size % SPLAT_BYTES_PER_POINT == 0:
            result["point_count"] = size // SPLAT_BYTES_PER_POINT
        return result

    spz_path = files.get("spz")
    if spz_path and os.path.isfile(spz_path):
        return {
            "compression": "spz",
            "metadata": {
                "derived_format": "spz",
                "derived_from": os.path.basename(spz_path),
                "available_formats": sorted(files.keys()),
                "spz_size_bytes": os.path.getsize(spz_path),
            },
        }

    return {}


def cover_from_record(paths, asset_id, record):
    cover_path = resolve_workspace_relative_path(paths, record.get("cover_path"))
    if cover_path and is_real_path_inside(cover_path, paths.model_asset_thumbnail_folder) and os.path.isfile(cover_path):
        return {
            "thumb_url": url_for_file(paths, cover_path),
            "thumb_version": int(os.path.getmtime(cover_path) * 1000),
            "thumbnail_state": "ready",
            "thumbnail_kind": record.get("cover_kind") or THUMBNAIL_MANUAL,
        }

    generated_path = os.path.join(paths.model_asset_thumbnail_folder, f"{safe_asset_filename(asset_id)}.jpg")
    if os.path.isfile(generated_path):
        return {
            "thumb_url": url_for_file(paths, generated_path),
            "thumb_version": int(os.path.getmtime(generated_path) * 1000),
            "thumbnail_state": "ready",
            "thumbnail_kind": record.get("cover_kind") or THUMBNAIL_SYSTEM,
        }

    return {
        "thumb_url": None,
        "thumb_version": None,
        "thumbnail_state": record.get("cover_status") or THUMBNAIL_MISSING,
        "thumbnail_kind": record.get("cover_kind") or THUMBNAIL_MISSING,
    }


def build_generated_asset(paths, asset_id, files, record=None, include_details=False):
    record = record or {}
    primary_format = select_primary_format(files)
    primary_path = files.get(primary_format) if primary_format else None
    if not primary_path:
        return None

    metadata = model_gallery.read_model_metadata(paths, asset_id)
    metadata_path = model_gallery.get_model_metadata_path(paths, asset_id)
    source_type = SOURCE_VIDEO if metadata.get("source_media_type") == "video" else SOURCE_GENERATED
    file_timestamps = [os.path.getmtime(path) for path in files.values()]
    if os.path.isfile(metadata_path):
        file_timestamps.append(os.path.getmtime(metadata_path))

    original_filename, original_path = model_gallery.find_original_image(paths, asset_id)
    if original_path:
        file_timestamps.append(os.path.getmtime(original_path))

    cover = cover_from_record(paths, asset_id, record)
    if not cover["thumb_url"]:
        thumb_path = model_gallery.get_thumbnail_path(paths, asset_id)
        if os.path.isfile(thumb_path):
            cover = {
                "thumb_url": f"/api/thumbnail/{quote(asset_id, safe='')}",
                "thumb_version": model_gallery.get_file_version(thumb_path),
                "thumbnail_state": "ready",
                "thumbnail_kind": THUMBNAIL_SYSTEM,
            }
            file_timestamps.append(os.path.getmtime(thumb_path))

    descriptors = []
    for fmt, path in sorted(files.items(), key=lambda entry: VIEWER_FORMAT_PRIORITY.index(entry[0])):
        descriptor = build_file_descriptor(paths, path, fmt, primary=fmt == primary_format)
        if descriptor:
            descriptor["download_url"] = f"/api/model-assets/{quote(asset_id, safe='')}/download?format={fmt}"
            descriptors.append(descriptor)

    total_size = sum(descriptor["size"] for descriptor in descriptors)
    primary_descriptor = next((item for item in descriptors if item["primary"]), descriptors[0])
    source_video_url = None
    if source_type == SOURCE_VIDEO:
        source_video_url = f"/api/gallery/{quote(asset_id, safe='')}/source-video"
    derived = derive_model_metadata(files) if include_details else {}
    derived_metadata = derived.get("metadata") if isinstance(derived.get("metadata"), dict) else {}
    detail_metadata = {
        **derived_metadata,
        **(metadata if include_details else {}),
    } if include_details else {}

    asset = {
        "id": asset_id,
        "name": record.get("display_name") or metadata.get("display_name") or asset_id,
        "source_type": source_type,
        "source_label": source_type,
        "primary_format": primary_format,
        "formats": [descriptor["format"] for descriptor in descriptors],
        "files": descriptors,
        "size": total_size,
        "primary_size": primary_descriptor["size"],
        "created_at": file_timestamp(primary_path),
        "updated_at": datetime.datetime.fromtimestamp(max(file_timestamps), tz=datetime.timezone.utc).isoformat(),
        "default_open_url": primary_descriptor["url"],
        "default_open_format": primary_format,
        "download_url": f"/api/model-assets/{quote(asset_id, safe='')}/download?format={primary_format}",
        "available": True,
        "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
        "note": record.get("note") or "",
        "is_generated": True,
        "is_imported": False,
        "source_media_type": metadata.get("source_media_type"),
        "source_media_id": metadata.get("source_media_id"),
        "source_name": metadata.get("source_name") or original_filename,
        "source_video_url": source_video_url,
        "image_url": f"/api/original/{quote(asset_id, safe='')}" if original_filename else None,
        "point_count": first_present(metadata.get("point_count"), metadata.get("gaussian_points"), derived.get("point_count")),
        "bounding_box": first_present(metadata.get("bounding_box"), derived.get("bounding_box")),
        "coordinate_system": first_present(metadata.get("coordinate_system"), derived.get("coordinate_system")),
        "attributes": first_present(metadata.get("attributes"), derived.get("attributes")),
        "compression": first_present(metadata.get("compression"), derived.get("compression"), compression_for_format(primary_format)),
        "version": first_present(metadata.get("version"), derived.get("version")),
        "metadata": detail_metadata,
        **cover,
    }
    return asset


def build_imported_asset(paths, asset_id, record, include_details=False):
    relative_path = record.get("model_path")
    model_path = resolve_workspace_relative_path(paths, relative_path)
    fmt = normalize_format(record.get("format")) or (format_for_path(model_path) if model_path else None)
    available = bool(
        model_path
        and fmt
        and is_real_path_inside(model_path, paths.model_asset_import_folder)
        and os.path.isfile(model_path)
    )

    descriptors = []
    if available:
        descriptor = build_file_descriptor(paths, model_path, fmt, primary=True)
        descriptor["download_url"] = f"/api/model-assets/{quote(asset_id, safe='')}/download?format={fmt}"
        descriptors.append(descriptor)

    cover = cover_from_record(paths, asset_id, record)
    size = descriptors[0]["size"] if descriptors else 0
    created_at = record.get("created_at") or record.get("imported_at") or utc_now_iso()
    modified_at = descriptors[0]["modified_at"] if descriptors else record.get("updated_at") or created_at
    files = {fmt: model_path} if available and fmt and model_path else {}
    derived = derive_model_metadata(files) if include_details else {}
    derived_metadata = derived.get("metadata") if isinstance(derived.get("metadata"), dict) else {}
    record_metadata = record.get("metadata", {}) if isinstance(record.get("metadata"), dict) else {}
    detail_metadata = {
        **derived_metadata,
        **record_metadata,
    } if include_details else {}

    return {
        "id": asset_id,
        "name": record.get("display_name") or os.path.splitext(record.get("original_name") or asset_id)[0],
        "source_type": SOURCE_IMPORTED,
        "source_label": SOURCE_IMPORTED,
        "primary_format": fmt,
        "formats": [fmt] if fmt else [],
        "files": descriptors,
        "size": size,
        "primary_size": size,
        "created_at": created_at,
        "updated_at": record.get("updated_at") or modified_at,
        "default_open_url": descriptors[0]["url"] if descriptors else None,
        "default_open_format": fmt,
        "download_url": f"/api/model-assets/{quote(asset_id, safe='')}/download?format={fmt}" if fmt else None,
        "available": available,
        "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
        "note": record.get("note") or "",
        "is_generated": False,
        "is_imported": True,
        "source_media_type": None,
        "source_media_id": None,
        "source_name": record.get("original_name"),
        "source_video_url": None,
        "image_url": None,
        "point_count": first_present(record.get("point_count"), record_metadata.get("point_count"), derived.get("point_count")),
        "bounding_box": first_present(record.get("bounding_box"), record_metadata.get("bounding_box"), derived.get("bounding_box")),
        "coordinate_system": first_present(record.get("coordinate_system"), record_metadata.get("coordinate_system"), derived.get("coordinate_system")),
        "attributes": first_present(record.get("attributes"), record_metadata.get("attributes"), derived.get("attributes")),
        "compression": first_present(record.get("compression"), record_metadata.get("compression"), derived.get("compression"), compression_for_format(fmt)),
        "version": first_present(record.get("version"), record_metadata.get("version"), derived.get("version")),
        "metadata": detail_metadata,
        **cover,
    }


def build_all_assets(paths, include_details=False):
    index = read_asset_index(paths)
    assets = []
    generated_groups = collect_generated_file_groups(paths)

    for asset_id, files in generated_groups.items():
        record = get_user_record(index, asset_id)
        asset = build_generated_asset(paths, asset_id, files, record, include_details=include_details)
        if asset:
            assets.append(asset)

    for asset_id, record in index.get("assets", {}).items():
        if not isinstance(record, dict) or record.get("source_type") != SOURCE_IMPORTED:
            continue
        assets.append(build_imported_asset(paths, asset_id, record, include_details=include_details))

    return assets


def parse_positive_int(value, fallback, minimum=0, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def sort_assets(assets, sort):
    reverse = True
    key_name = "updated_at"
    if sort == "modified_asc":
        reverse = False
    elif sort == "created_desc":
        key_name = "created_at"
    elif sort == "created_asc":
        key_name = "created_at"
        reverse = False
    elif sort == "name_asc":
        key_name = "name"
        reverse = False
    elif sort == "name_desc":
        key_name = "name"
    elif sort == "size_desc":
        key_name = "size"
    elif sort == "size_asc":
        key_name = "size"
        reverse = False

    def get_key(asset):
        value = asset.get(key_name)
        if key_name == "name":
            return str(value or "").lower()
        if key_name == "size":
            return int(value or 0)
        return str(value or "")

    return sorted(assets, key=get_key, reverse=reverse)


def filter_assets(assets, source=SOURCE_ALL, fmt="all", tag=None):
    filtered = assets
    if source and source != SOURCE_ALL:
        filtered = [asset for asset in filtered if asset.get("source_type") == source]

    normalized_format = normalize_format(fmt)
    if normalized_format:
        filtered = [asset for asset in filtered if normalized_format in asset.get("formats", [])]

    if tag:
        filtered = [asset for asset in filtered if tag in asset.get("tags", [])]

    return filtered


def build_asset_counts(assets):
    counts = {
        SOURCE_ALL: len(assets),
        SOURCE_GENERATED: 0,
        SOURCE_IMPORTED: 0,
        SOURCE_VIDEO: 0,
    }
    format_counts = {fmt: 0 for fmt in SUPPORTED_MODEL_FORMATS}
    tags = set()

    for asset in assets:
        source_type = asset.get("source_type")
        if source_type in counts:
            counts[source_type] += 1
        for fmt in asset.get("formats", []):
            if fmt in format_counts:
                format_counts[fmt] += 1
        for tag in asset.get("tags", []):
            if isinstance(tag, str) and tag:
                tags.add(tag)

    return counts, format_counts, sorted(tags, key=str.lower)


def list_model_assets(paths, args):
    all_assets = build_all_assets(paths, include_details=False)
    counts, format_counts, tags = build_asset_counts(all_assets)
    source = args.get("source", SOURCE_ALL)
    fmt = args.get("format", "all")
    tag = args.get("tag")
    sort = args.get("sort", "modified_desc")
    limit = parse_positive_int(args.get("limit"), DEFAULT_BATCH_SIZE, minimum=1, maximum=MAX_BATCH_SIZE)
    cursor = parse_positive_int(args.get("cursor"), 0, minimum=0)

    filtered = filter_assets(all_assets, source=source, fmt=fmt, tag=tag)
    filtered = sort_assets(filtered, sort)
    total = len(filtered)
    total_size = sum(int(asset.get("size") or asset.get("primary_size") or 0) for asset in filtered)
    page_items = filtered[cursor:cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None

    return {
        "items": page_items,
        "total": total,
        "total_size": total_size,
        "next_cursor": str(next_cursor) if next_cursor is not None else None,
        "cursor": str(cursor),
        "limit": limit,
        "counts": counts,
        "format_counts": format_counts,
        "available_tags": tags,
        "sort": sort,
        "source": source,
        "format": fmt,
        "tag": tag,
    }


def get_model_asset(paths, asset_id, include_details=True):
    index = read_asset_index(paths)
    record = get_user_record(index, asset_id)
    if record.get("source_type") == SOURCE_IMPORTED:
        return build_imported_asset(paths, asset_id, record, include_details=include_details)

    generated_asset_id = model_gallery.normalize_model_item_id(asset_id)
    if not generated_asset_id:
        return None

    record = get_user_record(index, generated_asset_id)
    generated_files = collect_supported_files(paths.output_folder, generated_asset_id)
    if generated_files:
        return build_generated_asset(
            paths,
            generated_asset_id,
            generated_files,
            record,
            include_details=include_details,
        )

    return None


def normalize_tags(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Tags must be an array")
    tags = []
    for raw in value[:24]:
        if not isinstance(raw, str):
            continue
        tag = raw.strip()
        if tag and tag not in tags:
            tags.append(tag[:40])
    return tags


def update_model_asset_profile(paths, asset_id, payload):
    asset = get_model_asset(paths, asset_id, include_details=False)
    if not asset:
        return None
    asset_id = asset["id"]

    with _INDEX_LOCK:
        index = read_asset_index(paths)
        assets = index.setdefault("assets", {})
        existing = get_user_record(index, asset_id)
        record = dict(existing)
        record.setdefault("source_type", SOURCE_IMPORTED if asset.get("is_imported") else SOURCE_GENERATED)
        record["asset_id"] = asset_id
        record["display_name"] = str(payload.get("display_name") or payload.get("name") or asset["name"]).strip()[:120]
        record["tags"] = normalize_tags(payload.get("tags", asset.get("tags", [])))
        record["note"] = str(payload.get("note") or "").strip()[:2000]
        record["updated_at"] = utc_now_iso()
        # 编辑资料时只保留导入模型的身份字段，display_name/tags/note 以本次编辑为准。
        if asset.get("is_imported"):
            carry_imported_record_fields(existing, record, IMPORTED_IDENTITY_KEYS)
        assets[asset_id] = record
        write_asset_index(paths, index)
    return get_model_asset(paths, asset_id, include_details=True)


def unique_import_target(paths, filename, extension):
    """Allocate a safe storage name while preserving the validated model suffix."""
    if extension not in SUPPORTED_MODEL_EXTENSIONS:
        raise ValueError("Unsupported model format")

    original_stem = os.path.splitext(normalize_upload_filename(filename))[0]
    stem = secure_filename(original_stem) or f"model-{uuid.uuid4().hex[:8]}"
    candidate = f"{stem}{extension}"
    counter = 1
    while os.path.exists(os.path.join(paths.model_asset_import_folder, candidate)):
        candidate = f"{stem}-{counter}{extension}"
        counter += 1
    return candidate


def save_file_storage(file_storage, target_path, max_bytes):
    temp_path = f"{target_path}.tmp-{uuid.uuid4().hex[:8]}"
    total = 0
    try:
        with open(temp_path, "wb") as output:
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("File is too large")
                output.write(chunk)
        os.replace(temp_path, target_path)
        return total
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def import_model_assets(paths, files):
    if len(files) > MAX_IMPORT_FILES:
        return {
            "success": False,
            "assets": [],
            "failed": [{"filename": "", "code": "too_many_files", "error": "Too many files in one batch"}],
        }

    os.makedirs(paths.model_asset_import_folder, exist_ok=True)
    imported = []
    failed = []
    new_records = {}
    batch_bytes = 0

    for file_storage in files:
        original_name = normalize_upload_filename(file_storage.filename)
        extension = os.path.splitext(original_name)[1].lower()
        fmt = SUPPORTED_MODEL_EXTENSIONS.get(extension)
        if not fmt:
            failed.append({
                "filename": original_name,
                "code": "unsupported_format",
                "error": "Unsupported model format",
            })
            continue

        target_filename = unique_import_target(paths, original_name, extension)
        target_path = os.path.realpath(os.path.join(paths.model_asset_import_folder, target_filename))
        if not is_real_path_inside(target_path, paths.model_asset_import_folder):
            failed.append({
                "filename": original_name,
                "code": "invalid_target",
                "error": "Import target is outside the controlled model asset directory",
            })
            continue

        try:
            size = save_file_storage(file_storage, target_path, MAX_IMPORT_FILE_BYTES)
        except ValueError as exc:
            failed.append({"filename": original_name, "code": "file_too_large", "error": str(exc)})
            continue
        except Exception as exc:
            failed.append({"filename": original_name, "code": "save_failed", "error": str(exc)})
            continue

        batch_bytes += size
        if batch_bytes > MAX_IMPORT_BATCH_BYTES:
            try:
                os.remove(target_path)
            except OSError:
                pass
            failed.append({
                "filename": original_name,
                "code": "batch_too_large",
                "error": "Import batch is too large",
            })
            continue

        asset_id = f"imported-{uuid.uuid4().hex[:12]}"
        record = {
            "asset_id": asset_id,
            "source_type": SOURCE_IMPORTED,
            "model_path": workspace_relative_path(paths, target_path),
            "format": fmt,
            "original_name": original_name,
            "display_name": os.path.splitext(os.path.basename(original_name))[0] or os.path.splitext(target_filename)[0],
            "tags": [],
            "note": "",
            "cover_status": THUMBNAIL_PENDING,
            "cover_kind": THUMBNAIL_SYSTEM,
            "imported_at": utc_now_iso(),
            "created_at": file_timestamp(target_path),
            "updated_at": file_timestamp(target_path),
        }
        new_records[asset_id] = record
        imported.append(build_imported_asset(paths, asset_id, record, include_details=True))

    # 文件已经安全落盘，最后在锁内合并进索引，避免并发导入互相覆盖记录。
    if new_records:
        with _INDEX_LOCK:
            index = read_asset_index(paths)
            index.setdefault("assets", {}).update(new_records)
            write_asset_index(paths, index)

    return {
        "success": bool(imported),
        "assets": imported,
        "failed": failed,
    }


def validate_cover_image(path):
    with Image.open(path) as image:
        image.verify()


def save_model_asset_cover(paths, asset_id, file_storage, kind=THUMBNAIL_MANUAL):
    asset = get_model_asset(paths, asset_id, include_details=False)
    if not asset:
        return None, {"error": "Model asset not found", "code": "model_asset_not_found"}, 404
    asset_id = asset["id"]

    original_name = file_storage.filename or ""
    extension = os.path.splitext(original_name)[1].lower()
    normalized_extension = ALLOWED_COVER_EXTENSIONS.get(extension)
    if not normalized_extension:
        return None, {"error": "Unsupported cover image type", "code": "unsupported_cover_type"}, 400

    os.makedirs(paths.model_asset_thumbnail_folder, exist_ok=True)
    target_name = f"{safe_asset_filename(asset_id)}.{normalized_extension}"
    target_path = os.path.realpath(os.path.join(paths.model_asset_thumbnail_folder, target_name))
    if not is_real_path_inside(target_path, paths.model_asset_thumbnail_folder):
        return None, {"error": "Invalid cover target", "code": "invalid_cover_target"}, 400

    try:
        save_file_storage(file_storage, target_path, MAX_COVER_BYTES)
        validate_cover_image(target_path)
    except ValueError as exc:
        return None, {"error": str(exc), "code": "cover_too_large"}, 413
    except Exception:
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
        except OSError:
            pass
        return None, {"error": "Invalid cover image", "code": "invalid_cover_image"}, 400

    with _INDEX_LOCK:
        index = read_asset_index(paths)
        assets = index.setdefault("assets", {})
        existing = get_user_record(index, asset_id)
        record = dict(existing)
        record.setdefault("source_type", SOURCE_IMPORTED if asset.get("is_imported") else SOURCE_GENERATED)
        if asset.get("is_imported"):
            carry_imported_record_fields(existing, record, IMPORTED_PROFILE_KEYS)
        record["asset_id"] = asset_id
        record["cover_path"] = workspace_relative_path(paths, target_path)
        record["cover_kind"] = kind
        record["cover_status"] = "ready"
        record["updated_at"] = utc_now_iso()
        assets[asset_id] = record
        write_asset_index(paths, index)
    return get_model_asset(paths, asset_id, include_details=True), None, 200


def refresh_model_asset_cover(paths, asset_id):
    asset = get_model_asset(paths, asset_id, include_details=False)
    if not asset:
        return None
    asset_id = asset["id"]

    with _INDEX_LOCK:
        index = read_asset_index(paths)
        assets = index.setdefault("assets", {})
        existing = get_user_record(index, asset_id)
        record = dict(existing)
        cover_path = resolve_workspace_relative_path(paths, record.get("cover_path"))
        if cover_path and is_real_path_inside(cover_path, paths.model_asset_thumbnail_folder):
            try:
                if os.path.isfile(cover_path):
                    os.remove(cover_path)
            except OSError:
                pass
        record.pop("cover_path", None)
        record.setdefault("source_type", SOURCE_IMPORTED if asset.get("is_imported") else SOURCE_GENERATED)
        if asset.get("is_imported"):
            carry_imported_record_fields(existing, record, IMPORTED_PROFILE_KEYS)
        record["asset_id"] = asset_id
        record["cover_status"] = THUMBNAIL_PENDING
        record["cover_kind"] = THUMBNAIL_SYSTEM
        record["updated_at"] = utc_now_iso()
        assets[asset_id] = record
        write_asset_index(paths, index)
    return get_model_asset(paths, asset_id, include_details=True)


def delete_model_asset(paths, asset_id):
    asset = get_model_asset(paths, asset_id, include_details=True)
    if not asset:
        return False
    asset_id = asset["id"]

    with _INDEX_LOCK:
        index = read_asset_index(paths)
        record = get_user_record(index, asset_id)
        cover_path = resolve_workspace_relative_path(paths, record.get("cover_path"))
        if cover_path and is_real_path_inside(cover_path, paths.model_asset_thumbnail_folder):
            try:
                if os.path.isfile(cover_path):
                    os.remove(cover_path)
            except OSError:
                pass

        generated_cover = os.path.join(paths.model_asset_thumbnail_folder, f"{safe_asset_filename(asset_id)}.jpg")
        try:
            if os.path.isfile(generated_cover):
                os.remove(generated_cover)
        except OSError:
            pass

        if asset.get("is_imported"):
            model_path = resolve_workspace_relative_path(paths, record.get("model_path"))
            if model_path and is_real_path_inside(model_path, paths.model_asset_import_folder):
                try:
                    if os.path.isfile(model_path):
                        os.remove(model_path)
                except OSError:
                    pass
            index.get("assets", {}).pop(asset_id, None)
            write_asset_index(paths, index)
            return True

        model_gallery.delete_gallery_item(paths, asset_id)
        if asset_id in index.get("assets", {}):
            index["assets"].pop(asset_id, None)
            write_asset_index(paths, index)
    return True


def resolve_asset_source_files(paths, asset_id):
    """从受控目录直接反查资产的真实模型文件，避免从对外 URL 逆向拼路径。"""
    index = read_asset_index(paths)
    record = get_user_record(index, asset_id)
    if record.get("source_type") == SOURCE_IMPORTED:
        model_path = resolve_workspace_relative_path(paths, record.get("model_path"))
        asset_format = normalize_format(record.get("format")) or (
            format_for_path(model_path) if model_path else None
        )
        if (
            model_path
            and asset_format
            and is_real_path_inside(model_path, paths.model_asset_import_folder)
            and os.path.isfile(model_path)
        ):
            return {asset_format: model_path}
        return {}

    generated_asset_id = model_gallery.normalize_model_item_id(asset_id)
    if not generated_asset_id:
        return {}
    return collect_supported_files(paths.output_folder, generated_asset_id)


def resolve_download_file(paths, asset_id, fmt=None):
    asset = get_model_asset(paths, asset_id, include_details=False)
    if not asset:
        return None

    files = resolve_asset_source_files(paths, asset["id"])
    if not files:
        return None

    requested_format = normalize_format(fmt) or select_primary_format(files)
    path = files.get(requested_format) or files.get(select_primary_format(files))
    if not path or not os.path.isfile(path):
        return None

    extension = os.path.splitext(path)[1].lower()
    display_name = str(asset.get("name") or "").strip()
    metadata = {"display_name": display_name} if display_name else None
    download_name = model_gallery.make_model_download_name(
        paths,
        asset["id"],
        extension,
        metadata=metadata,
    )
    return path, download_name

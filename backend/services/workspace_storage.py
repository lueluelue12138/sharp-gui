import datetime
import os
import threading
import time

from backend.services import model_assets, model_gallery, photo_gallery
from backend.services.static_files import is_real_path_inside


WORKSPACE_STORAGE_CACHE_TTL_SECONDS = 60
WORKSPACE_STORAGE_RETRY_AFTER_MS = 600
WORKSPACE_STORAGE_FAILURE_RETRY_SECONDS = 5
SCAN_YIELD_EVERY = 256
ACTIVE_DOWNLOAD_GRACE_SECONDS = 5 * 60

_snapshot_lock = threading.Lock()
_snapshot_states = {}


def _empty_bucket():
    return {"files": 0, "bytes": 0}


def _empty_diagnostics():
    return {"skipped_entries": 0, "symlinks_skipped": 0}


def _merge_bucket(target, source):
    target["files"] += int(source.get("files", 0))
    target["bytes"] += int(source.get("bytes", 0))
    return target


def _merge_diagnostics(target, source):
    target["skipped_entries"] += int(source.get("skipped_entries", 0))
    target["symlinks_skipped"] += int(source.get("symlinks_skipped", 0))
    return target


def _sum_buckets(*buckets):
    total = _empty_bucket()
    for bucket in buckets:
        _merge_bucket(total, bucket)
    return total


def _normalized_path(path):
    return os.path.normcase(os.path.abspath(path))


def _is_link_like(path):
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return os.path.islink(path) or is_junction(path)


def _is_safe_managed_root(folder, allowed_root):
    return (
        not _is_link_like(folder)
        and is_real_path_inside(folder, allowed_root)
    )


def _scan_tree(folder, *, allowed_root=None, excluded_roots=None, include_file=None):
    """低干扰遍历受控目录；不跟随符号链接，并周期性让出执行权。"""
    stats = _empty_bucket()
    diagnostics = _empty_diagnostics()
    excluded = {_normalized_path(path) for path in (excluded_roots or ())}
    root = _normalized_path(folder)
    if root in excluded or not os.path.isdir(folder):
        return stats, diagnostics
    if _is_link_like(folder) or (
        allowed_root and not is_real_path_inside(folder, allowed_root)
    ):
        diagnostics["symlinks_skipped"] += 1
        return stats, diagnostics

    pending = [folder]
    visited_entries = 0
    while pending:
        current = pending.pop()
        if _normalized_path(current) in excluded:
            continue
        try:
            entries = os.scandir(current)
        except OSError:
            diagnostics["skipped_entries"] += 1
            continue

        with entries:
            for entry in entries:
                visited_entries += 1
                if visited_entries % SCAN_YIELD_EVERY == 0:
                    time.sleep(0.001)
                try:
                    if entry.is_symlink() or _is_link_like(entry.path):
                        diagnostics["symlinks_skipped"] += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if _normalized_path(entry.path) not in excluded:
                            pending.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        diagnostics["skipped_entries"] += 1
                        continue
                    if include_file and not include_file(entry.path, entry.name):
                        continue
                    stats["files"] += 1
                    stats["bytes"] += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    diagnostics["skipped_entries"] += 1
    return stats, diagnostics


def _scan_known_files(paths, *, allowed_root=None):
    stats = _empty_bucket()
    diagnostics = _empty_diagnostics()
    seen = set()
    for path in paths:
        normalized = _normalized_path(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if allowed_root and not is_real_path_inside(path, allowed_root):
            diagnostics["symlinks_skipped"] += 1
            continue
        try:
            stat = os.stat(path, follow_symlinks=False)
            if _is_link_like(path) or not os.path.isfile(path):
                diagnostics["symlinks_skipped"] += int(_is_link_like(path))
                continue
        except FileNotFoundError:
            continue
        except OSError:
            diagnostics["skipped_entries"] += 1
            continue
        stats["files"] += 1
        stats["bytes"] += stat.st_size
    return stats, diagnostics


def _scan_immediate_files(folder, predicate, *, allowed_root=None):
    stats = _empty_bucket()
    diagnostics = _empty_diagnostics()
    if _is_link_like(folder) or (
        allowed_root and not is_real_path_inside(folder, allowed_root)
    ):
        diagnostics["symlinks_skipped"] += 1
        return stats, diagnostics
    try:
        entries = os.scandir(folder)
    except FileNotFoundError:
        return stats, diagnostics
    except OSError:
        diagnostics["skipped_entries"] += 1
        return stats, diagnostics

    with entries:
        for entry in entries:
            try:
                if entry.is_symlink() or _is_link_like(entry.path):
                    diagnostics["symlinks_skipped"] += 1
                    continue
                if not entry.is_file(follow_symlinks=False) or not predicate(entry.name):
                    continue
                stats["files"] += 1
                stats["bytes"] += entry.stat(follow_symlinks=False).st_size
            except OSError:
                diagnostics["skipped_entries"] += 1
    return stats, diagnostics


def _scan_photo_downloads(paths):
    """一次遍历区分可清理残留 ZIP 与仍在使用/刚生成的 ZIP。"""
    clearable = _empty_bucket()
    active = _empty_bucket()
    diagnostics = _empty_diagnostics()
    folder = paths.photo_gallery_cache_folder
    if not _is_safe_managed_root(folder, paths.workspace_folder):
        diagnostics["symlinks_skipped"] += 1
        return clearable, active, diagnostics
    try:
        entries = os.scandir(folder)
    except FileNotFoundError:
        return clearable, active, diagnostics
    except OSError:
        diagnostics["skipped_entries"] += 1
        return clearable, active, diagnostics

    now = time.time()
    with entries:
        for entry in entries:
            if not entry.name.startswith("photo-gallery-") or not entry.name.endswith(".zip"):
                continue
            try:
                if entry.is_symlink() or _is_link_like(entry.path):
                    diagnostics["symlinks_skipped"] += 1
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
                is_active = (
                    photo_gallery.is_active_photo_download(entry.path)
                    or now - stat.st_mtime < ACTIVE_DOWNLOAD_GRACE_SECONDS
                )
                target = active if is_active else clearable
                target["files"] += 1
                target["bytes"] += stat.st_size
            except OSError:
                diagnostics["skipped_entries"] += 1
    return clearable, active, diagnostics


def _model_cover_classification(paths):
    index, index_status = model_assets.read_asset_index_with_status(paths)
    if index_status != "valid":
        return set(), set(), set(), set(), index_status
    assets = index.get("assets", {})
    if not isinstance(assets, dict):
        assets = {}

    manual_paths = set()
    system_paths = set()
    manual_names = set()
    system_names = set()
    if _is_safe_managed_root(paths.output_folder, paths.workspace_folder):
        system_names = {
            f"{model_assets.safe_asset_filename(asset_id)}.jpg"
            for asset_id in model_assets.collect_generated_file_groups(paths)
        }
    for asset_id, record in assets.items():
        if not isinstance(record, dict):
            continue
        fallback_name = f"{model_assets.safe_asset_filename(asset_id)}.jpg"
        cover_kind = record.get("cover_kind")
        if cover_kind == model_assets.THUMBNAIL_SYSTEM:
            system_names.add(fallback_name)
        elif cover_kind:
            manual_names.add(fallback_name)
        cover_path = model_assets.resolve_workspace_relative_path(paths, record.get("cover_path"))
        if not cover_path or not is_real_path_inside(
            cover_path,
            paths.model_asset_thumbnail_folder,
        ):
            continue
        normalized = _normalized_path(cover_path)
        if cover_kind == model_assets.THUMBNAIL_SYSTEM:
            system_paths.add(normalized)
        else:
            manual_paths.add(normalized)

    # 同一路径若被任何手动记录引用，按受保护内容处理。
    system_paths.difference_update(manual_paths)
    system_names.difference_update(manual_names)
    return manual_paths, system_paths, manual_names, system_names, index_status


def _scan_model_cover_buckets(paths):
    system_stats = _empty_bucket()
    protected_stats = _empty_bucket()
    diagnostics = _empty_diagnostics()
    thumbnail_root = paths.model_asset_thumbnail_folder
    if not _is_safe_managed_root(thumbnail_root, paths.workspace_folder):
        diagnostics["symlinks_skipped"] += 1
        return system_stats, protected_stats, diagnostics
    manual_paths, system_paths, manual_names, system_names, index_status = _model_cover_classification(paths)
    if index_status != "valid":
        if index_status == "invalid":
            diagnostics["skipped_entries"] += 1
        protected_stats, scan = _scan_tree(
            thumbnail_root,
            allowed_root=paths.workspace_folder,
        )
        _merge_diagnostics(diagnostics, scan)
        return system_stats, protected_stats, diagnostics
    try:
        entries = os.scandir(thumbnail_root)
    except FileNotFoundError:
        return system_stats, protected_stats, diagnostics
    except OSError:
        diagnostics["skipped_entries"] += 1
        return system_stats, protected_stats, diagnostics

    with entries:
        for entry in entries:
            try:
                if entry.is_symlink() or _is_link_like(entry.path):
                    diagnostics["symlinks_skipped"] += 1
                    continue
                if not entry.is_file(follow_symlinks=False):
                    diagnostics["skipped_entries"] += 1
                    continue
                stat = entry.stat(follow_symlinks=False)
                normalized = _normalized_path(entry.path)
                is_system = (
                    normalized not in manual_paths
                    and entry.name not in manual_names
                    and (normalized in system_paths or entry.name in system_names)
                )
                target = system_stats if is_system else protected_stats
                target["files"] += 1
                target["bytes"] += stat.st_size
            except OSError:
                diagnostics["skipped_entries"] += 1
    return system_stats, protected_stats, diagnostics


def collect_workspace_storage_snapshot(paths):
    """统计 Sharp GUI 管理的 workspace 内容，不触碰外部相册原图目录。"""
    started_at = time.monotonic()
    diagnostics = _empty_diagnostics()

    index_files, scan = _scan_known_files((
        paths.photo_catalog_file,
        paths.photo_index_file,
        f"{paths.photo_index_file}.bak",
    ), allowed_root=paths.workspace_folder)
    _merge_diagnostics(diagnostics, scan)
    album_indexes, scan = _scan_tree(
        paths.photo_album_index_folder,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    gallery_indexes = _sum_buckets(index_files, album_indexes)

    photo_thumbnails, scan = _scan_tree(
        paths.photo_thumbnail_folder,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    video_posters, scan = _scan_tree(
        paths.video_poster_folder,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    temporary_downloads, active_downloads, scan = _scan_photo_downloads(paths)
    _merge_diagnostics(diagnostics, scan)

    known_gallery_files = {
        _normalized_path(paths.photo_catalog_file),
        _normalized_path(paths.photo_index_file),
        _normalized_path(f"{paths.photo_index_file}.bak"),
    }
    gallery_cache_root = _normalized_path(paths.photo_gallery_cache_folder)
    gallery_other, scan = _scan_tree(
        paths.photo_gallery_cache_folder,
        allowed_root=paths.workspace_folder,
        excluded_roots=(
            paths.photo_album_index_folder,
            paths.photo_thumbnail_folder,
            paths.video_poster_folder,
        ),
        include_file=lambda path, name: (
            _normalized_path(path) not in known_gallery_files
            and not (
                _normalized_path(os.path.dirname(path)) == gallery_cache_root
                and name.startswith("photo-gallery-")
                and name.endswith(".zip")
            )
        ),
    )
    _merge_diagnostics(diagnostics, scan)

    legacy_model_previews, scan = _scan_tree(
        paths.thumbnail_folder,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    system_model_previews, asset_covers, scan = _scan_model_cover_buckets(paths)
    _merge_diagnostics(diagnostics, scan)
    model_previews = _sum_buckets(legacy_model_previews, system_model_previews)

    clearable_cache = {
        "gallery_indexes": gallery_indexes,
        "photo_thumbnails": photo_thumbnails,
        "video_posters": video_posters,
        "model_previews": model_previews,
        "temporary_downloads": temporary_downloads,
        "other": gallery_other,
    }
    clearable_cache["total"] = _sum_buckets(*clearable_cache.values())

    source_images, scan = _scan_immediate_files(
        paths.input_folder,
        lambda _name: True,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    generated_models, scan = _scan_immediate_files(
        paths.output_folder,
        lambda _name: True,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    imported_models, scan = _scan_immediate_files(
        paths.model_asset_import_folder,
        lambda _name: True,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    asset_library, scan = _scan_immediate_files(
        os.path.dirname(paths.model_asset_index_file),
        lambda _name: True,
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)
    video_uploads, scan = _scan_tree(
        os.path.join(paths.video_reconstruction_folder, "uploads"),
        allowed_root=paths.workspace_folder,
    )
    _merge_diagnostics(diagnostics, scan)

    protected_storage = {
        "source_images": source_images,
        "generated_models": generated_models,
        "imported_models": imported_models,
        "asset_library": asset_library,
        "asset_covers": asset_covers,
        "video_uploads": video_uploads,
        "active_downloads": active_downloads,
    }
    protected_storage["total"] = _sum_buckets(*protected_storage.values())

    return {
        "schema_version": 1,
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_ms": max(0, round((time.monotonic() - started_at) * 1000)),
        "clearable_cache": clearable_cache,
        "protected_storage": protected_storage,
        "managed_total": _sum_buckets(
            clearable_cache["total"],
            protected_storage["total"],
        ),
        "scan": {
            **diagnostics,
            "incomplete": diagnostics["skipped_entries"] > 0,
        },
    }


def _workspace_key(paths):
    return os.path.normcase(os.path.realpath(os.path.abspath(paths.workspace_folder)))


def _new_snapshot_state():
    return {
        "snapshot": None,
        "completed_at": 0.0,
        "active_workers": 0,
        "error": False,
        "retry_not_before": 0.0,
        "generation": 0,
        "active_mutations": 0,
    }


def _refresh_snapshot(paths, key, generation):
    snapshot = None
    failure = None
    try:
        snapshot = collect_workspace_storage_snapshot(paths)
    except BaseException as exc:
        failure = exc
        print(f"⚠️ Workspace storage scan failed: {exc}")

    with _snapshot_lock:
        state = _snapshot_states.get(key)
        if not state:
            return
        state["active_workers"] = max(0, state["active_workers"] - 1)
        if state["generation"] != generation:
            return
        if failure is not None:
            state["error"] = True
            state["retry_not_before"] = time.monotonic() + WORKSPACE_STORAGE_FAILURE_RETRY_SECONDS
            return
        state["snapshot"] = snapshot
        state["completed_at"] = time.monotonic()
        state["error"] = False
        state["retry_not_before"] = 0.0


def request_workspace_storage_stats(paths, *, refresh=False):
    """立即返回已有快照；需要重算时只启动一个后台扫描。"""
    key = _workspace_key(paths)
    now = time.monotonic()
    start_refresh = False
    generation = 0

    with _snapshot_lock:
        state = _snapshot_states.setdefault(key, _new_snapshot_state())
        snapshot = state["snapshot"]
        expired = bool(
            snapshot
            and now - state["completed_at"] >= WORKSPACE_STORAGE_CACHE_TTL_SECONDS
        )
        retry_allowed = refresh or now >= state["retry_not_before"]
        if (
            state["active_mutations"] == 0
            and (refresh or snapshot is None or expired)
            and state["active_workers"] == 0
            and retry_allowed
        ):
            state["active_workers"] += 1
            state["error"] = False
            start_refresh = True
            generation = state["generation"]

        in_flight = state["active_workers"] > 0 or state["active_mutations"] > 0
        scan_failed = bool(state["error"] and snapshot is None and not in_flight)
        stale = bool(snapshot and (expired or state["error"]))

    if start_refresh:
        thread = threading.Thread(
            target=_refresh_snapshot,
            args=(paths, key, generation),
            daemon=True,
            name="workspace-storage-scan",
        )
        try:
            thread.start()
        except Exception as exc:
            print(f"⚠️ Workspace storage scan could not start: {exc}")
            with _snapshot_lock:
                state = _snapshot_states.get(key)
                if state:
                    state["active_workers"] = max(0, state["active_workers"] - 1)
                    if state["generation"] == generation:
                        state["error"] = True
                        state["retry_not_before"] = (
                            time.monotonic() + WORKSPACE_STORAGE_FAILURE_RETRY_SECONDS
                        )
            in_flight = False
            scan_failed = snapshot is None
            stale = bool(snapshot)

    return {
        "success": not scan_failed,
        "status": "error" if scan_failed else ("checking" if snapshot is None else "ready"),
        "refreshing": in_flight,
        "stale": stale,
        "retry_after_ms": WORKSPACE_STORAGE_RETRY_AFTER_MS if in_flight else None,
        "snapshot": snapshot,
        **({"error": "Workspace storage scan failed"} if scan_failed else {}),
    }


def invalidate_workspace_storage_stats(paths):
    """使旧扫描结果失效；正在执行的旧线程完成后也不会覆盖新快照。"""
    key = _workspace_key(paths)
    with _snapshot_lock:
        state = _snapshot_states.setdefault(key, _new_snapshot_state())
        state["generation"] += 1
        state["snapshot"] = None
        state["completed_at"] = 0.0
        state["error"] = False
        state["retry_not_before"] = 0.0


def _remove_tree_contents(folder, *, allowed_root=None, keep_file=None):
    removed = _empty_bucket()
    if (
        not os.path.isdir(folder)
        or _is_link_like(folder)
        or (allowed_root and not is_real_path_inside(folder, allowed_root))
    ):
        return removed

    pending = [(folder, False)]
    while pending:
        current, visited = pending.pop()
        if visited:
            if _normalized_path(current) != _normalized_path(folder):
                try:
                    os.rmdir(current)
                except OSError:
                    pass
            continue

        pending.append((current, True))
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if not (entry.is_symlink() or _is_link_like(entry.path)) and entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, False))
                    continue
                if entry.is_symlink() or _is_link_like(entry.path):
                    continue
                if keep_file and keep_file(entry.path, entry.name):
                    continue
                stat = entry.stat(follow_symlinks=False)
                os.unlink(entry.path)
                removed["files"] += 1
                removed["bytes"] += stat.st_size
            except OSError:
                pass
    return removed


def clear_rebuildable_workspace_cache(paths):
    """清理可重建缓存；模型、原图、手动封面和视频重建工作文件均保留。"""
    key = _workspace_key(paths)
    with _snapshot_lock:
        state = _snapshot_states.setdefault(key, _new_snapshot_state())
        state["active_mutations"] += 1
        state["generation"] += 1
        state["snapshot"] = None
        state["completed_at"] = 0.0
        state["error"] = False
        state["retry_not_before"] = 0.0
    removed = _empty_bucket()
    failure = None

    gallery_cache_root = _normalized_path(paths.photo_gallery_cache_folder)

    def keep_recent_download(path, name):
        if (
            _normalized_path(os.path.dirname(path)) != gallery_cache_root
            or not name.startswith("photo-gallery-")
            or not name.endswith(".zip")
        ):
            return False
        try:
            return (
                photo_gallery.is_active_photo_download(path)
                or time.time() - os.path.getmtime(path) < ACTIVE_DOWNLOAD_GRACE_SECONDS
            )
        except OSError:
            return True

    try:
        _merge_bucket(
            removed,
            _remove_tree_contents(
                paths.photo_gallery_cache_folder,
                allowed_root=paths.workspace_folder,
                keep_file=keep_recent_download,
            ),
        )
        photo_gallery.invalidate_photo_gallery_memory_cache()
        with model_gallery.thumbnail_cache_lock:
            _merge_bucket(
                removed,
                _remove_tree_contents(
                    paths.thumbnail_folder,
                    allowed_root=paths.workspace_folder,
                ),
            )
        _merge_bucket(removed, model_assets.clear_rebuildable_model_asset_covers(paths))
    except Exception as exc:
        failure = exc
        print(f"⚠️ Workspace cache cleanup failed: {exc}")
    finally:
        with _snapshot_lock:
            state = _snapshot_states.setdefault(key, _new_snapshot_state())
            state["active_mutations"] = max(0, state["active_mutations"] - 1)
            state["generation"] += 1
            state["snapshot"] = None
            state["completed_at"] = 0.0
            state["error"] = False
            state["retry_not_before"] = 0.0

    return {
        "success": failure is None,
        "removed": removed,
        "stats": request_workspace_storage_stats(paths, refresh=True),
        **({"error": "Workspace cache cleanup failed"} if failure is not None else {}),
    }


def reset_workspace_storage_cache_for_tests():
    with _snapshot_lock:
        _snapshot_states.clear()

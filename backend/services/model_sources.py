"""Content-based provenance. Warm queries use catalogs; repair never scans folders."""
import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from copy import deepcopy

from PIL import Image, ImageOps

from backend.services import model_assets, model_gallery, photo_gallery

SYSTEM_ALBUM_ID = 'model-sources'
_LOCK = threading.RLock()
_HASH_CACHE = OrderedDict()
_REPAIRS = {}
_SNAPSHOTS = OrderedDict()
_AVAILABILITY = {}
REPAIR_RETRY_SECONDS = 300
AVAILABILITY_TTL_SECONDS = 30
_INFO_KEYS = ('size', 'mtime', 'ctime', 'width', 'height', 'duration', 'mime_type',
              'video_codec', 'audio_codec', 'bitrate')


def media_version(meta):
    return {key: (meta or {}).get(key) for key in ('size', 'mtime')}


def version_matches(version, meta):
    return isinstance(version, dict) and version.get('size') is not None and media_version(version) == media_version(meta)


def capture_source(path, name, media_type, meta=None):
    """Hash a validated input once per file version, without buffering the media."""
    # 历史单图模型没有媒体类型字段；空值应视为图片，不能写入无效来源类型。
    media_type = 'video' if media_type == 'video' else 'image'
    stat = os.stat(path)
    key = (os.path.normcase(os.path.realpath(path)), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    with _LOCK:
        digest = _HASH_CACHE.get(key)
    if digest is None:
        hasher = hashlib.sha256()
        with open(path, 'rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                hasher.update(chunk)
        after = os.stat(path)
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Source media changed while being read')
        digest = hasher.hexdigest()
        with _LOCK:
            _HASH_CACHE[key] = digest
            while len(_HASH_CACHE) > 512:
                _HASH_CACHE.popitem(last=False)
    info = {key: (meta or {}).get(key) for key in _INFO_KEYS}
    info.update({'id': digest, 'media_type': media_type,
                 'name': str(name or os.path.basename(path)).replace('\\', '/').rsplit('/', 1)[-1],
                 'size': stat.st_size, 'mtime': stat.st_mtime, 'ctime': stat.st_ctime})
    if media_type == 'image' and not info.get('width'):
        try:
            with Image.open(path) as image:
                info['width'], info['height'] = ImageOps.exif_transpose(image).size
        except OSError:
            pass  # The existing generation pipeline reports invalid inputs, not provenance capture.
    return info


def source_id_for_asset(asset):
    if asset.get('source_provenance_unverified'):
        return None
    identity = asset.get('source_identity') or {}
    if re.fullmatch(r'[a-f0-9]{64}', str(identity.get('id', ''))):
        return identity['id']
    if not asset.get('is_generated') or not (asset.get('image_url') or asset.get('source_video_url')):
        return None
    # Provisional identities keep offline originals visible until content can be verified.
    reference = asset.get('source_media_id') or asset.get('source_parent_asset_id') or asset['id']
    return hashlib.sha256(('unverified:' + reference).encode()).hexdigest()


def source_media_type_for_asset(asset):
    """按明确来源类型分类；历史单图模型的缺失或空类型统一为图片。"""
    identity = asset.get('source_identity') or {}
    for media_type in (identity.get('media_type'), asset.get('source_media_type')):
        if media_type in ('image', 'video'):
            return media_type
    return 'video' if asset.get('source_type') == model_assets.SOURCE_VIDEO else 'image'


def source_groups(paths):
    assets, index = model_assets.get_catalog_items(paths)
    groups = {}
    for asset in assets.values():
        source_id = source_id_for_asset(asset)
        if not source_id:
            continue
        info = {**(asset.get('source_identity') or {}),
                'media_type': source_media_type_for_asset(asset)}
        info['name'] = info.get('name') or asset.get('source_name') or asset['name']
        group = groups.setdefault(source_id, {'source_id': source_id, 'source': info, 'models': []})
        group['models'].append(asset)
    defaults = index.get('source_defaults', {})
    for source_id, group in groups.items():
        group['models'].sort(key=lambda asset: asset.get('created_at', ''), reverse=True)
        available = [asset for asset in group['models'] if asset.get('available')]
        preferred = defaults.get(source_id)
        group.update({'model_count': len(available), 'total_count': len(group['models']),
                      'default_model_id': preferred if any(asset['id'] == preferred for asset in available) else None})
    return groups, index


def link_summary(group):
    if not group:
        return {'source_id': None, 'model_count': 0, 'total_count': 0, 'default_model_id': None}
    return {key: group[key] for key in ('source_id', 'model_count', 'total_count', 'default_model_id')}


def indexed_meta(paths, media_id):
    album_id = photo_gallery.parse_media_id(media_id)
    if not album_id or album_id == SYSTEM_ALBUM_ID or not photo_gallery.find_photo_album(album_id):
        return None
    return (photo_gallery.load_album_index(paths, album_id) or {}).get('media', {}).get(media_id)


def remember_album_source(paths, media_id, version, digest):
    album_id = photo_gallery.parse_media_id(media_id)
    if not album_id or album_id == SYSTEM_ALBUM_ID:
        return
    with photo_gallery.get_album_lock(album_id):
        index = photo_gallery.load_album_index(paths, album_id)
        current = (index or {}).get('media', {}).get(media_id)
        if current and version_matches(version, current):
            index['media'][media_id] = {**current, 'model_source_hash': digest}
            photo_gallery.save_album_index(paths, album_id, index)


def group_for_media(paths, media_id, groups):
    if media_id.startswith(SYSTEM_ALBUM_ID + '_'):
        return groups.get(media_id[len(SYSTEM_ALBUM_ID) + 1:])
    meta = indexed_meta(paths, media_id)
    if not meta:
        return None
    digest = meta.get('model_source_hash')
    if digest in groups:
        return groups[digest]
    for group in groups.values():
        if any(asset.get('source_media_id') == media_id and
               version_matches(asset.get('source_media_version'), meta) for asset in group['models']):
            return group
    return None


def query_links(paths, media_ids):
    schedule_repair(paths)
    groups, index = source_groups(paths)
    return {'links': {media_id: link_summary(group_for_media(paths, media_id, groups)) for media_id in media_ids},
            'repairing': repair_status(paths), 'revision': index.get('updated_at')}


def query_models(paths, media_id):
    schedule_repair(paths)
    groups, _ = source_groups(paths)
    group = group_for_media(paths, media_id, groups)
    result = deepcopy(group) if group else {**link_summary(None), 'source': {}, 'models': []}
    result['repairing'] = repair_status(paths)
    result['source_available'] = cached_availability(paths, group['source_id']) if group else None
    return result


def cached_availability(paths, source_id):
    with _LOCK:
        cached = _AVAILABILITY.get((paths.workspace_folder, source_id))
    return cached[1] if cached and time.monotonic() - cached[0] < AVAILABILITY_TTL_SECONDS else None


def set_default(paths, source_id, asset_id):
    with model_assets._INDEX_LOCK:
        groups, index = source_groups(paths)
        group = groups.get(source_id)
        if not group or (asset_id is not None and not any(
            asset['id'] == asset_id and asset.get('available') for asset in group['models']
        )):
            return {'error': 'Model does not belong to this source', 'code': 'model_source_default_invalid'}, 400
        actual = model_assets.get_model_asset(paths, asset_id) if asset_id is not None else None
        if asset_id is not None and (not actual or not actual.get('available')):
            return {'error': 'Model is unavailable', 'code': 'model_source_default_invalid'}, 400
        defaults = index.setdefault('source_defaults', {})
        if asset_id is None:
            defaults.pop(source_id, None)
        else:
            defaults[source_id] = asset_id
        model_assets.write_asset_index(paths, index)
    return {'success': True, 'default_model_id': asset_id}, 200


def resolve_asset_original(paths, asset):
    if source_media_type_for_asset(asset) == 'video':
        # Never recurse through a virtual ID stored by regeneration.
        if str(asset.get('source_media_id') or '').startswith(SYSTEM_ALBUM_ID + '_'):
            return None
        resolved = model_gallery.resolve_gallery_source_video(paths, asset['id'])
        if not resolved:
            return None
        path = resolved['path']
    else:
        _, path = model_gallery.find_original_image(paths, asset['id'])
        if not path or not model_assets.is_controlled_path(paths, path, paths.input_folder):
            return None
    try:
        stat = os.stat(path)
        identity = asset.get('source_identity')
        if identity and not version_matches(identity, {'size': stat.st_size, 'mtime': stat.st_mtime}):
            # A changed timestamp may be an identical copy; verify only on explicit access.
            current = capture_source(path, asset.get('source_name'), source_media_type_for_asset(asset))
            if current['id'] != identity['id']:
                return None
        return path
    except (OSError, ValueError):
        return None


def resolve_source_media(paths, media_id, expected_type=None):
    groups, _ = source_groups(paths)
    group = groups.get(media_id.removeprefix(SYSTEM_ALBUM_ID + '_'))
    if not group or (expected_type and group['source'].get('media_type') != expected_type):
        return None
    for asset in group['models']:
        path = resolve_asset_original(paths, asset)
        if path:
            stat = os.stat(path)
            info = group['source']
            meta = {**info, 'id': media_id, 'album_id': SYSTEM_ALBUM_ID,
                    'source_media_id': asset.get('source_media_id'),
                    'size': stat.st_size, 'mtime': stat.st_mtime, 'ctime': stat.st_ctime}
            with _LOCK:
                _AVAILABILITY[(paths.workspace_folder, group['source_id'])] = (time.monotonic(), True)
            return {'id': SYSTEM_ALBUM_ID, 'path': os.path.dirname(path)}, path, meta
    with _LOCK:
        _AVAILABILITY[(paths.workspace_folder, group['source_id'])] = (time.monotonic(), False)
    return None


def source_thumbnail_url(group):
    """Choose a cache-only media endpoint without inspecting files during pagination."""
    if any(asset.get('source_identity') or
           photo_gallery.parse_media_id(asset.get('source_media_id')) not in (None, SYSTEM_ALBUM_ID)
           for asset in group['models']):
        endpoint = 'video-poster' if group['source'].get('media_type') == 'video' else 'photo-thumbnail'
        return f"/api/{endpoint}/{SYSTEM_ALBUM_ID}_{group['source_id']}"
    return next((asset.get('thumb_url') for asset in group['models'] if asset.get('thumb_url')), None)


def resolve_source_thumbnail(paths, media_id, media_type):
    """Reuse existing album thumbnails only; never read or regenerate source media."""
    groups, _ = source_groups(paths)
    group = groups.get(media_id.removeprefix(SYSTEM_ALBUM_ID + '_'))
    if not group or group['source'].get('media_type', 'image') != media_type:
        return None, None
    root = paths.video_poster_folder if media_type == 'video' else paths.photo_thumbnail_folder
    filename_for = photo_gallery.get_video_poster_filename if media_type == 'video' else photo_gallery.get_photo_thumbnail_filename
    seen = set()

    def matching_media():
        for asset in group['models']:
            reference = asset.get('source_media_id')
            if not reference or reference in seen:
                continue
            seen.add(reference)
            meta = indexed_meta(paths, reference)
            if meta:
                digest = meta.get('model_source_hash')
                matches = digest == group['source_id'] if digest else version_matches(asset.get('source_media_version'), meta)
                if matches:
                    yield reference, meta
        # Historical uploads may have an exact content association but no original album ID.
        # Only this explicit thumbnail access reads album indexes; list queries remain catalog-only.
        for album in photo_gallery.normalize_photo_album_roots():
            index = photo_gallery.load_album_index(paths, album['id']) or {}
            for reference, meta in index.get('media', {}).items():
                if reference not in seen and meta.get('model_source_hash') == group['source_id']:
                    seen.add(reference)
                    yield reference, meta

    for reference, meta in matching_media():
        if meta.get('media_type', 'image') != media_type:
            continue
        try:
            candidate = os.path.join(root, filename_for(reference, meta))
            if model_assets.is_controlled_path(paths, candidate, root) and os.path.isfile(candidate):
                return candidate, None
        except (OSError, TypeError, ValueError):
            continue
    fallback = next((asset.get('thumb_url') for asset in group['models']
                     if str(asset.get('thumb_url') or '').startswith(('/api/thumbnail/', '/files/'))), None)
    return None, fallback


def system_album(paths):
    groups, index = source_groups(paths)
    sources = [group for group in groups.values() if group['total_count']]
    video_count = sum(group['source'].get('media_type') == 'video' for group in sources)
    return {'id': SYSTEM_ALBUM_ID, 'system': 'model-sources', 'name': 'Model Sources',
            'cover_thumb_url': next((thumb for group in sources if (thumb := source_thumbnail_url(group))), None),
            'photo_count': len(sources) - video_count, 'media_count': len(sources), 'video_count': video_count,
            'recursive': False, 'enabled': True, 'available': True, 'scan_status': 'idle',
            'updated_at': index.get('updated_at'), 'error': None}


def source_photo_item(paths, group):
    info = group['source']
    media_id = SYSTEM_ALBUM_ID + '_' + group['source_id']
    media_type = info.get('media_type', 'image')
    endpoint = 'video-original' if media_type == 'video' else 'photo-original'
    thumb = source_thumbnail_url(group)
    item = {key: info.get(key) for key in _INFO_KEYS}
    updated_at = group['models'][0].get('updated_at')
    item.update({'id': media_id, 'album_id': SYSTEM_ALBUM_ID, 'source_id': group['source_id'],
                 'name': info.get('name') or media_id, 'media_type': media_type,
                 'thumb_url': thumb, 'poster_url': thumb, 'preview_url': f'/api/{endpoint}/{media_id}',
                 'download_url': f'/api/{endpoint}/{media_id}?download=1',
                 'created_at': group['models'][-1].get('created_at'), 'updated_at': updated_at,
                 'model_link': link_summary(group)})
    item['source_available'] = cached_availability(paths, group['source_id'])
    if media_type == 'video':
        item['playback_url'] = photo_gallery.build_video_playback_url(media_id, item['name'])
        if photo_gallery.requires_browser_audio_stream(item['name'], item.get('audio_codec')):
            item['audio_stream_url'] = photo_gallery.build_browser_audio_stream_url(media_id, item['name'])
    else:
        item['full_url'] = item['preview_url']
    return item


def list_source_media(paths, sort, cursor, limit, media_type, snapshot_token=None):
    schedule_repair(paths)
    media_type = photo_gallery.normalize_media_type(media_type)
    if sort not in ('mtime_asc', 'mtime_desc', 'ctime_asc', 'ctime_desc',
                    'name_asc', 'name_desc', 'size_asc', 'size_desc'):
        sort = 'mtime_desc'
    groups, index = source_groups(paths)
    token = str(index.get('updated_at') or 'empty')
    cache_key = (paths.workspace_folder, snapshot_token or token)
    with _LOCK:
        snapshot = _SNAPSHOTS.get(cache_key)
        if snapshot is None:
            snapshot = deepcopy(list(groups.values()))
            cache_key = (paths.workspace_folder, token)
            _SNAPSHOTS[cache_key] = snapshot
            while len(_SNAPSHOTS) > 16:
                _SNAPSHOTS.popitem(last=False)
        else:
            token = cache_key[1]
    counts = photo_gallery.get_media_counts([group['source'] for group in snapshot])
    filtered = [group for group in snapshot if media_type not in ('image', 'video')
                or group['source'].get('media_type') == media_type]
    field = sort.rsplit('_', 1)[0]
    filtered.sort(key=lambda group: (str(group['source'].get('name') or '').lower() if field == 'name'
                                    else group['source'].get(field) or
                                    (group['source'].get('mtime') if field == 'ctime' else 0) or 0),
                  reverse=sort.endswith('desc'))
    cursor = model_assets.parse_positive_int(cursor, 0)
    limit = model_assets.parse_positive_int(limit, 60, minimum=1, maximum=120)
    return {'items': [source_photo_item(paths, group) for group in filtered[cursor:cursor + limit]],
            'next_cursor': str(cursor + limit) if cursor + limit < len(filtered) else None,
            'total': len(filtered), 'media_counts': counts, 'snapshot': token,
            'scan_status': 'idle', 'available': True, 'error': None, 'repairing': repair_status(paths)}


def repair_status(paths):
    with _LOCK:
        state = _REPAIRS.get(paths.workspace_folder, {})
        return bool(state.get('running') or state.get('pending'))


def repair_sources(paths):
    """Bounded repair, using existing album indexes and controlled model originals only."""
    assets, _ = model_assets.get_catalog_items(paths)
    pending = False
    old = [asset for asset in assets.values() if source_id_for_asset(asset) and not asset.get('source_identity')]
    with _LOCK:
        attempts = _REPAIRS.setdefault(paths.workspace_folder, {}).setdefault('attempts', {})
        now = time.monotonic()
        for attempt, retry_at in list(attempts.items()):
            if retry_at <= now:
                attempts.pop(attempt, None)
        old = [asset for asset in old if (asset['id'], asset.get('updated_at')) not in attempts]
    for asset in old[:32]:
        attempt = (asset['id'], asset.get('updated_at'))
        with _LOCK:
            attempts[attempt] = now + REPAIR_RETRY_SECONDS
        path = resolve_asset_original(paths, asset)
        if not path:
            continue
        try:
            meta = indexed_meta(paths, asset.get('source_media_id', '')) if asset.get('source_media_id') else None
            identity = capture_source(path, asset.get('source_name'), source_media_type_for_asset(asset), meta)
            with model_assets._INDEX_LOCK:
                current_assets, _ = model_assets.get_catalog_items(paths)
                if asset['id'] not in current_assets or current_assets[asset['id']].get('source_identity'):
                    continue
                metadata = model_gallery.read_model_metadata(paths, asset['id'])
                metadata['source_identity'] = identity
                if meta:
                    metadata['source_media_version'] = media_version(meta)
                model_gallery.write_model_metadata(paths, asset['id'], metadata, preserve_timestamp=True)
                model_assets.sync_generated_model_asset(paths, asset['id'])
                updated = model_assets.read_asset_index(paths)
                defaults = updated.get('source_defaults', {})
                provisional = source_id_for_asset(asset)
                if defaults.get(provisional) == asset['id']:
                    defaults.setdefault(identity['id'], asset['id'])
                    defaults.pop(provisional, None)
                    model_assets.write_asset_index(paths, updated)
            with _LOCK:
                attempts.pop(attempt, None)
        except (OSError, ValueError):
            continue
    pending = len(old) > 32
    groups, _ = source_groups(paths)
    sizes = {group['source'].get('size') for group in groups.values()}
    candidates = []
    for album in photo_gallery.normalize_photo_album_roots():
        index = photo_gallery.load_album_index(paths, album['id']) or {}
        candidates.extend(meta for meta in index.get('media', {}).values()
                          if meta.get('size') in sizes and not meta.get('model_source_hash')
                          and (meta['id'], meta.get('mtime')) not in attempts)
    for meta in candidates[:256]:
        with _LOCK:
            attempts[(meta['id'], meta.get('mtime'))] = now + REPAIR_RETRY_SECONDS
        resolved = photo_gallery.resolve_media_path(paths, meta['id'], allow_stale=True)
        if not resolved:
            continue
        try:
            identity = capture_source(resolved[1], meta.get('name'), meta.get('media_type', 'image'), resolved[2])
            remember_album_source(paths, meta['id'], identity, identity['id'])
            with _LOCK:
                attempts.pop((meta['id'], meta.get('mtime')), None)
        except (OSError, ValueError):
            continue
    return pending or len(candidates) > 256


def schedule_repair(paths):
    # Catalog timestamps change only on mutations; the album catalog tracks rescan/version changes.
    _, index = model_assets.get_catalog_items(paths)
    signature = (index.get('updated_at'), photo_gallery.load_catalog(paths).get('updated_at'))
    key = paths.workspace_folder
    with _LOCK:
        state = _REPAIRS.setdefault(key, {})
        now = time.monotonic()
        retry_due = (state.get('failed') and now - state.get('finished', 0) >= REPAIR_RETRY_SECONDS
                     or now >= min(state.get('attempts', {}).values(), default=float('inf')))
        if state.get('running') or (state.get('signature') == signature and not state.get('pending') and not retry_due):
            return
        cooldown = REPAIR_RETRY_SECONDS if state.get('failed') else 1
        if now - state.get('finished', 0) < cooldown:
            return
        state['running'] = True

    def run():
        pending = False
        failed = False
        latest_signature = signature
        try:
            pending = repair_sources(paths)
            _, latest = model_assets.get_catalog_items(paths)
            latest_signature = (latest.get('updated_at'), photo_gallery.load_catalog(paths).get('updated_at'))
        except (OSError, ValueError, model_assets.ModelAssetServiceError):
            failed = True
            logging.getLogger(__name__).warning('Model source repair deferred; the catalog or source is unavailable')
        finally:
            with _LOCK:
                state.update({'running': False, 'pending': pending, 'signature': latest_signature,
                              'finished': time.monotonic(), 'failed': failed})

    threading.Thread(target=run, name='model-source-repair', daemon=True).start()

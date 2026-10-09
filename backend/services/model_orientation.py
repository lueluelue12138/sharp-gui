import math


VIEWER_ORIENTATION_DEFAULT = "default"
VIEWER_ORIENTATION_Y_FRONT = "y-front"
VIEWER_ORIENTATION_UNKNOWN = "unknown"

VIEWER_ORIENTATIONS = frozenset({
    VIEWER_ORIENTATION_DEFAULT,
    VIEWER_ORIENTATION_Y_FRONT,
    VIEWER_ORIENTATION_UNKNOWN,
})

SOURCE_MEDIA_TYPE_IMAGE = "image"
SOURCE_MEDIA_TYPE_VIDEO = "video"
SOURCE_MEDIA_TYPES = frozenset({
    SOURCE_MEDIA_TYPE_IMAGE,
    SOURCE_MEDIA_TYPE_VIDEO,
})


def normalize_viewer_camera(value):
    """只向前端传递有限、非退化的重建相机取景数据。"""
    if not isinstance(value, dict):
        return None
    try:
        vectors = {}
        for key in ('position', 'target', 'up'):
            raw = value.get(key)
            if not isinstance(raw, (list, tuple)) or len(raw) != 3:
                return None
            if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in raw):
                return None
            vectors[key] = [float(item) for item in raw]
            if not all(math.isfinite(item) and abs(item) <= 1e6 for item in vectors[key]):
                return None
        direction = [target - origin for target, origin in zip(vectors['target'], vectors['position'])]
        up = vectors['up']
        cross = [direction[1] * up[2] - direction[2] * up[1],
                 direction[2] * up[0] - direction[0] * up[2],
                 direction[0] * up[1] - direction[1] * up[0]]
        if sum(item * item for item in cross) < 1e-12:
            return None
        fov, aspect = float(value['fov_y_degrees']), float(value['aspect'])
        if not (1 < fov < 179 and 0.01 < aspect < 100):
            return None
        return {**vectors, 'fov_y_degrees': fov, 'aspect': aspect}
    except (TypeError, ValueError, KeyError):
        return None


def normalize_viewer_orientation(value):
    """Normalize an explicit preview hint without interpreting geometry facts."""
    normalized = str(value or "").strip().lower()
    if normalized in VIEWER_ORIENTATIONS:
        return normalized
    return VIEWER_ORIENTATION_UNKNOWN


def normalize_source_media_type(value):
    """Return a trusted source-media classification or None."""
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SOURCE_MEDIA_TYPES else None


def resolve_viewer_orientation(
    viewer_orientation=None,
    *,
    source_media_type=None,
    source_type=None,
):
    """Resolve the asset preview contract from explicit or trusted provenance.

    Coordinate-system metadata is intentionally not accepted here: it records a
    format fact, while ``viewer_orientation`` is a product preview instruction.
    """
    raw_orientation = str(viewer_orientation or "").strip()
    if raw_orientation:
        return normalize_viewer_orientation(raw_orientation)

    normalized_source = normalize_source_media_type(source_media_type)
    if normalized_source == SOURCE_MEDIA_TYPE_IMAGE:
        return VIEWER_ORIENTATION_DEFAULT
    if normalized_source == SOURCE_MEDIA_TYPE_VIDEO:
        return VIEWER_ORIENTATION_Y_FRONT

    if str(source_type or "").strip().lower() == SOURCE_MEDIA_TYPE_VIDEO:
        return VIEWER_ORIENTATION_Y_FRONT
    return VIEWER_ORIENTATION_UNKNOWN

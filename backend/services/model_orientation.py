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

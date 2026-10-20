import base64
import html
import json
import os
import re

from backend import runtime
from backend.services import model_gallery
from backend.services.model_orientation import (
    normalize_source_media_type, normalize_viewer_camera, normalize_viewer_transform,
    resolve_viewer_orientation,
)
from backend.services.model_convert import ply_to_splat, ply_to_spz
from backend.services.model_gallery import (
    MODEL_FORMAT_PRIORITY,
    collect_model_variants,
    normalize_model_item_id,
)


def _read_model_file(paths, filename):
    path = os.path.join(paths.output_folder, filename)
    with open(path, "rb") as file:
        return file.read()


def _resolve_export_payload(paths, model_id, requested_format):
    """Resolve or convert a model payload and report the format actually embedded."""
    item_id = normalize_model_item_id(model_id)
    if not item_id:
        return None

    variants = collect_model_variants(paths, item_id)
    if not variants:
        return None

    if requested_format == "spz" and "spz" not in variants and "ply" in variants:
        ply_path = os.path.join(paths.output_folder, variants["ply"])
        spz_filename = f"{item_id}.spz"
        spz_path = os.path.join(paths.output_folder, spz_filename)
        ply_to_spz(ply_path, spz_path)
        variants["spz"] = spz_filename

    if requested_format == "splat" and "splat" not in variants and "ply" in variants:
        ply_path = os.path.join(paths.output_folder, variants["ply"])
        return ply_to_splat(ply_path), "splat"

    format_order = [requested_format, "spz", "ply", "splat", "rad"]
    for model_format in dict.fromkeys(format_order):
        filename = variants.get(model_format)
        if filename:
            return _read_model_file(paths, filename), model_format
    return None


def build_export_html(paths, model_id, fmt):
    """Build the standalone HTML export and its response metadata."""
    if fmt not in MODEL_FORMAT_PRIORITY:
        fmt = "spz"

    item_id = normalize_model_item_id(model_id)
    if not item_id or not collect_model_variants(paths, item_id):
        return None, {"error": "Model not found"}, 404

    # The exact bundled viewer ships in dist with every application update.
    viewer_dir = os.path.join(runtime.BASE_DIR, "frontend", "dist", "share")
    assets = {}
    try:
        for key, filename in (("VIEWER_SCRIPT", "share-viewer.js"), ("VIEWER_STYLE", "share-viewer.css"),
                              ("LICENSE_NOTICES", "LICENSES.txt")):
            with open(os.path.join(viewer_dir, filename), encoding="utf-8") as file:
                assets[key] = file.read()
        with open(os.path.join(runtime.BASE_DIR, "frontend", "dist", "favicon-96x96.png"), "rb") as file:
            assets["FAVICON_DATA"] = "data:image/png;base64," + base64.b64encode(file.read()).decode("ascii")
    except FileNotFoundError:
        return None, {"error": "Standalone viewer files are missing. Build the frontend and retry.",
                      "code": "share_viewer_unavailable"}, 503

    resolved_payload = _resolve_export_payload(paths, model_id, fmt)
    if not resolved_payload:
        return None, {"error": "Model not found"}, 404

    model_bytes, actual_format = resolved_payload
    model_size = len(model_bytes)
    model_data = base64.b64encode(model_bytes).decode("ascii")
    scene_format = actual_format.upper()
    # Keep server logs ASCII-safe because Windows consoles may still use a
    # legacy code page such as GBK/CP936.
    print(f"[export] {model_id} as {scene_format} ({model_size / 1024 / 1024:.1f}MB)...")

    metadata = model_gallery.read_model_metadata(paths, item_id)
    source_type = normalize_source_media_type(metadata.get("source_media_type"))
    manifest = {
        "version": 1, "format": actual_format, "sourceMediaType": source_type,
        "viewerOrientation": resolve_viewer_orientation(metadata.get("viewer_orientation"),
                                                        source_media_type=source_type),
        "viewerTransform": normalize_viewer_transform(metadata.get("viewer_transform")),
        "viewerCamera": normalize_viewer_camera(metadata.get("viewer_camera")),
    }
    manifest_json = json.dumps(manifest, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")

    template_path = os.path.join(runtime.BASE_DIR, "templates", "share_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    display_name = model_gallery.get_model_display_name(paths, model_id)
    download_name = model_gallery.make_model_download_name(
        paths,
        model_id,
        ".html",
        suffix="_share",
    )
    replacements = {
        **assets,
        "MODEL_DATA": model_data,
        "MODEL_NAME": html.escape(display_name),
        "SCENE_FORMAT": scene_format,
        "VIEWER_MANIFEST": manifest_json,
    }
    replacements["VIEWER_SCRIPT"] = re.sub(r"</script", r"<\\/script", assets["VIEWER_SCRIPT"], flags=re.I)
    replacements["LICENSE_NOTICES"] = html.escape(assets["LICENSE_NOTICES"])
    # One pass: user names containing placeholder text must stay literal.
    html_content = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: replacements[match[1]], template)

    html_size = len(html_content.encode("utf-8"))
    print(
        f"[export] complete: model={model_size / 1024 / 1024:.1f}MB, "
        f"html={html_size / 1024 / 1024:.1f}MB"
    )

    return {
        "html": html_content,
        "format": actual_format,
        "model_size": model_size,
        "html_size": html_size,
        "download_name": download_name,
    }, None, 200

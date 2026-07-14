import base64
import html
import os

from backend import runtime
from backend.services.model_convert import ply_to_splat, ply_to_spz
from backend.services.model_gallery import (
    MODEL_FORMAT_PRIORITY,
    collect_model_variants,
    normalize_model_item_id,
)


def _pick_existing_path(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No available asset found in candidates: {candidates}")


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

    three_js_candidates = [
        os.path.join(runtime.BASE_DIR, "frontend", "node_modules", "three", "build", "three.module.js"),
        os.path.join(runtime.BASE_DIR, "static", "lib", "three.module.js"),
    ]
    orbit_controls_candidates = [
        os.path.join(
            runtime.BASE_DIR,
            "frontend",
            "node_modules",
            "three",
            "examples",
            "jsm",
            "controls",
            "OrbitControls.js",
        ),
    ]
    spark_js_candidates = [
        os.path.join(
            runtime.BASE_DIR,
            "frontend",
            "node_modules",
            "@sparkjsdev",
            "spark",
            "dist",
            "spark.module.js",
        ),
    ]
    pass_js_candidates = [
        os.path.join(
            runtime.BASE_DIR,
            "frontend",
            "node_modules",
            "three",
            "examples",
            "jsm",
            "postprocessing",
            "Pass.js",
        ),
    ]

    three_js_path = _pick_existing_path(three_js_candidates)
    orbit_controls_path = _pick_existing_path(orbit_controls_candidates)
    spark_js_path = _pick_existing_path(spark_js_candidates)
    pass_js_path = _pick_existing_path(pass_js_candidates)

    with open(three_js_path, "r", encoding="utf-8") as f:
        three_module_text = f.read()

    three_core_path = os.path.join(os.path.dirname(three_js_path), "three.core.js")
    three_core_data_url = "data:text/javascript,export%20{};"
    if os.path.exists(three_core_path):
        with open(three_core_path, "rb") as f:
            three_core_b64 = base64.b64encode(f.read()).decode("utf-8")
        three_core_data_url = f"data:text/javascript;base64,{three_core_b64}"
        three_module_text = three_module_text.replace("'./three.core.js'", "'three-core'")
        three_module_text = three_module_text.replace('"./three.core.js"', '"three-core"')

    three_js_b64 = base64.b64encode(three_module_text.encode("utf-8")).decode("utf-8")
    with open(orbit_controls_path, "rb") as f:
        orbit_controls_b64 = base64.b64encode(f.read()).decode("utf-8")
    with open(spark_js_path, "rb") as f:
        spark_js_b64 = base64.b64encode(f.read()).decode("utf-8")
    with open(pass_js_path, "rb") as f:
        pass_js_b64 = base64.b64encode(f.read()).decode("utf-8")

    three_data_url = f"data:text/javascript;base64,{three_js_b64}"
    orbit_controls_data_url = f"data:text/javascript;base64,{orbit_controls_b64}"
    spark_data_url = f"data:text/javascript;base64,{spark_js_b64}"
    pass_data_url = f"data:text/javascript;base64,{pass_js_b64}"

    template_path = os.path.join(runtime.BASE_DIR, "templates", "share_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    html_content = template.replace("{{MODEL_DATA}}", model_data)
    html_content = html_content.replace("{{MODEL_NAME}}", html.escape(model_id))
    html_content = html_content.replace("{{SCENE_FORMAT}}", scene_format)
    html_content = html_content.replace("{{THREE_DATA_URL}}", three_data_url)
    html_content = html_content.replace("{{THREE_CORE_DATA_URL}}", three_core_data_url)
    html_content = html_content.replace("{{ORBIT_CONTROLS_DATA_URL}}", orbit_controls_data_url)
    html_content = html_content.replace("{{SPARK_DATA_URL}}", spark_data_url)
    html_content = html_content.replace("{{PASS_DATA_URL}}", pass_data_url)

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
    }, None, 200

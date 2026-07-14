import base64
import contextlib
import io
import os

from backend.paths import build_path_context, ensure_runtime_directories
from backend import runtime
from backend.services import export_html, model_gallery


def write_model(paths, filename, payload):
    path = os.path.join(paths.output_folder, filename)
    with open(path, "wb") as file:
        file.write(payload)
    return path


def prepare_gallery_assets(paths, item_id):
    with open(model_gallery.get_model_metadata_path(paths, item_id), "w", encoding="utf-8") as file:
        file.write("{}")
    with open(model_gallery.get_thumbnail_path(paths, item_id), "wb") as file:
        file.write(b"jpg")


def test_gallery_groups_companion_formats_and_lists_standalone_formats(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)

    write_model(paths, "paired.ply", b"ply")
    write_model(paths, "paired.spz", b"spz")
    write_model(paths, "standalone.splat", b"splat")
    write_model(paths, "stream.rad", b"rad")
    os.mkdir(os.path.join(paths.output_folder, "ignored.ply"))
    for item_id in ("paired", "standalone", "stream"):
        prepare_gallery_assets(paths, item_id)

    items = {item["id"]: item for item in model_gallery.list_gallery_items(paths)}

    assert set(items) == {"paired", "standalone", "stream"}
    assert items["paired"]["model_format"] == "ply"
    assert items["paired"]["available_formats"] == ["ply", "spz"]
    assert items["paired"]["spz_url"].endswith("paired.spz")
    assert items["standalone"]["model_format"] == "splat"
    assert items["standalone"]["model_url"].endswith("standalone.splat")
    assert items["stream"]["model_format"] == "rad"
    assert items["stream"]["model_url"].endswith("stream.rad")


def test_download_falls_back_without_losing_requested_format_preference(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)

    write_model(paths, "paired.ply", b"ply")
    write_model(paths, "paired.spz", b"spz")
    write_model(paths, "standalone.splat", b"splat")

    assert model_gallery.resolve_download_model(paths, "paired", "spz") == "paired.spz"
    assert model_gallery.resolve_download_model(paths, "paired", "ply") == "paired.ply"
    assert model_gallery.resolve_download_model(paths, "standalone", "spz") == "standalone.splat"
    assert model_gallery.resolve_download_model(paths, "../paired", "ply") is None
    assert model_gallery.resolve_download_model(paths, "..\\paired", "ply") is None
    assert model_gallery.resolve_download_model(paths, "paired:stream", "ply") is None


def test_delete_removes_all_variants_for_one_gallery_item(workspace):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)

    for extension in model_gallery.MODEL_EXTENSIONS:
        write_model(paths, f"demo{extension}", extension.encode("ascii"))
    prepare_gallery_assets(paths, "demo")

    model_gallery.delete_gallery_item(paths, "demo")

    assert model_gallery.collect_model_variants(paths, "demo") == {}
    assert not os.path.exists(model_gallery.get_thumbnail_path(paths, "demo"))
    assert not os.path.exists(model_gallery.get_model_metadata_path(paths, "demo"))


def test_export_payload_supports_all_formats_and_safe_fallbacks(workspace, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)

    write_model(paths, "raw.ply", b"ply")
    write_model(paths, "standalone.splat", b"splat")
    write_model(paths, "stream.rad", b"rad")

    monkeypatch.setattr(export_html, "ply_to_splat", lambda _path: b"converted-splat")

    def fake_ply_to_spz(_ply_path, spz_path):
        with open(spz_path, "wb") as file:
            file.write(b"converted-spz")
        return spz_path

    monkeypatch.setattr(export_html, "ply_to_spz", fake_ply_to_spz)

    assert export_html._resolve_export_payload(paths, "raw", "ply") == (b"ply", "ply")
    assert export_html._resolve_export_payload(paths, "raw", "splat") == (
        b"converted-splat",
        "splat",
    )
    assert export_html._resolve_export_payload(paths, "raw", "spz") == (
        b"converted-spz",
        "spz",
    )
    assert export_html._resolve_export_payload(paths, "standalone", "spz") == (
        b"splat",
        "splat",
    )
    assert export_html._resolve_export_payload(paths, "stream", "rad") == (b"rad", "rad")
    assert export_html._resolve_export_payload(paths, "missing", "rad") is None


def test_build_export_html_reports_the_format_actually_embedded(workspace, tmp_path, monkeypatch):
    paths = build_path_context({"workspace_folder": str(workspace)})
    ensure_runtime_directories(paths)
    write_model(paths, "stream.rad", b"rad-data")

    base_dir = tmp_path / "runtime"
    asset_contents = {
        "frontend/node_modules/three/build/three.module.js": "export {};",
        "frontend/node_modules/three/examples/jsm/controls/OrbitControls.js": "export {};",
        "frontend/node_modules/three/examples/jsm/postprocessing/Pass.js": "export {};",
        "frontend/node_modules/@sparkjsdev/spark/dist/spark.module.js": "export {};",
    }
    for relative_path, content in asset_contents.items():
        asset_path = base_dir / relative_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(content, encoding="utf-8")

    template_path = base_dir / "templates/share_template.html"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "|".join([
            "{{MODEL_DATA}}",
            "{{MODEL_NAME}}",
            "{{SCENE_FORMAT}}",
            "{{THREE_DATA_URL}}",
            "{{THREE_CORE_DATA_URL}}",
            "{{ORBIT_CONTROLS_DATA_URL}}",
            "{{PASS_DATA_URL}}",
            "{{SPARK_DATA_URL}}",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "BASE_DIR", str(base_dir))

    legacy_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp936")
    with contextlib.redirect_stdout(legacy_stdout):
        result, error, status_code = export_html.build_export_html(paths, "stream", "spz")
        legacy_stdout.flush()

    assert error is None
    assert status_code == 200
    assert result["format"] == "rad"
    assert result["model_size"] == len(b"rad-data")
    assert base64.b64encode(b"rad-data").decode("ascii") in result["html"]
    assert "{{" not in result["html"]

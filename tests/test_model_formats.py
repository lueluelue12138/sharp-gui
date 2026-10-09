import base64
import contextlib
import gzip
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np
from plyfile import PlyData, PlyElement
import pytest

from backend.paths import build_path_context, ensure_runtime_directories
from backend import runtime
from backend.services import export_html, model_gallery
from backend.services import model_convert


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


def make_gaussian_vertices(sh_degree, point_count=5, rest_names=None):
    count = (0, 9, 24, 45)[sh_degree]
    if rest_names is None:
        rest_names = [f'f_rest_{index}' for index in range(count)]
    names = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2'] + rest_names
    names += ['opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    vertices = np.zeros(point_count, dtype=[(name, '<f4') for name in names])
    rng = np.random.default_rng(726)
    for name in ('x', 'y', 'z'):
        vertices[name] = rng.uniform(-3, 3, point_count)
    for name in ('f_dc_0', 'f_dc_1', 'f_dc_2'):
        vertices[name] = rng.uniform(-1, 1, point_count)
    vertices['opacity'] = rng.uniform(-2, 2, point_count)
    for name in ('scale_0', 'scale_1', 'scale_2'):
        vertices[name] = rng.uniform(-5, -1, point_count)
    quaternions = rng.normal(size=(point_count, 4))
    quaternions /= np.linalg.norm(quaternions, axis=1, keepdims=True)
    for component in range(4):
        vertices[f'rot_{component}'] = quaternions[:, component]
    for name in rest_names:
        vertices[name] = rng.uniform(-0.8, 0.8, point_count)
    return vertices


def write_gaussian_ply(path, vertices):
    PlyData([PlyElement.describe(vertices, 'vertex')], text=False, byte_order='<').write(path)
    return path


def decode_spz_v3_for_test(path):
    """独立按 Niantic v3 布局解码，验证真正的属性内容与 PLY 往返。"""
    raw = gzip.decompress(path.read_bytes())
    magic, version, count, degree, fractional_bits, flags, reserved = struct.unpack_from('<IIIBBBB', raw)
    assert (magic, version, flags, reserved) == (0x5053474E, 3, 0, 0)
    sh_count = (0, 9, 24, 45)[degree]
    assert len(raw) == 16 + count * (20 + sh_count)
    vertices = make_gaussian_vertices(degree, point_count=count)
    offset = 16
    for point in range(count):
        for component, name in enumerate(('x', 'y', 'z')):
            start = offset + point * 9 + component * 3
            fixed = int.from_bytes(raw[start:start + 3], 'little', signed=True)
            vertices[name][point] = fixed / (1 << fractional_bits)
    offset += count * 9
    for point in range(count):
        alpha = raw[offset + point] / 255
        vertices['opacity'][point] = math.log(alpha / (1 - alpha))
    offset += count
    for point in range(count):
        for component in range(3):
            vertices[f'f_dc_{component}'][point] = (raw[offset + point * 3 + component] / 255 - 0.5) / 0.15
    offset += count * 3
    for point in range(count):
        for component in range(3):
            vertices[f'scale_{component}'][point] = raw[offset + point * 3 + component] / 16 - 10
    offset += count * 3
    for point in range(count):
        packed = struct.unpack_from('<I', raw, offset + point * 4)[0]
        largest = packed >> 30
        quaternion = [0.0] * 4
        shift = 20
        for component in range(4):
            if component == largest:
                continue
            encoded = (packed >> shift) & 1023
            magnitude = (encoded & 511) / 511 / math.sqrt(2)
            quaternion[component] = -magnitude if encoded & 512 else magnitude
            shift -= 10
        quaternion[largest] = math.sqrt(max(0, 1 - sum(value * value for value in quaternion)))
        for component, name in enumerate(('rot_1', 'rot_2', 'rot_3', 'rot_0')):
            vertices[name][point] = quaternion[component]
    offset += count * 4
    dimensions = sh_count // 3
    for point in range(count):
        for coefficient in range(dimensions):
            for channel in range(3):
                encoded = raw[offset + point * sh_count + coefficient * 3 + channel]
                vertices[f'f_rest_{channel * dimensions + coefficient}'][point] = (encoded - 128) / 128
    return vertices, raw, degree


@pytest.mark.parametrize('sh_degree', range(4))
def test_spz_preserves_all_spherical_harmonic_degrees_and_ply_roundtrip(tmp_path, sh_degree):
    source = make_gaussian_vertices(sh_degree)
    ply_path = write_gaussian_ply(tmp_path / 'source.ply', source)
    spz_path = tmp_path / 'source.spz'

    assert model_convert.ply_to_spz(ply_path, spz_path) == spz_path
    decoded, raw, degree = decode_spz_v3_for_test(spz_path)

    assert degree == sh_degree
    assert decoded.dtype.names == source.dtype.names
    for name in ('x', 'y', 'z'):
        np.testing.assert_allclose(decoded[name], source[name], atol=1 / 4096, rtol=0)
    for name in ('f_dc_0', 'f_dc_1', 'f_dc_2'):
        np.testing.assert_allclose(decoded[name], source[name], atol=1 / (255 * 0.15 * 2) + 1e-7, rtol=0)
    for name in ('scale_0', 'scale_1', 'scale_2'):
        np.testing.assert_allclose(decoded[name], source[name], atol=1 / 32, rtol=0)
    expected_alpha = 1 / (1 + np.exp(-source['opacity']))
    actual_alpha = 1 / (1 + np.exp(-decoded['opacity']))
    np.testing.assert_allclose(actual_alpha, expected_alpha, atol=1 / 510 + 1e-7, rtol=0)
    source_quats = np.column_stack([source[f'rot_{component}'] for component in range(4)])
    decoded_quats = np.column_stack([decoded[f'rot_{component}'] for component in range(4)])
    np.testing.assert_allclose(np.abs(np.sum(source_quats * decoded_quats, axis=1)), 1, atol=2e-6, rtol=0)
    dimensions = (0, 3, 8, 15)[sh_degree]
    for channel in range(3):
        for coefficient in range(dimensions):
            name = f'f_rest_{channel * dimensions + coefficient}'
            tolerance = (1 / 32 if coefficient < 3 else 1 / 16) + 1 / 256
            np.testing.assert_allclose(decoded[name], source[name], atol=tolerance + 1e-7, rtol=0)
    restored_ply = write_gaussian_ply(tmp_path / 'restored.ply', decoded)
    restored_spz = tmp_path / 'restored.spz'
    model_convert.ply_to_spz(restored_ply, restored_spz)
    assert gzip.decompress(restored_spz.read_bytes()) == raw


def test_spz_sh_payload_matches_official_quantization_and_channel_order(tmp_path):
    source = make_gaussian_vertices(2, point_count=1)
    channels = [
        [0, 0.03125, 0.0625, 0.0625, 0.125, 0.1875, 0.25, -0.0625],
        [-0.03125, -0.0625, -0.09375, -0.125, -0.1875, -0.25, -0.3125, -0.375],
        [1, -1, 0.96875, 1, -1, 0.9375, -0.9375, 0.03125],
    ]
    for channel, coefficients in enumerate(channels):
        for coefficient, value in enumerate(coefficients):
            source[f'f_rest_{channel * 8 + coefficient}'] = value
    source_path = write_gaussian_ply(tmp_path / 'golden.ply', source)
    spz_path = tmp_path / 'golden.spz'
    model_convert.ply_to_spz(source_path, spz_path)

    raw = gzip.decompress(spz_path.read_bytes())
    assert raw[36:] == bytes([
        128, 128, 255, 136, 120, 0, 136, 120, 255, 144, 112, 255,
        144, 112, 0, 160, 96, 255, 160, 96, 16, 128, 80, 128,
    ])


def test_spz_sh_rounds_half_values_away_from_zero(tmp_path):
    source = make_gaussian_vertices(1, point_count=1)
    source['f_rest_0'] = -4.5 / 128
    source['f_rest_3'] = 3.5 / 128
    source['f_rest_6'] = 0
    source_path = write_gaussian_ply(tmp_path / 'half.ply', source)
    spz_path = tmp_path / 'half.spz'
    model_convert.ply_to_spz(source_path, spz_path)

    assert gzip.decompress(spz_path.read_bytes())[36:39] == bytes([120, 136, 128])


def test_spz_sh_resolves_numeric_names_independent_of_ply_property_order(tmp_path):
    source = make_gaussian_vertices(3)
    reversed_names = list(reversed(source.dtype.names))
    reordered = np.empty(len(source), dtype=[(name, '<f4') for name in reversed_names])
    for name in reversed_names:
        reordered[name] = source[name]
    first_path = write_gaussian_ply(tmp_path / 'ordered.ply', source)
    second_path = write_gaussian_ply(tmp_path / 'reordered.ply', reordered)
    first_spz = tmp_path / 'ordered.spz'
    second_spz = tmp_path / 'reordered.spz'

    model_convert.ply_to_spz(first_path, first_spz)
    model_convert.ply_to_spz(second_path, second_spz)

    assert gzip.decompress(first_spz.read_bytes()) == gzip.decompress(second_spz.read_bytes())


@pytest.mark.parametrize('rest_names', [
    ['f_rest_0'],
    [f'f_rest_{index}' for index in range(8)],
    [f'f_rest_{index}' for index in range(10)],
    [f'f_rest_{index}' for index in range(44)],
    [f'f_rest_{index}' for index in range(72)],
    [f'f_rest_{index}' for index in range(1, 10)],
    [f'f_rest_{index}' for index in range(8)] + ['f_rest_bad'],
])
def test_spz_rejects_incomplete_or_unsupported_sh_without_overwriting_target(tmp_path, rest_names):
    source = make_gaussian_vertices(1, rest_names=rest_names)
    source_path = write_gaussian_ply(tmp_path / 'invalid.ply', source)
    spz_path = tmp_path / 'invalid.spz'
    spz_path.write_bytes(b'existing model')

    with pytest.raises(ValueError, match='complete f_rest'):
        model_convert.ply_to_spz(source_path, spz_path)

    assert spz_path.read_bytes() == b'existing model'
    assert list(tmp_path.glob('.spz-*.tmp')) == []


def test_spz_rejects_nonfinite_sh_and_cleans_partial_conversion(tmp_path):
    source = make_gaussian_vertices(3)
    source['f_rest_44'][2] = np.nan
    source_path = write_gaussian_ply(tmp_path / 'nonfinite.ply', source)
    spz_path = tmp_path / 'nonfinite.spz'
    spz_path.write_bytes(b'existing model')

    with pytest.raises(ValueError, match='finite'):
        model_convert.ply_to_spz(source_path, spz_path)

    assert spz_path.read_bytes() == b'existing model'
    assert list(tmp_path.glob('.spz-*.tmp')) == []


def test_spz_streaming_chunks_preserve_global_attribute_layout(tmp_path, monkeypatch):
    source = make_gaussian_vertices(3, point_count=7)
    source_path = write_gaussian_ply(tmp_path / 'chunked.ply', source)
    single_spz = tmp_path / 'single.spz'
    chunked_spz = tmp_path / 'chunked.spz'
    model_convert.ply_to_spz(source_path, single_spz)
    monkeypatch.setattr(model_convert, 'SPZ_CHUNK_POINTS', 2)

    model_convert.ply_to_spz(source_path, chunked_spz)

    assert gzip.decompress(chunked_spz.read_bytes()) == gzip.decompress(single_spz.read_bytes())
    assert decode_spz_v3_for_test(chunked_spz)[2] == 3


@pytest.mark.parametrize('sh_degree', range(4))
def test_spz_is_readable_with_project_spark_decoder(tmp_path, sh_degree):
    node = shutil.which('node')
    spark_module = Path(__file__).resolve().parents[1] / 'frontend/node_modules/@sparkjsdev/spark/dist/spark.module.js'
    if node is None or not spark_module.is_file():
        pytest.skip('Spark decoder integration requires installed frontend dependencies and Node.js')
    source = make_gaussian_vertices(sh_degree)
    source_path = write_gaussian_ply(tmp_path / 'spark.ply', source)
    spz_path = tmp_path / 'spark.spz'
    model_convert.ply_to_spz(source_path, spz_path)
    decoded, _, _ = decode_spz_v3_for_test(spz_path)
    script = '''
        import { readFileSync } from 'node:fs';
        const { SpzReader } = await import(process.argv[1]);
        const reader = new SpzReader({ fileBytes: new Uint8Array(readFileSync(process.argv[2])) });
        await reader.parseHeader();
        const centers = [], alphas = [], colors = [], scales = [], quaternions = [], sh = [];
        await reader.parseSplats(
            (i, ...values) => { centers[i] = values; },
            (i, value) => { alphas[i] = value; },
            (i, ...values) => { colors[i] = values; },
            (i, ...values) => { scales[i] = values; },
            (i, ...values) => { quaternions[i] = values; },
            (i, ...bands) => { sh[i] = bands.filter(Boolean).flatMap(band => Array.from(band)); },
        );
        console.log(JSON.stringify({ degree: reader.shDegree, count: reader.numSplats,
            centers, alphas, colors, scales, quaternions, sh }));
    '''
    result = subprocess.run(
        [node, '--input-type=module', '-e', script, spark_module.as_uri(), str(spz_path)],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    actual = json.loads(result.stdout)
    assert (actual['degree'], actual['count']) == (sh_degree, len(source))
    np.testing.assert_allclose(actual['centers'], np.column_stack([decoded[name] for name in ('x', 'y', 'z')]))
    np.testing.assert_allclose(actual['alphas'], 1 / (1 + np.exp(-decoded['opacity'])), atol=1e-7, rtol=0)
    expected_colors = 0.5 + 0.28209479177387814 * np.column_stack([
        decoded[f'f_dc_{channel}'] for channel in range(3)
    ])
    np.testing.assert_allclose(actual['colors'], expected_colors, atol=1e-7, rtol=0)
    expected_scales = np.exp(np.column_stack([decoded[f'scale_{component}'] for component in range(3)]))
    np.testing.assert_allclose(actual['scales'], expected_scales, atol=1e-7, rtol=0)
    expected_quaternions = np.column_stack([decoded[name] for name in ('rot_1', 'rot_2', 'rot_3', 'rot_0')])
    np.testing.assert_allclose(actual['quaternions'], expected_quaternions, atol=1e-7, rtol=0)
    if sh_degree == 0:
        assert actual['sh'] == []
    else:
        count = (0, 9, 24, 45)[sh_degree]
        expected_sh = np.column_stack([decoded[f'f_rest_{index}'] for index in range(count)])
        expected_sh = expected_sh.reshape(len(decoded), 3, count // 3).transpose(0, 2, 1).reshape(len(decoded), count)
        np.testing.assert_array_equal(actual['sh'], expected_sh)

import hashlib
import math
import os
import struct
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.services import brush_engine
from tools import install_brush
from backend.services.model_orientation import normalize_viewer_camera


def write_colmap_model(root, names, point_count=3, text=False):
    root.mkdir(parents=True, exist_ok=True)
    if text:
        (root / 'cameras.txt').write_text('1 PINHOLE 16 16 12 12 8 8\n', encoding='utf-8')
        (root / 'images.txt').write_text(
            '# Image list with two lines of data per image:\n'
            + ''.join(f'{index} 1 0 0 0 0 0 0 1 {name}\n\n'
                      for index, name in enumerate(names, 1)),
            encoding='utf-8',
        )
        (root / 'points3D.txt').write_text(
            '# 3D point list\n'
            + ''.join(f'{index} 1 2 3 255 128 0 0.1\n' for index in range(point_count)),
            encoding='utf-8',
        )
        return
    (root / 'cameras.bin').write_bytes(
        struct.pack('<QiiQQdddd', 1, 1, 1, 16, 16, 12.0, 12.0, 8.0, 8.0),
    )
    records = [struct.pack('<Q', len(names))]
    for index, name in enumerate(names, 1):
        records.extend([
            struct.pack('<i7di', index, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1),
            name.encode('utf-8') + b'\0', struct.pack('<Q', 0),
        ])
    (root / 'images.bin').write_bytes(b''.join(records))
    (root / 'points3D.bin').write_bytes(
        struct.pack('<Q', point_count)
        + b''.join(struct.pack('<QdddBBBdQ', index, 1.0, 2.0, 3.0, 255, 128, 0, 0.1, 0)
                   for index in range(point_count)),
    )


def write_gaussian_ply(path, sh_degree=3, count=2, non_finite=False):
    names = [
        'x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2',
        *[f'f_rest_{index}' for index in range(3 * ((sh_degree + 1) ** 2 - 1))],
        'opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3',
    ]
    vertices = np.zeros(count, dtype=[(name, '<f4') for name in names])
    vertices['rot_0'] = 1
    if non_finite:
        vertices['f_rest_44'][-1] = np.nan
    header = ('ply\nformat binary_little_endian 1.0\n'
              f'element vertex {count}\n'
              + ''.join(f'property float {name}\n' for name in names)
              + 'end_header\n').encode('ascii')
    path.write_bytes(header + vertices.tobytes())
    return vertices


def test_initial_view_uses_registered_camera_and_positive_point_depth(tmp_path):
    write_colmap_model(tmp_path / 'sparse' / '0', ['frame_000001.jpg'])
    hint = brush_engine.build_brush_viewer_camera(tmp_path)
    assert hint['position'] == [0.0, 0.0, 0.0]
    assert hint['target'] == [0.0, 0.0, 3.0]
    assert hint['up'] == [0.0, -1.0, 0.0]
    assert hint['fov_y_degrees'] == pytest.approx(math.degrees(2 * math.atan(16 / 24)))
    assert normalize_viewer_camera(hint) == hint
    assert normalize_viewer_camera({**hint, 'position': [float('nan'), 0, 0]}) is None
    assert normalize_viewer_camera({**hint, 'target': hint['position']}) is None
    assert normalize_viewer_camera({**hint, 'up': [0, 0, 1]}) is None
    assert normalize_viewer_camera({**hint, 'aspect': 'bad'}) is None


def test_initial_view_falls_back_when_no_points_are_visible(tmp_path):
    write_colmap_model(tmp_path / 'sparse' / '0', ['frame.jpg'], point_count=0)
    assert brush_engine.build_brush_viewer_camera(tmp_path) is None


def test_bundled_brush_has_priority_over_explicit_configuration(tmp_path, monkeypatch):
    bundled = tmp_path / brush_engine.BRUSH_INSTALL_RELATIVE_PATH / 'brush_app.exe'
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b'bundled')
    configured = tmp_path / 'custom brush.exe'
    configured.write_bytes(b'configured')
    environment = {'SHARP_BRUSH_EXECUTABLE': str(configured), 'PATH': ''}
    assert brush_engine.find_brush_executable(tmp_path, environment) == str(bundled.resolve())
    bundled.unlink()
    assert brush_engine.find_brush_executable(tmp_path, environment) == str(configured.resolve())
    configured.unlink()
    assert brush_engine.find_brush_executable(tmp_path, environment) is None


def test_brush_train_command_matches_locked_cli_and_preserves_full_sh(tmp_path):
    command = brush_engine.build_brush_train_command('brush_app.exe', tmp_path / 'data', tmp_path / 'output', {
        'max_num_iterations': 8000, 'brush_max_resolution': 1600,
        'brush_growth_grad_threshold': 0.00004,
        'brush_growth_select_fraction': 0.15,
        'brush_growth_stop_iter': 6000, 'brush_max_splats': 1000000,
    })
    options = dict(zip(command[1:-1:2], command[2:-1:2]))
    assert options['--total-steps'] == '8000'
    assert options['--growth-stop-iter'] == '6000'
    assert options['--max-resolution'] == '1600'
    assert options['--max-splats'] == '1000000'
    assert options['--sh-degree'] == '3'
    assert options['--export-every'] == '8000'
    assert options['--export-name'] == 'final.ply'
    assert command[-1] == str((tmp_path / 'data').resolve())
    assert '--with-viewer' not in command


@pytest.mark.parametrize('profile', [
    {'max_num_iterations': -1},
    {'brush_max_splats': 0},
    {'brush_growth_grad_threshold': float('nan')},
    {'brush_growth_select_fraction': 1.1},
    {'max_num_iterations': 8000, 'brush_growth_stop_iter': 8001},
])
def test_training_rejects_invalid_resource_and_growth_parameters(tmp_path, profile):
    with pytest.raises(ValueError):
        brush_engine.build_brush_train_command('brush', tmp_path, tmp_path, profile)


def test_brush_gpu_environment_is_child_only_and_respects_explicit_device():
    original = {'PATH': 'original', 'RUST_LOG': 'warn', 'CUBECL_WGPU_DEFAULT_DEVICE': 'DiscreteGpu(1)'}
    environment = brush_engine.build_brush_environment(original)
    assert original == {'PATH': 'original', 'RUST_LOG': 'warn', 'CUBECL_WGPU_DEFAULT_DEVICE': 'DiscreteGpu(1)'}
    assert environment['CUBECL_WGPU_DEFAULT_DEVICE'] == 'DiscreteGpu(1)'
    assert 'brush_cli=info' in environment['RUST_LOG']
    automatic = brush_engine.build_brush_environment({})
    assert automatic['CUBECL_WGPU_DEFAULT_DEVICE'] == 'DiscreteGpu(0)'
    if os.name == 'nt':
        assert automatic['DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1'] == '1'
    assert 'CUBECL_WGPU_DEFAULT_DEVICE' not in brush_engine.build_brush_environment({}, False)


def test_progress_uses_actual_locked_brush_logs_and_ignores_elapsed_estimates():
    progress = brush_engine.parse_brush_progress(
        '\x1b[32m[2026-09-28T12:34:56Z INFO brush_cli] Refine iter 1200, 45,678 splats.\x1b[0m', 8000,
    )
    assert progress == {
        'step': 1200, 'iteration': 1200, 'total_steps': 8000, 'progress': 0.15, 'splat_count': 45678,
    }
    assert brush_engine.parse_brush_progress('[00:30] oooo 800/8000 Steps (26.7/s, 4m remaining)', 8000)['progress'] == 0.1
    assert brush_engine.parse_brush_progress('Training took 2m 34s', 8000) is None
    assert brush_engine.parse_brush_progress('Refine iter 9000, 50000 splats.', 8000) is None
    assert brush_engine.parse_brush_progress('100/30000 Steps', 8000) is None


def test_best_colmap_submodel_is_chosen_by_registered_views_not_folder_zero(tmp_path):
    data = tmp_path / 'data'
    write_colmap_model(data / 'colmap' / 'sparse' / '0', ['a.png', 'b.png'], point_count=10)
    write_colmap_model(data / 'colmap' / 'sparse' / '1', ['a.png', 'b.png', 'c.png'], point_count=3)
    model = brush_engine.inspect_colmap_models(data)
    assert model['model_dir'].endswith(str(Path('sparse') / '1'))
    assert model['registered_images'] == 3
    assert model['sfm_points'] == 3
    assert len(model['models']) == 2


def test_dataset_copies_registered_full_size_images_and_keeps_source_untouched(tmp_path):
    data = tmp_path / 'data'
    images = data / 'images'
    images.mkdir(parents=True)
    for name in ('a.png', 'b.png', 'unregistered.png'):
        Image.new('RGB', (40, 24), (123, 40, 50)).save(images / name)
    write_colmap_model(data / 'colmap' / 'sparse' / '0', ['a.png', 'b.png'])
    original = {path: path.read_bytes() for path in data.rglob('*') if path.is_file()}
    target = tmp_path / 'brush-data'
    result = brush_engine.prepare_brush_dataset(data, target)
    assert result['image_count'] == result['registered_images'] == 2
    assert not (target / 'images' / 'unregistered.png').exists()
    assert (target / 'sparse' / '0' / 'points3D.bin').exists()
    with Image.open(target / 'images' / 'a.png') as image:
        assert image.size == (40, 24)
    assert all(path.read_bytes() == payload for path, payload in original.items())


@pytest.mark.parametrize('text', [False, True])
def test_z_up_normalization_preserves_projection_and_original_model_hashes(tmp_path, text):
    data = tmp_path / 'data'
    model = data / 'colmap' / 'sparse' / '0'
    write_colmap_model(model, ['a.png', 'b.png'], text=text)
    (data / 'images').mkdir()
    for name in ('a.png', 'b.png'):
        (data / 'images' / name).write_bytes(b'synthetic image')
    original_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in model.iterdir()}
    original_poses = brush_engine._read_colmap_poses(model, 'txt' if text else 'bin')
    result = brush_engine.prepare_brush_dataset(data, tmp_path / 'brush-data')
    alignment = np.asarray(result['up_alignment']['rotation_matrix'])
    assert result['up_alignment']['aligned']
    new_model = Path(result['model_dir'])
    new_poses = brush_engine._read_colmap_poses(new_model, 'txt' if text else 'bin')
    original_point = np.asarray([1.0, 2.0, 3.0])
    if text:
        line = next(line for line in (new_model / 'points3D.txt').read_text().splitlines()
                    if line.strip() and not line.startswith('#'))
        new_point = np.asarray([float(value) for value in line.split()[1:4]])
    else:
        fields = struct.unpack('<Q3d3BdQ', (new_model / 'points3D.bin').read_bytes()[8:59])
        new_point = np.asarray(fields[1:4])
    np.testing.assert_allclose(new_point, alignment @ original_point, atol=1e-12)
    np.testing.assert_allclose(alignment @ np.asarray(result['up_alignment']['source_up']), [0, 0, 1], atol=1e-12)
    for (old_rotation, old_translation), (rotation, translation) in zip(original_poses, new_poses):
        # 整个世界旋转后，同一点仍投影到完全相同的相机空间坐标。
        np.testing.assert_allclose(rotation @ new_point + translation,
                                   old_rotation @ original_point + old_translation, atol=1e-12)
        np.testing.assert_allclose(-rotation.T[:, 1], [0, 0, 1], atol=1e-12)
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest
               for path, digest in original_hashes.items())


@pytest.mark.parametrize('axis', [np.asarray([1, 0, 0]), np.asarray([0, 1, 0]),
                                np.asarray([0, 0, 1]), np.asarray([1, 2, 3])])
def test_quaternion_roundtrip_is_stable_near_half_turn(axis):
    axis = axis / np.linalg.norm(axis)
    for angle in (0.0, 0.00001, np.pi / 2, np.pi - 1e-12, np.pi):
        quaternion = np.concatenate([[np.cos(angle / 2)], axis * np.sin(angle / 2)])
        rotation = brush_engine._quaternion_to_rotation(quaternion)
        recovered = brush_engine._rotation_to_quaternion(rotation)
        np.testing.assert_allclose(brush_engine._quaternion_to_rotation(recovered), rotation, atol=1e-12)


def test_object_focus_uses_colmap_forward_rays_in_the_same_world_frame(tmp_path):
    model = tmp_path / 'sparse' / '0'
    names = [f'{index}.png' for index in range(8)]
    write_colmap_model(model, names)
    center = np.asarray([1.0, 2.0, 3.0])
    records = [struct.pack('<Q', len(names))]
    for index, name in enumerate(names):
        angle = index * np.pi / 4
        origin = center + np.asarray([4 * np.cos(angle), 4 * np.sin(angle), 1])
        forward = center - origin
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 0, 1])
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        rotation = np.asarray([right, down, forward])
        translation = -rotation @ origin
        records.extend([
            struct.pack('<i7di', index + 1, *brush_engine._rotation_to_quaternion(rotation),
                        *translation, 1), name.encode() + b'\0', struct.pack('<Q', 0),
        ])
    (model / 'images.bin').write_bytes(b''.join(records))
    focus = brush_engine.estimate_brush_object_focus(tmp_path)
    assert focus is not None
    np.testing.assert_allclose(focus[0], center, atol=1e-12)
    assert focus[1] == pytest.approx(np.sqrt(17) * 0.55)


def test_text_colmap_empty_observation_lines_and_nested_names_are_supported(tmp_path):
    data = tmp_path / 'data'
    write_colmap_model(data / 'sparse' / '3', ['nested/a.png', 'space b.png'], text=True)
    (data / 'images' / 'nested').mkdir(parents=True)
    (data / 'images' / 'nested' / 'a.png').write_bytes(b'synthetic image')
    (data / 'images' / 'space b.png').write_bytes(b'synthetic image')
    target = tmp_path / 'brush-data'
    result = brush_engine.prepare_brush_dataset(data, target)
    assert result['registered_images'] == 2
    assert (target / 'images' / 'nested' / 'a.png').read_bytes() == b'synthetic image'
    assert (target / 'sparse' / '0' / 'images.txt').exists()


def test_missing_or_escaping_registered_image_does_not_publish_partial_dataset(tmp_path):
    data = tmp_path / 'data'
    write_colmap_model(data / 'colmap' / 'sparse' / '0', ['a.png', '../private.png'])
    (data / 'images').mkdir()
    (data / 'images' / 'a.png').write_bytes(b'image')
    target = tmp_path / 'brush-data'
    with pytest.raises(ValueError, match='Unsafe COLMAP image path'):
        brush_engine.prepare_brush_dataset(data, target)
    assert not target.exists()
    write_colmap_model(data / 'colmap' / 'sparse' / '0', ['a.png', 'missing.png'])
    with pytest.raises(ValueError, match='missing'):
        brush_engine.prepare_brush_dataset(data, target)
    assert not target.exists()


def test_truncated_colmap_binary_is_rejected_without_large_allocation(tmp_path):
    write_colmap_model(tmp_path / 'sparse' / '0', ['a.png', 'b.png'])
    (tmp_path / 'sparse' / '0' / 'images.bin').write_bytes(struct.pack('<Q', 2 ** 63))
    with pytest.raises(ValueError, match='No complete COLMAP model'):
        brush_engine.inspect_colmap_models(tmp_path)


def test_dataset_target_cannot_overwrite_or_alias_input(tmp_path):
    write_colmap_model(tmp_path / 'data' / 'sparse' / '0', ['a.png', 'b.png'])
    with pytest.raises(ValueError, match='separate'):
        brush_engine.prepare_brush_dataset(tmp_path / 'data', tmp_path / 'data' / 'brush')
    destination = tmp_path / 'existing'
    destination.mkdir()
    marker = destination / 'keep.txt'
    marker.write_text('keep', encoding='utf-8')
    with pytest.raises(ValueError, match='empty'):
        brush_engine.prepare_brush_dataset(tmp_path / 'data', destination)
    assert marker.read_text(encoding='utf-8') == 'keep'


def test_gaussian_output_retains_sh3_and_validation_releases_file_handle(tmp_path):
    output = tmp_path / 'final.ply'
    write_gaussian_ply(output)
    assert brush_engine.find_brush_output(tmp_path) == str(output.resolve())
    metadata = brush_engine.validate_brush_ply(output)
    assert metadata['sh_degree'] == 3
    assert metadata['vertex_count'] == 2
    output.rename(tmp_path / 'published.ply')
    assert brush_engine.find_brush_output(tmp_path) is None


@pytest.mark.parametrize('failure', ['truncated', 'nonfinite', 'pointcloud'])
def test_invalid_gaussian_export_is_rejected(tmp_path, failure):
    output = tmp_path / 'final.ply'
    if failure == 'pointcloud':
        output.write_bytes(b'ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nend_header\n' + b'\0' * 4)
    else:
        write_gaussian_ply(output, non_finite=failure == 'nonfinite')
        if failure == 'truncated':
            output.write_bytes(output.read_bytes()[:-1])
    with pytest.raises(ValueError):
        brush_engine.validate_brush_ply(output)


def test_windows_official_release_is_locked_and_other_platforms_are_explicit():
    locked = install_brush.resolve_release('Windows', 'AMD64')
    assert locked['url'] == 'https://github.com/ArthurBrussee/brush/releases/download/v0.3.0/brush-app-x86_64-pc-windows-msvc.zip'
    assert locked['archive_sha256'] == 'b68e3e9cf052d51bf3ee30776fa5a364de7f2ba13b58443128ff797bb7bcfcd6'
    assert locked['binary_sha256'] == '37e46cbf808b9983dd15a5f9a25328dbe43e7e06d53c4f59fbeaeb10e3a5b34a'
    with pytest.raises(RuntimeError, match='supports'):
        install_brush.resolve_release('Windows', 'arm64')


def test_archive_traversal_and_tar_links_are_rejected(tmp_path):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('../outside.txt', 'must not be written')
    with pytest.raises(RuntimeError, match='Unsafe path'):
        install_brush.extract_archive(archive, tmp_path / 'extracted')
    assert not (tmp_path / 'outside.txt').exists()
    archive = tmp_path / 'unsafe.tar.xz'
    with tarfile.open(archive, 'w:xz') as bundle:
        member = tarfile.TarInfo('brush_app')
        member.type = tarfile.SYMTYPE
        member.linkname = '../outside'
        bundle.addfile(member)
    with pytest.raises(RuntimeError, match='Links'):
        install_brush.extract_archive(archive, tmp_path / 'tar-extracted')


def test_verified_install_keeps_license_attribution_and_is_idempotent(tmp_path, monkeypatch):
    archive = tmp_path / 'brush.zip'
    binary = b'synthetic executable for contract test'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('release/brush_app.exe', binary)
        bundle.writestr('release/NOTICE', 'upstream archive notice')
    release = {
        'archive': archive.name, 'archive_sha256': install_brush.sha256_file(archive),
        'binary': 'brush_app.exe', 'binary_sha256': hashlib.sha256(binary).hexdigest(),
        'platform': 'windows', 'architecture': 'x86_64', 'url': 'https://example.invalid/fixed.zip',
    }
    monkeypatch.setattr(install_brush, 'resolve_release', lambda: release)
    validations = []
    monkeypatch.setattr(install_brush, 'verify_brush_cli', lambda path: validations.append(path))
    target = tmp_path / 'dependency'
    executable = install_brush.install_brush(target, archive)
    assert executable.read_bytes() == binary
    assert 'Apache License' in (target / 'LICENSE.txt').read_text(encoding='utf-8')
    assert 'Arthur Brussee' in (target / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
    assert (target / 'upstream-release' / 'release' / 'NOTICE').read_text() == 'upstream archive notice'
    assert install_brush.install_brush(target, archive) == executable
    assert len(validations) == 2


def test_archive_hash_failure_keeps_previous_engine(tmp_path, monkeypatch):
    target = tmp_path / 'dependency'
    target.mkdir()
    previous = target / 'brush_app.exe'
    previous.write_bytes(b'previous engine')
    archive = tmp_path / 'bad.zip'
    archive.write_bytes(b'not the official download')
    with pytest.raises(RuntimeError, match='SHA-256 mismatch'):
        install_brush.install_brush(target, archive, force=True, verify_cli=False)
    assert previous.read_bytes() == b'previous engine'

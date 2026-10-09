"""用合成 COLMAP/PLY 数据验证视频重建链路，不读取用户视频。"""

import gzip
import io
import json
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from plyfile import PlyData, PlyElement

from backend.config import get_default_video_reconstruction_config
from backend.paths import build_path_context
from backend.services import brush_engine, model_assets, model_gallery, video_geometry, video_reconstruction
from backend.services.task_queue import TaskManager
from tools import train_splatfacto


def write_colmap_model(data_dir, registered, extracted=None):
    """创建带共享相机、位姿、观测和点轨迹的合法小型 COLMAP 二进制模型。"""
    root = Path(data_dir)
    images = root / 'images'
    sparse = root / 'colmap' / 'sparse' / '0'
    images.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(parents=True, exist_ok=True)
    image_names = [f'frame_{index:06d}.jpg' for index in range(1, registered + 1)]
    for index in range(1, (extracted or registered) + 1):
        Image.new('RGB', (64, 36), (index % 255, 80, 160)).save(images / f'frame_{index:06d}.jpg')
    with (sparse / 'cameras.bin').open('wb') as stream:
        stream.write(struct.pack('<Q', 1))
        stream.write(struct.pack('<iiQQ4d', 1, 2, 64, 36, 50.0, 32.0, 18.0, 0.0))
    with (sparse / 'images.bin').open('wb') as stream:
        stream.write(struct.pack('<Q', registered))
        for image_id, name in enumerate(image_names, 1):
            stream.write(struct.pack('<i4d3di', image_id, 1.0, 0.0, 0.0, 0.0,
                                     image_id * 0.01, 0.0, 0.0, 1))
            stream.write(name.encode('utf-8') + b'\0')
            stream.write(struct.pack('<Q', 4))
            for point_id in range(1, 5):
                stream.write(struct.pack('<ddq', 16.0 + point_id * 4, 12.0 + point_id, point_id))
    with (sparse / 'points3D.bin').open('wb') as stream:
        stream.write(struct.pack('<Q', 4))
        for point_id in range(1, 5):
            stream.write(struct.pack('<Q3d3BdQ', point_id, (point_id - 2) * 0.1,
                                     0.05, 3.0, 120, 160, 200, 0.1, registered))
            for image_id in range(1, registered + 1):
                stream.write(struct.pack('<ii', image_id, point_id - 1))
    return image_names


def write_gaussian_ply(path, vertex_count=25, marker=0.1):
    """生成完整 SH3 Gaussian PLY，包含应由自动模式保留的离群点。"""
    properties = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity',
                  'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    properties += [f'f_rest_{index}' for index in range(45)]
    vertices = np.zeros(vertex_count, dtype=[(name, '<f4') for name in properties])
    vertices['x'] = np.linspace(-0.1, 0.1, vertex_count)
    vertices['y'] = marker
    vertices['z'] = 3
    vertices['x'][-1] = 50
    vertices['opacity'] = 2
    vertices['rot_0'] = 1
    for name in ('scale_0', 'scale_1', 'scale_2'):
        vertices[name] = -4
    for index in range(45):
        vertices[f'f_rest_{index}'] = (index - 22) * 0.01
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(vertices, 'vertex')], text=False, byte_order='<').write(path)
    return path.read_bytes()


@pytest.fixture
def video_task(tmp_path, monkeypatch):
    """任务仅指向本测试生成的占位视频，所有媒体探测和外部进程均被替换。"""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source = workspace / 'synthetic.mp4'
    source.write_bytes(b'synthetic video placeholder')
    paths = build_path_context({'workspace_folder': str(workspace)})
    manager = TaskManager(paths=paths)
    task = {
        'id': 'video-contract', 'kind': 'video_3dgs', 'filename': 'synthetic.ply',
        'status': 'pending', 'created_at': 1, 'source_media_id': 'synthetic-video',
        'source_name': source.name, 'source_video_path': str(source),
        'mode': 'auto', 'quality': 'high', 'engine': 'brush', 'resolved_engine': 'brush',
        'vram_budget': '12gb', 'output_name': 'synthetic',
        'output_path': str(Path(paths.output_folder) / 'synthetic.ply'),
        'spz_path': str(Path(paths.output_folder) / 'synthetic.spz'),
        'keep_intermediate_files': False, 'details': {'warnings': [], 'logs': []},
        'error': None,
    }
    manager.task_status[task['id']] = task
    monkeypatch.setattr(video_reconstruction, 'effective_vram_budget', lambda _configured: '12gb')
    monkeypatch.setattr(video_reconstruction, 'build_video_process_env', lambda: {})
    monkeypatch.setattr(brush_engine, 'find_brush_executable', lambda: 'synthetic-brush')
    monkeypatch.setattr(video_geometry, 'probe_video', lambda *_args: {
        'width': 1920, 'height': 1080, 'duration_seconds': 5.0, 'source_fps': 30,
    })
    monkeypatch.setattr(video_geometry, 'colmap_option_names', lambda _env: ('SiftExtraction', 'SiftMatching'))
    monkeypatch.setattr(model_gallery, 'generate_video_thumbnail', lambda *_args: None)
    return manager, task


class SyntheticGeometry:
    """替换外部命令，保留真实抽帧目录和真实 COLMAP 文件契约。"""

    def __init__(self, registered_counts, mapper_failures=(), cancel_at=None):
        self.registered_counts = registered_counts
        self.mapper_failures = set(mapper_failures)
        self.cancel_at = cancel_at
        self.commands = []
        self.extracted = {}

    def __call__(self, _manager, _task_id, command, **kwargs):
        self.commands.append((list(command), kwargs))
        operation = command[1] if len(command) > 1 else ''
        if kwargs.get('stage') == 'video_extract_frames':
            images = Path(command[-1]).parent
            count = int(command[command.index('-frames:v') + 1])
            self.extracted[images.parent] = count
            for index in range(1, count + 1):
                Image.new('RGB', (64, 36), (80, index % 255, 160)).save(images / f'frame_{index:06d}.jpg')
            operation = 'extract'
        attempt = 1 if any('colmap-rescue' in str(part) for part in command) else 0
        if self.cancel_at == (attempt, operation):
            return -1, ['cancelled'], True
        if operation == 'mapper':
            if attempt in self.mapper_failures:
                return 1, ['No good initial image pair found.'], False
            root = Path(command[command.index('--output_path') + 1]).parents[1]
            count = min(self.registered_counts[attempt], self.extracted[root])
            write_colmap_model(root, count, self.extracted[root])
        if operation == 'image_undistorter':
            model = Path(command[command.index('--input_path') + 1])
            output = Path(command[command.index('--output_path') + 1])
            images = Path(command[command.index('--image_path') + 1])
            stats = brush_engine.inspect_colmap_models(model)
            shutil.copytree(model, output / 'sparse')
            (output / 'images').mkdir()
            for name in stats['image_names']:
                shutil.copy2(images / name, output / 'images' / name)
            with (output / 'sparse' / 'cameras.bin').open('wb') as stream:
                stream.write(struct.pack('<QiiQQ4d', 1, 1, 1, 64, 36, 50.0, 50.0, 32.0, 18.0))
        return 0, [], False


def run_geometry(video_task, runner):
    manager, task = video_task
    job = Path(manager.paths.video_reconstruction_jobs_folder) / task['id']
    data = job / 'nerfstudio-data'
    profile = video_reconstruction.resolve_quality_profile('high', '12gb', engine='brush')
    return video_geometry.run_video_geometry(manager, task['id'], task, str(job), str(data), profile, runner, {})


def test_default_engine_is_brush_and_auto_prefers_available_brush():
    assert get_default_video_reconstruction_config()['default_engine'] == 'brush'
    available = {'brush': {'available': True}, 'splatfacto': {'available': True}}
    assert video_reconstruction.resolve_engine_strategy('auto', available) == ('brush', None)
    assert video_reconstruction.resolve_engine_strategy('splatfacto', available) == ('splatfacto', None)
    unavailable = {'brush': {'available': False}, 'splatfacto': {'available': True}}
    assert video_reconstruction.resolve_engine_strategy('auto', unavailable) == ('stable', None)
    assert video_reconstruction.resolve_engine_strategy('brush', unavailable) == (
        None, video_reconstruction.ERROR_BRUSH_UNAVAILABLE,
    )


@pytest.mark.parametrize('configured, expected', [('auto', '12gb'), ('24gb', '12gb'), ('8gb', '8gb')])
def test_vram_budget_cannot_exceed_detected_12gb(monkeypatch, configured, expected):
    monkeypatch.setattr(video_reconstruction.subprocess, 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=0, stdout='12227\n'))
    assert video_reconstruction.effective_vram_budget(configured) == expected
    for quality in ('preview', 'high', 'extreme'):
        profile = video_reconstruction.resolve_quality_profile(quality, '12gb', engine='brush')
        assert profile['brush_max_splats'] == 1_500_000
        assert profile['frame_count'] <= 1200
        assert profile['max_resolution'] <= 3840
        assert profile['brush_growth_stop_iter'] < profile['max_num_iterations']


@pytest.mark.parametrize('width, height, expected', [
    (1920, 1080, (1920, 1080)), (1080, 1920, (1080, 1920)),
    (3840, 2160, (1920, 1080)), (640, 360, (640, 360)),
])
def test_extraction_scales_once_by_long_edge_and_never_enlarges(tmp_path, width, height, expected):
    profile = video_reconstruction.resolve_quality_profile('high', '12gb', engine='brush')
    plan = video_geometry.frame_plan({'width': width, 'height': height, 'duration_seconds': 20,
                                      'source_fps': 30}, profile)
    assert (plan['working_width'], plan['working_height']) == expected
    command = video_geometry.build_extract_command('synthetic.mp4', tmp_path / 'images', plan)
    assert command[command.index('-vf') + 1] == f'fps=8.00000000,scale={expected[0]}:{expected[1]}:flags=lanczos'
    assert command[command.index('-frames:v') + 1] == '160'
    assert command[-1].endswith('frame_%06d.jpg')
    assert '--num-downscales' not in command


def test_sampling_caps_source_fps_and_long_video_workload():
    profile = video_reconstruction.resolve_quality_profile('extreme', '12gb', engine='brush')
    assert video_geometry.frame_plan({'width': 1920, 'height': 1080, 'duration_seconds': 10,
                                      'source_fps': 5}, profile)['target_frames'] == 50
    long = video_geometry.frame_plan({'width': 1920, 'height': 1080, 'duration_seconds': 3600,
                                      'source_fps': 30}, profile)
    assert long['target_frames'] == 1200
    assert long['sampling_fps'] == pytest.approx(1 / 3)


def test_splatfacto_1080_source_uses_full_resolution_after_geometry(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'transforms.json').write_text(json.dumps({'w': 1920, 'h': 1080, 'frames': [{}] * 20}))
    profile = video_reconstruction.resolve_quality_profile('high', '12gb', engine='splatfacto')
    adjusted = video_reconstruction.resolve_training_profile(profile, str(data))
    assert adjusted['downscale_factor'] == 1
    command = video_reconstruction.build_train_command(str(data), str(tmp_path / 'train'), adjusted)
    assert command[command.index('--downscale-factor') + 1] == '1'


def test_auto_custom_request_retains_brush_resolution(monkeypatch):
    monkeypatch.setattr(video_reconstruction, 'get_video_reconstruction_config',
                        get_default_video_reconstruction_config)
    request, error, status = video_reconstruction.validate_reconstruction_options({
        'engine': 'auto', 'quality': 'custom',
        'custom_options': {'frame_count': 120, 'max_num_iterations': 18000,
                           'max_resolution': 3200, 'matching_method': 'sequential'},
    })
    assert status == 200
    assert error is None
    profile = video_reconstruction.resolve_quality_profile('custom', '12gb', request['custom_options'],
                                                          engine='brush')
    assert profile['max_resolution'] == 3200
    assert profile['frame_count'] == 120
    assert profile['brush_growth_stop_iter'] == 14400


@pytest.mark.parametrize('stream_duration, format_duration, fps, expected_fps', [
    ('N/A', '5.5', '30000/1001', 30000 / 1001),
    ('nan', '5.5', '0/0', 0),
    ('0', '5.5', 'N/A', 0),
    ('5.5', '10', '-1/1', 0),
])
def test_probe_uses_valid_duration_and_handles_unknown_fps(monkeypatch, stream_duration,
                                                        format_duration, fps, expected_fps):
    payload = {'streams': [{'width': 1920, 'height': 1080, 'duration': stream_duration,
                            'avg_frame_rate': fps, 'side_data_list': [{'rotation': -90}]}],
               'format': {'duration': format_duration}}
    monkeypatch.setattr(video_geometry.subprocess, 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    metadata = video_geometry.probe_video('synthetic.mp4', {})
    assert metadata['duration_seconds'] == 5.5
    assert metadata['source_fps'] == pytest.approx(expected_fps)
    assert (metadata['width'], metadata['height']) == (1080, 1920)


def test_invalid_video_has_stable_error_and_never_launches_commands(video_task, monkeypatch):
    manager, task = video_task
    def invalid_video(*_args):
        raise video_geometry.InvalidVideoError('The video dimensions or duration are invalid.')
    monkeypatch.setattr(video_geometry, 'probe_video', invalid_video)
    monkeypatch.setattr(video_reconstruction, 'run_command', lambda *_args, **_kwargs:
                        pytest.fail('无效媒体不应启动 COLMAP 或训练'))
    video_reconstruction.run_video_reconstruction_task(manager, task['id'], task)
    assert task['status'] == 'failed'
    assert task['error_code'] == video_reconstruction.ERROR_INVALID_VIDEO
    assert not Path(task['output_path']).exists()
    assert not Path(manager.paths.video_reconstruction_jobs_folder, task['id']).exists()


@pytest.mark.parametrize('extractor, matcher', [('SiftExtraction', 'SiftMatching'),
                                             ('FeatureExtraction', 'FeatureMatching')])
def test_colmap_3_and_4_option_names_match_real_cli_contract(tmp_path, monkeypatch, extractor, matcher):
    def help_command(command, **_kwargs):
        group = extractor if command[1] == 'feature_extractor' else matcher
        return SimpleNamespace(returncode=0, stdout=f'--{group}.use_gpu\n--{group}.gpu_index\n', stderr='')
    monkeypatch.setattr(video_geometry.subprocess, 'run', help_command)
    names = video_geometry.colmap_option_names({})
    assert names == (extractor, matcher)
    profile = video_reconstruction.resolve_quality_profile('extreme', '12gb', engine='brush')
    features, matches, mapper = video_geometry.build_colmap_commands(tmp_path, profile, names)
    assert features[features.index('--ImageReader.single_camera') + 1] == '1'
    assert features[features.index(f'--{extractor}.max_image_size') + 1] == '3200'
    assert features[features.index('--SiftExtraction.max_num_features') + 1] == '16384'
    assert f'--{matcher}.use_gpu' in matches
    assert matches[matches.index('--SequentialMatching.overlap') + 1] == '10'
    assert mapper[mapper.index('--Mapper.tri_ignore_two_view_tracks') + 1] == '0'


def test_geometry_rescue_uses_more_frames_and_exhaustive_matching(video_task):
    runner = SyntheticGeometry([20, 55])
    status, chosen, _lines, report = run_geometry(video_task, runner)
    assert status == 'ok'
    assert Path(chosen).parent.name == 'colmap-rescue'
    assert report['undistortion']['applied'] is True
    assert [attempt['extracted_frames'] for attempt in report['attempts']] == [40, 60]
    assert report['registered_frames'] == 55
    assert report['matching_method'] == 'exhaustive'
    assert report['retried'] is True
    assert any(command[1] == 'exhaustive_matcher' for command, _kwargs in runner.commands)


def test_mapper_failure_can_be_rescued(video_task):
    runner = SyntheticGeometry([0, 55], mapper_failures={0})
    status, _chosen, _lines, report = run_geometry(video_task, runner)
    assert status == 'ok'
    assert report['attempts'][0]['registered_frames'] == 0
    assert report['registered_frames'] == 55


def test_failed_rescue_keeps_usable_primary_geometry(video_task):
    runner = SyntheticGeometry([25, 0], mapper_failures={1})
    status, chosen, _lines, report = run_geometry(video_task, runner)
    assert status == 'ok'
    assert Path(chosen).parent.name == 'nerfstudio-data'
    assert report['registered_frames'] == 25
    assert report['retried'] is True


@pytest.mark.parametrize('result', ['failure', 'cancelled', 'missing_view'])
def test_undistortion_must_finish_before_training(video_task, result):
    geometry = SyntheticGeometry([38, 0])
    def runner(*args, **kwargs):
        command = args[2]
        if len(command) > 1 and command[1] == 'image_undistorter':
            if result == 'failure':
                return 1, ['Unable to undistort images.'], False
            if result == 'cancelled':
                return -1, [], True
            geometry(*args, **kwargs)
            output = Path(command[command.index('--output_path') + 1])
            next((output / 'images').glob('*.jpg')).unlink()
            return 0, [], False
        return geometry(*args, **kwargs)
    status, chosen, _lines, report = run_geometry(video_task, runner)
    assert status == ('cancelled' if result == 'cancelled' else 'failed')
    assert chosen is None
    assert report['registered_frames'] == 38


@pytest.mark.parametrize('cancel_at', [(0, 'extract'), (1, 'mapper')])
def test_geometry_cancellation_never_falls_back_to_training(video_task, cancel_at):
    runner = SyntheticGeometry([25, 55], cancel_at=cancel_at)
    assert run_geometry(video_task, runner) == ('cancelled', None, None, None)
    if cancel_at == (0, 'extract'):
        assert len(runner.commands) == 1


@pytest.mark.parametrize('engine', ['brush', 'splatfacto'])
def test_low_registration_stops_before_any_training(video_task, monkeypatch, engine):
    manager, task = video_task
    task['engine'] = task['resolved_engine'] = engine
    runner = SyntheticGeometry([7, 7])
    commands = []
    def fake_command(*args, **kwargs):
        command = args[2]
        commands.append(command)
        if command[0] == 'ns-process-data':
            data = Path(command[command.index('--output-dir') + 1])
            (data / 'images').mkdir(parents=True, exist_ok=True)
            for index in range(20):
                (data / 'images' / f'{index:06d}.jpg').write_bytes(b'synthetic')
            (data / 'transforms.json').write_text(json.dumps({'w': 1920, 'h': 1080, 'frames': [{}] * 7}))
            return 0, [], False
        return runner(*args, **kwargs)
    monkeypatch.setattr(video_reconstruction, 'run_command', fake_command)
    video_reconstruction.run_video_reconstruction_task(manager, task['id'], task)
    assert task['status'] == 'failed'
    assert task['error_code'] == video_reconstruction.ERROR_GEOMETRY_INSUFFICIENT
    assert all(command[0] not in ('ns-train', 'synthetic-brush') for command in commands)
    assert not Path(task['output_path']).exists()
    assert not Path(task['spz_path']).exists()


def test_brush_pipeline_publishes_real_sh3_ply_spz_and_final_report(video_task, monkeypatch):
    manager, task = video_task
    geometry = SyntheticGeometry([38, 0])
    exported = []
    commands = []
    def fake_command(*args, **kwargs):
        command = args[2]
        commands.append(command)
        if command[0] != 'synthetic-brush':
            return geometry(*args, **kwargs)
        dataset = Path(command[-1])
        assert (dataset / 'sparse' / '0' / 'cameras.bin').is_file()
        assert brush_engine.inspect_colmap_models(dataset)['registered_images'] == 38
        assert len(list((dataset / 'images').glob('*.jpg'))) == 38
        assert '--downscale-factor' not in command
        assert command[command.index('--max-resolution') + 1] == '1920'
        assert command[command.index('--max-splats') + 1] == '1500000'
        assert command[command.index('--sh-degree') + 1] == '3'
        output = Path(command[command.index('--export-path') + 1]) / brush_engine.BRUSH_EXPORT_NAME
        exported.append(write_gaussian_ply(output))
        return 0, ['Refine iter 15000, 25 splats\n'], False
    monkeypatch.setattr(video_reconstruction, 'run_command', fake_command)
    monkeypatch.setattr(video_reconstruction, 'clean_gaussian_splat_ply', lambda *_args, **_kwargs:
                        pytest.fail('自动模式不应裁剪或删除 Gaussian'))
    video_reconstruction.run_video_reconstruction_task(manager, task['id'], task)
    assert task['status'] == 'completed'
    assert task['error_code'] is None
    assert task['stage'] == 'video_done'
    assert Path(task['output_path']).read_bytes() == exported[0]
    payload = gzip.decompress(Path(task['spz_path']).read_bytes())
    assert struct.unpack('<4sIIBBBB', payload[:16]) == (b'NGSP', 3, 25, 3, 11, 0, 0)
    assert len(payload) == 16 + 65 * 25
    metadata = model_gallery.read_model_metadata(manager.paths, 'synthetic')
    assert metadata['resolved_engine'] == 'brush'
    assert metadata['source_media_type'] == 'video'
    assert metadata['viewer_camera'] is not None
    assert model_gallery.build_gallery_item(manager.paths, 'synthetic')['viewer_camera'] == metadata['viewer_camera']
    asset = model_assets.sync_generated_model_asset(manager.paths, 'synthetic')
    assert asset['viewer_camera'] == metadata['viewer_camera']
    report = metadata['reconstruction']
    assert report['geometry']['registered_frames'] == 38
    assert report['output_stats']['sh_degree'] == 3
    assert report['up_alignment']['target_up'] == [0.0, 0.0, 1.0]
    assert report['geometry']['undistortion']['registered_frames'] == 38
    assert 'video_compress_spz' in report['stage_durations']
    assert 'focused_cleanup' not in report
    assert not Path(manager.paths.video_reconstruction_jobs_folder, task['id']).exists()
    assert all(command[0] not in ('ns-train', 'ns-export', 'ns-process-data') for command in commands)


@pytest.mark.parametrize('second_has_output', [True, False])
def test_brush_oom_retry_isolates_outputs_and_reduces_actual_budgets(video_task, monkeypatch, second_has_output):
    manager, task = video_task
    geometry = SyntheticGeometry([38, 0])
    brush_commands = []
    final_bytes = []
    def fake_command(*args, **kwargs):
        command = args[2]
        if command[0] != 'synthetic-brush':
            return geometry(*args, **kwargs)
        brush_commands.append(command)
        output = Path(command[command.index('--export-path') + 1]) / brush_engine.BRUSH_EXPORT_NAME
        if len(brush_commands) == 1:
            write_gaussian_ply(output, marker=0.2)
            return 1, ['VK_ERROR_OUT_OF_DEVICE_MEMORY\n'], False
        if second_has_output:
            final_bytes.append(write_gaussian_ply(output, marker=0.7))
        return 0, [], False
    monkeypatch.setattr(video_reconstruction, 'run_command', fake_command)
    video_reconstruction.run_video_reconstruction_task(manager, task['id'], task)
    assert len(brush_commands) == 2
    first, second = brush_commands
    assert first[first.index('--export-path') + 1] != second[second.index('--export-path') + 1]
    assert second[second.index('--max-resolution') + 1] == '1440'
    assert second[second.index('--max-splats') + 1] == '1005000'
    assert second[second.index('--total-steps') + 1] == first[first.index('--total-steps') + 1]
    assert task['details']['brush_oom_retry']['max_resolution'] == 1440
    if second_has_output:
        assert task['status'] == 'completed'
        assert Path(task['output_path']).read_bytes() == final_bytes[0]
        metadata = model_gallery.read_model_metadata(manager.paths, 'synthetic')
        assert metadata['reconstruction']['brush_oom_retry']['max_splats'] == 1_005_000
    else:
        assert task['status'] == 'failed'
        assert task['error_code'] == video_reconstruction.ERROR_OUTPUT_MISSING
        assert not Path(task['output_path']).exists()


def test_brush_cancellation_after_export_does_not_publish(video_task, monkeypatch):
    manager, task = video_task
    geometry = SyntheticGeometry([38, 0])
    def fake_command(*args, **kwargs):
        command = args[2]
        if command[0] != 'synthetic-brush':
            return geometry(*args, **kwargs)
        output = Path(command[command.index('--export-path') + 1]) / brush_engine.BRUSH_EXPORT_NAME
        write_gaussian_ply(output)
        return 0, [], True
    monkeypatch.setattr(video_reconstruction, 'run_command', fake_command)
    video_reconstruction.run_video_reconstruction_task(manager, task['id'], task)
    assert task['status'] == 'cancelled'
    assert not Path(task['output_path']).exists()
    assert not Path(task['spz_path']).exists()


def test_splatfacto_reset_patch_is_idempotent_and_skips_correct_versions():
    resets = []
    originals = []
    class BrokenStrategy:
        reset_every = 3000
        refine_stop_iter = 7000
        prune_opa = 0.005

        def step_post_backward(self, params, optimizers, state, step, info, packed=False):
            originals.append((step, packed))
            if step % self.reset_every == 0 & step > 0:
                resets.append({'legacy': True})

    assert train_splatfacto.patch_opacity_reset(BrokenStrategy, lambda **kwargs: resets.append(kwargs)) is True
    assert train_splatfacto.patch_opacity_reset(BrokenStrategy, lambda **kwargs: pytest.fail('重复 reset')) is False
    strategy = BrokenStrategy()
    for step in (0, 2999, 3000, 6000, 7000, 9000):
        strategy.step_post_backward({}, {}, {}, step, {}, packed=True)
    assert len(resets) == 2
    assert all(reset['value'] == 0.01 for reset in resets)
    assert originals == [(step, True) for step in (0, 2999, 3000, 6000, 7000, 9000)]

    class CorrectStrategy:
        def step_post_backward(self, params, optimizers, state, step, info, packed=False):
            if step > 0 and step % 3000 == 0:
                resets.append({'correct': True})

    original = CorrectStrategy.step_post_backward
    assert train_splatfacto.patch_opacity_reset(CorrectStrategy, lambda **_kwargs: None) is False
    assert CorrectStrategy.step_post_backward is original


@pytest.mark.parametrize('steps, downscales', [(6000, 1), (15000, 0), (48000, 0)])
def test_splatfacto_schedules_follow_total_steps(steps, downscales):
    schedulers = [SimpleNamespace(max_steps=30000), SimpleNamespace(max_steps=50000)]
    config = SimpleNamespace(pipeline=SimpleNamespace(model=SimpleNamespace()), optimizers={
        'means': {'scheduler': schedulers[0]}, 'camera': {'scheduler': schedulers[1]},
        'colors': {'scheduler': None},
    })
    train_splatfacto.configure_schedule(config, steps)
    assert config.pipeline.model.stop_split_at == round(steps * 0.8)
    assert config.pipeline.model.num_downscales == downscales
    assert all(scheduler.max_steps == steps for scheduler in schedulers)


def test_ns_train_executes_compatibility_wrapper(video_task, monkeypatch):
    manager, task = video_task
    actual = []
    process = SimpleNamespace(poll=lambda: 0)
    monkeypatch.setattr(video_reconstruction, 'resolve_video_python', lambda: 'video-python')
    monkeypatch.setattr(video_reconstruction.subprocess, 'Popen', lambda command, **_kwargs:
                        actual.append(command) or process)
    monkeypatch.setattr(video_reconstruction, 'wait_for_process', lambda *_args, **_kwargs: (0, False))
    command = ['ns-train', 'splatfacto', '--max-num-iterations', '6000']
    assert video_reconstruction.run_command(manager, task['id'], command) == (0, [], False)
    assert actual[0][0] == 'video-python'
    assert Path(actual[0][1]).name == 'train_splatfacto.py'
    assert actual[0][2:] == command[1:]


@pytest.mark.parametrize('failure_at', ['write', 'flush'])
def test_optional_log_disk_failure_does_not_interrupt_training_output(video_task, failure_at):
    manager, task = video_task
    calls = []
    class FullDiskLog:
        def write(self, _line):
            calls.append('write')
            if failure_at == 'write':
                raise OSError('disk is full')
        def flush(self):
            calls.append('flush')
            raise OSError('disk is full')
    process = SimpleNamespace(stdout=io.StringIO('first line\nsecond line\n'), wait=lambda: 0)
    lines = []
    assert video_reconstruction.wait_for_process(manager, task['id'], process, lines,
                                                log_file=FullDiskLog()) == (0, False)
    assert lines == ['first line\n', 'second line\n']
    assert calls.count('write') == 1


def test_command_observation_failure_terminates_gpu_process(video_task, monkeypatch):
    manager, task = video_task
    process = SimpleNamespace(poll=lambda: None)
    terminated = []
    monkeypatch.setattr(video_reconstruction.subprocess, 'Popen', lambda *_args, **_kwargs: process)
    monkeypatch.setattr(video_reconstruction, 'terminate_process_tree', terminated.append)
    def read_failure(*_args, **_kwargs):
        raise OSError('stdout read failed')
    monkeypatch.setattr(video_reconstruction, 'wait_for_process', read_failure)
    with pytest.raises(OSError, match='stdout read failed'):
        video_reconstruction.run_command(manager, task['id'], ['synthetic-brush'])
    assert terminated == [process]
    assert task['id'] not in manager.running_processes

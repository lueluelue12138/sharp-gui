"""真实生成计时、资产重启读取及缺失记录行为。"""

import json
from pathlib import Path

import pytest
from PIL import Image

from backend.paths import build_path_context, ensure_runtime_directories
from backend.services import model_assets, model_gallery, model_generation, video_reconstruction
from backend.services.task_queue import TaskManager


def test_generation_duration_excludes_queue_and_freezes_after_completion(monkeypatch):
    clock = {'mono': 20.0}
    monkeypatch.setattr(model_generation.time, 'monotonic', lambda: clock['mono'])
    task = {'created_at': 1, 'started_at': 1000, 'kind': 'video_3dgs'}
    model_generation.start_generation(task)
    clock['mono'] = 32.5
    task['_generation_completed_monotonic'] = clock['mono']
    task['completed_at'] = 1012.5
    clock['mono'] = 200
    result = model_generation.build_generation_summary(task, engine='OOOBrush')
    assert result['duration_seconds'] == 12.5
    assert result['started_at'].endswith('+00:00')
    assert not any('monotonic' in key for key in result)
    assert 'duration_seconds' not in model_generation.build_generation_summary({}, engine='unknown')


def test_image_completion_persists_duration_and_asset_source_dimensions(tmp_path, monkeypatch):
    paths = build_path_context({'workspace_folder': str(tmp_path)})
    ensure_runtime_directories(paths)
    source = Path(paths.input_folder) / 'image.jpg'
    Image.new('RGB', (24, 16), 'blue').save(source)
    output = Path(paths.output_folder) / 'image.ply'
    output.write_bytes(b'ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n')
    clock = {'mono': 10.0}
    monkeypatch.setattr(model_generation.time, 'monotonic', lambda: clock['mono'])

    def convert(_path):
        clock['mono'] += 5

    manager = TaskManager(paths=paths, spz_converter=convert)
    task = {'id': 'image-task', 'kind': 'image_sharp', 'model_id': 'image',
            'filename': 'image.jpg', 'input_filename': 'image.jpg', 'input_path': str(source),
            'status': 'processing', 'generation_device': 'cuda', 'started_at': 1000}
    model_generation.start_generation(task)
    manager.task_status[task['id']] = task
    clock['mono'] = 30.0
    manager._finish_process(task['id'], 'image.jpg', paths.output_folder, 0, [])
    metadata = model_gallery.read_model_metadata(paths, 'image')
    assert metadata['generation']['duration_seconds'] == 25
    assert metadata['generation']['stage_durations'] == {'image_inference': 20, 'image_postprocessing': 5}
    assert metadata['generation']['source_width'] == 24
    assert metadata['generation']['source_height'] == 16
    assert metadata['generation']['device'] == 'cuda'
    model_assets.refresh_model_asset_catalog(paths)
    asset = model_assets.get_model_asset(paths, 'image')
    assert asset['generation'] == metadata['generation']


def test_video_metadata_summary_keeps_actual_profile_without_disk_paths():
    task = {'kind': 'video_3dgs', 'quality': 'high', 'completed_at': 100,
            'source_video_path': 'C:/private/source.mp4', 'details': {
                'resource_profile': {'recipe_version': 'test-v1', 'max_num_iterations': 15000,
                                     'max_resolution': 1920, 'brush_max_splats': 1000000},
                'geometry': {'source': {'width': 3840, 'height': 2160, 'duration_seconds': 25},
                             'registered_frames': 197, 'extracted_frames': 197, 'registration_ratio': 1},
                'output_stats': {'vertex_count': 600000},
                'stage_durations': {'video_optimize': 900},
            }}
    summary = video_reconstruction.build_video_model_metadata(task)['generation']
    assert summary['training_iterations'] == 15000
    assert summary['registered_frames'] == 197
    assert summary['splat_count'] == 600000
    assert summary['source_duration_seconds'] == 25
    assert 'private' not in json.dumps(summary)
    assert 'duration_seconds' not in summary


def test_repeated_video_stages_accumulate_with_monotonic_clock(tmp_path, monkeypatch):
    manager = TaskManager(paths=build_path_context({'workspace_folder': str(tmp_path)}))
    clock = {'mono': 100.0}
    monkeypatch.setattr(model_generation.time, 'monotonic', lambda: clock['mono'])
    task = {'id': 'video', 'stage': 'video_geometry', 'stage_started_at': 1, 'started_at': 1, 'details': {}}
    model_generation.start_generation(task)
    manager.task_status['video'] = task
    clock['mono'] = 104
    video_reconstruction.update_task(manager, 'video', stage='video_extract_frames')
    clock['mono'] = 107
    video_reconstruction.update_task(manager, 'video', stage='video_geometry')
    clock['mono'] = 112
    video_reconstruction.update_task(manager, 'video', stage='video_optimize')
    assert task['details']['stage_durations']['video_geometry'] == pytest.approx(9)
    assert task['details']['stage_durations']['video_extract_frames'] == pytest.approx(3)

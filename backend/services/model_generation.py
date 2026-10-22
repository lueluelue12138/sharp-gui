"""生成任务的可持久化计时摘要；不从文件日期推测历史运行耗时。"""

from __future__ import annotations

import datetime
import math
import time


def finite_number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        return None
    return value


def utc_timestamp(value):
    if finite_number(value, positive=True) is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def start_generation(task):
    """仅在任务真正出队开始处理时调用；内部单调时间不写入模型文件。"""
    task['_generation_started_monotonic'] = time.monotonic()
    task['_stage_started_monotonic'] = task['_generation_started_monotonic']
    task.setdefault('started_at', time.time())


def build_generation_summary(task, *, engine, engine_version=None, engine_commit=None):
    """收集真实已知字段；白名单摘要不携带机器上的文件路径。"""
    started = finite_number(task.get('_generation_started_monotonic'))
    finished = task.get('_generation_completed_monotonic', time.monotonic())
    duration = None if started is None else round(max(0, finished - started), 3)
    details = task.get('details') or {}
    profile = details.get('resource_profile') or {}
    geometry = details.get('geometry') or {}
    source = geometry.get('source') or details.get('source') or {}
    output = details.get('output_stats') or {}
    stages = {key: round(value, 3) for key, value in (details.get('stage_durations') or {}).items()
              if finite_number(value) is not None}
    summary = {
        'schema_version': 1,
        'kind': task.get('kind') or 'image_sharp',
        'engine': engine,
        'engine_version': engine_version,
        'engine_commit': engine_commit,
        'recipe_version': profile.get('recipe_version'),
        'started_at': utc_timestamp(task.get('started_at')),
        'completed_at': utc_timestamp(task.get('completed_at')),
        'duration_seconds': duration,
        'stage_durations': stages,
        'quality': task.get('quality'),
        'device': task.get('generation_device'),
        'source_width': source.get('width'),
        'source_height': source.get('height'),
        'source_duration_seconds': source.get('duration_seconds'),
        'sampling_fps': geometry.get('sampling_fps'),
        'extracted_frames': geometry.get('extracted_frames'),
        'registered_frames': geometry.get('registered_frames'),
        'registration_ratio': geometry.get('registration_ratio'),
        'sfm_points': geometry.get('sfm_points'),
        'training_iterations': profile.get('max_num_iterations'),
        'training_resolution': profile.get('max_resolution'),
        'max_splats': profile.get('brush_max_splats'),
        'splat_count': output.get('point_count') or output.get('vertex_count'),
    }
    return {key: value for key, value in summary.items() if value is not None}

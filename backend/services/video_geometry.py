"""视频抽帧与 COLMAP 配准；与高斯训练器分开控制像素和覆盖率。"""

import json
import math
import os
import re
import subprocess
from pathlib import Path
from shutil import which

from backend.services import brush_engine


MIN_REGISTERED_IMAGES = 8
MIN_REGISTRATION_RATIO = 0.5
GOOD_REGISTRATION_RATIO = 0.8
MAX_PRESET_FRAMES = 1200


class InvalidVideoError(ValueError):
    """视频自身无法解码或元数据不足。"""


def probe_video(source_path, env):
    """读取尺寸、时长与旋转元数据，不读取其它用户媒体。"""
    result = subprocess.run(
        [which('ffprobe') or 'ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=width,height,avg_frame_rate,duration,nb_frames:stream_tags=rotate:stream_side_data=rotation:format=duration',
         '-of', 'json', str(source_path)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30, env=env,
    )
    if result.returncode:
        raise InvalidVideoError('Unable to read the video metadata.')
    data = json.loads(result.stdout)
    streams = data.get('streams') or []
    if not streams:
        raise InvalidVideoError('No video stream was found.')
    stream = streams[0]
    width, height = int(stream.get('width') or 0), int(stream.get('height') or 0)
    duration = 0
    for value in (stream.get('duration'), data.get('format', {}).get('duration')):
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            duration = candidate
            break
    try:
        rate = str(stream.get('avg_frame_rate') or '0/1').split('/')
        fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0
        if not math.isfinite(fps) or fps <= 0:
            fps = 0
    except (ValueError, ZeroDivisionError):
        fps = 0
    rotation = float(stream.get('tags', {}).get('rotate') or 0)
    for side_data in stream.get('side_data_list') or []:
        if 'rotation' in side_data:
            rotation = float(side_data['rotation'])
    if round(rotation) % 180 == 90:
        width, height = height, width
    if width <= 0 or height <= 0 or not math.isfinite(duration) or duration <= 0:
        raise InvalidVideoError('The video dimensions or duration are invalid.')
    try:
        source_frames = int(stream.get('nb_frames') or 0)
    except (ValueError, TypeError):
        source_frames = 0
    return {'width': width, 'height': height, 'duration_seconds': duration, 'source_fps': fps,
            'source_frame_count': max(0, source_frames)}


def scaled_dimensions(width, height, max_resolution):
    """按长边上限等比例缩小，低分辨率输入不放大。"""
    scale = min(1.0, max_resolution / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def frame_plan(metadata, profile, rescue=False):
    """固定源帧编号清单；缺少源帧总数时回退按时间采样，限制长视频的工作量。"""
    duration = metadata['duration_seconds']
    source_frames = int(metadata.get('source_frame_count') or 0)
    if profile.get('sampling_fps'):
        initial_fps = float(profile['sampling_fps'])
        candidate_fps = max(initial_fps, float(profile.get('rescue_sampling_fps') or initial_fps * 1.5))
        fps = candidate_fps if rescue else initial_fps
        fps = max(fps, 30 / duration)
        frame_limit = MAX_PRESET_FRAMES
    else:
        frame_limit = int(profile['frame_count'])
        fps = frame_limit / duration
    source_fps = metadata.get('source_fps') or (source_frames / duration if source_frames > 0 else fps)
    fps = min(fps, source_fps, frame_limit / duration)
    count = max(1, min(frame_limit, math.ceil(duration * fps)))
    width, height = scaled_dimensions(metadata['width'], metadata['height'], profile['max_resolution'])
    plan = {'sampling_fps': fps, 'target_frames': count, 'working_width': width, 'working_height': height,
            'selection_method': 'timestamp_fps'}
    if source_frames > 0:
        count = max(1, min(source_frames, frame_limit, math.floor(duration * fps + 0.5)))
        candidate_count = count
        if profile.get('sampling_fps') and not rescue:
            rescue_fps = min(max(candidate_fps, 30 / duration),
                             source_fps, frame_limit / duration)
            candidate_count = min(source_frames, frame_limit,
                                  max(count, math.floor(duration * rescue_fps + 0.5)))
        # 初次从补密候选池取均匀子集；补密使用同一候选池，保留原先选中的源帧。
        candidates = [position * source_frames // candidate_count for position in range(candidate_count)]
        indices = [candidates[position * candidate_count // count] for position in range(count)]
        plan.update(sampling_fps=count / duration, target_frames=count,
                    selection_method='source_frame_indices', selected_frame_indices=indices)
    return plan


def extraction_filter(plan):
    """过滤表达式只包含经过规划的整数编号，不拼接源媒体路径。"""
    indices = plan.get('selected_frame_indices')
    # 线性相加在较长清单上会超过 FFmpeg 表达式的递归限制；平衡分支也减少每帧比较次数。
    def select_range(start, stop):
        if stop - start == 1:
            return f'eq(n,{indices[start]})'
        middle = (start + stop) // 2
        return (f'if(lt(n,{indices[middle]}),'
                f'{select_range(start, middle)},{select_range(middle, stop)})')

    sample = ("select='" + select_range(0, len(indices)) + "'"
              if indices else f"fps={plan['sampling_fps']:.8f}")
    return f"{sample},scale={plan['working_width']}:{plan['working_height']}:flags=lanczos"


def build_extract_command(source_path, images_dir, plan):
    """直接产出训练工作图，不重复生成多套下采样 PNG。"""
    command = [
        which('ffmpeg') or 'ffmpeg', '-nostdin', '-hide_banner', '-y', '-i', str(source_path),
        '-map', '0:v:0', '-an',
    ]
    if plan.get('selected_frame_indices'):
        command += ['-filter_script:v', str(Path(images_dir).parent / 'frame-selection.filter'), '-vsync', 'vfr']
    else:
        command += ['-vf', extraction_filter(plan)]
    return command + [
        '-frames:v', str(plan['target_frames']), '-q:v', '2',
        str(Path(images_dir) / 'frame_%06d.jpg'),
    ]


def colmap_option_names(env):
    """兼容 COLMAP 3.x 与 4.x 的 GPU/尺寸选项名称。"""
    executable = which('colmap') or 'colmap'
    help_text = {}
    for command in ('feature_extractor', 'sequential_matcher'):
        result = subprocess.run(
            [executable, command, '-h'], capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=15, env=env,
        )
        if result.returncode:
            raise ValueError('Unable to inspect the COLMAP command options.')
        help_text[command] = result.stdout + result.stderr
    extraction = 'FeatureExtraction' if '--FeatureExtraction.use_gpu' in help_text['feature_extractor'] else 'SiftExtraction'
    matching = 'FeatureMatching' if '--FeatureMatching.use_gpu' in help_text['sequential_matcher'] else 'SiftMatching'
    return extraction, matching


def build_colmap_commands(data_dir, profile, option_names):
    """共享相机、限制 SfM 像素，视频使用邻近匹配。"""
    data_dir = Path(data_dir)
    images = data_dir / 'images'
    database = data_dir / 'colmap' / 'database.db'
    sparse = data_dir / 'colmap' / 'sparse'
    extractor, matcher = option_names
    executable = which('colmap') or 'colmap'
    features = [
        executable, 'feature_extractor', '--database_path', str(database), '--image_path', str(images),
        '--ImageReader.single_camera', '1', '--ImageReader.camera_model', 'SIMPLE_RADIAL',
        f'--{extractor}.use_gpu', '1', f'--{extractor}.gpu_index', '0',
        f'--{extractor}.max_image_size', str(profile['sfm_max_resolution']),
        '--SiftExtraction.max_num_features', str(profile['sfm_max_features']),
    ]
    method = profile['matching_method']
    matches = [executable, f'{method}_matcher', '--database_path', str(database),
               f'--{matcher}.use_gpu', '1', f'--{matcher}.gpu_index', '0']
    if method == 'sequential':
        # 没有词汇树时显式关闭在线/隐式闭环；另用有界关键帧对补充跨时间约束。
        matches += ['--SequentialMatching.overlap', '10', '--SequentialMatching.loop_detection', '0']
    mapper = [executable, 'mapper', '--database_path', str(database), '--image_path', str(images),
              '--output_path', str(sparse)]
    if profile.get('sfm_allow_two_view_tracks'):
        mapper += ['--Mapper.tri_ignore_two_view_tracks', '0']
    commands = [features, matches]
    if method == 'sequential' and profile.get('sfm_nonlocal_matching'):
        commands.append([
            executable, 'matches_importer', '--database_path', str(database),
            '--match_list_path', str(data_dir / 'nonlocal-pairs.txt'), '--match_type', 'pairs',
            f'--{matcher}.use_gpu', '1', f'--{matcher}.gpu_index', '0',
        ])
    return (*commands, mapper)


def write_nonlocal_match_pairs(data_dir):
    """复用已提取特征，对最多 24 个均匀关键帧做跨时间匹配；不猜相机位姿。"""
    data_dir = Path(data_dir)
    names = sorted(path.name for path in (data_dir / 'images').glob('frame_*.jpg') if path.is_file())
    count = min(24, len(names))
    indices = sorted({round(index * (len(names) - 1) / (count - 1)) for index in range(count)}) if count > 1 else []
    pairs = [(names[left], names[right]) for offset, left in enumerate(indices)
             for right in indices[offset + 1:] if right - left > 10]
    (data_dir / 'nonlocal-pairs.txt').write_text(
        ''.join(f'{left} {right}\n' for left, right in pairs), encoding='utf-8',
    )
    return {'strategy': 'bounded-keyframes-v1', 'keyframes': len(indices), 'candidate_pairs': len(pairs)}


def registration_summary(data_dir, plan):
    """仅将统计信息写入任务，内部模型路径不进入公开响应。"""
    stats = brush_engine.inspect_colmap_models(data_dir)
    extracted = len(list((Path(data_dir) / 'images').glob('frame_*.jpg')))
    registered = int(stats['registered_images'])
    ratio = registered / extracted if extracted else 0
    indices = sorted(int(match.group(1)) for name in stats.get('image_names', [])
                     if (match := re.search(r'frame_(\d+)', str(name))))
    temporal_coverage = (indices[-1] - indices[0] + 1) / extracted if indices and extracted else 0
    return stats, {
        **plan, 'extracted_frames': extracted, 'registered_frames': registered,
        'registration_ratio': ratio, 'temporal_coverage': temporal_coverage,
        'sfm_points': int(stats['sfm_points']),
        'usable': registered >= MIN_REGISTERED_IMAGES and ratio >= MIN_REGISTRATION_RATIO and int(stats['sfm_points']) > 0,
    }


def build_undistort_command(data_dir, model_dir, output_dir, profile):
    """将径向相机和图片同时转换为 Brush 支持的针孔相机。"""
    return [
        which('colmap') or 'colmap', 'image_undistorter',
        '--image_path', str(Path(data_dir) / 'images'), '--input_path', str(model_dir),
        '--output_path', str(output_dir), '--output_type', 'COLMAP',
        '--max_image_size', str(profile['max_resolution']), '--max_scale', '1',
    ]


def run_video_geometry(task_manager, task_id, task, job_dir, data_dir, profile, run_command, env):
    """配准不足时补密一次；质量不足时在长训练前停止。"""
    metadata = probe_video(task['source_video_path'], env)
    options = colmap_option_names(env)
    attempts = []
    candidates = []
    for attempt in range(2):
        attempt_dir = Path(data_dir) if attempt == 0 else Path(job_dir) / 'colmap-rescue'
        images = attempt_dir / 'images'
        sparse = attempt_dir / 'colmap' / 'sparse'
        images.mkdir(parents=True, exist_ok=True)
        sparse.mkdir(parents=True, exist_ok=True)
        plan = frame_plan(metadata, profile, rescue=bool(attempt))
        if plan.get('selected_frame_indices'):
            (attempt_dir / 'frame-selection.filter').write_text(extraction_filter(plan), encoding='utf-8')
        (attempt_dir / 'frame-plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        attempt_profile = dict(profile)
        # 小规模失败允许穷举补救；长视频保持局部匹配，避免平方级耗时。
        if attempt and plan['target_frames'] <= 450:
            attempt_profile['matching_method'] = 'exhaustive'
        if attempt and attempts and plan['sampling_fps'] <= attempts[0]['sampling_fps'] and attempt_profile['matching_method'] == profile['matching_method']:
            break
        command_stages = [
            (build_extract_command(task['source_video_path'], images, plan), 'video_extract_frames', 12),
            *[(cmd, 'video_geometry', 34) for cmd in build_colmap_commands(attempt_dir, attempt_profile, options)],
        ]
        failed = False
        nonlocal_matching = None
        for command, stage, progress in command_stages:
            if len(command) > 1 and command[1] == 'matches_importer':
                nonlocal_matching = write_nonlocal_match_pairs(attempt_dir)
                if not nonlocal_matching['candidate_pairs']:
                    continue
            code, lines, cancelled = run_command(task_manager, task_id, command, cwd=job_dir, stage=stage, progress=progress)
            if cancelled:
                return 'cancelled', None, None, None
            if code:
                failed = True
                if not candidates and len(command) > 1 and command[1] != 'mapper':
                    return 'failed', None, lines, None
                break
        if failed:
            attempts.append({**plan, 'extracted_frames': len(list(images.glob('frame_*.jpg'))),
                             'registered_frames': 0, 'registration_ratio': 0,
                             'temporal_coverage': 0, 'sfm_points': 0, 'usable': False})
        if not failed:
            try:
                stats, summary = registration_summary(attempt_dir, plan)
            except (ValueError, OSError, KeyError):
                summary = {**plan, 'extracted_frames': len(list(images.glob('frame_*.jpg'))),
                           'registered_frames': 0, 'registration_ratio': 0,
                           'temporal_coverage': 0, 'sfm_points': 0, 'usable': False}
            else:
                summary['matching_method'] = attempt_profile['matching_method']
                if nonlocal_matching is not None:
                    summary['nonlocal_matching'] = nonlocal_matching
                candidates.append((attempt_dir, stats, summary))
            attempts.append(summary)
            if summary['registration_ratio'] >= GOOD_REGISTRATION_RATIO and summary.get('usable'):
                break
        if not profile.get('sampling_fps') or attempt:
            break
        # 所有处理均位于本任务目录；重试保留初次模型供回退比较。
        with task_manager.task_lock:
            task.setdefault('details', {}).setdefault('warnings', []).append({
                'code': 'video_reconstruction_geometry_retry',
                'message': 'Camera registration was incomplete; retrying once with denser sampling or broader matching.',
            })
    if not candidates:
        return 'quality_failed', None, None, {'attempts': attempts, 'source': metadata}
    chosen_dir, chosen_model, chosen = max(candidates, key=lambda candidate: (
        candidate[2]['usable'], candidate[2]['registration_ratio'], candidate[2]['registered_frames']))
    summary = {**chosen, 'attempts': attempts, 'source': metadata, 'retried': len(attempts) > 1}
    if not chosen['usable']:
        return 'quality_failed', None, None, summary
    # Brush 不读取 COLMAP 畸变系数。必须同时去畸变图片和内参，不能直接忽略 k。
    undistorted_dir = chosen_dir / 'undistorted'
    command = build_undistort_command(chosen_dir, chosen_model['model_dir'], undistorted_dir, profile)
    code, lines, cancelled = run_command(
        task_manager, task_id, command, cwd=job_dir, stage='video_geometry', progress=48,
    )
    if cancelled:
        return 'cancelled', None, None, summary
    if code:
        return 'failed', None, lines, summary
    try:
        undistorted = brush_engine.inspect_colmap_models(undistorted_dir)
        names = undistorted['image_names']
        if set(names) != set(chosen_model['image_names']) or not all(
            (undistorted_dir / 'images' / name).is_file() for name in names
        ):
            raise ValueError('Undistortion did not preserve every registered view.')
    except (ValueError, OSError, KeyError) as error:
        return 'failed', None, [str(error)], summary
    summary['undistortion'] = {'applied': True, 'registered_frames': len(names),
                               'max_resolution': profile['max_resolution']}
    return 'ok', str(undistorted_dir), None, summary

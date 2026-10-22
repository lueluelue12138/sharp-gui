import os
import copy
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
from shutil import which

from werkzeug.utils import secure_filename

from backend import runtime
from backend.config import get_video_reconstruction_config
from backend.services import brush_engine, model_gallery, model_generation, photo_gallery, video_geometry
from backend.services.model_orientation import VIEWER_ORIENTATION_Y_FRONT
from backend.services.static_files import is_real_path_inside

TASK_KIND_VIDEO_3DGS = "video_3dgs"

VALID_RECONSTRUCTION_MODES = {"auto", "object", "environment"}
PRESET_RECONSTRUCTION_QUALITIES = {"preview", "high", "extreme"}
CUSTOM_RECONSTRUCTION_QUALITY = "custom"
VALID_RECONSTRUCTION_QUALITIES = PRESET_RECONSTRUCTION_QUALITIES | {CUSTOM_RECONSTRUCTION_QUALITY}
VALID_RECONSTRUCTION_ENGINES = {"auto", "brush"}
VALID_VRAM_BUDGETS = {"auto", "8gb", "12gb", "16gb", "24gb"}
VALID_MATCHING_METHODS = {"sequential", "exhaustive"}

ERROR_DEPENDENCY_MISSING = "video_reconstruction_dependency_missing"
ERROR_DEPENDENCIES_CHECKING = "video_reconstruction_dependencies_checking"
ERROR_INVALID_REQUEST = "video_reconstruction_invalid_request"
ERROR_SOURCE_UNAVAILABLE = "video_reconstruction_source_unavailable"
ERROR_CANCELLED = "video_reconstruction_cancelled"
ERROR_OOM = "video_reconstruction_oom"
ERROR_GPU_DEVICE_LOST = 'video_reconstruction_gpu_device_lost'
ERROR_HOST_MEMORY = 'video_reconstruction_host_memory'
ERROR_TRAINING_FAILED = 'video_reconstruction_training_failed'
ERROR_OUTPUT_MISSING = "video_reconstruction_output_missing"
ERROR_SPZ_FAILED = "video_reconstruction_spz_failed"
ERROR_UNSUPPORTED_VIDEO = "video_reconstruction_unsupported_video"
ERROR_GEOMETRY_INSUFFICIENT = "video_reconstruction_geometry_insufficient"
ERROR_BRUSH_UNAVAILABLE = "video_reconstruction_brush_unavailable"
ERROR_INVALID_VIDEO = "video_reconstruction_invalid_video"

CUSTOM_QUALITY_DEFAULTS = {
    'frame_count': 600, 'max_num_iterations': 15000,
    'matching_method': 'sequential', 'max_resolution': 1920,
}

CUSTOM_QUALITY_LIMITS = {
    "frame_count": (24, 1200),
    "max_num_iterations": (1000, 80000),
    "exhaustive_frame_count_max": 450,
}


FOCUSED_CLEANUP_PROFILE = {
    "position_quantiles": (5.0, 95.0),
    "alpha_min": 0.12,
    "scale_quantile": 98.5,
    "min_keep_ratio": 0.25,
    "object_min_keep_ratio": 0.1,
    "min_vertices": 1000,
}

STAGE_PROGRESS = {
    "video_prepare": 3,
    "video_extract_frames": 12,
    "video_foreground": 22,
    "video_geometry": 34,
    "video_optimize": 58,
    "video_export": 86,
    "video_compress_spz": 94,
    "video_done": 100,
}

OOM_PATTERNS = (
    "cuda out of memory",
    "outofmemoryerror",
    "cublas_status_alloc_failed",
    "cudnn_status_alloc_failed",
    "hip out of memory",
    'vk_error_out_of_device_memory',
    'cuda_error_out_of_memory',
    'hip_error_out_of_memory',
    'out of gpu memory',
    'gpu out of memory',
    'gpu allocation failed',
    'gpu memory allocation failed',
)
DEVICE_LOST_PATTERNS = (
    'devicelost', 'device lost', 'device_lost', 'parent device is lost',
    'dxgi_error_device_removed', 'dxgi_error_device_reset', 'dxgi_error_device_hung',
)
HOST_MEMORY_PATTERN = re.compile(
    r'\b(?:_array)?memoryerror\b|std::bad_alloc|out.of.host.memory|\bcannot allocate memory\b|'
    r'\bmemory allocation of \d+ bytes failed\b',
)
TYPED_OOM_PATTERN = re.compile(r'\boutofmemory(?:error)?\b')


VIDEO_RUNTIME_PROCESS_TOKENS = (
    "colmap",
    "brush_app",
    "brush",
)

_DEPENDENCY_STATUS_LOCK = threading.Lock()
_DEPENDENCY_STATUS_CACHE = None
_DEPENDENCY_STATUS_CHECKED_AT = None
_DEPENDENCY_STATUS_REFRESHING = False


def _local_video_reconstruction_paths():
    root = Path(__file__).resolve().parents[2]
    return (root / '.sharp-gui-tools' / 'colmap' / 'bin', root / 'tools' / 'ffmpeg' / 'bin')


def _prepend_existing_path_entries(path_value, candidates):
    path_parts = [part for part in (path_value or "").split(os.pathsep) if part]
    preferred = []
    preferred_keys = set()

    for candidate in candidates:
        if candidate.exists():
            candidate_text = str(candidate)
            key = os.path.normcase(os.path.abspath(candidate_text))
            if key not in preferred_keys:
                preferred.append(candidate_text)
                preferred_keys.add(key)

    remaining = [
        part
        for part in path_parts
        if os.path.normcase(os.path.abspath(part)) not in preferred_keys
    ]
    return os.pathsep.join([*preferred, *remaining])


def ensure_local_video_reconstruction_path():
    current_path = os.environ.get("PATH", "")
    preferred_path = _prepend_existing_path_entries(
        current_path,
        _local_video_reconstruction_paths(),
    )

    if preferred_path != current_path:
        os.environ["PATH"] = preferred_path


def build_video_process_env():
    ensure_local_video_reconstruction_path()
    process_env = os.environ.copy()
    process_env['PATH'] = _prepend_existing_path_entries(process_env.get('PATH', ''), _local_video_reconstruction_paths())
    if os.name == 'nt':
        process_env['Path'] = process_env['PATH']
    process_env.setdefault('PYTHONUTF8', '1')
    process_env.setdefault('PYTHONIOENCODING', 'utf-8')
    return process_env


def normalize_video_reconstruction_settings(value):
    raw = value if isinstance(value, dict) else {}
    defaults = get_video_reconstruction_config(persist_missing=False)
    quality = raw.get("default_quality")
    vram_budget = raw.get("vram_budget")

    return {
        "default_quality": quality if quality in PRESET_RECONSTRUCTION_QUALITIES else defaults["default_quality"],
        "default_engine": "brush",
        "vram_budget": vram_budget if vram_budget in VALID_VRAM_BUDGETS else defaults["vram_budget"],
        "keep_intermediate_files": bool(raw.get("keep_intermediate_files")),
    }


def coerce_form_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def parse_custom_options_value(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def coerce_custom_int(options, key, default, minimum, maximum):
    raw_value = options.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, {
            "error": f"{key} must be an integer",
            "code": ERROR_INVALID_REQUEST,
            "field": f"custom_options.{key}",
        }
    if value < minimum or value > maximum:
        return None, {
            "error": f"{key} must be between {minimum} and {maximum}",
            "code": ERROR_INVALID_REQUEST,
            "field": f"custom_options.{key}",
        }
    return value, None


def normalize_custom_quality_options(value, engine='brush'):
    options = parse_custom_options_value(value)
    if options is None:
        return None, {'error': 'custom_options must be an object', 'code': ERROR_INVALID_REQUEST, 'field': 'custom_options'}
    if engine not in VALID_RECONSTRUCTION_ENGINES:
        return None, {'error': 'Unsupported reconstruction engine', 'code': ERROR_INVALID_REQUEST, 'field': 'engine'}
    normalized = {}
    for field, limits in (('frame_count', CUSTOM_QUALITY_LIMITS['frame_count']),
                          ('max_num_iterations', CUSTOM_QUALITY_LIMITS['max_num_iterations']),
                          ('max_resolution', (640, 3840))):
        normalized[field], error = coerce_custom_int(options, field, CUSTOM_QUALITY_DEFAULTS[field], *limits)
        if error:
            return None, error
    matching = str(options.get('matching_method', CUSTOM_QUALITY_DEFAULTS['matching_method'])).strip().lower()
    if matching not in VALID_MATCHING_METHODS:
        return None, {'error': 'matching_method must be sequential or exhaustive', 'code': ERROR_INVALID_REQUEST,
                      'field': 'custom_options.matching_method'}
    if matching == 'exhaustive' and normalized['frame_count'] > CUSTOM_QUALITY_LIMITS['exhaustive_frame_count_max']:
        return None, {'error': 'exhaustive matching is limited to 450 custom frames', 'code': ERROR_INVALID_REQUEST,
                      'field': 'custom_options.frame_count'}
    normalized['matching_method'] = matching
    return normalized, None


def validate_reconstruction_options(data):
    if not isinstance(data, dict):
        data = {}

    config = get_video_reconstruction_config()
    mode = data.get("mode") or "auto"
    quality = data.get("quality") or config["default_quality"]
    engine = data.get("engine") or config["default_engine"]
    output_name = data.get("output_name")

    if mode not in VALID_RECONSTRUCTION_MODES:
        return None, {
            "error": "Unsupported reconstruction mode",
            "code": ERROR_INVALID_REQUEST,
            "field": "mode",
        }, 400
    if quality not in VALID_RECONSTRUCTION_QUALITIES:
        return None, {
            "error": "Unsupported reconstruction quality",
            "code": ERROR_INVALID_REQUEST,
            "field": "quality",
        }, 400

    custom_options = None
    if quality == CUSTOM_RECONSTRUCTION_QUALITY:
        custom_options, custom_error = normalize_custom_quality_options(data.get("custom_options"), engine)
        if custom_error:
            return None, custom_error, 400

    if engine not in VALID_RECONSTRUCTION_ENGINES:
        return None, {
            "error": "Unsupported reconstruction engine",
            "code": ERROR_INVALID_REQUEST,
            "field": "engine",
        }, 400

    if output_name is not None:
        if not isinstance(output_name, str):
            return None, {
                "error": "output_name must be a string",
                "code": ERROR_INVALID_REQUEST,
                "field": "output_name",
            }, 400
        output_name = output_name.strip()
        if len(output_name) > 120:
            return None, {
                "error": "output_name is too long",
                "code": ERROR_INVALID_REQUEST,
                "field": "output_name",
            }, 400

    keep_intermediate_files = data.get("keep_intermediate_files")
    if keep_intermediate_files is None:
        keep_intermediate_files = config["keep_intermediate_files"]

    return {
        "mode": mode,
        "quality": quality,
        "engine": engine,
        "vram_budget": config["vram_budget"],
        "output_name": output_name or None,
        "custom_options": custom_options,
        "keep_intermediate_files": coerce_form_bool(keep_intermediate_files, config["keep_intermediate_files"]),
    }, None, 200


def validate_create_request(data):
    request_data, error_payload, status_code = validate_reconstruction_options(data)
    if error_payload:
        return None, error_payload, status_code

    video_id = data.get("video_id") if isinstance(data, dict) else None
    if not isinstance(video_id, str) or not video_id.strip():
        return None, {
            "error": "video_id is required",
            "code": ERROR_INVALID_REQUEST,
            "field": "video_id",
        }, 400

    return {
        **request_data,
        "video_id": video_id.strip(),
    }, None, 200


def validate_upload_request(form_data, uploaded_file):
    request_data, error_payload, status_code = validate_reconstruction_options(dict(form_data or {}))
    if error_payload:
        return None, error_payload, status_code

    if not uploaded_file or not uploaded_file.filename:
        return None, {
            "error": "video file is required",
            "code": ERROR_INVALID_REQUEST,
            "field": "file",
        }, 400

    original_name = uploaded_file.filename
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in photo_gallery.ALLOWED_VIDEO_EXTENSIONS:
        return None, {
            "error": "Unsupported video format",
            "code": ERROR_UNSUPPORTED_VIDEO,
            "field": "file",
        }, 400

    return {
        **request_data,
        "source_name": original_name,
    }, None, 200


def resolve_brush_quality_profile(quality, vram_budget, custom_options=None):
    """固定 Brush 日程，并分别控制 SfM 与训练图像的真实长边。"""
    presets = {
        'preview': (6, 9, 1600, 1200, 4096, 8000, 7000, 0.0022, 0.11),
        # 中档对齐 OOOSplat 均衡档的实际工作图、帧覆盖和配准预算。
        'high': (8, 12, 1920, 1600, 8192, 15000, 13000, 0.002, 0.12),
        'extreme': (12, 15, 3840, 3200, 16384, 30000, 23000, 0.0016, 0.14),
    }
    fps, rescue_fps, resolution, sfm_resolution, features, iterations, stop, threshold, fraction = presets.get(quality, presets['high'])
    # 引擎版本与增密阈值必须一起变化；这不是旧 0.3.0 梯度口径。
    max_splats = 500000 if quality == 'preview' else 1000000
    if quality in {'extreme', CUSTOM_RECONSTRUCTION_QUALITY}:
        max_splats = 4000000 if vram_budget in {'16gb', '24gb'} else 1500000
        if vram_budget == '8gb':
            resolution, stop, threshold, fraction = min(resolution, 1920), 21000, 0.0018, 0.13
            max_splats = 1000000
    profile = {
        'engine': 'brush', 'sampling_fps': fps, 'rescue_sampling_fps': rescue_fps, 'frame_count': 1200,
        'max_resolution': resolution, 'sfm_max_resolution': sfm_resolution,
        # 普通不透明视频不启用仅两个视图支持的点，避免引入弱约束几何。
        'sfm_max_features': features, 'sfm_allow_two_view_tracks': False,
        'sfm_nonlocal_matching': quality != CUSTOM_RECONSTRUCTION_QUALITY,
        'max_num_iterations': iterations, 'matching_method': 'sequential',
        'brush_growth_grad_threshold': threshold, 'brush_growth_select_fraction': fraction,
        'brush_growth_stop_iter': stop, 'brush_max_splats': max_splats,
        'vram_budget': vram_budget, 'recipe_version': brush_engine.BRUSH_RECIPE_VERSION,
    }
    if quality == CUSTOM_RECONSTRUCTION_QUALITY:
        options, error = normalize_custom_quality_options(custom_options, 'brush')
        if error:
            raise ValueError(error['error'])
        profile.update(options)
        profile['sampling_fps'] = None
        profile['brush_growth_stop_iter'] = max(1, round(options['max_num_iterations'] * 0.85))
    return profile


def effective_vram_budget(configured):
    """仅在任务开始探测显存；用户预算可以更低，不能高于实际设备。"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode:
            return configured
        memory_mb = max(int(line.strip()) for line in result.stdout.splitlines() if line.strip())
        # 留出驱动保留显存造成的 MiB 偏差，12227 MiB 属于标称 12GB 卡。
        detected = '24gb' if memory_mb >= 23000 else '16gb' if memory_mb >= 15300 else '12gb' if memory_mb >= 11500 else '8gb'
        if configured == 'auto':
            return detected
        order = ['8gb', '12gb', '16gb', '24gb']
        return order[min(order.index(configured), order.index(detected))] if configured in order else detected
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return configured


def resolve_quality_profile(quality, vram_budget, custom_options=None, engine='brush'):
    if engine not in VALID_RECONSTRUCTION_ENGINES:
        raise ValueError('Unsupported reconstruction engine')
    return resolve_brush_quality_profile(quality, vram_budget, custom_options)


def command_version(name, args=None, timeout=5):
    command = which(name)
    if not command:
        return {
            "name": name,
            "category": "required",
            "required": True,
            "available": False,
            "version": None,
            "message": f"{name} not found in PATH",
        }

    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        # Windows batch entrypoints may experience a transient cold
        # first launch can occasionally return a transient non-zero status
        # while Windows is still loading/scanning the bundled Python modules.
        # Retry only these wrappers, once; native tools and persistent wrapper
        # failures keep their original result and diagnostics.
        attempts = 2 if Path(command).suffix.lower() in {".bat", ".cmd"} else 1
        for attempt in range(attempts):
            result = subprocess.run(
                [command, *(args or ["-version"])],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
            if result.returncode == 0 or attempt + 1 == attempts:
                break
            time.sleep(0.25)
        output = (result.stdout or result.stderr or "").strip().splitlines()
        return {
            "name": name,
            "category": "required",
            "required": True,
            "available": result.returncode == 0,
            "version": output[0][:220] if output else None,
            "message": None if result.returncode == 0 else f"{name} returned {result.returncode}",
        }
    except Exception as exc:
        return {
            "name": name,
            "category": "required",
            "required": True,
            "available": False,
            "version": None,
            "message": str(exc),
        }


def _decorate_dependency_status(dependencies, *, checked_at, refreshing, cached):
    result = copy.deepcopy(dependencies)
    summary = result.setdefault("summary", {})
    summary["checking"] = bool(refreshing)
    summary["checked_at"] = checked_at
    summary["cached"] = bool(cached)
    return result


def _pending_dependency_status():
    message = 'Video reconstruction tools are being checked in the background.'
    return {'required': {'available': False, 'tools': [], 'message': message},
            'brush': {'available': False, 'tools': [], 'message': message},
            'summary': {'available': False, 'brush_available': False, 'checking': True,
                        'checked_at': None, 'cached': False}}


def _dependency_error_status(exc):
    message = f'Failed to check video reconstruction tools: {exc}'
    return {'required': {'available': False, 'tools': [], 'message': message},
            'brush': {'available': False, 'tools': [], 'message': message},
            'summary': {'available': False, 'brush_available': False}}


def _scan_dependencies():
    ensure_local_video_reconstruction_path()
    required_tools = [command_version('ffmpeg'), command_version('ffprobe')]
    for tool in required_tools:
        tool.update(category='required', required=True)
    colmap = command_version('colmap', ['-h'], timeout=10)
    colmap.update(category='brush', required=True)
    brush_path = brush_engine.find_brush_executable()
    brush = command_version(brush_path, ['--help'], timeout=15) if brush_path else {
        'available': False, 'message': 'Install the pinned Brush CLI using tools/install_brush.py.',
    }
    brush.update(name='brush', category='brush', required=True)
    required_available = all(tool['available'] for tool in required_tools)
    available = required_available and colmap['available'] and brush['available']
    return {'required': {'available': required_available, 'tools': required_tools,
                         'message': None if required_available else 'ffmpeg and ffprobe are required for video decoding.'},
            'brush': {'available': available, 'tools': [colmap, brush],
                      'message': None if available else 'COLMAP and the pinned Brush CLI are required for video reconstruction.'},
            'summary': {'available': available, 'brush_available': available}}


def resolve_engine_strategy(engine, dependencies=None):
    if engine not in VALID_RECONSTRUCTION_ENGINES:
        return None, ERROR_INVALID_REQUEST
    dependencies = dependencies or check_dependencies()
    if not dependencies.get('required', {}).get('available'):
        return None, ERROR_DEPENDENCY_MISSING
    available = bool(dependencies.get('brush', {}).get('available'))
    return ('brush', None) if available else (None, ERROR_BRUSH_UNAVAILABLE)


def sanitize_output_stem(name):
    raw = str(name or "").strip()
    if not raw:
        raw = "video-reconstruction"
    raw = os.path.splitext(os.path.basename(raw))[0]
    raw = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", raw)
    raw = re.sub(r"\s+", "_", raw).strip("._ ")
    if not raw:
        raw = "video-reconstruction"

    safe_ascii = secure_filename(raw)
    if safe_ascii:
        return safe_ascii[:96]

    readable = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_", " "))
    readable = re.sub(r"\s+", "_", readable).strip("._ ")
    return (readable or "video-reconstruction")[:96]


def unique_output_paths(paths, requested_name, fallback_name):
    base = sanitize_output_stem(requested_name or fallback_name)
    for index in range(1000):
        suffix = "" if index == 0 else f"-{index + 1}"
        stem = f"{base}{suffix}"
        ply_path = os.path.join(paths.output_folder, f"{stem}.ply")
        spz_path = os.path.join(paths.output_folder, f"{stem}.spz")
        metadata_path = os.path.join(paths.output_folder, f'{stem}.meta.json')
        if not os.path.exists(ply_path) and not os.path.exists(spz_path) and not os.path.exists(metadata_path):
            return stem, ply_path, spz_path
    raise RuntimeError("Could not allocate a unique output name")


def resolve_source_video(paths, video_id):
    resolved = photo_gallery.resolve_media_path(
        paths,
        video_id,
        expected_type=photo_gallery.MEDIA_TYPE_VIDEO,
        allow_stale=True,
    )
    if not resolved:
        return None

    album, full_path, meta = resolved
    root_path = os.path.realpath(album["path"])
    real_path = os.path.realpath(full_path)
    if not is_real_path_inside(real_path, root_path) or not os.path.isfile(real_path):
        return None
    if meta.get("media_type") != photo_gallery.MEDIA_TYPE_VIDEO:
        return None
    return album, real_path, meta


def build_video_task(paths, request_data):
    source = resolve_source_video(paths, request_data["video_id"])
    if not source:
        return None, {
            "error": "Video not found",
            "code": ERROR_SOURCE_UNAVAILABLE,
        }, 404

    _, full_path, meta = source
    dependencies = check_dependencies()
    if dependencies.get("summary", {}).get("checking"):
        return None, {
            "error": "Video reconstruction dependencies are still being checked",
            "code": ERROR_DEPENDENCIES_CHECKING,
            "dependencies": dependencies,
        }, 409
    engine, engine_error = resolve_engine_strategy(request_data["engine"], dependencies)
    if engine_error:
        return None, {
            "error": "Video reconstruction dependencies are not available",
            "code": engine_error,
            "dependencies": dependencies,
        }, 409

    output_name, output_path, spz_path = unique_output_paths(
        paths,
        request_data.get("output_name"),
        meta.get("name") or os.path.basename(full_path),
    )

    from backend.services import model_sources
    source_identity = model_sources.capture_source(full_path, meta.get('name'), 'video', meta)
    model_sources.remember_album_source(paths, request_data['video_id'], model_sources.media_version(meta), source_identity['id'])
    task_payload = {
        "kind": TASK_KIND_VIDEO_3DGS,
        "filename": f"{output_name}.ply",
        "source_media_id": (meta.get('source_media_id') if request_data['video_id'].startswith('model-sources_')
                            else request_data['video_id']),
        "source_identity": source_identity,
        "source_id": source_identity['id'],
        "source_media_version": model_sources.media_version(meta),
        "source_name": meta.get("name") or os.path.basename(full_path),
        "source_video_path": full_path,
        "mode": request_data["mode"],
        "quality": request_data["quality"],
        "custom_options": request_data.get("custom_options"),
        "engine": request_data["engine"],
        "resolved_engine": engine,
        "vram_budget": request_data["vram_budget"],
        "output_name": output_name,
        "output_path": output_path,
        "spz_path": spz_path,
        "keep_intermediate_files": request_data["keep_intermediate_files"],
        "details": {
            "dependencies": dependencies,
            "warnings": [],
            "logs": [],
        },
    }
    prepare_video_model_assets(paths, task_payload, generate_thumbnail=False)
    return task_payload, None, 200


def save_uploaded_source_video(paths, uploaded_file):
    original_name = uploaded_file.filename or "video.mp4"
    safe_name = secure_filename(original_name)
    if not safe_name:
        _, ext = os.path.splitext(original_name)
        safe_name = f"video{ext.lower() if ext else '.mp4'}"

    upload_id = uuid.uuid4().hex
    upload_dir = os.path.join(model_gallery.get_video_uploads_folder(paths), upload_id)
    os.makedirs(upload_dir, exist_ok=True)
    target_path = os.path.realpath(os.path.join(upload_dir, safe_name))
    upload_root = os.path.realpath(model_gallery.get_video_uploads_folder(paths))
    if not is_real_path_inside(target_path, upload_root):
        raise ValueError("Unsafe uploaded video path")

    uploaded_file.save(target_path)
    return target_path


def build_uploaded_video_task(paths, request_data, uploaded_file):
    dependencies = check_dependencies()
    if dependencies.get("summary", {}).get("checking"):
        return None, {
            "error": "Video reconstruction dependencies are still being checked",
            "code": ERROR_DEPENDENCIES_CHECKING,
            "dependencies": dependencies,
        }, 409
    engine, engine_error = resolve_engine_strategy(request_data["engine"], dependencies)
    if engine_error:
        return None, {
            "error": "Video reconstruction dependencies are not available",
            "code": engine_error,
            "dependencies": dependencies,
        }, 409

    source_name = request_data.get("source_name") or uploaded_file.filename or "video.mp4"
    output_name, output_path, spz_path = unique_output_paths(
        paths,
        request_data.get("output_name"),
        source_name,
    )
    source_video_path = save_uploaded_source_video(paths, uploaded_file)

    from backend.services import model_sources
    source_identity = model_sources.capture_source(source_video_path, source_name, 'video')

    task_payload = {
        "kind": TASK_KIND_VIDEO_3DGS,
        "filename": f"{output_name}.ply",
        "source_media_id": None,
        "source_identity": source_identity,
        "source_id": source_identity['id'],
        "source_media_version": model_sources.media_version(source_identity),
        "source_name": source_name,
        "source_video_path": source_video_path,
        "source_mime_type": photo_gallery.get_video_mime_type(source_name),
        "mode": request_data["mode"],
        "quality": request_data["quality"],
        "custom_options": request_data.get("custom_options"),
        "engine": request_data["engine"],
        "resolved_engine": engine,
        "vram_budget": request_data["vram_budget"],
        "output_name": output_name,
        "output_path": output_path,
        "spz_path": spz_path,
        "keep_intermediate_files": request_data["keep_intermediate_files"],
        "details": {
            "dependencies": dependencies,
            "warnings": [],
            "logs": [],
        },
    }
    prepare_video_model_assets(paths, task_payload, generate_thumbnail=False)
    return task_payload, None, 200


def _refresh_dependency_status_sync():
    global _DEPENDENCY_STATUS_CACHE, _DEPENDENCY_STATUS_CHECKED_AT, _DEPENDENCY_STATUS_REFRESHING

    try:
        dependencies = _scan_dependencies()
    except Exception as exc:
        dependencies = _dependency_error_status(exc)

    checked_at = time.time()
    with _DEPENDENCY_STATUS_LOCK:
        _DEPENDENCY_STATUS_CACHE = dependencies
        _DEPENDENCY_STATUS_CHECKED_AT = checked_at
        _DEPENDENCY_STATUS_REFRESHING = False

    return _decorate_dependency_status(
        dependencies,
        checked_at=checked_at,
        refreshing=False,
        cached=True,
    )


def start_dependency_warmup(force=False):
    """Start one non-blocking dependency scan for this process."""
    global _DEPENDENCY_STATUS_REFRESHING

    with _DEPENDENCY_STATUS_LOCK:
        if _DEPENDENCY_STATUS_REFRESHING:
            return False
        if _DEPENDENCY_STATUS_CACHE is not None and not force:
            return False
        _DEPENDENCY_STATUS_REFRESHING = True

    thread = threading.Thread(
        target=_refresh_dependency_status_sync,
        name="video-reconstruction-dependency-check",
        daemon=True,
    )
    thread.start()
    return True


def get_dependency_status(force=False):
    """Return cached dependency status immediately and warm it in the background."""
    if force:
        start_dependency_warmup(force=True)
    else:
        start_dependency_warmup()

    with _DEPENDENCY_STATUS_LOCK:
        if _DEPENDENCY_STATUS_CACHE is None:
            return _pending_dependency_status()
        return _decorate_dependency_status(
            _DEPENDENCY_STATUS_CACHE,
            checked_at=_DEPENDENCY_STATUS_CHECKED_AT,
            refreshing=_DEPENDENCY_STATUS_REFRESHING,
            cached=True,
        )


def check_dependencies(force=False):
    """Return video reconstruction dependencies, reusing the per-process cache."""
    global _DEPENDENCY_STATUS_REFRESHING

    with _DEPENDENCY_STATUS_LOCK:
        if _DEPENDENCY_STATUS_CACHE is not None and not force:
            return _decorate_dependency_status(
                _DEPENDENCY_STATUS_CACHE,
                checked_at=_DEPENDENCY_STATUS_CHECKED_AT,
                refreshing=_DEPENDENCY_STATUS_REFRESHING,
                cached=True,
            )
        if _DEPENDENCY_STATUS_REFRESHING and not force:
            return _pending_dependency_status()
        _DEPENDENCY_STATUS_REFRESHING = True

    return _refresh_dependency_status_sync()


def build_video_model_metadata(task):
    """Build safe sidecar metadata for a video reconstruction output."""
    details = task.get('details') or {}
    report = {key: copy.deepcopy(details[key]) for key in (
        'resource_profile', 'geometry', 'stage_durations', 'focused_cleanup', 'output_stats',
        'brush_oom_retry', 'up_alignment',
    ) if key in details}
    return {
        "source_media_type": "video",
        "viewer_orientation": VIEWER_ORIENTATION_Y_FRONT,
        'viewer_camera': details.get('viewer_camera'),
        'point_count': (details.get('output_stats') or {}).get('vertex_count'),
        "source_media_id": task.get("source_media_id"),
        "source_identity": task.get('source_identity'),
        "source_media_version": task.get('source_media_version'),
        "source_name": task.get("source_name"),
        "source_video_path": task.get("source_video_path"),
        "source_mime_type": task.get("source_mime_type"),
        "generator": TASK_KIND_VIDEO_3DGS,
        "mode": task.get("mode"),
        "quality": task.get("quality"),
        "custom_options": task.get("custom_options"),
        "engine": task.get("engine"),
        "resolved_engine": task.get("resolved_engine"),
        'reconstruction': report,
        'generation': model_generation.build_generation_summary(
            task, engine='OOOBrush', engine_version=brush_engine.BRUSH_VERSION,
            engine_commit=brush_engine.BRUSH_COMMIT,
        ) if task.get('completed_at') is not None else None,
    }


def prepare_video_model_assets(paths, task, *, generate_thumbnail=True):
    """Write sidecar metadata early and optionally prepare the video thumbnail."""
    model_id = os.path.splitext(os.path.basename(task["output_path"]))[0]
    metadata = build_video_model_metadata(task)
    try:
        model_gallery.write_model_metadata(paths, model_id, metadata)
    except Exception as exc:
        print(f"⚠️ Failed to write model metadata for {model_id}: {exc}")

    if generate_thumbnail:
        try:
            model_gallery.generate_video_thumbnail(paths, task["source_video_path"], model_id)
        except Exception as exc:
            print(f"⚠️ Failed to generate video model thumbnail for {model_id}: {exc}")


def persist_video_model_assets(paths, task):
    """为视频重建输出写入图库元数据并生成源视频缩略图。"""
    prepare_video_model_assets(paths, task, generate_thumbnail=True)


def _format_duration(seconds):
    if seconds is None:
        return "?"
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{sec:02d}s"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def update_task(task_manager, task_id, **patch):
    log_snapshot = None
    with task_manager.task_lock:
        task = task_manager.task_status.get(task_id)
        if task:
            now = time.time()
            previous_stage = task.get("stage")
            new_stage = patch.get("stage")
            stage_changed = bool(new_stage and new_stage != previous_stage)
            prev_stage_duration = None
            if stage_changed:
                stage_started = task.get("stage_started_at")
                if previous_stage and stage_started:
                    monotonic_start = task.get('_stage_started_monotonic')
                    prev_stage_duration = max(0, time.monotonic() - monotonic_start) if monotonic_start is not None else max(0, now - stage_started)
                    durations = task.setdefault("details", {}).setdefault("stage_durations", {})
                    durations[previous_stage] = round(durations.get(previous_stage, 0) + prev_stage_duration, 3)
                task["stage_started_at"] = now
                task['_stage_started_monotonic'] = time.monotonic()
            if patch.get('status') == 'completed':
                task['_generation_completed_monotonic'] = time.monotonic()
            task.update(patch)
            started_at = task.get("started_at")
            total_elapsed = (now - started_at) if started_at else None
            details = task.get("details")
            stage_durations = dict(details.get("stage_durations", {})) if isinstance(details, dict) else {}
            log_snapshot = {
                "filename": task.get("filename"),
                "status": task.get("status"),
                "stage": task.get("stage"),
                "progress": task.get("progress"),
                "error": task.get("error"),
                "error_code": task.get("error_code"),
                "output_path": task.get("output_path"),
                "previous_stage": previous_stage,
                "prev_stage_duration": prev_stage_duration,
                "total_elapsed": total_elapsed,
                "stage_durations": stage_durations,
            }

    if not log_snapshot:
        return

    status = patch.get("status")
    stage = patch.get("stage")
    elapsed_text = _format_duration(log_snapshot["total_elapsed"])
    if status == "failed":
        runtime.log(
            "ERROR",
            "Video task "
            f"{task_id} failed: file={log_snapshot['filename']} "
            f"stage={log_snapshot['stage']} code={log_snapshot['error_code']} "
            f"elapsed={elapsed_text} error={log_snapshot['error']}",
        )
    elif status == "cancelled":
        runtime.log(
            "WARN",
            f"Video task {task_id} cancelled: file={log_snapshot['filename']} "
            f"stage={log_snapshot['stage']} elapsed={elapsed_text}",
        )
    elif status == "completed":
        log_level = "WARN" if log_snapshot.get("error") else "INFO"
        stage_summary = ", ".join(
            f"{name}={_format_duration(duration)}"
            for name, duration in log_snapshot["stage_durations"].items()
        )
        summary_suffix = f" stages=[{stage_summary}]" if stage_summary else ""
        warning_suffix = f" warning={log_snapshot['error']}" if log_snapshot.get("error") else ""
        runtime.log(
            log_level,
            "Video task "
            f"{task_id} completed: file={log_snapshot['filename']} output={log_snapshot['output_path']} "
            f"total={elapsed_text}{summary_suffix}{warning_suffix}",
        )
    elif stage and stage != log_snapshot["previous_stage"]:
        previous = log_snapshot["previous_stage"]
        prev_duration = log_snapshot["prev_stage_duration"]
        prev_suffix = (
            f" ({previous} took {_format_duration(prev_duration)})"
            if previous and prev_duration is not None
            else ""
        )
        runtime.log(
            "INFO",
            "Video task "
            f"{task_id} stage={stage} progress={log_snapshot['progress']} "
            f"elapsed={elapsed_text}{prev_suffix} file={log_snapshot['filename']}",
        )


def append_task_log(task_manager, task_id, line, limit=80):
    text = str(line or "").rstrip()
    if not text:
        return
    with task_manager.task_lock:
        task = task_manager.task_status.get(task_id)
        if not task:
            return
        details = task.setdefault("details", {})
        logs = details.setdefault("logs", [])
        logs.append(text[-1000:])
        if len(logs) > limit:
            del logs[:-limit]
    runtime.log("DEBUG", f"Video task {task_id} | {text}")


def is_task_cancelled(task_manager, task_id):
    with task_manager.task_lock:
        return task_manager.task_status.get(task_id, {}).get("status") == "cancelled"


def wait_for_process(task_manager, task_id, process, output_lines, stage=None, profile=None, last_output=None, log_file=None):
    cancelled = False
    last_reported_progress = None
    for line in iter(process.stdout.readline, ""):
        if not line:
            break
        if last_output is not None:
            last_output[0] = time.time()
        output_lines.append(line)
        if log_file is not None:
            try:
                log_file.write(line)
                log_file.flush()
            except OSError as exc:
                runtime.log('WARN', f'Video task {task_id} stage log was disabled after a write failure: {exc}')
                log_file = None
        append_task_log(task_manager, task_id, line)
        if stage == "video_optimize":
            if profile:
                step_progress = parse_training_progress(line, profile)
                if step_progress is not None and step_progress != last_reported_progress:
                    last_reported_progress = step_progress
                    update_task(task_manager, task_id, progress=step_progress, stage=stage)
        if is_task_cancelled(task_manager, task_id):
            cancelled = True
            break

    if cancelled:
        terminate_process_tree(process)
        return None, True

    if process.stdout:
        process.stdout.close()
    return process.wait(), False


def parse_training_progress(line, profile):
    parsed = brush_engine.parse_brush_progress(line, int(profile.get('max_num_iterations') or 0))
    if not parsed:
        return None
    base, ceiling = STAGE_PROGRESS['video_optimize'], STAGE_PROGRESS['video_export']
    return int(base + (ceiling - base) * min(1.0, max(0.0, parsed['progress'])))


def terminate_process_tree(process):
    """Terminate the process and its children so GPU workers don't leak.

    Brush / COLMAP can spawn child processes; a plain
    process.terminate() only signals the parent, which on Windows leaves orphans
    holding VRAM and can OOM the next queued task. Kill the whole tree instead,
    falling back to single-process terminate/kill if the tree call fails.
    """
    if process.poll() is not None:
        return

    pid = process.pid
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                check=False,
                capture_output=True,
                timeout=15,
            )
            return
        import signal

        try:
            group_id = os.getpgid(pid)
        except (ProcessLookupError, OSError):
            group_id = None

        if group_id is not None:
            try:
                os.killpg(group_id, signal.SIGTERM)
                process.wait(timeout=5)
                return
            except ProcessLookupError:
                return
            except Exception:
                try:
                    os.killpg(group_id, signal.SIGKILL)
                    return
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback: best-effort single-process termination.
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _log_command_heartbeat(task_id, stage, command_name, process, last_output, stop_event,
                           interval=45, quiet_threshold=40):
    """Periodically reassure the user that a quiet long-running step is alive.

    Steps like COLMAP camera alignment can run for minutes
    without emitting any stdout, which looks like a freeze. When no tool output
    has arrived for a while, log a short INFO heartbeat with elapsed time until
    the process finishes.
    """
    started = time.time()
    while not stop_event.wait(interval):
        if process.poll() is not None:
            break
        quiet_seconds = time.time() - last_output[0]
        if quiet_seconds >= quiet_threshold:
            runtime.log(
                "INFO",
                f"Video task {task_id} stage={stage or '-'} command={command_name} still working "
                f"(no output for {int(quiet_seconds)}s, step elapsed {_format_duration(time.time() - started)}); "
                "this step can take several minutes, please wait.",
            )


def run_command(task_manager, task_id, cmd, cwd=None, stage=None, progress=None, profile=None):
    if is_task_cancelled(task_manager, task_id):
        return None, [], True
    if stage:
        update_task(task_manager, task_id, stage=stage, progress=progress or STAGE_PROGRESS.get(stage, 0))

    process_env = build_video_process_env()
    if profile and profile.get('engine') == 'brush':
        process_env = brush_engine.build_brush_environment(process_env)
    command_name = Path(str(cmd[0])).name if cmd else "command"
    actual_cmd = cmd
    append_task_log(task_manager, task_id, "$ " + " ".join(str(part) for part in cmd))
    runtime.log(
        "INFO",
        f"Video task {task_id} starting stage={stage or '-'} command={command_name}",
    )
    runtime.log(
        "DEBUG",
        "Video task "
        f"{task_id} command stage={stage or '-'} cwd={cwd or os.getcwd()}: "
        f"{runtime.format_command_for_log(cmd)}",
    )
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(
        actual_cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=process_env,
        **popen_kwargs,
    )
    with task_manager.task_lock:
        task_manager.running_processes[task_id] = process

    output_lines = []
    last_output = [time.time()]
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_log_command_heartbeat,
        args=(task_id, stage, command_name, process, last_output, heartbeat_stop),
        daemon=True,
    )
    heartbeat.start()
    log_file = None
    if cwd and stage:
        try:
            log_dir = Path(cwd) / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = (log_dir / f'{stage}-{uuid.uuid4().hex[:8]}.log').open('w', encoding='utf-8')
        except OSError as exc:
            runtime.log('WARN', f'Video task {task_id} could not write a stage log: {exc}')
    try:
        return_code, cancelled = wait_for_process(
            task_manager,
            task_id,
            process,
            output_lines,
            stage=stage,
            profile=profile,
            last_output=last_output,
            log_file=log_file,
        )
    except Exception:
        terminate_process_tree(process)
        raise
    finally:
        if log_file is not None:
            try:
                log_file.close()
            except OSError as exc:
                runtime.log('WARN', f'Video task {task_id} could not close its stage log: {exc}')
        heartbeat_stop.set()
        with task_manager.task_lock:
            if task_manager.running_processes.get(task_id) is process:
                task_manager.running_processes.pop(task_id, None)

    if cancelled:
        runtime.log("WARN", f"Video task {task_id} command cancelled stage={stage or '-'}")
    else:
        level = "INFO" if return_code == 0 else "ERROR"
        runtime.log("DEBUG", f"Video task {task_id} command produced {len(output_lines)} output lines stage={stage or '-'}")
        runtime.log(level, f"Video task {task_id} command finished stage={stage or '-'} return_code={return_code}")

    return return_code, output_lines, cancelled


def classify_process_failure(text):
    """只在明确显存不足时允许降预算；设备中断优先停止。"""
    normalized = (text or "").lower()
    if any(pattern in normalized for pattern in DEVICE_LOST_PATTERNS):
        return ERROR_GPU_DEVICE_LOST
    if any(pattern in normalized for pattern in OOM_PATTERNS):
        return ERROR_OOM
    if HOST_MEMORY_PATTERN.search(normalized):
        return ERROR_HOST_MEMORY
    if TYPED_OOM_PATTERN.search(normalized):
        return ERROR_OOM
    return ERROR_TRAINING_FAILED


def contains_oom(text):
    return classify_process_failure(text) == ERROR_OOM


def build_failure_message(return_code, output_lines):
    output = "".join(output_lines or [])
    tail = "\n".join(output.splitlines()[-24:])
    failure = classify_process_failure(output)
    if failure == ERROR_GPU_DEVICE_LOST:
        return failure, (
            'The GPU device was lost or reset. Check the driver and GPU connection, '
            'then retry.'
        )
    if failure == ERROR_HOST_MEMORY:
        return failure, (
            'System RAM is not enough for this reconstruction. Free system memory '
            'and check virtual memory before retrying.'
        )
    if failure == ERROR_OOM:
        return ERROR_OOM, (
            "GPU memory is not enough for this reconstruction. "
            "Try a lower quality preset, fewer frames, or lower resolution."
        )
    return failure, tail or f"Command failed with return code {return_code}"


def clean_job_dir(job_dir, keep):
    if keep:
        return
    try:
        shutil.rmtree(job_dir)
    except OSError:
        pass


def _remove_file_if_inside(path, root):
    if not path:
        return False
    try:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(root)
        if real_path == real_root or not is_real_path_inside(real_path, real_root):
            return False
        if os.path.isfile(real_path):
            os.remove(real_path)
            return True
    except OSError:
        return False
    return False


def _remove_tree_if_inside(path, root):
    if not path:
        return False
    try:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(root)
        if real_path == real_root or not is_real_path_inside(real_path, real_root):
            return False
        if os.path.isdir(real_path):
            shutil.rmtree(real_path)
            return True
    except OSError:
        return False
    return False


def _is_path_stale(path, stale_age_seconds, now=None):
    if stale_age_seconds <= 0:
        return True
    try:
        return (now or time.time()) - os.path.getmtime(path) >= stale_age_seconds
    except OSError:
        return False


def cleanup_unfinished_model_assets(paths, task):
    """Remove output placeholders for a video task that did not complete."""
    removed = 0
    for key in ("output_path", "spz_path"):
        if _remove_file_if_inside(task.get(key), paths.output_folder):
            removed += 1

    model_id = task.get("output_name")
    if not model_id and task.get("output_path"):
        model_id = os.path.splitext(os.path.basename(task["output_path"]))[0]
    if model_id:
        if _remove_file_if_inside(model_gallery.get_model_metadata_path(paths, model_id), paths.output_folder):
            removed += 1
        if _remove_file_if_inside(model_gallery.get_thumbnail_path(paths, model_id), paths.thumbnail_folder):
            removed += 1
    return removed


def cleanup_failed_task_artifacts(paths, task, job_dir, keep_intermediate):
    """Clean controlled temporary artifacts for a failed or cancelled video task."""
    clean_job_dir(job_dir, keep_intermediate)
    removed = cleanup_unfinished_model_assets(paths, task)
    try:
        model_gallery.delete_uploaded_source_video(paths, task)
    except Exception as exc:
        runtime.log("WARN", f"Failed to clean uploaded source video for task {task.get('id')}: {exc}")
    return removed


def collect_referenced_uploaded_source_paths(paths):
    """Return uploaded source files still referenced by completed video models."""
    references = set()
    if not os.path.isdir(paths.output_folder):
        return references

    upload_root = os.path.realpath(model_gallery.get_video_uploads_folder(paths))
    suffix = model_gallery.MODEL_METADATA_SUFFIX
    try:
        entries = list(os.scandir(paths.output_folder))
    except OSError:
        return references

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        model_id = entry.name[:-len(suffix)]
        if not os.path.isfile(os.path.join(paths.output_folder, model_id + ".ply")):
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as file:
                metadata = json.load(file)
        except (OSError, ValueError):
            continue
        source_video_path = metadata.get("source_video_path") if isinstance(metadata, dict) else None
        if not isinstance(source_video_path, str) or not source_video_path:
            continue
        real_path = os.path.realpath(source_video_path)
        if is_real_path_inside(real_path, upload_root):
            references.add(real_path)
    return references


def _path_is_or_contains_reference(path, references):
    if not references:
        return False
    real_path = os.path.realpath(path)
    for reference in references:
        if reference == real_path or is_real_path_inside(reference, real_path):
            return True
    return False


def cleanup_orphan_video_uploads(paths, stale_age_seconds=0):
    upload_root = model_gallery.get_video_uploads_folder(paths)
    if not os.path.isdir(upload_root):
        return 0

    referenced_paths = collect_referenced_uploaded_source_paths(paths)
    removed = 0
    now = time.time()
    try:
        entries = list(os.scandir(upload_root))
    except OSError:
        return removed

    for entry in entries:
        if _path_is_or_contains_reference(entry.path, referenced_paths):
            continue
        if not _is_path_stale(entry.path, stale_age_seconds, now=now):
            continue
        if entry.is_dir(follow_symlinks=False):
            if _remove_tree_if_inside(entry.path, upload_root):
                removed += 1
        elif entry.is_file(follow_symlinks=False):
            if _remove_file_if_inside(entry.path, upload_root):
                removed += 1
    return removed


def cleanup_unfinished_video_sidecars(paths):
    if not os.path.isdir(paths.output_folder):
        return 0

    suffix = model_gallery.MODEL_METADATA_SUFFIX
    removed = 0
    try:
        entries = list(os.scandir(paths.output_folder))
    except OSError:
        return removed

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        model_id = entry.name[:-len(suffix)]
        if os.path.isfile(os.path.join(paths.output_folder, model_id + ".ply")):
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as file:
                metadata = json.load(file)
        except (OSError, ValueError):
            continue
        if not isinstance(metadata, dict) or metadata.get("generator") != TASK_KIND_VIDEO_3DGS:
            continue
        if _remove_file_if_inside(entry.path, paths.output_folder):
            removed += 1
        _remove_file_if_inside(model_gallery.get_thumbnail_path(paths, model_id), paths.thumbnail_folder)
    return removed


def cleanup_stale_job_dirs(paths, stale_age_seconds=0):
    jobs_root = paths.video_reconstruction_jobs_folder
    if not os.path.isdir(jobs_root):
        return 0

    removed = 0
    now = time.time()
    try:
        entries = list(os.scandir(jobs_root))
    except OSError:
        return removed

    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        if not _is_path_stale(entry.path, stale_age_seconds, now=now):
            continue
        if _remove_tree_if_inside(entry.path, jobs_root):
            removed += 1
    return removed


def _normalized_path_fragment(path):
    return os.path.normcase(os.path.normpath(os.path.realpath(path)))


def _text_mentions_path(value, root):
    if not value:
        return False
    normalized = os.path.normcase(os.path.normpath(str(value).strip("\"'")))
    return root in normalized


def process_info_matches_video_runtime(info, runtime_root):
    cmdline = info.get("cmdline") or []
    name = info.get("name") or ""
    process_text = " ".join(str(part) for part in [name, *cmdline]).lower()
    if not any(token in process_text for token in VIDEO_RUNTIME_PROCESS_TOKENS):
        return False

    real_runtime_root = os.path.realpath(runtime_root)
    cwd = info.get("cwd")
    if cwd:
        try:
            if is_real_path_inside(os.path.realpath(cwd), real_runtime_root):
                return True
        except OSError:
            pass

    root_fragment = _normalized_path_fragment(real_runtime_root)
    return any(_text_mentions_path(part, root_fragment) for part in cmdline)


def _terminate_psutil_process_tree(psutil_module, process):
    try:
        targets = list(process.children(recursive=True))
        targets.append(process)
        for target in targets:
            try:
                target.terminate()
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                pass
        _, alive = psutil_module.wait_procs(targets, timeout=5)
        for target in alive:
            try:
                target.kill()
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                pass
        if alive:
            psutil_module.wait_procs(alive, timeout=5)
        return True
    except psutil_module.NoSuchProcess:
        return False
    except Exception as exc:
        runtime.log("WARN", f"Failed to terminate stale video reconstruction process tree: {exc}")
        return False


def terminate_stale_video_processes(paths):
    try:
        import psutil
    except Exception:
        return 0

    terminated = 0
    runtime_root = paths.video_reconstruction_folder
    current_pid = os.getpid()
    for process in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            if process.pid == current_pid:
                continue
            if not process_info_matches_video_runtime(process.info, runtime_root):
                continue
            if _terminate_psutil_process_tree(psutil, process):
                terminated += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            runtime.log("WARN", f"Failed to inspect video reconstruction process: {exc}")
    return terminated


def cleanup_stale_runtime_artifacts(
    paths,
    *,
    stale_job_age_seconds=0,
    stale_upload_age_seconds=0,
    terminate_processes=True,
):
    """Best-effort cleanup for artifacts left behind by interrupted video tasks."""
    summary = {
        "processes_terminated": 0,
        "jobs_removed": 0,
        "uploads_removed": 0,
        "sidecars_removed": 0,
    }
    if terminate_processes:
        summary["processes_terminated"] = terminate_stale_video_processes(paths)
    summary["jobs_removed"] = cleanup_stale_job_dirs(paths, stale_age_seconds=stale_job_age_seconds)
    summary["sidecars_removed"] = cleanup_unfinished_video_sidecars(paths)
    summary["uploads_removed"] = cleanup_orphan_video_uploads(paths, stale_age_seconds=stale_upload_age_seconds)

    if any(summary.values()):
        runtime.log(
            "INFO",
            "Cleaned stale video reconstruction runtime artifacts: "
            f"processes={summary['processes_terminated']} "
            f"jobs={summary['jobs_removed']} "
            f"sidecars={summary['sidecars_removed']} "
            f"uploads={summary['uploads_removed']}",
        )
    return summary


def should_apply_focused_cleanup(task):
    return task.get("mode") == "object"


def clean_gaussian_splat_ply(source_path, output_path, profile=None, object_focus=None):
    import numpy as np
    from plyfile import PlyData, PlyElement

    cleanup_profile = profile or FOCUSED_CLEANUP_PROFILE
    ply = PlyData.read(source_path)
    vertex = ply["vertex"].data
    names = vertex.dtype.names or ()
    required_names = {"x", "y", "z"}
    if not required_names.issubset(names):
        raise ValueError("PLY vertex data is missing x/y/z fields.")

    positions = np.column_stack([vertex["x"], vertex["y"], vertex["z"]]).astype(np.float64, copy=False)
    input_vertices = int(len(vertex))
    quantile_min, quantile_max = cleanup_profile["position_quantiles"]
    lower_bounds = np.percentile(positions, quantile_min, axis=0)
    upper_bounds = np.percentile(positions, quantile_max, axis=0)
    position_mask = np.all((positions >= lower_bounds) & (positions <= upper_bounds), axis=1)

    if "opacity" in names:
        opacity = np.asarray(vertex["opacity"], dtype=np.float64)
        alpha = 1.0 / (1.0 + np.exp(-opacity))
    else:
        alpha = np.ones(len(vertex), dtype=np.float64)
    alpha_mask = alpha >= cleanup_profile["alpha_min"]

    scale_names = [name for name in ("scale_0", "scale_1", "scale_2") if name in names]
    if scale_names:
        scales = np.column_stack([vertex[name] for name in scale_names]).astype(np.float64, copy=False)
        max_scale = np.exp(np.max(scales, axis=1))
        scale_limit = float(np.percentile(max_scale, cleanup_profile["scale_quantile"]))
        scale_mask = max_scale <= scale_limit
    else:
        scale_limit = None
        scale_mask = np.ones(len(vertex), dtype=bool)

    mask = position_mask & alpha_mask & scale_mask

    object_focus_applied = False
    object_focus_center = None
    object_focus_radius = None
    if object_focus is not None:
        center = np.asarray(object_focus[0], dtype=np.float64).reshape(-1)
        radius = float(object_focus[1])
        if center.shape == (3,) and np.isfinite(center).all() and np.isfinite(radius) and radius > 0:
            sphere_mask = np.sum((positions - center) ** 2, axis=1) <= radius * radius
            candidate = mask & sphere_mask
            candidate_count = int(candidate.sum())
            candidate_ratio = candidate_count / input_vertices if input_vertices else 0.0
            if candidate_count >= cleanup_profile["min_vertices"] and candidate_ratio >= cleanup_profile["object_min_keep_ratio"]:
                mask = candidate
                object_focus_applied = True
                object_focus_center = [float(value) for value in center]
                object_focus_radius = radius

    output_vertices = int(mask.sum())
    keep_ratio = output_vertices / input_vertices if input_vertices else 0.0
    stats = {
        "input_vertices": input_vertices,
        "output_vertices": output_vertices,
        "keep_ratio": keep_ratio,
        "position_quantiles": list(cleanup_profile["position_quantiles"]),
        "alpha_min": cleanup_profile["alpha_min"],
        "scale_quantile": cleanup_profile["scale_quantile"],
        "scale_limit": scale_limit,
        "object_focus_applied": object_focus_applied,
        "object_focus_center": object_focus_center,
        "object_focus_radius": object_focus_radius,
        "skipped": False,
    }

    # Object focus is allowed to keep a smaller fraction (it deliberately drops
    # the surrounding environment), so relax the "removed too much" guard when it
    # actually fired.
    effective_min_keep = (
        cleanup_profile["object_min_keep_ratio"] if object_focus_applied else cleanup_profile["min_keep_ratio"]
    )
    too_small = (
        output_vertices < cleanup_profile["min_vertices"]
        or keep_ratio < effective_min_keep
    )
    if too_small:
        shutil.copy2(source_path, output_path)
        stats["output_vertices"] = input_vertices
        stats["keep_ratio"] = 1.0
        stats["skipped"] = True
        stats["object_focus_applied"] = False
        stats["reason"] = "cleanup_would_remove_too_much"
        return stats

    cleaned_vertex = vertex[mask].copy()
    PlyData([PlyElement.describe(cleaned_vertex, "vertex")], text=False).write(output_path)
    return stats


def add_object_mode_warning(task):
    details = task.setdefault("details", {})
    warnings = details.setdefault("warnings", [])
    warning = {
        "code": "video_reconstruction_object_foreground_degraded",
        "message": "Automatic foreground segmentation is not configured; object mode will run without masks.",
    }
    if warning not in warnings:
        warnings.append(warning)


def run_brush_training_stage(task_manager, task_id, task, job_dir, data_dir, train_dir, profile):
    """显存不足时有限重试；高质量 / 极致 / 自定义保留请求的训练像素。"""
    executable = brush_engine.find_brush_executable()
    if not executable:
        return 'failed', None, ERROR_BRUSH_UNAVAILABLE, 'The pinned Brush CLI is not installed.'
    dataset_dir = os.path.join(train_dir, 'dataset')
    dataset = brush_engine.prepare_brush_dataset(data_dir, dataset_dir)
    task.setdefault('details', {})['up_alignment'] = dataset['up_alignment']
    task['details']['viewer_camera'] = brush_engine.build_brush_viewer_camera(dataset_dir)
    profile['brush_max_splats'] = max(int(profile['brush_max_splats']), int(dataset['sfm_points']))
    for attempt in range(2):
        output_dir = os.path.join(train_dir, f'brush-{attempt + 1}')
        os.makedirs(output_dir, exist_ok=True)
        command = brush_engine.build_brush_train_command(executable, dataset_dir, output_dir, profile)
        return_code, lines, cancelled = run_command(
            task_manager, task_id, command, cwd=job_dir,
            stage='video_optimize', progress=STAGE_PROGRESS['video_optimize'], profile=profile,
        )
        if cancelled or is_task_cancelled(task_manager, task_id):
            return 'cancelled', None, None, None
        if return_code == 0:
            exported_ply = brush_engine.find_brush_output(output_dir)
            if not exported_ply:
                return 'failed', None, ERROR_OUTPUT_MISSING, 'Brush completed without a final PLY.'
            stats = brush_engine.validate_brush_ply(exported_ply)
            task.setdefault('details', {})['output_stats'] = stats
            update_task(task_manager, task_id, stage='video_export', progress=STAGE_PROGRESS['video_export'])
            return 'ok', exported_ply, None, None
        if attempt == 0 and contains_oom(''.join(lines)):
            previous = {'max_resolution': profile['max_resolution'], 'max_splats': profile['brush_max_splats']}
            if task.get('quality') == 'preview':
                profile['max_resolution'] = max(640, round(profile['max_resolution'] * 0.75))
            profile['brush_max_splats'] = max(int(dataset['sfm_points']), round(profile['brush_max_splats'] * 0.67))
            task.setdefault('details', {})['brush_oom_retry'] = {
                'previous': previous, 'max_resolution': profile['max_resolution'],
                'max_splats': profile['brush_max_splats'],
            }
            message = ('Brush ran out of VRAM; retrying once with a smaller image and splat budget.'
                       if task.get('quality') == 'preview' else
                       'Brush ran out of VRAM; retrying once with a smaller splat budget while preserving training resolution.')
            append_task_log(task_manager, task_id, message)
            continue
        code, message = build_failure_message(return_code, lines)
        return 'failed', None, code, message
    return 'failed', None, ERROR_OOM, 'Brush could not fit this reconstruction in GPU memory.'


def publish_video_ply(source_path, output_path):
    """完整复制后原子发布，图库不会读到半个训练结果。"""
    output_dir = os.path.dirname(output_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix='.video-export-', suffix='.tmp', delete=False) as file:
            temporary = file.name
        shutil.copy2(source_path, temporary)
        os.replace(temporary, output_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def run_video_reconstruction_task(task_manager, task_id, task):
    job_dir = os.path.join(task_manager.paths.video_reconstruction_jobs_folder, task_id)
    source_dir = os.path.join(job_dir, "source")
    data_dir = os.path.join(job_dir, "colmap-data")
    train_dir = os.path.join(job_dir, "train")
    export_dir = os.path.join(job_dir, "export")
    logs_dir = os.path.join(job_dir, "logs")
    keep_intermediate = bool(task.get("keep_intermediate_files")) or task.get('mode') == 'object'
    engine = task.get('resolved_engine') or task.get('engine') or 'brush'
    budget = effective_vram_budget(task.get('vram_budget') or '12gb')
    profile = resolve_quality_profile(
        task.get("quality"),
        budget,
        task.get("custom_options"),
        engine=engine,
    )
    task.setdefault("details", {})["resource_profile"] = profile

    def cleanup_failed():
        cleanup_failed_task_artifacts(task_manager.paths, task, job_dir, keep_intermediate)

    for folder in (source_dir, data_dir, train_dir, export_dir, logs_dir):
        os.makedirs(folder, exist_ok=True)

    try:
        if is_task_cancelled(task_manager, task_id):
            cleanup_failed()
            return
        update_task(
            task_manager,
            task_id,
            status="processing",
            progress=STAGE_PROGRESS["video_prepare"],
            stage="video_prepare",
        )

        if task.get("mode") == "object":
            add_object_mode_warning(task)
            update_task(
                task_manager,
                task_id,
                progress=STAGE_PROGRESS["video_foreground"],
                stage="video_foreground",
            )
            append_task_log(
                task_manager,
                task_id,
                "Automatic foreground segmentation is not configured; continuing without masks.",
            )

        geometry_status, chosen_data_dir, geometry_lines, geometry_report = video_geometry.run_video_geometry(
            task_manager, task_id, task, job_dir, data_dir, profile, run_command, build_video_process_env(),
        )
        task.setdefault('details', {})['geometry'] = geometry_report
        if geometry_status == 'ok':
            data_dir = chosen_data_dir
            geometry_code, geometry_message = None, None
            if geometry_report['registration_ratio'] < 0.8:
                task['details'].setdefault('warnings', []).append({
                    'code': 'video_reconstruction_geometry_incomplete',
                    'message': 'Some video views could not be registered; inspect the reconstruction report.',
                })
        elif geometry_status == 'quality_failed':
            geometry_code = ERROR_GEOMETRY_INSUFFICIENT
            geometry_message = 'Too few video views were aligned reliably; training was stopped before spending more time.'
        elif geometry_status == 'cancelled':
            geometry_code, geometry_message = None, None
        else:
            geometry_code, geometry_message = build_failure_message(1, geometry_lines)
        if geometry_status == "cancelled":
            update_task(task_manager, task_id, status="cancelled", error=None)
            cleanup_failed()
            return
        if geometry_status != "ok":
            update_task(
                task_manager,
                task_id,
                status="failed",
                error=geometry_message,
                error_code=geometry_code,
            )
            cleanup_failed()
            return

        training_status, exported_ply, code, message = run_brush_training_stage(
            task_manager, task_id, task, job_dir, data_dir, train_dir, profile,
        )
        if training_status != 'ok':
            update_task(task_manager, task_id, status='cancelled' if training_status == 'cancelled' else 'failed',
                        error=message, error_code=code)
            cleanup_failed()
            return

        output_ply = exported_ply
        if should_apply_focused_cleanup(task):
            focused_ply = os.path.join(export_dir, "splat-focused.ply")
            object_focus = None
            if task.get("mode") == "object":
                object_focus = (
                    brush_engine.estimate_brush_object_focus(os.path.join(train_dir, 'dataset'))
                )
                if object_focus is None:
                    append_task_log(
                        task_manager,
                        task_id,
                        "Object focus could not be estimated from camera geometry; applying statistical cleanup only.",
                    )
            try:
                cleanup_stats = clean_gaussian_splat_ply(exported_ply, focused_ply, object_focus=object_focus)
                task.setdefault("details", {})["focused_cleanup"] = cleanup_stats
                output_ply = focused_ply
                if cleanup_stats.get("skipped"):
                    append_task_log(task_manager, task_id, "Focused cleanup skipped because it would remove too much geometry.")
                else:
                    if cleanup_stats.get("object_focus_applied"):
                        append_task_log(
                            task_manager,
                            task_id,
                            (
                                "Object focus crop kept "
                                f"{cleanup_stats['output_vertices']} / {cleanup_stats['input_vertices']} splats "
                                f"({cleanup_stats['keep_ratio']:.1%}) within radius "
                                f"{cleanup_stats['object_focus_radius']:.3f}."
                            ),
                        )
                    else:
                        append_task_log(
                            task_manager,
                            task_id,
                            (
                                "Focused cleanup kept "
                                f"{cleanup_stats['output_vertices']} / {cleanup_stats['input_vertices']} splats "
                                f"({cleanup_stats['keep_ratio']:.1%})."
                            ),
                        )
            except Exception as exc:
                output_ply = exported_ply
                details = task.setdefault("details", {})
                warnings = details.setdefault("warnings", [])
                warnings.append({
                    "code": "video_reconstruction_cleanup_failed",
                    "message": f"Focused cleanup failed; the raw export was kept. {exc}",
                })
                append_task_log(task_manager, task_id, f"Focused cleanup failed: {exc}")

        os.makedirs(task_manager.paths.output_folder, exist_ok=True)
        publish_video_ply(output_ply, task["output_path"])
        persist_video_model_assets(task_manager.paths, task)

        spz_error = None
        update_task(
            task_manager,
            task_id,
            progress=STAGE_PROGRESS["video_compress_spz"],
            stage="video_compress_spz",
        )
        try:
            task_manager.spz_converter(task["output_path"], task["spz_path"])
        except Exception as exc:
            spz_error = str(exc)
            append_task_log(task_manager, task_id, f"SPZ conversion failed: {spz_error}")

        if is_task_cancelled(task_manager, task_id):
            cleanup_failed()
            return

        update_task(
            task_manager,
            task_id,
            status="completed",
            progress=STAGE_PROGRESS["video_done"],
            stage="video_done",
            output_path=task["output_path"],
            spz_path=task["spz_path"] if os.path.exists(task["spz_path"]) else None,
            error=spz_error,
            error_code=ERROR_SPZ_FAILED if spz_error else None,
            completed_at=time.time(),
        )
        # 完成状态结算最后阶段耗时后再保存精简报告，清理帧图也不会丢失诊断。
        try:
            model_gallery.write_model_metadata(task_manager.paths, task['output_name'], build_video_model_metadata(task))
        except OSError as exc:
            runtime.log('WARN', f'Video task {task_id} could not save its final reconstruction report: {exc}')
        try:
            from backend.services import model_assets

            # 摘要写完再同步缓存，避免列表先读到 generation=None 的旧快照。
            model_assets.sync_generated_model_asset(task_manager.paths, task['output_name'])
        except Exception as exc:
            runtime.log('WARN', f'Model asset catalog sync failed after video task {task_id}: {exc}')
        clean_job_dir(job_dir, keep_intermediate)
    except video_geometry.InvalidVideoError as exc:
        update_task(task_manager, task_id, status='failed', error=str(exc), error_code=ERROR_INVALID_VIDEO)
        cleanup_failed()
    except Exception as exc:
        if is_task_cancelled(task_manager, task_id):
            update_task(task_manager, task_id, status="cancelled", error=None)
        else:
            error_text = traceback.format_exc()
            runtime.log("ERROR", f"Video task {task_id} exception traceback:\n{error_text}")
            update_task(task_manager, task_id, status="failed",
                        error='The video reconstruction failed unexpectedly. Inspect the local task logs.',
                        error_code='video_reconstruction_unexpected_failure')
        cleanup_failed()

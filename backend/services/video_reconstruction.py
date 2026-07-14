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
from urllib.parse import urlparse

from werkzeug.utils import secure_filename

from backend import runtime
from backend.config import get_video_reconstruction_config
from backend.services import model_gallery, photo_gallery
from backend.services.static_files import is_real_path_inside

TASK_KIND_VIDEO_3DGS = "video_3dgs"

VALID_RECONSTRUCTION_MODES = {"auto", "object", "environment"}
PRESET_RECONSTRUCTION_QUALITIES = {"preview", "high", "extreme"}
CUSTOM_RECONSTRUCTION_QUALITY = "custom"
VALID_RECONSTRUCTION_QUALITIES = PRESET_RECONSTRUCTION_QUALITIES | {CUSTOM_RECONSTRUCTION_QUALITY}
VALID_RECONSTRUCTION_ENGINES = {"auto", "stable"}
VALID_VRAM_BUDGETS = {"auto", "8gb", "12gb", "16gb", "24gb"}
VALID_MATCHING_METHODS = {"sequential", "exhaustive"}
VALID_CACHE_IMAGE_MODES = {"gpu", "cpu"}
VALID_DOWNSCALE_FACTORS = {1, 2, 4}

ERROR_DEPENDENCY_MISSING = "video_reconstruction_dependency_missing"
ERROR_DEPENDENCIES_CHECKING = "video_reconstruction_dependencies_checking"
ERROR_STABLE_UNAVAILABLE = "video_reconstruction_stable_unavailable"
ERROR_INVALID_REQUEST = "video_reconstruction_invalid_request"
ERROR_SOURCE_UNAVAILABLE = "video_reconstruction_source_unavailable"
ERROR_CANCELLED = "video_reconstruction_cancelled"
ERROR_OOM = "video_reconstruction_oom"
ERROR_OUTPUT_MISSING = "video_reconstruction_output_missing"
ERROR_SPZ_FAILED = "video_reconstruction_spz_failed"
ERROR_UNSUPPORTED_VIDEO = "video_reconstruction_unsupported_video"

# COLMAP 特征匹配策略按质量档绑定：
# - preview: sequential，只匹配相邻帧，最快，快速预览可接受偶尔断链；
# - high: exhaustive，180 帧两两匹配（~1.6 万对）最大化相机注册率，避免长视频
#   sequential 断链导致只重建前半段甚至相机过少崩溃，且无需联网下载词表；
# - extreme: exhaustive，与高质量档保持同一匹配策略，宁可增加 COLMAP 匹配耗时，
#   也优先保证注册完整性；词表检索在部分素材上可能配准过少，导致极致档反而
#   只重建极少视角。
# 自定义档由用户显式填写帧数、迭代、下采样、匹配方式和缓存位置；后端只做
# 范围校验与危险组合限制，不再把长视频方案伪装成一个通用预设。
QUALITY_PROFILES = {
    "preview": {
        "frame_count": 90,
        "max_resolution": 1280,
        "max_num_iterations": 7000,
        "num_downscales": 3,
        "downscale_factor": 4,
        "matching_method": "sequential",
        "train_cameras_sampling_strategy": "fps",
        "camera_optimizer_mode": "off",
        "num_random": 50000,
        "densify_grad_thresh": 0.0008,
        "cull_alpha_thresh": 0.1,
        "use_scale_regularization": False,
        "use_bilateral_grid": False,
        "cache_images": "gpu",
        "progress_weight": 0.18,
    },
    "high": {
        "frame_count": 180,
        "max_resolution": 1920,
        "max_num_iterations": 30000,
        "num_downscales": 2,
        "downscale_factor": 2,
        "matching_method": "exhaustive",
        "train_cameras_sampling_strategy": "fps",
        "camera_optimizer_mode": "SO3xR3",
        "num_random": 80000,
        "densify_grad_thresh": 0.00055,
        "cull_alpha_thresh": 0.04,
        "use_scale_regularization": True,
        "use_bilateral_grid": True,
        "cache_images": "gpu",
        "progress_weight": 0.45,
    },
    "extreme": {
        "frame_count": 360,
        "max_resolution": 2160,
        "max_num_iterations": 50000,
        "num_downscales": 1,
        "downscale_factor": 1,
        "matching_method": "exhaustive",
        "train_cameras_sampling_strategy": "fps",
        "camera_optimizer_mode": "SO3xR3",
        "num_random": 120000,
        "densify_grad_thresh": 0.0004,
        "cull_alpha_thresh": 0.02,
        "use_scale_regularization": True,
        "use_bilateral_grid": True,
        "cache_images": "cpu",
        "progress_weight": 0.72,
    },
}

CUSTOM_QUALITY_DEFAULTS = {
    "frame_count": 600,
    "max_num_iterations": 35000,
    "downscale_factor": 2,
    "matching_method": "sequential",
    "cache_images": "cpu",
}

CUSTOM_QUALITY_LIMITS = {
    "frame_count": (24, 1200),
    "max_num_iterations": (1000, 80000),
    "exhaustive_frame_count_max": 450,
}

CUSTOM_DOWNSCALE_MAX_RESOLUTION = {
    1: 2160,
    2: 1920,
    4: 1280,
}

FOCUSED_CLEANUP_PROFILE = {
    "position_quantiles": (5.0, 95.0),
    "alpha_min": 0.12,
    "scale_quantile": 98.5,
    "min_keep_ratio": 0.25,
    "min_vertices": 1000,
}

# Object-mode focus crop (C1): only applied when the user explicitly picks the
# "object" mode. Estimates the subject center/radius from the orbiting camera
# geometry and drops splats outside that sphere, removing far-away environment
# (walls, distant floor). auto / environment modes are never touched.
OBJECT_FOCUS = {
    "radius_factor": 0.55,   # subject radius ≈ median(camera-to-center distance) × factor
    "min_cameras": 8,        # need enough orbiting views to trust the geometry
    "min_keep_ratio": 0.1,   # if the sphere keeps less than this, abandon it (fall back to stats-only)
}

VRAM_PROFILE_LIMITS = {
    "auto": {
        "frame_scale": 1.0,
        "iteration_scale": 1.0,
        "max_resolution_cap": 1600,
    },
    "8gb": {
        "frame_scale": 0.72,
        "iteration_scale": 0.75,
        "max_resolution_cap": 1280,
    },
    "12gb": {
        "frame_scale": 1.0,
        "iteration_scale": 1.0,
        "max_resolution_cap": 1920,
    },
    "16gb": {
        "frame_scale": 1.18,
        "iteration_scale": 1.1,
        "max_resolution_cap": 1920,
    },
    "24gb": {
        "frame_scale": 1.35,
        "iteration_scale": 1.2,
        "max_resolution_cap": 2160,
    },
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
    "memoryerror",
)

TRAIN_VISUALIZER_VIEWER = "viewer"
TRAIN_VISUALIZER_FALLBACK = "tensorboard"

VISER_STARTUP_FAILURE_PATTERNS = (
    "psutil.nosuchprocess",
    "process no longer exists",
    "_client_autobuild",
    "ensure_client_is_built",
)

VIDEO_RUNTIME_PROCESS_TOKENS = (
    "ns-process-data",
    "ns-train",
    "ns-export",
    "colmap",
)

_DEPENDENCY_STATUS_LOCK = threading.Lock()
_DEPENDENCY_STATUS_CACHE = None
_DEPENDENCY_STATUS_CHECKED_AT = None
_DEPENDENCY_STATUS_REFRESHING = False


def _local_video_reconstruction_paths():
    root = Path(__file__).resolve().parents[2]
    local_env = root / ".video-reconstruction-env"
    return (
        local_env / "portable-bin",
        local_env / "Scripts",
        local_env / "colmap" / "bin",
    )


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


def find_existing_path(candidates):
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def find_cuda_home():
    configured = os.environ.get("CUDA_HOME") or os.environ.get("CUDA_PATH")
    candidates = [
        configured,
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9",
    ]
    return find_existing_path(candidates)


def find_vcvars64():
    candidates = [
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
    ]
    return find_existing_path(candidates)


def read_vcvars_environment():
    vcvars = find_vcvars64()
    if not vcvars:
        return {}

    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".cmd",
            delete=False,
            encoding="utf-8",
            newline="\r\n",
        ) as script:
            script.write("@echo off\n")
            script.write(f'call "{vcvars}" >nul\n')
            script.write("set\n")
            script_path = script.name

        result = subprocess.run(
            ["cmd.exe", "/d", "/c", script_path],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception:
        return {}
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    if result.returncode != 0:
        return {}

    env = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    return env


def build_video_process_env():
    ensure_local_video_reconstruction_path()

    process_env = os.environ.copy()
    vc_env = read_vcvars_environment()
    if vc_env:
        process_env.update(vc_env)
        for path_key in ("PATH", "Path", "path"):
            if vc_env.get(path_key):
                process_env["PATH"] = vc_env[path_key]
                break

    path_candidates = list(_local_video_reconstruction_paths())

    cuda_home = find_cuda_home()
    if cuda_home:
        process_env["CUDA_HOME"] = cuda_home
        process_env["CUDA_PATH"] = cuda_home
        cuda_bin = os.path.join(cuda_home, "bin")
        if os.path.exists(cuda_bin):
            path_candidates.append(Path(cuda_bin))

    process_env["PATH"] = _prepend_existing_path_entries(
        process_env.get("PATH", ""),
        path_candidates,
    )
    if os.name == "nt":
        process_env["Path"] = process_env["PATH"]
    process_env.setdefault("PYTHONUTF8", "1")
    process_env.setdefault("PYTHONIOENCODING", "utf-8")
    process_env.setdefault("TORCH_CUDA_ARCH_LIST", "12.0")
    process_env.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
    process_env.setdefault("VSLANG", "1033")
    return process_env


def normalize_video_reconstruction_settings(value):
    raw = value if isinstance(value, dict) else {}
    defaults = get_video_reconstruction_config(persist_missing=False)
    quality = raw.get("default_quality")
    engine = raw.get("default_engine")
    vram_budget = raw.get("vram_budget")

    return {
        "default_quality": quality if quality in PRESET_RECONSTRUCTION_QUALITIES else defaults["default_quality"],
        "default_engine": engine if engine in VALID_RECONSTRUCTION_ENGINES else defaults["default_engine"],
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


def normalize_custom_quality_options(value):
    options = parse_custom_options_value(value)
    if options is None:
        return None, {
            "error": "custom_options must be an object",
            "code": ERROR_INVALID_REQUEST,
            "field": "custom_options",
        }

    frame_min, frame_max = CUSTOM_QUALITY_LIMITS["frame_count"]
    frame_count, error = coerce_custom_int(
        options,
        "frame_count",
        CUSTOM_QUALITY_DEFAULTS["frame_count"],
        frame_min,
        frame_max,
    )
    if error:
        return None, error

    iter_min, iter_max = CUSTOM_QUALITY_LIMITS["max_num_iterations"]
    max_num_iterations, error = coerce_custom_int(
        options,
        "max_num_iterations",
        CUSTOM_QUALITY_DEFAULTS["max_num_iterations"],
        iter_min,
        iter_max,
    )
    if error:
        return None, error

    downscale_factor, error = coerce_custom_int(
        options,
        "downscale_factor",
        CUSTOM_QUALITY_DEFAULTS["downscale_factor"],
        min(VALID_DOWNSCALE_FACTORS),
        max(VALID_DOWNSCALE_FACTORS),
    )
    if error:
        return None, error
    if downscale_factor not in VALID_DOWNSCALE_FACTORS:
        return None, {
            "error": "downscale_factor must be 1, 2, or 4",
            "code": ERROR_INVALID_REQUEST,
            "field": "custom_options.downscale_factor",
        }

    matching_method = str(options.get("matching_method", CUSTOM_QUALITY_DEFAULTS["matching_method"])).strip().lower()
    if matching_method not in VALID_MATCHING_METHODS:
        return None, {
            "error": "matching_method must be sequential or exhaustive",
            "code": ERROR_INVALID_REQUEST,
            "field": "custom_options.matching_method",
        }

    if (
        matching_method == "exhaustive"
        and frame_count > CUSTOM_QUALITY_LIMITS["exhaustive_frame_count_max"]
    ):
        return None, {
            "error": "exhaustive matching is limited to 450 custom frames",
            "code": ERROR_INVALID_REQUEST,
            "field": "custom_options.frame_count",
        }

    cache_images = str(options.get("cache_images", CUSTOM_QUALITY_DEFAULTS["cache_images"])).strip().lower()
    if cache_images not in VALID_CACHE_IMAGE_MODES:
        return None, {
            "error": "cache_images must be gpu or cpu",
            "code": ERROR_INVALID_REQUEST,
            "field": "custom_options.cache_images",
        }

    return {
        "frame_count": frame_count,
        "max_num_iterations": max_num_iterations,
        "downscale_factor": downscale_factor,
        "matching_method": matching_method,
        "cache_images": cache_images,
    }, None


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
        custom_options, custom_error = normalize_custom_quality_options(data.get("custom_options"))
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


def build_custom_quality_profile(custom_options, vram_budget):
    options, error = normalize_custom_quality_options(custom_options)
    if error:
        options = dict(CUSTOM_QUALITY_DEFAULTS)

    downscale_factor = options["downscale_factor"]
    max_resolution = CUSTOM_DOWNSCALE_MAX_RESOLUTION[downscale_factor]
    num_random = 120000 if downscale_factor == 1 else 90000 if options["frame_count"] >= 360 else 80000

    return {
        "frame_count": options["frame_count"],
        "max_resolution": max_resolution,
        "max_num_iterations": options["max_num_iterations"],
        "num_downscales": downscale_factor_to_num_downscales(downscale_factor),
        "downscale_factor": downscale_factor,
        "matching_method": options["matching_method"],
        "train_cameras_sampling_strategy": "fps",
        "camera_optimizer_mode": "SO3xR3",
        "num_random": num_random,
        "densify_grad_thresh": 0.00055,
        "cull_alpha_thresh": 0.04,
        "use_scale_regularization": True,
        "use_bilateral_grid": True,
        "cache_images": options["cache_images"],
        "progress_weight": 0.58,
        "vram_budget": vram_budget if vram_budget in VRAM_PROFILE_LIMITS else "auto",
        "custom_options": options,
    }


def resolve_quality_profile(quality, vram_budget, custom_options=None):
    if quality == CUSTOM_RECONSTRUCTION_QUALITY:
        return build_custom_quality_profile(custom_options, vram_budget)

    base = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["high"])
    limits = VRAM_PROFILE_LIMITS.get(vram_budget, VRAM_PROFILE_LIMITS["auto"])

    frame_count = max(24, int(round(base["frame_count"] * limits["frame_scale"])))
    max_iterations = max(1000, int(round(base["max_num_iterations"] * limits["iteration_scale"])))
    max_resolution = min(base["max_resolution"], limits["max_resolution_cap"])
    downscale_factor = resolve_downscale_factor(base["downscale_factor"], max_resolution)
    num_downscales = max(base["num_downscales"], downscale_factor_to_num_downscales(downscale_factor))

    return {
        **base,
        "frame_count": frame_count,
        "max_num_iterations": max_iterations,
        "max_resolution": max_resolution,
        "downscale_factor": downscale_factor,
        "num_downscales": num_downscales,
        "vram_budget": vram_budget if vram_budget in VRAM_PROFILE_LIMITS else "auto",
    }


def resolve_downscale_factor(base_downscale_factor, max_resolution):
    downscale_factor = max(1, int(base_downscale_factor))
    if max_resolution <= 1280:
        return max(downscale_factor, 4)
    if max_resolution <= 1920:
        return max(downscale_factor, 2)
    return downscale_factor


def downscale_factor_to_num_downscales(downscale_factor):
    downscale_factor = max(1, int(downscale_factor))
    num_downscales = 0
    generated_factor = 1
    while generated_factor < downscale_factor:
        generated_factor *= 2
        num_downscales += 1
    return num_downscales


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


def resolve_video_python():
    """Return the Python executable that hosts the video reconstruction env."""
    local_env = Path(__file__).resolve().parents[2] / ".video-reconstruction-env"
    candidates = [
        local_env / "Scripts" / "python.exe",
        local_env / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return which("python") or which("python3") or "python"


def _decorate_dependency_status(dependencies, *, checked_at, refreshing, cached):
    result = copy.deepcopy(dependencies)
    summary = result.setdefault("summary", {})
    summary["checking"] = bool(refreshing)
    summary["checked_at"] = checked_at
    summary["cached"] = bool(cached)
    return result


def _pending_dependency_status():
    message = "Video reconstruction tools are being checked in the background."
    return {
        "required": {
            "available": False,
            "tools": [],
            "message": message,
        },
        "stable": {
            "available": False,
            "tools": [],
            "message": message,
        },
        "summary": {
            "available": False,
            "stable_available": False,
            "checking": True,
            "checked_at": None,
            "cached": False,
        },
    }


def _dependency_error_status(exc):
    message = f"Failed to check video reconstruction tools: {exc}"
    return {
        "required": {
            "available": False,
            "tools": [],
            "message": message,
        },
        "stable": {
            "available": False,
            "tools": [],
            "message": message,
        },
        "summary": {
            "available": False,
            "stable_available": False,
        },
    }


def _scan_dependencies():
    ensure_local_video_reconstruction_path()

    ffmpeg = command_version("ffmpeg")
    ffprobe = command_version("ffprobe")

    ns_process_data = command_version("ns-process-data", ["--help"], timeout=30)
    ns_train = command_version("ns-train", ["--help"], timeout=30)
    ns_export = command_version("ns-export", ["--help"], timeout=30)
    colmap = command_version("colmap", ["-h"], timeout=10)
    stable_tools = [ns_process_data, ns_train, ns_export, colmap]
    for tool in stable_tools:
        tool["category"] = "stable"
        tool["required"] = True

    required_tools = [ffmpeg, ffprobe]
    stable_available = all(tool["available"] for tool in stable_tools)
    required_available = all(tool["available"] for tool in required_tools)

    return {
        "required": {
            "available": required_available,
            "tools": required_tools,
            "message": None if required_available else "ffmpeg and ffprobe are required for video decoding.",
        },
        "stable": {
            "available": required_available and stable_available,
            "tools": stable_tools,
            "message": None if stable_available else "Nerfstudio CLI tools and COLMAP are required for the stable Splatfacto route.",
        },
        "summary": {
            "available": required_available and stable_available,
            "stable_available": required_available and stable_available,
        },
    }


def resolve_engine_strategy(engine, dependencies=None):
    dependencies = dependencies or check_dependencies()
    stable_available = bool(dependencies["stable"]["available"])

    if engine in {"auto", "stable"}:
        if not stable_available:
            return None, ERROR_DEPENDENCY_MISSING
        return "stable", None

    return None, ERROR_INVALID_REQUEST


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
        if not os.path.exists(ply_path) and not os.path.exists(spz_path):
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

    task_payload = {
        "kind": TASK_KIND_VIDEO_3DGS,
        "filename": f"{output_name}.ply",
        "source_media_id": request_data["video_id"],
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

    task_payload = {
        "kind": TASK_KIND_VIDEO_3DGS,
        "filename": f"{output_name}.ply",
        "source_media_id": None,
        "source_name": source_name,
        "source_video_path": source_video_path,
        "source_mime_type": uploaded_file.mimetype,
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
    return {
        "source_media_type": "video",
        "source_media_id": task.get("source_media_id"),
        "source_name": task.get("source_name"),
        "source_video_path": task.get("source_video_path"),
        "source_mime_type": task.get("source_mime_type"),
        "generator": TASK_KIND_VIDEO_3DGS,
        "mode": task.get("mode"),
        "quality": task.get("quality"),
        "custom_options": task.get("custom_options"),
        "engine": task.get("engine"),
        "resolved_engine": task.get("resolved_engine"),
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
                    prev_stage_duration = now - stage_started
                    durations = task.setdefault("details", {}).setdefault("stage_durations", {})
                    durations[previous_stage] = round(prev_stage_duration, 1)
                task["stage_started_at"] = now
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


def wait_for_process(task_manager, task_id, process, output_lines, stage=None, profile=None, last_output=None):
    cancelled = False
    last_reported_progress = None
    viewer_url_logged = False
    for line in iter(process.stdout.readline, ""):
        if not line:
            break
        if last_output is not None:
            last_output[0] = time.time()
        output_lines.append(line)
        append_task_log(task_manager, task_id, line)
        if stage == "video_optimize":
            if not viewer_url_logged:
                viewer_url, viewer_port = parse_viewer_url(line)
                if viewer_url:
                    viewer_url_logged = True
                    if set_task_viewer_endpoint(task_manager, task_id, viewer_url, viewer_port):
                        port_hint = f":{viewer_port}" if viewer_port else ""
                        runtime.log(
                            "INFO",
                            f"Video task {task_id} live viewer available at {viewer_url} "
                            f"(LAN clients: open http://<this-machine-ip>{port_hint})",
                        )
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


TRAIN_STEP_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
TRAIN_PERCENT_PATTERN = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*%\s*\)")
VIEWER_URL_PATTERN = re.compile(r"https?://[^\s'\"\]\)]+")


def parse_training_progress(line, profile):
    """Map a Nerfstudio training log line into the optimize progress band.

    Nerfstudio's local writer prints a periodic table whose data rows look like
    ``2980 (9.93%)``; some setups instead emit ``step/total``. We trust the
    percentage form first, then fall back to ``step/total`` when the denominator
    matches the configured iteration count. Returns an integer percentage within
    [video_optimize, video_export), or None when the line carries no progress.
    """
    max_iter = int(profile.get("max_num_iterations") or 0)
    if max_iter <= 0:
        return None

    ratio = None
    percent_matches = TRAIN_PERCENT_PATTERN.findall(line)
    if percent_matches:
        try:
            percent = float(percent_matches[-1])
        except ValueError:
            percent = None
        if percent is not None and 0.0 <= percent <= 100.0:
            ratio = percent / 100.0

    if ratio is None:
        step = None
        for match in TRAIN_STEP_PATTERN.finditer(line):
            if int(match.group(2)) == max_iter:
                step = int(match.group(1))
        if step is not None:
            ratio = step / max_iter

    if ratio is None:
        return None

    ratio = min(1.0, max(0.0, ratio))
    base = STAGE_PROGRESS["video_optimize"]
    ceiling = STAGE_PROGRESS["video_export"]
    return int(base + (ceiling - base) * ratio)


def parse_viewer_url(line):
    """Extract the Nerfstudio/viser live viewer URL from a training log line.

    The viewer is the most reliable real-time progress source, so surface it as
    soon as the trainer prints it. ``0.0.0.0`` is rewritten to ``localhost`` for a
    readable, locally-openable display URL, but the listening port is returned
    separately so the frontend can rebuild the URL against whichever host the
    user actually reached Sharp GUI on (works for LAN clients, not just local).
    Returns ``(display_url, port)`` or ``(None, None)``.
    """
    lowered = line.lower()
    if "http://" not in lowered and "https://" not in lowered:
        return None, None
    for match in VIEWER_URL_PATTERN.finditer(line):
        url = match.group(0).rstrip(".,)]'\"")
        low = url.lower()
        if any(token in low for token in ("localhost", "127.0.0.1", "0.0.0.0", "nerf.studio", "viewer")):
            display_url = url.replace("0.0.0.0", "localhost")
            try:
                port = urlparse(url).port
            except ValueError:
                port = None
            return display_url, port
    return None, None


def set_task_viewer_endpoint(task_manager, task_id, url, port=None):
    with task_manager.task_lock:
        task = task_manager.task_status.get(task_id)
        if not task:
            return False
        details = task.setdefault("details", {})
        if details.get("viewer_url") == url and details.get("viewer_port") == port:
            return False
        details["viewer_url"] = url
        if port is not None:
            details["viewer_port"] = port
        return True


def terminate_process_tree(process):
    """Terminate the process and its children so GPU workers don't leak.

    ns-train / ns-process-data can spawn child processes (and a viewer); a plain
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

    Steps like ns-process-data (frame extraction + COLMAP) can run for minutes
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
    if stage:
        update_task(task_manager, task_id, stage=stage, progress=progress or STAGE_PROGRESS.get(stage, 0))

    process_env = build_video_process_env()
    command_name = Path(str(cmd[0])).name if cmd else "command"

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
        cmd,
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
    try:
        return_code, cancelled = wait_for_process(
            task_manager,
            task_id,
            process,
            output_lines,
            stage=stage,
            profile=profile,
            last_output=last_output,
        )
    finally:
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


def contains_oom(text):
    normalized = (text or "").lower()
    return any(pattern in normalized for pattern in OOM_PATTERNS)


def is_viewer_startup_failure(output_lines):
    normalized = "\n".join(str(line or "") for line in (output_lines or [])).lower()
    return (
        "viser" in normalized
        and ("viewerstate" in normalized or "viserserver" in normalized or "viewer.py" in normalized)
        and any(pattern in normalized for pattern in VISER_STARTUP_FAILURE_PATTERNS)
    )


def should_retry_train_without_viewer(visualizer, output_lines):
    return visualizer == TRAIN_VISUALIZER_VIEWER and is_viewer_startup_failure(output_lines)


def build_failure_message(return_code, output_lines):
    output = "".join(output_lines or [])
    tail = "\n".join(output.splitlines()[-24:])
    if contains_oom(output):
        return ERROR_OOM, (
            "GPU memory is not enough for this reconstruction. "
            "Try a lower quality preset, fewer frames, or lower resolution."
        )
    return None, tail or f"Command failed with return code {return_code}"


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


def find_exported_ply(export_dir):
    candidates = sorted(Path(export_dir).rglob("*.ply"), key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else None


def should_apply_focused_cleanup(task):
    return task.get("mode") != "environment"


def _find_dataparser_transforms(train_dir):
    candidates = sorted(
        Path(train_dir).rglob("dataparser_transforms.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return str(candidates[0]) if candidates else None


def estimate_object_focus(train_dir, data_dir):
    """Estimate subject center/radius in the exported splat's coordinate frame.

    Object videos orbit a central subject, so the look-at rays of all cameras
    converge near the subject. We intersect those rays (least squares) to locate
    the subject, and size a sphere from the median camera distance. Camera poses
    come from ``transforms.json`` (original COLMAP frame) and are mapped into the
    Nerfstudio training frame via ``dataparser_transforms.json`` so they line up
    with the exported ``.ply``. Returns ``(center_xyz, radius)`` or ``None`` when
    it cannot be estimated safely (caller then skips the focus crop).
    """
    import numpy as np

    try:
        transforms_path = os.path.join(data_dir, "transforms.json")
        with open(transforms_path, "r", encoding="utf-8") as file:
            transforms = json.load(file)
        frames = transforms.get("frames")
        if not isinstance(frames, list) or len(frames) < OBJECT_FOCUS["min_cameras"]:
            return None

        dataparser_path = _find_dataparser_transforms(train_dir)
        if not dataparser_path:
            return None
        with open(dataparser_path, "r", encoding="utf-8") as file:
            dataparser = json.load(file)
        transform = np.asarray(dataparser.get("transform"), dtype=np.float64)
        scale = float(dataparser.get("scale", 1.0))
        if transform.shape != (3, 4) or not np.isfinite(scale) or scale <= 0:
            return None
        rotation = transform[:3, :3]
        translation = transform[:3, 3]

        origins = []
        directions = []
        for frame in frames:
            matrix = frame.get("transform_matrix")
            if not isinstance(matrix, list):
                continue
            c2w = np.asarray(matrix, dtype=np.float64)
            if c2w.shape != (4, 4):
                continue
            position = scale * (rotation @ c2w[:3, 3] + translation)
            look = rotation @ (-c2w[:3, 2])
            norm = np.linalg.norm(look)
            if not np.isfinite(position).all() or not np.isfinite(norm) or norm < 1e-8:
                continue
            origins.append(position)
            directions.append(look / norm)

        if len(origins) < OBJECT_FOCUS["min_cameras"]:
            return None
        origins = np.asarray(origins)
        directions = np.asarray(directions)

        identity = np.eye(3)
        a_matrix = np.zeros((3, 3))
        b_vector = np.zeros(3)
        for origin, direction in zip(origins, directions):
            projector = identity - np.outer(direction, direction)
            a_matrix += projector
            b_vector += projector @ origin
        center = np.linalg.solve(a_matrix, b_vector)
        if not np.isfinite(center).all():
            return None

        camera_distances = np.linalg.norm(origins - center, axis=1)
        median_distance = float(np.median(camera_distances))
        if not np.isfinite(median_distance) or median_distance <= 0:
            return None
        # Sanity: the converged center should sit inside the camera cloud.
        if np.linalg.norm(center - origins.mean(axis=0)) > 2.0 * median_distance:
            return None

        radius = median_distance * OBJECT_FOCUS["radius_factor"]
        return center.astype(np.float64), float(radius)
    except Exception:
        return None


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
            if candidate_count >= cleanup_profile["min_vertices"] and candidate_ratio >= OBJECT_FOCUS["min_keep_ratio"]:
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
        OBJECT_FOCUS["min_keep_ratio"] if object_focus_applied else cleanup_profile["min_keep_ratio"]
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


def build_process_data_command(source_video_path, data_dir, profile):
    return [
        "ns-process-data",
        "video",
        "--data",
        source_video_path,
        "--output-dir",
        data_dir,
        "--num-frames-target",
        str(profile["frame_count"]),
        "--num-downscales",
        str(profile["num_downscales"]),
        "--matching-method",
        profile["matching_method"],
    ]


def run_colmap_geometry_stage(task_manager, task_id, task, job_dir, data_dir, profile):
    """运行现有 COLMAP 几何阶段（ns-process-data）。返回 (status, code, message)。"""
    process_cmd = build_process_data_command(task["source_video_path"], data_dir, profile)
    return_code, output_lines, cancelled = run_command(
        task_manager,
        task_id,
        process_cmd,
        cwd=job_dir,
        stage="video_extract_frames",
        progress=STAGE_PROGRESS["video_extract_frames"],
    )
    if cancelled or is_task_cancelled(task_manager, task_id):
        return "cancelled", None, None
    if return_code != 0:
        code, message = build_failure_message(return_code, output_lines)
        return "failed", code, message
    return "ok", None, None


def run_geometry_stage(task_manager, task_id, task, job_dir, data_dir, profile):
    """Run the stable COLMAP geometry stage and return (status, code, message)."""
    details = task.setdefault("details", {})
    details["geometry_engine"] = "colmap"
    return run_colmap_geometry_stage(task_manager, task_id, task, job_dir, data_dir, profile)


def build_train_command(data_dir, output_dir, profile, visualizer=TRAIN_VISUALIZER_VIEWER):
    return [
        "ns-train",
        "splatfacto",
        "--output-dir",
        output_dir,
        "--max-num-iterations",
        str(profile["max_num_iterations"]),
        "--vis",
        visualizer,
        "--viewer.quit-on-train-completion",
        "True",
        "--pipeline.datamanager.train-cameras-sampling-strategy",
        profile["train_cameras_sampling_strategy"],
        "--pipeline.model.camera-optimizer.mode",
        profile["camera_optimizer_mode"],
        "--pipeline.model.num-random",
        str(profile["num_random"]),
        "--pipeline.model.densify-grad-thresh",
        str(profile["densify_grad_thresh"]),
        "--pipeline.model.cull-alpha-thresh",
        str(profile["cull_alpha_thresh"]),
        "--pipeline.model.use-scale-regularization",
        str(profile["use_scale_regularization"]),
        "--pipeline.model.use-bilateral-grid",
        str(profile["use_bilateral_grid"]),
        "--pipeline.datamanager.cache-images",
        profile["cache_images"],
        "nerfstudio-data",
        "--data",
        data_dir,
        "--downscale-factor",
        str(profile["downscale_factor"]),
    ]


def build_export_command(config_path, export_dir):
    return [
        "ns-export",
        "gaussian-splat",
        "--load-config",
        config_path,
        "--output-dir",
        export_dir,
    ]


def find_nerfstudio_config(train_dir):
    candidates = sorted(Path(train_dir).rglob("config.yml"), key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else None


# Nerfstudio's FPS camera sampling uses fpsample bucket_fps_kdline_sampling with
# h=3, which asserts 2**3 <= number_of_cameras. After the train/eval split the
# usable count is even smaller, so when COLMAP only registers a handful of
# cameras the trainer crashes with "2**h should be <= n_pts". Below this
# conservative threshold we fall back to random sampling, which has no such
# requirement, instead of letting the whole task fail.
FPS_MIN_REGISTERED_FRAMES = 16


def count_registered_frames(data_dir):
    """Return the number of cameras COLMAP registered in transforms.json, or None."""
    transforms_path = os.path.join(data_dir, "transforms.json")
    try:
        with open(transforms_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return None
    frames = data.get("frames") if isinstance(data, dict) else None
    return len(frames) if isinstance(frames, list) else None


def resolve_training_profile(profile, data_dir, task_manager=None, task_id=None, task=None):
    """Downgrade FPS camera sampling to random when too few cameras registered."""
    if profile.get("train_cameras_sampling_strategy") != "fps":
        return profile

    registered = count_registered_frames(data_dir)
    if registered is None or registered >= FPS_MIN_REGISTERED_FRAMES:
        return profile

    adjusted = {**profile, "train_cameras_sampling_strategy": "random"}
    message = (
        f"Only {registered} cameras were registered; using random camera sampling "
        "instead of FPS to avoid a sampling assertion. Reconstruction quality may be "
        "limited with so few views."
    )
    if task_manager is not None and task_id is not None:
        append_task_log(task_manager, task_id, message)
    if isinstance(task, dict):
        task.setdefault("details", {})["camera_sampling_fallback"] = {
            "registered_frames": registered,
            "strategy": "random",
        }
    return adjusted


def add_object_mode_warning(task):
    details = task.setdefault("details", {})
    warnings = details.setdefault("warnings", [])
    warning = {
        "code": "video_reconstruction_object_foreground_degraded",
        "message": "Automatic foreground segmentation is not configured; object mode will run without masks.",
    }
    if warning not in warnings:
        warnings.append(warning)


def record_train_visualizer_fallback(task, from_visualizer, to_visualizer, reason):
    details = task.setdefault("details", {})
    details["train_visualizer_fallback"] = {
        "from": from_visualizer,
        "to": to_visualizer,
        "reason": reason,
    }
    warnings = details.setdefault("warnings", [])
    warning = {
        "code": "video_reconstruction_viewer_disabled",
        "message": (
            "Nerfstudio's live viewer failed to start on this machine; "
            "retrying training without the viewer."
        ),
    }
    if warning not in warnings:
        warnings.append(warning)


def run_video_reconstruction_task(task_manager, task_id, task):
    job_dir = os.path.join(task_manager.paths.video_reconstruction_jobs_folder, task_id)
    source_dir = os.path.join(job_dir, "source")
    data_dir = os.path.join(job_dir, "nerfstudio-data")
    train_dir = os.path.join(job_dir, "train")
    export_dir = os.path.join(job_dir, "export")
    logs_dir = os.path.join(job_dir, "logs")
    keep_intermediate = bool(task.get("keep_intermediate_files"))
    profile = resolve_quality_profile(
        task.get("quality"),
        task.get("vram_budget"),
        task.get("custom_options"),
    )
    task.setdefault("details", {})["resource_profile"] = profile

    def cleanup_failed():
        cleanup_failed_task_artifacts(task_manager.paths, task, job_dir, keep_intermediate)

    for folder in (source_dir, data_dir, train_dir, export_dir, logs_dir):
        os.makedirs(folder, exist_ok=True)

    try:
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

        geometry_status, geometry_code, geometry_message = run_geometry_stage(
            task_manager, task_id, task, job_dir, data_dir, profile
        )
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

        training_profile = resolve_training_profile(
            profile,
            data_dir,
            task_manager=task_manager,
            task_id=task_id,
            task=task,
        )
        train_visualizer = TRAIN_VISUALIZER_VIEWER
        train_cmd = build_train_command(data_dir, train_dir, training_profile, visualizer=train_visualizer)
        return_code, output_lines, cancelled = run_command(
            task_manager,
            task_id,
            train_cmd,
            cwd=job_dir,
            stage="video_optimize",
            progress=STAGE_PROGRESS["video_optimize"],
            profile=training_profile,
        )
        if cancelled:
            update_task(task_manager, task_id, status="cancelled", error=None)
            cleanup_failed()
            return
        if is_task_cancelled(task_manager, task_id):
            update_task(task_manager, task_id, status="cancelled", error=None)
            cleanup_failed()
            return
        if return_code != 0 and should_retry_train_without_viewer(train_visualizer, output_lines):
            fallback_visualizer = TRAIN_VISUALIZER_FALLBACK
            record_train_visualizer_fallback(
                task,
                train_visualizer,
                fallback_visualizer,
                "viser_startup_failed",
            )
            append_task_log(
                task_manager,
                task_id,
                (
                    "Nerfstudio viewer failed during startup; "
                    f"retrying ns-train with --vis {fallback_visualizer}."
                ),
            )
            runtime.log(
                "WARN",
                "Video task "
                f"{task_id} retrying ns-train with --vis {fallback_visualizer} "
                "because the Viser live viewer failed to start.",
            )
            shutil.rmtree(train_dir, ignore_errors=True)
            os.makedirs(train_dir, exist_ok=True)
            train_visualizer = fallback_visualizer
            train_cmd = build_train_command(
                data_dir,
                train_dir,
                training_profile,
                visualizer=train_visualizer,
            )
            return_code, output_lines, cancelled = run_command(
                task_manager,
                task_id,
                train_cmd,
                cwd=job_dir,
                stage="video_optimize",
                progress=STAGE_PROGRESS["video_optimize"],
                profile=training_profile,
            )
            if cancelled:
                update_task(task_manager, task_id, status="cancelled", error=None)
                cleanup_failed()
                return
            if is_task_cancelled(task_manager, task_id):
                update_task(task_manager, task_id, status="cancelled", error=None)
                cleanup_failed()
                return
        if return_code != 0:
            code, message = build_failure_message(return_code, output_lines)
            update_task(task_manager, task_id, status="failed", error=message, error_code=code)
            cleanup_failed()
            return

        config_path = find_nerfstudio_config(train_dir)
        if not config_path:
            update_task(
                task_manager,
                task_id,
                status="failed",
                error="Nerfstudio training finished but config.yml was not found.",
                error_code=ERROR_OUTPUT_MISSING,
            )
            cleanup_failed()
            return

        return_code, output_lines, cancelled = run_command(
            task_manager,
            task_id,
            build_export_command(config_path, export_dir),
            cwd=job_dir,
            stage="video_export",
            progress=STAGE_PROGRESS["video_export"],
        )
        if cancelled:
            update_task(task_manager, task_id, status="cancelled", error=None)
            cleanup_failed()
            return
        if is_task_cancelled(task_manager, task_id):
            update_task(task_manager, task_id, status="cancelled", error=None)
            cleanup_failed()
            return
        if return_code != 0:
            code, message = build_failure_message(return_code, output_lines)
            update_task(task_manager, task_id, status="failed", error=message, error_code=code)
            cleanup_failed()
            return

        exported_ply = find_exported_ply(export_dir)
        if not exported_ply:
            update_task(
                task_manager,
                task_id,
                status="failed",
                error="Nerfstudio export finished but no .ply file was found.",
                error_code=ERROR_OUTPUT_MISSING,
            )
            cleanup_failed()
            return

        output_ply = exported_ply
        if should_apply_focused_cleanup(task):
            focused_ply = os.path.join(export_dir, "splat-focused.ply")
            object_focus = None
            if task.get("mode") == "object":
                object_focus = estimate_object_focus(train_dir, data_dir)
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
        shutil.copy2(output_ply, task["output_path"])
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
        clean_job_dir(job_dir, keep_intermediate)
    except Exception as exc:
        if is_task_cancelled(task_manager, task_id):
            update_task(task_manager, task_id, status="cancelled", error=None)
        else:
            error_text = traceback.format_exc()
            runtime.log("ERROR", f"Video task {task_id} exception traceback:\n{error_text}")
            update_task(task_manager, task_id, status="failed", error=error_text)
        cleanup_failed()

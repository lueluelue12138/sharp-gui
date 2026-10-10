import json
import os
import secrets

from backend import runtime


def load_config():
    """加载配置文件。"""
    config_file = runtime.get_config_file()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                if "workspace_folder" not in config and "input_folder" in config:
                    old_input = config.get("input_folder", "")
                    if old_input.endswith("/inputs") or old_input.endswith("\\inputs"):
                        config["workspace_folder"] = os.path.dirname(old_input)
                    else:
                        config["workspace_folder"] = runtime.DEFAULT_WORKSPACE_FOLDER
                return config
        except Exception:
            pass
    return {"workspace_folder": runtime.DEFAULT_WORKSPACE_FOLDER}


def save_config(config):
    """保存配置文件。"""
    config_file = runtime.get_config_file()
    config_dir = os.path.dirname(config_file)
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_default_access_control_config():
    return {
        "enabled": False,
        "password_hash": "",
        "session_secret": "",
        "session_days": 30,
        "allow_localhost_bypass": True,
        "allow_remote_generation": False,
        "session_version": 1,
        "lan_bind_enabled": True,
    }


def get_default_video_reconstruction_config():
    return {
        "default_quality": "high",
        "default_engine": "brush",
        "vram_budget": "12gb",
        "keep_intermediate_files": False,
    }


def coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def coerce_int(value, default, minimum=None, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def normalize_access_control_config(current_config):
    defaults = get_default_access_control_config()
    raw = current_config.get("access_control")
    changed = False

    if not isinstance(raw, dict):
        raw = {}
        changed = True

    normalized = {
        "enabled": coerce_bool(raw.get("enabled"), defaults["enabled"]),
        "password_hash": raw.get("password_hash") if isinstance(raw.get("password_hash"), str) else "",
        "session_secret": raw.get("session_secret") if isinstance(raw.get("session_secret"), str) else "",
        "session_days": coerce_int(raw.get("session_days"), defaults["session_days"], 1, 365),
        "allow_localhost_bypass": coerce_bool(
            raw.get("allow_localhost_bypass"),
            defaults["allow_localhost_bypass"],
        ),
        "allow_remote_generation": coerce_bool(
            raw.get("allow_remote_generation"),
            defaults["allow_remote_generation"],
        ),
        "session_version": coerce_int(raw.get("session_version"), defaults["session_version"], 1),
        "lan_bind_enabled": coerce_bool(raw.get("lan_bind_enabled"), defaults["lan_bind_enabled"]),
    }

    if not normalized["session_secret"]:
        normalized["session_secret"] = secrets.token_urlsafe(32)
        changed = True

    for key, value in normalized.items():
        if raw.get(key) != value:
            changed = True
            break

    current_config["access_control"] = normalized
    return normalized, changed


def normalize_video_reconstruction_config(current_config):
    defaults = get_default_video_reconstruction_config()
    raw = current_config.get("video_reconstruction")
    changed = False

    if not isinstance(raw, dict):
        raw = {}
        changed = True

    default_quality = raw.get("default_quality")
    if default_quality not in {"preview", "high", "extreme"}:
        default_quality = defaults["default_quality"]

    # 已保存的旧引擎选择统一迁移到当前视频路线。
    default_engine = "brush"

    vram_budget = raw.get("vram_budget")
    if not isinstance(vram_budget, str) or not vram_budget.strip():
        vram_budget = defaults["vram_budget"]
    else:
        vram_budget = vram_budget.strip().lower()
        if vram_budget not in {"auto", "8gb", "12gb", "16gb", "24gb"}:
            vram_budget = defaults["vram_budget"]

    normalized = {
        "default_quality": default_quality,
        "default_engine": default_engine,
        "vram_budget": vram_budget,
        "keep_intermediate_files": coerce_bool(
            raw.get("keep_intermediate_files"),
            defaults["keep_intermediate_files"],
        ),
    }

    for key, value in normalized.items():
        if raw.get(key) != value:
            changed = True
            break

    current_config["video_reconstruction"] = normalized
    return normalized, changed


def get_access_control_config(persist_missing=True):
    current_config = load_config()
    access_config, changed = normalize_access_control_config(current_config)
    if changed and persist_missing:
        save_config(current_config)
    return access_config


def get_video_reconstruction_config(persist_missing=True):
    current_config = load_config()
    video_config, changed = normalize_video_reconstruction_config(current_config)
    if changed and persist_missing:
        save_config(current_config)
    return video_config


def has_access_code(access_config):
    return bool(access_config.get("password_hash"))


def is_access_control_enabled(access_config):
    return coerce_bool(access_config.get("enabled"), False)

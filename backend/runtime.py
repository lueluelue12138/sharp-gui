import logging
import os
import platform
import shutil
import ssl
import sys

# Disable SSL verification for networks with SSL proxy (corporate/school networks).
ssl._create_default_https_context = ssl._create_unverified_context

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
REACT_BUILD_DIR = os.path.join(BASE_DIR, "frontend", "dist")

FRONTEND_MODE = os.environ.get("SHARP_FRONTEND_MODE", "react")
SHARP_VERBOSE = os.environ.get("SHARP_VERBOSE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "debug",
    "verbose",
}
SHARP_LOG_LEVEL = os.environ.get("SHARP_LOG_LEVEL", "INFO").strip().upper()
SHARP_LOG_FILE = os.environ.get("SHARP_LOG_FILE", os.path.join(BASE_DIR, "sharp-gui-verbose.log"))
SHARP_HTTP_LOGS = os.environ.get("SHARP_HTTP_LOGS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "debug",
}
SHARP_DEBUG = os.environ.get("SHARP_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "debug",
}

DEFAULT_WORKSPACE_FOLDER = BASE_DIR
LOG_LEVEL_VALUES = {
    "DEBUG": 10,
    "INFO": 20,
    "WARN": 30,
    "WARNING": 30,
    "ERROR": 40,
}


def get_log_level_value(level=None):
    return LOG_LEVEL_VALUES.get((level or SHARP_LOG_LEVEL or "INFO").upper(), 20)


def is_log_enabled(level):
    return get_log_level_value(level) >= get_log_level_value()


def log(level, message):
    """Print backend diagnostics using the configured SHARP_LOG_LEVEL."""
    normalized = (level or "INFO").upper()
    if normalized == "WARNING":
        normalized = "WARN"
    if not is_log_enabled(normalized):
        return
    print(f"[{normalized}] {message}", flush=True)


def get_config_file():
    """显式独立配置优先；默认使用与安装位置无关的用户配置。"""
    from backend.config_storage import user_config_dir

    return os.environ.get('SHARP_CONFIG_FILE', '').strip() or str(user_config_dir() / 'config.json')


def resolve_sharp_command():
    """Return an executable Sharp CLI path that subprocess can launch."""
    if os.name == "nt":
        bundled_cmd = os.path.join(BASE_DIR, "sharp.cmd")
        if os.path.exists(bundled_cmd):
            return bundled_cmd

        for candidate in ("sharp.cmd", "sharp.exe", "sharp"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

    resolved = shutil.which("sharp")
    return resolved or "sharp"


def select_sharp_device():
    """Return a device that can actually execute kernels."""
    configured = os.environ.get("SHARP_DEVICE", "").strip().lower()
    if configured in {"cpu", "cuda", "mps"}:
        return configured

    try:
        import torch
    except Exception as exc:
        print(f"[WARN] Unable to import torch, falling back to CPU: {exc}")
        return "cpu"

    if torch.cuda.is_available():
        try:
            x = torch.ones((4, 4), device="cuda")
            _ = (x @ x).sum().cpu()
            torch.cuda.synchronize()
            return "cuda"
        except Exception as exc:
            msg = str(exc).splitlines()[0] if str(exc) else repr(exc)
            print(f"[WARN] CUDA is visible but unusable, falling back to CPU: {msg}")
            return "cpu"

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"

    return "cpu"


def verbose_log(message):
    log("DEBUG", message)


class TeeStream:
    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary

    def write(self, data):
        self.primary.write(data)
        self.secondary.write(data)
        return len(data)

    def flush(self):
        self.primary.flush()
        self.secondary.flush()


_verbose_log_enabled = False


def enable_verbose_log_file():
    global _verbose_log_enabled
    if not SHARP_VERBOSE or _verbose_log_enabled:
        return

    try:
        log_dir = os.path.dirname(SHARP_LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        log_file = open(SHARP_LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception as exc:
        print(f"[WARN] Unable to open verbose log file: {exc}", flush=True)
        return

    sys.stdout = TeeStream(sys.stdout, log_file)
    sys.stderr = TeeStream(sys.stderr, log_file)
    _verbose_log_enabled = True
    print(f"[DEBUG] verbose_log_file={SHARP_LOG_FILE}", flush=True)


def format_command_for_log(cmd):
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in cmd)


def configure_werkzeug_logging():
    logging.basicConfig(level=get_log_level_value(), format="[%(levelname)s] %(name)s: %(message)s")
    log = logging.getLogger("werkzeug")
    log.setLevel(get_log_level_value() if SHARP_HTTP_LOGS else logging.WARNING)


def print_runtime_diagnostics(protocol=None, local_ip=None):
    if not SHARP_VERBOSE:
        return

    print("[DEBUG] Sharp GUI verbose diagnostics", flush=True)
    print(f"[DEBUG]   log_level={SHARP_LOG_LEVEL}", flush=True)
    print(f"[DEBUG]   base_dir={BASE_DIR}", flush=True)
    print(f"[DEBUG]   cwd={os.getcwd()}", flush=True)
    print(f"[DEBUG]   python={sys.executable}", flush=True)
    print(f"[DEBUG]   verbose_log_file={SHARP_LOG_FILE}", flush=True)
    print(f"[DEBUG]   python_version={sys.version.split()[0]}", flush=True)
    print(f"[DEBUG]   platform={platform.platform()}", flush=True)
    print(f"[DEBUG]   frontend_mode={FRONTEND_MODE}", flush=True)
    if protocol and local_ip:
        print(f"[DEBUG]   url_local={protocol}://127.0.0.1:5050", flush=True)
        print(f"[DEBUG]   url_lan={protocol}://{local_ip}:5050", flush=True)
    print(f"[DEBUG]   sharp_cmd={resolve_sharp_command()}", flush=True)
    print(f"[DEBUG]   which_sharp={shutil.which('sharp')}", flush=True)
    print(f"[DEBUG]   which_sharp_cmd={shutil.which('sharp.cmd')}", flush=True)
    print(f"[DEBUG]   path={os.environ.get('PATH', '')}", flush=True)

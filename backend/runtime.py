import logging
import os
import platform
import secrets
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
SHARP_LOG_LEVEL = os.environ.get("SHARP_LOG_LEVEL", "DEBUG" if SHARP_VERBOSE else "INFO").strip().upper()
SHARP_LOG_FILE = os.environ.get("SHARP_LOG_FILE", os.path.join(BASE_DIR, "sharp-gui-verbose.log"))
SHARP_DEBUG = os.environ.get("SHARP_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "debug",
}

DEFAULT_WORKSPACE_FOLDER = BASE_DIR


def coerce_env_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_config_file():
    """Return the active config file path, allowing tests to isolate config."""
    return os.environ.get("SHARP_CONFIG_FILE", CONFIG_FILE)


def is_docker_mode():
    """Return whether Docker-specific runtime UX should be enabled."""
    if "SHARP_DOCKER_MODE" in os.environ:
        return coerce_env_bool(os.environ.get("SHARP_DOCKER_MODE"), False)
    return bool(os.environ.get("SHARP_DOCKER_VARIANT"))


def get_owner_token_file():
    path = os.environ.get("SHARP_OWNER_TOKEN_FILE", "").strip()
    if path:
        return path
    data_dir = os.environ.get("SHARP_DATA_DIR", "").strip()
    if data_dir:
        return os.path.join(data_dir, "owner-token.txt")
    return ""


def ensure_owner_token():
    """Return the Docker owner bootstrap token, creating a token file if needed."""
    env_token = os.environ.get("SHARP_OWNER_TOKEN", "").strip()
    if env_token:
        return env_token

    token_file = get_owner_token_file()
    if not token_file:
        return ""

    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as file_obj:
                return file_obj.read().strip()
        except OSError:
            return ""

    try:
        token_dir = os.path.dirname(token_file)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        token = secrets.token_urlsafe(32)
        with open(token_file, "w", encoding="utf-8") as file_obj:
            file_obj.write(token)
            file_obj.write("\n")
        os.chmod(token_file, 0o600)
        return token
    except OSError:
        return ""


def has_owner_bootstrap_token():
    return bool(ensure_owner_token())


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
    if SHARP_VERBOSE:
        print(f"[DEBUG] {message}", flush=True)


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
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.DEBUG if SHARP_VERBOSE else logging.WARNING)


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

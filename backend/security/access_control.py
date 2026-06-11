import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlparse

from flask import jsonify, request

from backend import runtime
from backend.config import (
    coerce_bool,
    coerce_int,
    get_access_control_config,
    has_access_code,
    is_access_control_enabled,
)

ACCESS_COOKIE_NAME = "sharp_gui_access"
OWNER_COOKIE_NAME = "sharp_gui_owner"
ACCESS_PUBLIC = "public"
ACCESS_UNLOCKED = "unlocked"
ACCESS_OWNER = "owner"
LOGIN_FAILURE_WINDOW_SECONDS = 300
LOGIN_FAILURE_MAX_DELAY_SECONDS = 8
VIDEO_PLAY_TOKEN_TTL_SECONDS = 6 * 60 * 60

login_failure_lock = threading.Lock()
login_failures = {}


def is_local_request():
    """检测是否为本机访问。"""
    remote_addr = request.remote_addr
    local_ips = ["127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"]
    return remote_addr in local_ips


def get_request_hostname():
    host = request.host.split("@")[-1].strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host.strip("[]")
    return host.split(":", 1)[0]


def is_loopback_host(hostname):
    hostname = (hostname or "").strip().strip("[]").lower()
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def is_private_host(hostname):
    hostname = (hostname or "").strip().strip("[]").lower()
    if hostname in {"localhost", socket.gethostname().lower()}:
        return True
    try:
        address = ipaddress.ip_address(hostname)
        return address.is_loopback or address.is_private or address.is_link_local
    except ValueError:
        return hostname.endswith(".local")


def is_allowed_request_host():
    hostname = get_request_hostname()
    if not hostname:
        return False
    return is_private_host(hostname)


def is_origin_allowed(origin_value):
    if not origin_value:
        return True
    parsed = urlparse(origin_value)
    origin_host = (parsed.hostname or "").lower()
    request_host = get_request_hostname()
    if not origin_host:
        return False
    if origin_host == request_host:
        return True
    if is_loopback_host(origin_host) and is_loopback_host(request_host):
        return True
    if is_local_request() and is_loopback_host(origin_host):
        return True
    return False


def is_request_origin_allowed():
    fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
    if fetch_site == "cross-site":
        return False

    origin = request.headers.get("Origin")
    if origin and not is_origin_allowed(origin):
        return False

    referer = request.headers.get("Referer")
    if referer and not is_origin_allowed(referer):
        return False

    return True


def is_owner_request(access_config=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    if verify_owner_session_token(request.cookies.get(OWNER_COOKIE_NAME), access_config):
        return True
    return is_local_owner_request(access_config)


def is_local_owner_request(access_config=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    if not coerce_bool(access_config.get("allow_localhost_bypass"), True):
        return False
    return is_local_request() and is_allowed_request_host()


def encode_session_payload(payload):
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return encoded


def decode_session_payload(encoded):
    padding = "=" * (-len(encoded) % 4)
    data = base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
    return json.loads(data.decode("utf-8"))


def sign_session_payload(encoded, secret):
    return hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()


def sign_video_play_payload(video_id, expires_at, access_config):
    session_version = coerce_int(access_config.get("session_version"), 1, 1)
    message = f"video-play:{session_version}:{video_id}:{expires_at}"
    return hmac.new(
        access_config.get("session_secret", "").encode("utf-8"),
        message.encode("utf-8", "surrogatepass"),
        hashlib.sha256,
    ).hexdigest()


def create_video_play_token(video_id, access_config=None, now=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    expires_at = int(now or time.time()) + VIDEO_PLAY_TOKEN_TTL_SECONDS
    signature = sign_video_play_payload(video_id, expires_at, access_config)
    return f"{expires_at}.{signature}"


def verify_video_play_token(video_id, token, access_config=None, now=None):
    if not token or not isinstance(token, str) or "." not in token:
        return False

    raw_expires_at, signature = token.rsplit(".", 1)
    try:
        expires_at = int(raw_expires_at)
    except ValueError:
        return False

    if expires_at < int(now or time.time()):
        return False

    access_config = access_config or get_access_control_config(persist_missing=False)
    expected_signature = sign_video_play_payload(video_id, expires_at, access_config)
    return hmac.compare_digest(signature, expected_signature)


def create_access_session_token(access_config):
    now = int(time.time())
    session_days = coerce_int(access_config.get("session_days"), 30, 1, 365)
    payload = {
        "v": coerce_int(access_config.get("session_version"), 1, 1),
        "iat": now,
        "exp": now + session_days * 86400,
        "nonce": secrets.token_urlsafe(8),
    }
    encoded = encode_session_payload(payload)
    signature = sign_session_payload(encoded, access_config["session_secret"])
    return f"{encoded}.{signature}", payload["exp"]


def create_owner_session_token(access_config):
    now = int(time.time())
    session_days = coerce_int(access_config.get("session_days"), 30, 1, 365)
    payload = {
        "scope": "owner",
        "v": coerce_int(access_config.get("session_version"), 1, 1),
        "iat": now,
        "exp": now + session_days * 86400,
        "nonce": secrets.token_urlsafe(8),
    }
    encoded = encode_session_payload(payload)
    signature = sign_session_payload(encoded, access_config["session_secret"])
    return f"{encoded}.{signature}", payload["exp"]


def verify_access_session_token(token, access_config):
    if not token or not isinstance(token, str) or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    expected_signature = sign_session_payload(encoded, access_config.get("session_secret", ""))
    if not hmac.compare_digest(signature, expected_signature):
        return False
    try:
        payload = decode_session_payload(encoded)
    except Exception:
        return False
    if coerce_int(payload.get("v"), 0) != coerce_int(access_config.get("session_version"), 1, 1):
        return False
    if coerce_int(payload.get("exp"), 0) < int(time.time()):
        return False
    return True


def verify_owner_session_token(token, access_config):
    if not token or not isinstance(token, str) or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    expected_signature = sign_session_payload(encoded, access_config.get("session_secret", ""))
    if not hmac.compare_digest(signature, expected_signature):
        return False
    try:
        payload = decode_session_payload(encoded)
    except Exception:
        return False
    if payload.get("scope") != "owner":
        return False
    if coerce_int(payload.get("v"), 0) != coerce_int(access_config.get("session_version"), 1, 1):
        return False
    if coerce_int(payload.get("exp"), 0) < int(time.time()):
        return False
    return True


def verify_owner_bootstrap_token(token):
    if not runtime.is_docker_mode():
        return False
    expected_token = runtime.ensure_owner_token()
    if not expected_token or not token or not isinstance(token, str):
        return False
    return hmac.compare_digest(token, expected_token)


def is_authenticated_request(access_config=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    if not is_access_control_enabled(access_config):
        return True
    if is_owner_request(access_config):
        return True
    return verify_access_session_token(request.cookies.get(ACCESS_COOKIE_NAME), access_config)


def get_login_failure_key():
    return request.remote_addr or "unknown"


def prune_login_failures(at_time=None):
    now = at_time or time.time()
    cutoff = now - LOGIN_FAILURE_WINDOW_SECONDS
    for key in list(login_failures.keys()):
        login_failures[key] = [timestamp for timestamp in login_failures[key] if timestamp >= cutoff]
        if not login_failures[key]:
            login_failures.pop(key, None)


def get_login_delay_seconds():
    key = get_login_failure_key()
    now = time.time()
    with login_failure_lock:
        prune_login_failures(now)
        failure_count = len(login_failures.get(key, []))
    if failure_count < 3:
        return 0
    return min(LOGIN_FAILURE_MAX_DELAY_SECONDS, 2 ** (failure_count - 3))


def record_login_failure():
    key = get_login_failure_key()
    now = time.time()
    with login_failure_lock:
        prune_login_failures(now)
        login_failures.setdefault(key, []).append(now)


def clear_login_failures():
    with login_failure_lock:
        login_failures.pop(get_login_failure_key(), None)


def get_required_access_level(access_config=None):
    path = request.path
    method = request.method.upper()
    download = request.args.get("download", "0").lower() in ("1", "true", "yes")

    if method == "OPTIONS":
        return ACCESS_PUBLIC

    if path in {"/", "/api/auth/status", "/api/auth/login", "/api/auth/owner-bootstrap"}:
        return ACCESS_PUBLIC
    if path.startswith("/assets/"):
        return ACCESS_PUBLIC
    if path in {
        "/favicon.ico",
        "/favicon.svg",
        "/favicon-96x96.png",
        "/apple-touch-icon.png",
        "/site.webmanifest",
        "/web-app-manifest-192x192.png",
        "/web-app-manifest-512x512.png",
        "/logo.png",
    }:
        return ACCESS_PUBLIC

    if path in {"/api/auth/access-code", "/api/auth/revoke", "/api/auth/settings"}:
        return ACCESS_OWNER
    if path == "/api/auth/logout":
        return ACCESS_UNLOCKED

    if path == "/api/settings":
        return ACCESS_OWNER if method != "GET" else ACCESS_UNLOCKED
    if path in {"/api/browse-folder", "/api/restart", "/api/convert-all"}:
        return ACCESS_OWNER
    if path.startswith("/api/delete/") or (path.startswith("/api/task/") and path.endswith("/cancel")):
        return ACCESS_OWNER
    if path == "/api/photo-albums" and method != "GET":
        return ACCESS_OWNER
    if path == "/api/photo-gallery/cache":
        return ACCESS_OWNER if method != "GET" else ACCESS_UNLOCKED
    if path.startswith("/api/photo-albums/") and (method == "DELETE" or path.endswith("/scan")):
        return ACCESS_OWNER
    if path.startswith("/api/photo-albums/") and path.endswith("/uploads"):
        access_config = access_config or get_access_control_config(persist_missing=False)
        return ACCESS_UNLOCKED if is_access_control_enabled(access_config) else ACCESS_OWNER
    if path.startswith("/api/video-poster/"):
        return ACCESS_UNLOCKED
    if path.startswith("/api/video-play/"):
        parts = path.split("/", 5)
        video_id = parts[3] if len(parts) > 3 else ""
        token = parts[4] if len(parts) > 4 else ""
        if method == "GET" and verify_video_play_token(video_id, token, access_config):
            return ACCESS_PUBLIC
        return ACCESS_UNLOCKED
    if path.startswith("/api/video-original/"):
        video_id = path.rsplit("/", 1)[-1]
        token = request.args.get("play_token")
        if method == "GET" and not download and verify_video_play_token(video_id, token, access_config):
            return ACCESS_PUBLIC
        return ACCESS_UNLOCKED
    if path in {"/api/generate", "/api/photo-conversions"}:
        access_config = access_config or get_access_control_config(persist_missing=False)
        if not is_access_control_enabled(access_config):
            return ACCESS_OWNER
        return ACCESS_UNLOCKED if coerce_bool(access_config.get("allow_remote_generation"), False) else ACCESS_OWNER

    if path.startswith("/api/") or path.startswith("/files/"):
        return ACCESS_UNLOCKED

    return ACCESS_PUBLIC


def make_auth_error(message, status_code, code, **extra):
    payload = {"error": message, "code": code}
    payload.update(extra)
    return jsonify(payload), status_code


def build_auth_status(access_config=None, authenticated_override=None, owner_override=None):
    access_config = access_config or get_access_control_config(persist_missing=False)
    owner = is_owner_request(access_config)
    if owner_override is not None:
        owner = owner_override
    authenticated = owner or verify_access_session_token(request.cookies.get(ACCESS_COOKIE_NAME), access_config)
    if authenticated_override is not None:
        authenticated = authenticated_override
    access_control_enabled = is_access_control_enabled(access_config)
    access_code_configured = has_access_code(access_config)
    if not access_control_enabled:
        authenticated = True
    return {
        "authenticated": authenticated,
        "is_owner": owner,
        "is_local": owner,
        "is_docker": runtime.is_docker_mode(),
        "owner_bootstrap_available": runtime.is_docker_mode() and runtime.has_owner_bootstrap_token(),
        "owner_authenticated": owner,
        "access_control_enabled": access_control_enabled,
        "setup_required": access_control_enabled and not access_code_configured,
        "setup_recommended": (not access_control_enabled) or (not access_code_configured),
        "has_access_code": access_code_configured,
        "session_days": coerce_int(access_config.get("session_days"), 30, 1, 365),
        "allow_localhost_bypass": coerce_bool(access_config.get("allow_localhost_bypass"), True),
        "allow_remote_generation": access_control_enabled
        and coerce_bool(access_config.get("allow_remote_generation"), False),
        "lan_bind_enabled": coerce_bool(access_config.get("lan_bind_enabled"), True),
    }

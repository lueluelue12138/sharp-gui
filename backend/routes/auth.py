import datetime
import time

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from backend.config import coerce_bool, coerce_int, load_config, normalize_access_control_config, save_config
from backend.config import has_access_code, is_access_control_enabled
from backend.security.access_control import (
    ACCESS_COOKIE_NAME,
    build_auth_status,
    clear_login_failures,
    create_access_session_token,
    get_login_delay_seconds,
    make_auth_error,
    record_login_failure,
)

bp = Blueprint("auth", __name__)


@bp.route("/api/auth/status")
def auth_status():
    return jsonify({**build_auth_status(g.access_control),
                    'server_instance_id': current_app.config['SERVER_INSTANCE_ID']})


@bp.route("/api/auth/login", methods=["POST"])
def auth_login():
    access_config = g.access_control

    if not is_access_control_enabled(access_config):
        return jsonify(build_auth_status(access_config, authenticated_override=True))

    if g.is_owner:
        return jsonify(build_auth_status(access_config, authenticated_override=True))

    if not has_access_code(access_config):
        return make_auth_error(
            "Access code is not configured. Open Settings from localhost first.",
            403,
            "ACCESS_SETUP_REQUIRED",
            setup_required=True,
        )

    delay_seconds = get_login_delay_seconds()
    if delay_seconds:
        time.sleep(delay_seconds)

    data = request.get_json(silent=True) or {}
    password = data.get("password") or data.get("access_code") or data.get("accessCode")
    if not isinstance(password, str) or not check_password_hash(access_config["password_hash"], password):
        record_login_failure()
        return make_auth_error("Invalid access code", 401, "INVALID_ACCESS_CODE")

    clear_login_failures()
    token, expires_at = create_access_session_token(access_config)
    response = jsonify(build_auth_status(access_config, authenticated_override=True))
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        max_age=coerce_int(access_config.get("session_days"), 30, 1, 365) * 86400,
        expires=datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc),
        httponly=True,
        secure=request.is_secure,
        samesite="Strict",
        path="/",
    )
    return response


@bp.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    response = jsonify(build_auth_status(g.access_control, authenticated_override=g.is_owner))
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    return response


@bp.route("/api/auth/access-code", methods=["POST"])
def auth_set_access_code():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or data.get("access_code") or data.get("accessCode")
    if not isinstance(password, str) or len(password) < 8:
        return make_auth_error("Access code must be at least 8 characters", 400, "ACCESS_CODE_TOO_SHORT")

    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)
    access_config["enabled"] = True
    access_config["password_hash"] = generate_password_hash(password)
    if "session_days" in data:
        access_config["session_days"] = coerce_int(data.get("session_days"), access_config["session_days"], 1, 365)
    if "allow_remote_generation" in data and access_config["enabled"]:
        access_config["allow_remote_generation"] = coerce_bool(
            data.get("allow_remote_generation"),
            access_config["allow_remote_generation"],
        )
    if not access_config["enabled"]:
        access_config["allow_remote_generation"] = False
    access_config["session_version"] = coerce_int(access_config.get("session_version"), 1, 1) + 1
    current_config["access_control"] = access_config
    save_config(current_config)

    return jsonify(build_auth_status(access_config, authenticated_override=True))


@bp.route("/api/auth/revoke", methods=["POST"])
def auth_revoke_sessions():
    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)
    access_config["session_version"] = coerce_int(access_config.get("session_version"), 1, 1) + 1
    current_config["access_control"] = access_config
    save_config(current_config)
    return jsonify(build_auth_status(access_config, authenticated_override=True))


@bp.route("/api/auth/settings", methods=["POST"])
def auth_update_settings():
    data = request.get_json(silent=True) or {}
    current_config = load_config()
    access_config, _ = normalize_access_control_config(current_config)

    if "enabled" in data:
        access_config["enabled"] = coerce_bool(data.get("enabled"), access_config["enabled"])
        if not access_config["enabled"]:
            access_config["allow_remote_generation"] = False
    if "session_days" in data:
        access_config["session_days"] = coerce_int(data.get("session_days"), access_config["session_days"], 1, 365)
    if "allow_remote_generation" in data and access_config["enabled"]:
        access_config["allow_remote_generation"] = coerce_bool(
            data.get("allow_remote_generation"),
            access_config["allow_remote_generation"],
        )
    if not access_config["enabled"]:
        access_config["allow_remote_generation"] = False
    if "allow_localhost_bypass" in data:
        next_bypass = coerce_bool(data.get("allow_localhost_bypass"), access_config["allow_localhost_bypass"])
        if not next_bypass and not has_access_code(access_config):
            return make_auth_error("Set an access code before disabling localhost bypass", 400, "ACCESS_CODE_REQUIRED")
        access_config["allow_localhost_bypass"] = next_bypass
    if "lan_bind_enabled" in data:
        access_config["lan_bind_enabled"] = coerce_bool(data.get("lan_bind_enabled"), access_config["lan_bind_enabled"])

    current_config["access_control"] = access_config
    save_config(current_config)
    return jsonify(build_auth_status(access_config, authenticated_override=True))

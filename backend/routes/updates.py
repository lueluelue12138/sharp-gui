from flask import Blueprint, current_app, g, jsonify, request

from backend.services.self_update import UpdateError


bp = Blueprint("updates", __name__)


def _manager():
    return current_app.config["UPDATE_MANAGER"]


def _status():
    return _manager().status(
        is_owner=g.is_owner,
        server_instance_id=current_app.config["SERVER_INSTANCE_ID"],
    )


def _owner_error():
    return jsonify({"error": "Only localhost can manage application updates", "code": "OWNER_REQUIRED"}), 403


def _update_error(exc):
    return jsonify({"error": exc.code, "code": exc.code}), exc.status_code


def _json_object(allowed_keys):
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict) or set(payload) - set(allowed_keys):
        raise UpdateError("update_request_invalid", status_code=400)
    return payload


@bp.get("/api/updates/status")
def update_status():
    return jsonify(_status())


@bp.post("/api/updates/check")
def check_update():
    if not g.is_owner:
        return _owner_error()
    try:
        payload = _json_object({"channel"})
        result = _manager().check(
            payload.get("channel"),
            is_owner=True,
            server_instance_id=current_app.config["SERVER_INSTANCE_ID"],
        )
        return jsonify(result)
    except UpdateError as exc:
        return _update_error(exc)


@bp.post("/api/updates/apply")
def apply_update():
    if not g.is_owner:
        return _owner_error()
    try:
        payload = _json_object({"channel", "target_token"})
        result = _manager().start_apply(
            payload.get("channel"),
            payload.get("target_token"),
            is_owner=True,
            server_instance_id=current_app.config["SERVER_INSTANCE_ID"],
        )
        return jsonify(result), 202
    except UpdateError as exc:
        return _update_error(exc)


@bp.post("/api/updates/rollback")
def rollback_update():
    if not g.is_owner:
        return _owner_error()
    try:
        _json_object(set())
        result = _manager().start_rollback(
            is_owner=True,
            server_instance_id=current_app.config["SERVER_INSTANCE_ID"],
        )
        return jsonify(result), 202
    except UpdateError as exc:
        return _update_error(exc)

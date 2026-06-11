from flask import g, request

from backend.config import has_access_code, is_access_control_enabled
from backend.security.access_control import (
    ACCESS_PUBLIC,
    ACCESS_OWNER,
    get_access_control_config,
    get_required_access_level,
    is_allowed_request_host,
    is_authenticated_request,
    is_origin_allowed,
    is_owner_request,
    is_request_origin_allowed,
    make_auth_error,
)


def register_security_hooks(app):
    @app.before_request
    def enforce_lan_access_control():
        access_config = get_access_control_config()
        g.access_control = access_config
        g.is_owner = is_owner_request(access_config)
        g.is_authenticated = is_authenticated_request(access_config)
        required_access = get_required_access_level(access_config)
        g.required_access = required_access

        if not is_allowed_request_host():
            return make_auth_error("Request Host is not allowed", 400, "INVALID_HOST")

        if required_access != ACCESS_PUBLIC and not is_request_origin_allowed():
            return make_auth_error("Cross-origin private request is not allowed", 403, "ORIGIN_FORBIDDEN")

        if (
            request.path in {"/api/auth/login", "/api/auth/owner-bootstrap"}
            and request.method.upper() != "OPTIONS"
            and not is_request_origin_allowed()
        ):
            return make_auth_error("Cross-origin login request is not allowed", 403, "ORIGIN_FORBIDDEN")

        if required_access == ACCESS_PUBLIC:
            return None

        if required_access == ACCESS_OWNER:
            if not g.is_owner:
                return make_auth_error("Only localhost can perform this action", 403, "OWNER_REQUIRED")
            return None

        if not is_access_control_enabled(access_config):
            return None

        if not g.is_authenticated:
            if not has_access_code(access_config):
                return make_auth_error(
                    "Access code is not configured. Open Settings from localhost first.",
                    401,
                    "ACCESS_SETUP_REQUIRED",
                    setup_required=True,
                )
            return make_auth_error("Authentication required", 401, "AUTH_REQUIRED")

        return None

    @app.after_request
    def after_request(response):
        origin = request.headers.get("Origin")
        if origin and is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers.add("Vary", "Origin")
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
        return response

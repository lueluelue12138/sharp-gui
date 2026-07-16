from app import app as imported_app

EXPECTED_ROUTES = {
    ("/", ("GET",)),
    ("/<path:filename>", ("GET",)),
    ("/api/auth/access-code", ("POST",)),
    ("/api/auth/login", ("POST",)),
    ("/api/auth/logout", ("POST",)),
    ("/api/auth/revoke", ("POST",)),
    ("/api/auth/settings", ("POST",)),
    ("/api/auth/status", ("GET",)),
    ("/api/browse-folder", ("POST",)),
    ("/api/convert-all", ("POST",)),
    ("/api/delete/<item_id>", ("DELETE",)),
    ("/api/download/<item_id>", ("GET",)),
    ("/api/export/<model_id>", ("GET",)),
    ("/api/gallery", ("GET",)),
    ("/api/gallery/<item_id>/source-video", ("GET",)),
    ("/api/generate", ("POST",)),
    ("/api/model-asset-deletions", ("POST",)),
    ("/api/model-asset-downloads", ("POST",)),
    ("/api/model-asset-downloads/<download_id>", ("GET",)),
    ("/api/model-assets", ("GET",)),
    ("/api/model-assets/<asset_id>", ("DELETE",)),
    ("/api/model-assets/<asset_id>", ("GET",)),
    ("/api/model-assets/<asset_id>", ("PATCH", "POST")),
    ("/api/model-assets/<asset_id>/cover", ("POST",)),
    ("/api/model-assets/<asset_id>/cover/refresh", ("POST",)),
    ("/api/model-assets/<asset_id>/download", ("GET",)),
    ("/api/model-assets/import", ("POST",)),
    ("/api/original/<item_id>", ("GET",)),
    ("/api/photo-albums", ("GET", "POST")),
    ("/api/photo-albums/<album_id>", ("DELETE",)),
    ("/api/photo-albums/<album_id>/photos", ("GET",)),
    ("/api/photo-albums/<album_id>/scan", ("POST",)),
    ("/api/photo-albums/<album_id>/uploads", ("POST",)),
    ("/api/photo-gallery/cache", ("DELETE", "GET")),
    ("/api/photo-conversions", ("POST",)),
    ("/api/photo-downloads", ("POST",)),
    ("/api/photo-original/<photo_id>", ("GET",)),
    ("/api/photo-thumbnail/<photo_id>", ("GET",)),
    ("/api/restart", ("POST",)),
    ("/api/settings", ("GET", "POST")),
    ("/api/task/<task_id>/cancel", ("POST",)),
    ("/api/tasks", ("GET",)),
    ("/api/thumbnail/<item_id>", ("GET",)),
    ("/api/updates/apply", ("POST",)),
    ("/api/updates/check", ("POST",)),
    ("/api/updates/rollback", ("POST",)),
    ("/api/updates/status", ("GET",)),
    ("/api/video-play/<video_id>/<play_token>/<path:filename>", ("GET",)),
    ("/api/video-original/<video_id>", ("GET",)),
    ("/api/video-poster/<video_id>", ("GET",)),
    ("/api/video-reconstructions", ("POST",)),
    ("/api/video-reconstructions/status", ("GET",)),
    ("/api/video-reconstructions/upload", ("POST",)),
    ("/assets/<path:filename>", ("GET",)),
    ("/files/<path:filename>", ("GET",)),
    ("/static/<path:filename>", ("GET",)),
}


def route_signatures(flask_app):
    return {
        (rule.rule, tuple(sorted(method for method in rule.methods if method not in {"HEAD", "OPTIONS"})))
        for rule in flask_app.url_map.iter_rules()
    }


def test_key_routes_are_registered(app):
    assert EXPECTED_ROUTES.issubset(route_signatures(app))


def test_app_import_does_not_start_workers():
    assert imported_app.config["TASK_MANAGER"].workers_started is False

from flask import Flask

from backend import runtime
from backend.config import (
    load_config,
    normalize_access_control_config,
    normalize_video_reconstruction_config,
    save_config,
)
from backend.paths import build_path_context, ensure_runtime_directories, install_path_config
from backend.routes import register_routes
from backend.security.hooks import register_security_hooks
from backend.services.model_gallery import cleanup_interrupted_image_tasks, generate_thumbnail
from backend.services.photo_gallery import migrate_photo_gallery_roots_config
from backend.services.task_queue import TaskManager
from backend.services import video_reconstruction


def create_app(start_background_workers=False):
    """Create the Flask application without import-time worker side effects."""
    runtime.enable_verbose_log_file()

    app = Flask(
        __name__,
        template_folder=runtime.TEMPLATES_DIR,
        static_folder=runtime.STATIC_DIR,
    )

    config = load_config()
    _, access_config_changed = normalize_access_control_config(config)
    roots_migrated = migrate_photo_gallery_roots_config(config)
    _, video_config_changed = normalize_video_reconstruction_config(config)
    if access_config_changed or roots_migrated or video_config_changed:
        save_config(config)

    paths = build_path_context(config)
    ensure_runtime_directories(paths)
    image_cleanup = cleanup_interrupted_image_tasks(paths)
    if image_cleanup["removed"] or image_cleanup["recovered"]:
        runtime.log(
            "INFO",
            "Reconciled interrupted image tasks at startup: "
            f"removed={image_cleanup['removed']} recovered={image_cleanup['recovered']}",
        )
    if image_cleanup["errors"]:
        runtime.log(
            "WARN",
            f"Failed to reconcile {image_cleanup['errors']} interrupted image task(s)",
        )
    video_reconstruction.cleanup_stale_runtime_artifacts(paths)
    install_path_config(app, paths)

    task_manager = TaskManager(
        paths=paths,
        thumbnail_generator=lambda input_path, filename: generate_thumbnail(paths, input_path, filename),
    )
    app.config["TASK_MANAGER"] = task_manager

    register_security_hooks(app)
    register_routes(app)
    video_reconstruction.start_dependency_warmup()

    if start_background_workers:
        task_manager.start_workers()

    return app

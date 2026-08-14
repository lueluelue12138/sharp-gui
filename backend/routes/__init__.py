from backend.routes import (
    auth,
    export,
    files,
    frontend,
    gallery,
    model_assets,
    photo_gallery,
    settings,
    tasks,
    updates,
    video_reconstruction,
)


def register_routes(app):
    app.register_blueprint(auth.bp)
    app.register_blueprint(gallery.bp)
    app.register_blueprint(model_assets.bp)
    app.register_blueprint(photo_gallery.bp)
    app.register_blueprint(video_reconstruction.bp)
    app.register_blueprint(tasks.bp)
    app.register_blueprint(updates.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(frontend.bp)

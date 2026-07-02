import os
from dataclasses import dataclass

from backend import runtime


@dataclass(frozen=True)
class PathContext:
    workspace_folder: str
    input_folder: str
    output_folder: str
    thumbnail_folder: str
    model_asset_folder: str
    model_asset_import_folder: str
    model_asset_thumbnail_folder: str
    model_asset_index_file: str
    photo_gallery_cache_folder: str
    video_reconstruction_folder: str
    video_reconstruction_jobs_folder: str
    photo_thumbnail_folder: str
    video_poster_folder: str
    photo_index_file: str
    photo_catalog_file: str
    photo_album_index_folder: str

    @property
    def allowed_file_serve_roots(self):
        return (
            self.output_folder,
            self.thumbnail_folder,
            self.model_asset_import_folder,
            self.model_asset_thumbnail_folder,
        )


def build_path_context(config_data):
    workspace_folder = config_data.get("workspace_folder", runtime.DEFAULT_WORKSPACE_FOLDER)
    input_folder = os.path.join(workspace_folder, "inputs")
    output_folder = os.path.join(workspace_folder, "outputs")
    thumbnail_folder = os.path.join(input_folder, ".thumbnails")
    model_asset_folder = os.path.join(workspace_folder, "model-assets")
    model_asset_import_folder = os.path.join(model_asset_folder, "imports")
    model_asset_thumbnail_folder = os.path.join(model_asset_folder, "thumbnails")
    model_asset_index_file = os.path.join(workspace_folder, ".model-asset-library", "index.json")
    photo_gallery_cache_folder = os.path.join(workspace_folder, ".photo-gallery-cache")
    video_reconstruction_folder = os.path.join(workspace_folder, ".video-reconstruction")
    video_reconstruction_jobs_folder = os.path.join(video_reconstruction_folder, "jobs")
    photo_thumbnail_folder = os.path.join(photo_gallery_cache_folder, "thumbnails")
    video_poster_folder = os.path.join(photo_gallery_cache_folder, "video-posters")
    photo_index_file = os.path.join(photo_gallery_cache_folder, "index.json")
    photo_catalog_file = os.path.join(photo_gallery_cache_folder, "catalog.json")
    photo_album_index_folder = os.path.join(photo_gallery_cache_folder, "albums")

    return PathContext(
        workspace_folder=workspace_folder,
        input_folder=input_folder,
        output_folder=output_folder,
        thumbnail_folder=thumbnail_folder,
        model_asset_folder=model_asset_folder,
        model_asset_import_folder=model_asset_import_folder,
        model_asset_thumbnail_folder=model_asset_thumbnail_folder,
        model_asset_index_file=model_asset_index_file,
        photo_gallery_cache_folder=photo_gallery_cache_folder,
        video_reconstruction_folder=video_reconstruction_folder,
        video_reconstruction_jobs_folder=video_reconstruction_jobs_folder,
        photo_thumbnail_folder=photo_thumbnail_folder,
        video_poster_folder=video_poster_folder,
        photo_index_file=photo_index_file,
        photo_catalog_file=photo_catalog_file,
        photo_album_index_folder=photo_album_index_folder,
    )


def ensure_runtime_directories(paths):
    os.makedirs(paths.input_folder, exist_ok=True)
    os.makedirs(paths.output_folder, exist_ok=True)
    os.makedirs(paths.thumbnail_folder, exist_ok=True)
    os.makedirs(paths.model_asset_import_folder, exist_ok=True)
    os.makedirs(paths.model_asset_thumbnail_folder, exist_ok=True)
    os.makedirs(os.path.dirname(paths.model_asset_index_file), exist_ok=True)
    os.makedirs(paths.photo_thumbnail_folder, exist_ok=True)
    os.makedirs(paths.video_poster_folder, exist_ok=True)
    os.makedirs(paths.photo_album_index_folder, exist_ok=True)
    os.makedirs(paths.video_reconstruction_jobs_folder, exist_ok=True)


def install_path_config(app, paths):
    app.config["PATH_CONTEXT"] = paths
    app.config["WORKSPACE_FOLDER"] = paths.workspace_folder
    app.config["INPUT_FOLDER"] = paths.input_folder
    app.config["OUTPUT_FOLDER"] = paths.output_folder
    app.config["THUMBNAIL_FOLDER"] = paths.thumbnail_folder
    app.config["MODEL_ASSET_FOLDER"] = paths.model_asset_folder
    app.config["MODEL_ASSET_IMPORT_FOLDER"] = paths.model_asset_import_folder
    app.config["MODEL_ASSET_THUMBNAIL_FOLDER"] = paths.model_asset_thumbnail_folder
    app.config["MODEL_ASSET_INDEX_FILE"] = paths.model_asset_index_file
    app.config["PHOTO_GALLERY_CACHE_FOLDER"] = paths.photo_gallery_cache_folder
    app.config["VIDEO_RECONSTRUCTION_FOLDER"] = paths.video_reconstruction_folder
    app.config["VIDEO_RECONSTRUCTION_JOBS_FOLDER"] = paths.video_reconstruction_jobs_folder
    app.config["PHOTO_THUMBNAIL_FOLDER"] = paths.photo_thumbnail_folder
    app.config["VIDEO_POSTER_FOLDER"] = paths.video_poster_folder
    app.config["PHOTO_CATALOG_FILE"] = paths.photo_catalog_file
    app.config["PHOTO_ALBUM_INDEX_FOLDER"] = paths.photo_album_index_folder

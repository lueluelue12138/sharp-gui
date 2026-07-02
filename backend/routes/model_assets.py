import os

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from backend.services import model_assets

bp = Blueprint("model_assets", __name__)


def get_paths():
    return current_app.config["PATH_CONTEXT"]


@bp.route("/api/model-assets")
def list_model_assets():
    return jsonify(model_assets.list_model_assets(get_paths(), request.args))


@bp.route("/api/model-assets/<asset_id>")
def get_model_asset(asset_id):
    asset = model_assets.get_model_asset(get_paths(), asset_id, include_details=True)
    if not asset:
        return jsonify({"error": "Model asset not found", "code": "model_asset_not_found"}), 404
    return jsonify(asset)


@bp.route("/api/model-assets/import", methods=["POST"])
def import_model_assets():
    files = request.files.getlist("files")
    if not files:
        files = request.files.getlist("file")
    files = [file for file in files if file and file.filename]
    if not files:
        return jsonify({"error": "No model files selected", "code": "no_model_files"}), 400

    payload = model_assets.import_model_assets(get_paths(), files)
    status_code = 200 if payload["assets"] else 400
    return jsonify(payload), status_code


@bp.route("/api/model-assets/<asset_id>", methods=["POST", "PATCH"])
def update_model_asset(asset_id):
    try:
        asset = model_assets.update_model_asset_profile(get_paths(), asset_id, request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_model_asset_profile"}), 400
    if not asset:
        return jsonify({"error": "Model asset not found", "code": "model_asset_not_found"}), 404
    return jsonify(asset)


@bp.route("/api/model-assets/<asset_id>", methods=["DELETE"])
def delete_model_asset(asset_id):
    if not model_assets.delete_model_asset(get_paths(), asset_id):
        return jsonify({"error": "Model asset not found", "code": "model_asset_not_found"}), 404
    return jsonify({"success": True})


@bp.route("/api/model-assets/<asset_id>/cover", methods=["POST"])
def upload_model_asset_cover(asset_id):
    file = request.files.get("cover") or request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No cover image selected", "code": "no_cover_image"}), 400
    kind = request.form.get("kind") if request.form.get("kind") in {"manual", "system"} else "manual"
    asset, error_payload, status_code = model_assets.save_model_asset_cover(get_paths(), asset_id, file, kind=kind)
    if error_payload:
        return jsonify(error_payload), status_code
    return jsonify(asset)


@bp.route("/api/model-assets/<asset_id>/cover/refresh", methods=["POST"])
def refresh_model_asset_cover(asset_id):
    asset = model_assets.refresh_model_asset_cover(get_paths(), asset_id)
    if not asset:
        return jsonify({"error": "Model asset not found", "code": "model_asset_not_found"}), 404
    return jsonify(asset)


@bp.route("/api/model-assets/<asset_id>/download")
def download_model_asset(asset_id):
    resolved = model_assets.resolve_download_file(get_paths(), asset_id, request.args.get("format"))
    if not resolved:
        return jsonify({"error": "Model asset file not found", "code": "model_asset_file_not_found"}), 404

    path, filename = resolved
    return send_from_directory(
        os.path.dirname(path),
        os.path.basename(path),
        as_attachment=True,
        download_name=filename,
    )

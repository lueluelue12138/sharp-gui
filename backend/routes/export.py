import traceback
from io import BytesIO

from flask import Blueprint, current_app, jsonify, request, send_file

from backend.services.export_html import build_export_html

bp = Blueprint("export", __name__)


@bp.route("/api/export/<model_id>")
def export_model(model_id):
    """Export a model as a standalone HTML file."""
    fmt = request.args.get("format", "spz").lower()
    if fmt not in ("spz", "ply", "splat", "rad"):
        fmt = "spz"

    try:
        result, error_payload, status_code = build_export_html(current_app.config["PATH_CONTEXT"], model_id, fmt)
        if error_payload:
            return jsonify(error_payload), status_code

        response = send_file(
            BytesIO(result["html"].encode("utf-8")),
            as_attachment=True,
            download_name=result["download_name"],
            mimetype="text/html",
            max_age=0,
        )
        response.headers["X-Export-Format"] = result["format"]
        response.headers["X-Export-Model-Bytes"] = str(result["model_size"])
        response.headers["X-Export-Html-Bytes"] = str(result["html_size"])
        return response
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

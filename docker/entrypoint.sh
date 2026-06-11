#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${SHARP_DATA_DIR:-/data}"
WORKSPACE_DIR="${SHARP_WORKSPACE_FOLDER:-${DATA_DIR}/workspace}"

export HOME="${SHARP_HOME:-${DATA_DIR}}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${DATA_DIR}/.cache}"
export TORCH_HOME="${TORCH_HOME:-${DATA_DIR}/.cache/torch}"
export HF_HOME="${HF_HOME:-${DATA_DIR}/.cache/huggingface}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${DATA_DIR}/.cache/matplotlib}"
export SHARP_CONFIG_FILE="${SHARP_CONFIG_FILE:-${DATA_DIR}/config.json}"
export SHARP_FRONTEND_MODE="${SHARP_FRONTEND_MODE:-react}"
export SHARP_BIND_HOST="${SHARP_BIND_HOST:-0.0.0.0}"
export SHARP_LOG_FILE="${SHARP_LOG_FILE:-${DATA_DIR}/sharp-gui-verbose.log}"
export SHARP_DOCKER_MODE="${SHARP_DOCKER_MODE:-1}"
export SHARP_OWNER_TOKEN_FILE="${SHARP_OWNER_TOKEN_FILE:-${DATA_DIR}/owner-token.txt}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

mkdir -p \
  "${DATA_DIR}" \
  "${WORKSPACE_DIR}/inputs/.thumbnails" \
  "${WORKSPACE_DIR}/outputs" \
  "${WORKSPACE_DIR}/.photo-gallery-cache/thumbnails" \
  "${WORKSPACE_DIR}/.photo-gallery-cache/video-posters" \
  "${WORKSPACE_DIR}/.photo-gallery-cache/albums" \
	  "${TORCH_HOME}/hub/checkpoints" \
	  "${HF_HOME}" \
	  "${MPLCONFIGDIR}"

python - <<'PY'
import json
import os
import secrets

config_file = os.environ["SHARP_CONFIG_FILE"]
workspace_dir = os.environ.get("SHARP_WORKSPACE_FOLDER") or os.path.join(
    os.environ.get("SHARP_DATA_DIR", "/data"),
    "workspace",
)
owner_token_file = os.environ.get("SHARP_OWNER_TOKEN_FILE")
owner_token = os.environ.get("SHARP_OWNER_TOKEN")

if owner_token_file and not owner_token and not os.path.exists(owner_token_file):
    os.makedirs(os.path.dirname(owner_token_file), exist_ok=True)
    with open(owner_token_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(secrets.token_urlsafe(32))
        file_obj.write("\n")
    os.chmod(owner_token_file, 0o600)

config = {}
if os.path.exists(config_file):
    try:
        with open(config_file, "r", encoding="utf-8") as file_obj:
            config = json.load(file_obj)
    except Exception as exc:
        print(f"[WARN] Unable to read {config_file}: {exc}. Reinitializing container config.")

changed = False
if not config.get("workspace_folder"):
    config["workspace_folder"] = workspace_dir
    changed = True
if "photo_gallery_roots" not in config:
    config["photo_gallery_roots"] = []
    changed = True

if changed or not os.path.exists(config_file):
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as file_obj:
        json.dump(config, file_obj, indent=2, ensure_ascii=False)
        file_obj.write("\n")
PY

if [ -z "${SHARP_OWNER_TOKEN:-}" ]; then
  echo "[INFO] Docker owner token file: ${SHARP_OWNER_TOKEN_FILE}"
  echo "[INFO] Use this token in the Docker administrator verification screen."
fi

if [ "$#" -eq 0 ]; then
  set -- python /app/app.py
fi

exec "$@"

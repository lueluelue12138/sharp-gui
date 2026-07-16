#!/usr/bin/env bash
# Sharp GUI verified code updater
# Usage:
#   ./update.sh --channel stable --check
#   ./update.sh --channel stable
#   ./update.sh --channel latest
#   ./update.sh --rollback
# Legacy --pre is accepted as an alias for --channel latest.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Prefer the installation virtual environment, then a system interpreter.
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_EXE="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXE="python3"
elif command -v python &>/dev/null; then
    PYTHON_EXE="python"
else
    echo "[Error] Python was not found. Run ./install.sh first." >&2
    exit 1
fi

exec "$PYTHON_EXE" "$SCRIPT_DIR/tools/update.py" "$@"

#!/bin/sh
# Helper script to run the Sign Estimation app reliably from any location.
# Usage (from project root):
#   sh run_app.sh
# Optional env vars:
#   SIGN_APP_PORT=8060 SIGN_APP_INITIAL_CSV=Book2.csv bash run_app.sh

set -eu
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "Virtual environment Python not found at $VENV_PY" >&2
  echo "Creating virtual environment..." >&2
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3; else PYTHON_BIN=python; fi
  $PYTHON_BIN -m venv "$SCRIPT_DIR/.venv" || { echo "Failed to create venv" >&2; exit 1; }
  "$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo "Installing dependencies..." >&2
    "$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt" || { echo "Dependency install failed" >&2; exit 1; }
  fi
fi

# Show key info
echo "Using interpreter: $("$VENV_PY" -c 'import sys;print(sys.executable)')"
echo "Database: ${SIGN_APP_DB:-sign_estimation.db}" 
[ -n "${SIGN_APP_INITIAL_CSV:-}" ] && echo "Initial CSV: $SIGN_APP_INITIAL_CSV"
echo "Port: ${SIGN_APP_PORT:-8050}" 

echo "Starting app... (Ctrl+C to stop)"
exec "$VENV_PY" app.py

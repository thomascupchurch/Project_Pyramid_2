#!/usr/bin/env bash
# mac_quick_start.sh - Mac-friendly quick start & repair script for Sign Estimation App
# Usage: bash scripts/mac_quick_start.sh [--repair] [--no-run] [--python 3.11]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="python3"
ACTION_RUN=1
REPAIR=0

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repair) REPAIR=1; shift;;
    --no-run) ACTION_RUN=0; shift;;
    --python) PYTHON_BIN="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

VENV_DIR=".venv"
REQ_FILE="requirements.txt"

log(){ echo -e "[mac-quick] $*"; }
warn(){ echo -e "[mac-quick][warn] $*"; }

if [[ $REPAIR -eq 1 ]]; then
  log "Repair requested: removing existing virtual environment if present"
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtual environment ($VENV_DIR) with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  log "Using existing virtual environment ($VENV_DIR)"
fi

# Activate venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Defensive: ensure pip can run (handles distutils hack corruption)
python - <<'PY'
import sys, subprocess
try:
    import pip  # noqa: F401
except Exception as e:
    print(f"[mac-quick][repair] pip import failed: {e}; attempting ensurepip")
    subprocess.run([sys.executable, '-m', 'ensurepip', '--upgrade'], check=False)
PY

# Upgrade baseline tooling
python -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true

if [[ -f "$REQ_FILE" ]]; then
  log "Installing dependencies from $REQ_FILE"
  pip install -r "$REQ_FILE"
else
  warn "No requirements.txt found — installing core deps"
  pip install dash plotly pandas pillow reportlab cairosvg openpyxl
fi

# Environment validation subset
python scripts/verify_env.py || warn "Environment validation reported issues (see above)."

if [[ $ACTION_RUN -eq 1 ]]; then
  log "Launching app (http://127.0.0.1:8050)"
  exec python app.py
else
  log "Setup complete (skipping run per --no-run)"
fi

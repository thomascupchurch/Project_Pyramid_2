#!/usr/bin/env bash
set -euo pipefail

echo "[mac-setup] Starting macOS environment bootstrap..."

PYTHON_BIN=${PYTHON_BIN:-python3}
VENV_DIR=${VENV_DIR:-.venv-mac}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[mac-setup][error] Python executable '$PYTHON_BIN' not found in PATH" >&2
  exit 1
fi

echo "[mac-setup] Using Python: $($PYTHON_BIN -V 2>&1)"

if [ ! -d "$VENV_DIR" ]; then
  echo "[mac-setup] Creating virtual environment in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[mac-setup] Activating venv"
source "$VENV_DIR/bin/activate"

echo "[mac-setup] Upgrading pip"
python -m pip install --upgrade pip >/dev/null

echo "[mac-setup] Installing requirements"
pip install -r requirements.txt

if [ "${INSTALL_CAIROSVG:-0}" = "1" ]; then
  echo "[mac-setup] Installing native cairo dependencies via Homebrew (requires brew)"
  if ! command -v brew >/dev/null 2>&1; then
    echo "[mac-setup][warn] Homebrew not found; skipping native cairo install." >&2
  else
    brew list cairo >/dev/null 2>&1 || brew install cairo || true
    brew list pango >/dev/null 2>&1 || brew install pango || true
    brew list libffi >/dev/null 2>&1 || brew install libffi || true
    brew list pkg-config >/dev/null 2>&1 || brew install pkg-config || true
    echo "[mac-setup] Reinstalling cairosvg to bind to native libs"
    pip install --force-reinstall cairosvg
  fi
fi

echo "[mac-setup] Verifying environment"
python scripts/verify_env.py --json || true

echo "[mac-setup] Launching application (Ctrl+C to stop)"
exec python app.py

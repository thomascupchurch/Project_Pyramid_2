#!/usr/bin/env bash
# Cross-platform (macOS/Linux) launcher for Sign Estimation App
# Mirrors start_app.ps1 functionality where possible.
set -euo pipefail

# --- Resolve script directory ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if command -v py >/dev/null 2>&1; then
  PYTHON_BIN="py"
fi

# --- Virtual environment ---
if [ ! -d ".venv" ]; then
  echo "[setup] creating virtual environment (.venv)"
  $PYTHON_BIN -m venv .venv
fi
source .venv/bin/activate

# --- Dependencies (lazy install if requirements changed) ---
REQ_HASH_FILE=.venv/requirements.sha1
if [ -f requirements.txt ]; then
  CUR_HASH=$(shasum requirements.txt | awk '{print $1}')
  OLD_HASH=""
  [ -f "$REQ_HASH_FILE" ] && OLD_HASH=$(cat "$REQ_HASH_FILE") || true
  if [ "$CUR_HASH" != "$OLD_HASH" ]; then
    echo "[deps] Installing/updating requirements"
    pip install --upgrade pip >/dev/null 2>&1 || true
    pip install -r requirements.txt
    echo "$CUR_HASH" > "$REQ_HASH_FILE"
  fi
fi

# --- Optional cairo / SVG environment ---
# If user has installed cairo via Homebrew it will typically live under /opt/homebrew for arm64.
if command -v brew >/dev/null 2>&1; then
  CAIRO_PKG_DIR=$(brew --prefix cairo 2>/dev/null || true)
  if [ -n "$CAIRO_PKG_DIR" ] && [ -d "$CAIRO_PKG_DIR/lib" ]; then
    export DYLD_FALLBACK_LIBRARY_PATH="$CAIRO_PKG_DIR/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
  fi
fi

# Allow user override to disable SVG rendering
export DISABLE_SVG_RENDER=${DISABLE_SVG_RENDER:-0}

# Explicit backend hint if cairosvg present
python - <<'PY'
try:
    import cairosvg  # noqa
    print('[env] cairosvg available')
except Exception:
    print('[env] cairosvg not available (SVG rasterization disabled)')
PY

# --- Launch application ---
exec python app.py

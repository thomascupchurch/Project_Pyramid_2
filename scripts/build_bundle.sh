#!/usr/bin/env bash
set -euo pipefail
if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "PyInstaller not installed. Run: pip install pyinstaller" >&2
  exit 1
fi
SPEC=sign_estimator.spec
if [[ "${1:-}" == "--console" ]]; then
  SPEC=sign_estimator_console.spec
fi
pyinstaller "$SPEC" --noconfirm
echo "Bundle created under dist (spec: $SPEC)"

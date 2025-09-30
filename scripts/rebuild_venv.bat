@echo off
setlocal
REM Rebuild .venv (cross-platform mismatch repair helper)
if "%~1"=="" (
  echo Usage: %~nx0 [--force] [--yes] [--dry-run] [--json]
  echo Examples:
  echo   %~nx0 --dry-run
  echo   %~nx0 --force --yes
)
python scripts\rebuild_venv.py %*
endlocal

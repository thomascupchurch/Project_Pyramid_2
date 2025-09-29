@echo off
REM ---------------------------------------------------------------------------
REM  deploy_fast.bat
REM  Minimal fast deployment wrapper.
REM  Copies only changed files (hash manifest) + optional prune.
REM  Skips: backups, archives, log aggregation (unless explicitly added).
REM ---------------------------------------------------------------------------
REM  Usage:
REM    deploy_fast.bat          (just push changes quickly)
REM    deploy_fast.bat --prune  (also remove orphans)
REM    deploy_fast.bat --force  (force full copy)
REM    deploy_fast.bat --help   (show help)
REM ---------------------------------------------------------------------------

setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%.." >NUL
set REPO_ROOT=%CD%

set VENV1=%REPO_ROOT%\.venv\Scripts\python.exe
set VENV2=%REPO_ROOT%\activate\Scripts\python.exe
if exist "%VENV1%" (
  set PYTHON_EXE=%VENV1%
) else if exist "%VENV2%" (
  set PYTHON_EXE=%VENV2%
) else (
  for /f "usebackq delims=" %%P in (`where python 2^>NUL`) do (
    if not defined PYTHON_EXE set PYTHON_EXE=%%P
  )
)
if not defined PYTHON_EXE (
  echo [deploy_fast] ERROR: Python interpreter not found.>&2
  popd >NUL
  exit /b 1
)

set CMD="%PYTHON_EXE%" scripts\deploy.py
if not "%*"=="" (
  set CMD=%CMD% %*
)

echo --- Fast Deploy ---
echo Repo Root : %REPO_ROOT%
echo Python    : %PYTHON_EXE%
echo Extra Args: %*
echo -------------------

%CMD%
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% NEQ 0 (
  echo [deploy_fast] Deployment FAILED (exit %EXITCODE%).>&2
) else (
  echo [deploy_fast] Done.
)

popd >NUL
exit /b %EXITCODE%

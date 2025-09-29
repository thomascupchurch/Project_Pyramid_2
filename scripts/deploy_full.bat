@echo off
REM ---------------------------------------------------------------------------
REM  deploy_full.bat
REM  Convenience wrapper for the standard full deployment workflow.
REM  Applies: backup with retention, log aggregation, prune orphans, archive
REM  previous version, then copies only changed files using hash manifest.
REM ---------------------------------------------------------------------------
REM  Usage:
REM    deploy_full.bat               (run with standard flags)
REM    deploy_full.bat --force       (add extra flags)
REM    deploy_full.bat --help        (show deploy.py help after defaults)
REM    deploy_full.bat --no-defaults <your flags>
REM
REM  Any arguments you pass are appended AFTER the standard flag set unless
REM  you include --no-defaults as the first argument, in which case only the
REM  arguments you supply are used.
REM ---------------------------------------------------------------------------

setlocal enabledelayedexpansion

REM Determine repository root (this script is expected inside scripts/)
set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%.." >NUL
set REPO_ROOT=%CD%

REM Candidate virtual environments
set VENV1=%REPO_ROOT%\.venv\Scripts\python.exe
set VENV2=%REPO_ROOT%\activate\Scripts\python.exe

REM Pick python interpreter
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
  echo [deploy_full] ERROR: Could not find a Python interpreter.>&2
  echo Looked for .venv, activate, and system python.>&2
  popd >NUL
  exit /b 1
)

REM Default flag set
set DEFAULT_FLAGS=--backup-db --backup-retention 7 --collect-logs --prune --archive

REM Handle --no-defaults override
set USE_DEFAULTS=1
if "%~1"=="--no-defaults" (
  set USE_DEFAULTS=0
  shift
)

REM Build final command
set CMD="%PYTHON_EXE%" scripts\deploy.py
if %USE_DEFAULTS%==1 (
  set CMD=%CMD% %DEFAULT_FLAGS%
)
if not "%*"=="" (
  set CMD=%CMD% %*
)

REM Show what will run
echo ---------------------------------------------------------------------------
echo Running deployment from: %REPO_ROOT%
echo Using Python: %PYTHON_EXE%
if %USE_DEFAULTS%==1 (
  echo Applied default flags: %DEFAULT_FLAGS%
) else (
  echo Default flags suppressed (--no-defaults)
)
echo Additional args: %*
echo ---------------------------------------------------------------------------

%CMD%
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% NEQ 0 (
  echo [deploy_full] Deployment FAILED (exit %EXITCODE%).>&2
) else (
  echo [deploy_full] Deployment completed successfully.
)

popd >NUL
exit /b %EXITCODE%

@echo off
REM -------------------------------------------------------------
REM Sign Estimation App Launcher (Windows)
REM Supports optional environment variables before calling:
REM   SET SIGN_APP_PORT=8060
REM   SET SIGN_APP_DB=shared_signs.db
REM   SET SIGN_APP_INITIAL_CSV=Book2.csv
REM Then run:
REM   run_app.bat
REM -------------------------------------------------------------

SETLOCAL ENABLEDELAYEDEXPANSION

REM Determine script directory (handles spaces)
SET "SCRIPT_DIR=%~dp0"
PUSHD "%SCRIPT_DIR%"

REM Virtual environment python
SET "VENV_PY=.venv\Scripts\python.exe"
IF NOT EXIST "%VENV_PY%" (
  echo [!] Virtual environment not found at %VENV_PY%
  echo     Create it with:
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  EXIT /B 1
)

REM Defaults if not provided
IF NOT DEFINED SIGN_APP_PORT SET "SIGN_APP_PORT=8050"
IF NOT DEFINED SIGN_APP_DB SET "SIGN_APP_DB=sign_estimation.db"

ECHO --------------------------------------------
ECHO Launching Sign Estimation App
ECHO Python: %VENV_PY%
ECHO Database: %SIGN_APP_DB%
IF DEFINED SIGN_APP_INITIAL_CSV ECHO Initial CSV: %SIGN_APP_INITIAL_CSV%
ECHO Port: %SIGN_APP_PORT%
ECHO Working Dir: %SCRIPT_DIR%
ECHO --------------------------------------------

REM Pass environment through; app reads SIGN_APP_* directly
"%VENV_PY%" app.py

IF ERRORLEVEL 1 (
  ECHO.
  ECHO [!] Application exited with errors (code %ERRORLEVEL%).
) ELSE (
  ECHO.
  ECHO Application exited normally.
)

POPD
ENDLOCAL

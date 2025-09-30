@echo off
REM Optional flag: /HIDEENV suppresses environment notice banner inside the app
SET "HIDEENV=0"
FOR %%A IN (%*) DO (
  IF /I "%%~A"=="/HIDEENV" SET "HIDEENV=1"
)
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
SET "VENV_DIR=.venv"
SET "VENV_PY=%VENV_DIR%\Scripts\python.exe"

IF NOT EXIST "%VENV_PY%" (
  echo [setup] Virtual environment missing – attempting to create at %VENV_DIR%
  WHERE py >nul 2>&1
  IF %ERRORLEVEL%==0 (
    py -3 -m venv "%VENV_DIR%" || (
      echo [error] Failed to create venv with py launcher.& EXIT /B 2
    )
  ) ELSE (
    WHERE python >nul 2>&1 || (echo [error] Neither 'py' nor 'python' command found in PATH. Install Python 3.11+ first. & EXIT /B 3)
    python -m venv "%VENV_DIR%" || (echo [error] Failed to create venv with python.& EXIT /B 4)
  )
)

IF NOT EXIST "%VENV_PY%" (
  echo [error] Python executable still not found at %VENV_PY% after creation attempt.
  echo         Ensure anti-virus/OneDrive did not block file creation.
  EXIT /B 5
)

REM Bootstrap dependencies if needed (simple heuristic: check pip presence of dash)
"%VENV_PY%" -c "import dash" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
  echo [deps] Installing required packages (this may take a moment)...
  "%VENV_PY%" -m pip install --upgrade pip setuptools wheel >nul 2>&1
  IF EXIST requirements.txt (
    "%VENV_PY%" -m pip install -r requirements.txt || (echo [error] pip install failed.& EXIT /B 6)
  ) ELSE (
    echo [warn] requirements.txt not found – proceeding without dependency sync.
  )
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
IF "%HIDEENV%"=="1" ECHO (Environment notice suppressed)
ECHO --------------------------------------------

REM Pass environment through; app reads SIGN_APP_* directly
IF "%HIDEENV%"=="1" SET "SIGN_APP_HIDE_ENV_NOTICE=1"
"%VENV_PY%" app.py %*

IF ERRORLEVEL 1 (
  ECHO.
  ECHO [!] Application exited with errors (code %ERRORLEVEL%).
) ELSE (
  ECHO.
  ECHO Application exited normally.
)

POPD
ENDLOCAL

@echo off
REM Optional flag: /HIDEENV suppresses environment notice banner
SET "HIDEENV=0"
FOR %%A IN (%*) DO (
  IF /I "%%~A"=="/HIDEENV" SET "HIDEENV=1"
)
REM Simple launcher for Sign Package Estimator (Windows LAN / OneDrive)
SETLOCAL ENABLEDELAYEDEXPANSION
cd /d %~dp0

SET "VENV_DIR=.venv"
SET "VENV_PY=%VENV_DIR%\Scripts\python.exe"

IF NOT EXIST "%VENV_PY%" (
  echo [setup] Creating virtual environment (first run)...
  WHERE py >nul 2>&1
  IF %ERRORLEVEL%==0 (
    py -3 -m venv "%VENV_DIR%" || (echo [error] Failed to create venv with py.& EXIT /B 2)
  ) ELSE (
    WHERE python >nul 2>&1 || (echo [error] Python not found. Install from https://www.python.org/downloads/ and re-run.& EXIT /B 3)
    python -m venv "%VENV_DIR%" || (echo [error] Failed to create venv with python.& EXIT /B 4)
  )
)

IF NOT EXIST "%VENV_PY%" (
  echo [error] Python executable missing after venv creation (%VENV_PY%)
  EXIT /B 5
)

echo [deps] Verifying core packages...
"%VENV_PY%" -c "import dash" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
  echo [deps] Installing requirements (one-time)...
  "%VENV_PY%" -m pip install --upgrade pip setuptools wheel >nul 2>&1
  IF EXIST requirements.txt (
    "%VENV_PY%" -m pip install -r requirements.txt || (echo [error] pip install failed.& EXIT /B 6)
  ) ELSE (
    echo [warn] requirements.txt missing – proceeding anyway.
  )
)

echo --------------------------------------------
echo Launching Sign Package Estimator
echo Python     : %VENV_PY%
echo Port       : %SIGN_APP_PORT: =% (default 8050 if unset)
echo Working Dir: %CD%
IF "%HIDEENV%"=="1" echo (Environment notice suppressed)
echo --------------------------------------------
IF "%HIDEENV%"=="1" SET "SIGN_APP_HIDE_ENV_NOTICE=1"
"%VENV_PY%" app.py %*

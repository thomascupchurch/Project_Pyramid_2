@echo off
setlocal enabledelayedexpansion

REM Sign Estimation App Environment Bootstrap
REM Creates/updates a per-user virtual environment outside OneDrive and installs dependencies only when requirements changed.

set APP_NAME=SignEstimator
set REQUIREMENTS=requirements.txt
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-FileHash %REQUIREMENTS% -Algorithm SHA256).Hash"') do set REQ_HASH=%%i

set BASE_DIR=%LOCALAPPDATA%\%APP_NAME%
set VENV_DIR=%BASE_DIR%\venv
set HASH_FILE=%BASE_DIR%\requirements.sha256

if not exist "%BASE_DIR%" mkdir "%BASE_DIR%"

REM Detect python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python not found. Install Python 3.11+ and re-run.
    exit /b 1
  ) else (
    set PY_CMD=py -3
  )
) else (
  set PY_CMD=python
)

if not defined PY_CMD set PY_CMD=python

if not exist "%VENV_DIR%" (
  echo Creating virtual environment...
  %PY_CMD% -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat" || (
  echo Failed to activate venv.
  exit /b 1
)

REM Compare hash
set NEED_INSTALL=1
if exist "%HASH_FILE%" (
  set /p OLD_HASH=<"%HASH_FILE%"
  if /i "%OLD_HASH%"=="%REQ_HASH%" set NEED_INSTALL=0
)

if %NEED_INSTALL%==1 (
  echo Installing/Updating dependencies...
  python -m pip install --upgrade pip >nul 2>&1
  if exist wheelhouse (
    python -m pip install --no-index --find-links=wheelhouse -r %REQUIREMENTS%
  ) else (
    python -m pip install -r %REQUIREMENTS%
  )
  echo %REQ_HASH%>"%HASH_FILE%"
) else (
  echo Dependencies up-to-date.
)

echo Environment ready.
endlocal

@echo off
REM Minimal reliable launcher (supports /CHECK and /HIDEENV). No complex flow to avoid parser issues.

SETLOCAL
SET "SCRIPT_DIR=%~dp0"
PUSHD "%SCRIPT_DIR%" >NUL 2>&1

SET "VENV_PY=.venv\Scripts\python.exe"
IF NOT EXIST "%VENV_PY%" (
  echo [setup] Creating virtual environment (.venv)
  WHERE py >NUL 2>&1 && (py -3 -m venv .venv) || (python -m venv .venv)
)
IF NOT EXIST "%VENV_PY%" (
  echo [error] Could not find or create .venv\Scripts\python.exe
  echo         Ensure Python 3.10+ is installed and added to PATH: https://www.python.org/downloads/
  WHERE py >NUL 2>&1 || WHERE python >NUL 2>&1 || (
     echo [hint] Neither 'py' launcher nor 'python' command detected.
  )
  EXIT /B 2
)

REM Flag scan (string match)
SET "CHECKONLY=0"
SET "HIDEENV=0"
ECHO %* | FINDSTR /I "/CHECK"   >NUL 2>&1 && SET "CHECKONLY=1"
ECHO %* | FINDSTR /I "/DRYRUN"  >NUL 2>&1 && SET "CHECKONLY=1"
ECHO %* | FINDSTR /I "/HIDEENV" >NUL 2>&1 && SET "HIDEENV=1"
IF "%HIDEENV%"=="1" SET "SIGN_APP_HIDE_ENV_NOTICE=1"

REM Dependency probe
"%VENV_PY%" -c "import dash" >NUL 2>&1 || (
  echo [deps] Installing requirements...
  "%VENV_PY%" -m pip install --upgrade pip setuptools wheel >NUL 2>&1
  IF EXIST requirements.txt "%VENV_PY%" -m pip install -r requirements.txt || (echo [error] pip install failed & EXIT /B 3)
)

IF NOT DEFINED SIGN_APP_PORT SET "SIGN_APP_PORT=8050"
IF NOT DEFINED SIGN_APP_DB SET "SIGN_APP_DB=sign_estimation.db"

echo --------------------------------------------
echo Sign Estimation App
echo Python   : %VENV_PY%
echo Port     : %SIGN_APP_PORT%
echo Database : %SIGN_APP_DB%
IF "%HIDEENV%"=="1" echo (Environment notice suppressed)
echo --------------------------------------------

IF "%CHECKONLY%"=="1" (
  echo [info] CHECK mode: environment looks OK.
  POPD
  ENDLOCAL & EXIT /B 0
)

"%VENV_PY%" app.py %*
SET "CODE=%ERRORLEVEL%"
POPD
ENDLOCAL & EXIT /B %CODE%

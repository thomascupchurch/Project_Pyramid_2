@echo off
setlocal enabledelayedexpansion
REM ---------------------------------------------------------------------------
REM  deploy_and_bundle.bat
REM  One-step build (PyInstaller GUI bundle) + full deploy to OneDrive.
REM  Auto-detects OneDrive path if not provided; always rebuilds bundle.
REM ---------------------------------------------------------------------------

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%.." >NUL
set REPO_ROOT=%CD%

REM Pick python (prefer local venv if present)
set PY_EXE=
if exist .venv\Scripts\python.exe set PY_EXE=.venv\Scripts\python.exe
if exist activate\Scripts\python.exe set PY_EXE=activate\Scripts\python.exe
if not defined PY_EXE for /f "usebackq delims=" %%P in (`where python 2^>NUL`) do if not defined PY_EXE set PY_EXE=%%P
if not defined PY_EXE (
  echo [deploy_and_bundle] ERROR: No Python interpreter found.&goto :EOF
)

echo === Building GUI bundle (fresh) ===
"%PY_EXE%" -m pip show pyinstaller >nul 2>nul || (echo Installing PyInstaller... & "%PY_EXE%" -m pip install pyinstaller || goto :FAIL)

REM Clean previous build artifacts for a guaranteed fresh bundle
if exist build rd /s /q build
if exist dist rd /s /q dist

"%PY_EXE%" -m PyInstaller sign_estimator.spec --noconfirm || goto :FAIL

echo === Running full deploy with bundle ===
"%PY_EXE%" scripts\deploy.py --bundle --backup-db --backup-retention 7 --collect-logs --prune --archive %*
if errorlevel 1 goto :FAIL

echo.
echo [SUCCESS] Bundle built and deployment completed.
echo Your coworker can now run start_app.bat from the shared OneDrive folder.
goto :EOF

:FAIL
echo [FAIL] Deployment process aborted. See messages above.
exit /b 1

endlocal

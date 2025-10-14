@echo off
setlocal
REM Build PyInstaller bundle (folder or one-file)
REM Can be run from repo root or from the scripts folder.
REM Usage:
REM   scripts\build_bundle.bat                         -> folder bundle (spec: sign_estimator.spec)
REM   scripts\build_bundle.bat --console               -> folder bundle with console
REM   scripts\build_bundle.bat --onefile               -> one-file EXE (spec: sign_estimator_onefile.spec)
REM   scripts\build_bundle.bat --onefile --update-shortcuts   -> (explicit) refresh Desktop/Start Menu shortcuts after build
REM   scripts\build_bundle.bat --onefile --no-update-shortcuts -> (opt-out) skip shortcut refresh after build

REM Normalize working directory to repo root
pushd "%~dp0\.." >nul 2>nul
set "ROOT=%CD%"
echo [info] Repo root: "%ROOT%"

REM Use Python module invocation for PyInstaller to avoid broken shims
set USE_MODULE=1

set SPEC=sign_estimator.spec
set UPDATE_SHORTCUTS=0
set UPDATE_EXPLICIT=0

for %%A in (%*) do (
	if /i "%%~A"=="--console" set SPEC=sign_estimator_console.spec
	if /i "%%~A"=="--onefile" set SPEC=sign_estimator_onefile.spec
	if /i "%%~A"=="--update-shortcuts" (set UPDATE_SHORTCUTS=1 & set UPDATE_EXPLICIT=1)
	if /i "%%~A"=="--no-update-shortcuts" (set UPDATE_SHORTCUTS=0 & set UPDATE_EXPLICIT=1)
)

REM Default behavior: for one-file builds, auto-update shortcuts unless user opted out
if /i "%SPEC%"=="sign_estimator_onefile.spec" (
	if "%UPDATE_EXPLICIT%"=="0" set UPDATE_SHORTCUTS=1
)

REM Resolve Python executable
set "USE_PY_LAUNCHER=0"
set "PYEXE="
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYEXE=%ROOT%\.venv\Scripts\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\SignEstimator\venv\Scripts\python.exe" set "PYEXE=%LOCALAPPDATA%\SignEstimator\venv\Scripts\python.exe"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE where py >nul 2>nul && set "USE_PY_LAUNCHER=1"
if not defined PYEXE if "%USE_PY_LAUNCHER%"=="0" (
	echo [error] Python was not found. Install Python 3.x, or create a .venv, or ensure the py launcher is available.
	echo         Tried: .venv, per-user venv, system python, and py launcher.
	goto :fail
)

REM Verify Python is callable (avoid broken Store shims)
set "PY_OK=1"
call "%PYEXE%" -V >nul 2>&1
if errorlevel 1 (
	set "PY_OK=0"
	echo [warn] Python at "%PYEXE%" failed to run.
) else (
	for /f "usebackq tokens=*" %%V in (`"%PYEXE%" -V 2^>^&1`) do echo [info] Python version: %%V
)

REM If Python is broken and we already have a one-file EXE, skip build and refresh shortcuts
if %PY_OK%==0 (
	if /i "%SPEC%"=="sign_estimator_onefile.spec" if exist "%ROOT%\dist\sign_estimator.exe" (
		echo [warn] Python executable appears broken. Skipping rebuild and refreshing shortcuts for existing EXE.
		set UPDATE_SHORTCUTS=1
		goto :post_build
	)
)

REM Ensure icon exists for onefile build (optional)
if /i "%SPEC%"=="sign_estimator_onefile.spec" (
	if not exist "%ROOT%\assets\LSI_Logo.ico" (
		if %PY_OK%==1 (
			echo [info] Generating icon from SVG...
			"%PYEXE%" "%ROOT%\scripts\generate_icon.py" || echo [warn] Icon generation failed; proceeding without custom icon
		) else (
			echo [warn] Skipping icon generation due to unavailable Python.
		)
	)
)

if "%USE_PY_LAUNCHER%"=="1" (
	echo [info] Using Python via py launcher
) else (
	echo [info] Using Python: "%PYEXE%"
)

if %PY_OK%==0 (
	echo [error] Python is unavailable and no existing bundle can be built.
	goto :fail
) else (
	echo [info] Running: "%PYEXE%" -m PyInstaller %SPEC%
	set PYTHONNOUSERSITE=1
	set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
	"%PYEXE%" -m PyInstaller %SPEC% --noconfirm || (echo Build failed & goto :fail)
)
echo Bundle created under dist (spec: %SPEC%)

REM Optionally update shortcuts after a successful build
:post_build
if %UPDATE_SHORTCUTS%==1 (
	set "PS1=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
	if exist "%PS1%" (
		"%PS1%" -ExecutionPolicy Bypass -NoLogo -NoProfile -File "%ROOT%\scripts\post_build_update_shortcuts.ps1" || echo [warn] Shortcut update failed
	) else (
		rem Fallback to powershell in PATH if system32 path missing
		where powershell >nul 2>nul && powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File "%ROOT%\scripts\post_build_update_shortcuts.ps1" || echo [warn] powershell.exe not found; skipping shortcut update
	)
)
goto :done

:fail
echo.
echo Hints:
echo  - If the failure mentions 'No module named PyInstaller' or uninstall-no-record-file, run:
echo    "%PYEXE%" -m pip install --force-reinstall --no-deps pyinstaller==6.11.0
echo    or run the helper: powershell -ExecutionPolicy Bypass -File scripts\repair_and_build.ps1
echo  - If Python points to a broken Windows Store shim, recreate the venv:
echo    PowerShell: scripts\rebuild_venv.ps1 -Rebuild -Force
popd >nul 2>nul
endlocal & exit /b 1

:done
popd >nul 2>nul
endlocal & exit /b 0

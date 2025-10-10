@echo off
setlocal
REM Build PyInstaller bundle (folder or one-file)
REM Usage:
REM   scripts\build_bundle.bat                         -> folder bundle (spec: sign_estimator.spec)
REM   scripts\build_bundle.bat --console               -> folder bundle with console
REM   scripts\build_bundle.bat --onefile               -> one-file EXE (spec: sign_estimator_onefile.spec)
REM   scripts\build_bundle.bat --onefile --update-shortcuts   -> (explicit) refresh Desktop/Start Menu shortcuts after build
REM   scripts\build_bundle.bat --onefile --no-update-shortcuts -> (opt-out) skip shortcut refresh after build

where pyinstaller >nul 2>nul
if errorlevel 1 (
	echo [info] pyinstaller not found on PATH. Will attempt python -m PyInstaller.
	set USE_MODULE=1
) else (
	set USE_MODULE=0
)

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

REM Ensure icon exists for onefile build (optional)
if /i "%SPEC%"=="sign_estimator_onefile.spec" (
	if not exist assets\LSI_Logo.ico (
		echo [info] Generating icon from SVG...
		python scripts\generate_icon.py || echo [warn] Icon generation failed; proceeding without custom icon
	)
)

if %USE_MODULE%==1 (
	python -m PyInstaller %SPEC% --noconfirm || (echo Build failed & exit /b 1)
) else (
	pyinstaller %SPEC% --noconfirm || (echo Build failed & exit /b 1)
)
echo Bundle created under dist (spec: %SPEC%)

REM Optionally update shortcuts after a successful build
if %UPDATE_SHORTCUTS%==1 (
	set PS1=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
	if exist "%PS1%" (
		"%PS1%" -ExecutionPolicy Bypass -NoLogo -NoProfile -File scripts\post_build_update_shortcuts.ps1 || echo [warn] Shortcut update failed
	) else (
		echo [warn] powershell.exe not found; skipping shortcut update
	)
)
endlocal

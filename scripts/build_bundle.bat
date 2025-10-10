@echo off
setlocal
REM Build PyInstaller bundle (folder or one-file)
REM Usage:
REM   scripts\build_bundle.bat                -> folder bundle (spec: sign_estimator.spec)
REM   scripts\build_bundle.bat --console      -> folder bundle with console
REM   scripts\build_bundle.bat --onefile      -> one-file EXE (spec: sign_estimator_onefile.spec)

where pyinstaller >nul 2>nul
if errorlevel 1 (
	echo [info] pyinstaller not found on PATH. Will attempt python -m PyInstaller.
	set USE_MODULE=1
) else (
	set USE_MODULE=0
)

set SPEC=sign_estimator.spec
if /i "%1"=="--console" set SPEC=sign_estimator_console.spec
if /i "%1"=="--onefile" set SPEC=sign_estimator_onefile.spec

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
endlocal

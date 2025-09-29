@echo off
setlocal
REM Build PyInstaller bundle
REM Try where first; if missing fallback to python -m PyInstaller invocation
where pyinstaller >nul 2>nul
if errorlevel 1 (
	echo [info] pyinstaller not found on PATH. Will attempt python -m PyInstaller.
	set USE_MODULE=1
) else (
	set USE_MODULE=0
)
set SPEC=sign_estimator.spec
if /i "%1"=="--console" set SPEC=sign_estimator_console.spec
if %USE_MODULE%==1 (
	python -m PyInstaller %SPEC% --noconfirm || (echo Build failed & exit /b 1)
) else (
	pyinstaller %SPEC% --noconfirm || (echo Build failed & exit /b 1)
)
echo Bundle created under dist (spec: %SPEC%)
endlocal

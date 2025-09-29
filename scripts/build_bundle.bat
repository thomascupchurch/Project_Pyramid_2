@echo off
setlocal
REM Build PyInstaller bundle
where pyinstaller >nul 2>nul || (echo PyInstaller not installed. Run: pip install pyinstaller & exit /b 1)
set SPEC=sign_estimator.spec
if /i "%1"=="--console" set SPEC=sign_estimator_console.spec
pyinstaller %SPEC% --noconfirm || (echo Build failed & exit /b 1)
echo Bundle created under dist (spec: %SPEC%)
endlocal

@echo off
setlocal
REM Launch script for Sign Estimation App
pushd %~dp0\..
call scripts\setup_env.bat || (echo Setup failed & exit /b 1)
set APP_NAME=SignEstimator
set BASE_DIR=%LOCALAPPDATA%\%APP_NAME%
set VENV_DIR=%BASE_DIR%\venv
call "%VENV_DIR%\Scripts\activate.bat" || (echo Could not activate env & exit /b 1)
REM Optional environment variables
if not defined ONEDRIVE_AUTOSYNC_SEC set ONEDRIVE_AUTOSYNC_SEC=300
REM Start app
start "Sign Estimation" python app.py
popd
endlocal

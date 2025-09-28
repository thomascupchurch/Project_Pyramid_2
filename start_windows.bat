@echo off
REM Simple launcher for Sign Estimation Tool (Windows LAN / OneDrive)
SETLOCAL ENABLEDELAYEDEXPANSION
cd /d %~dp0

IF NOT EXIST .venv (
  echo Creating virtual environment...
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing/Updating dependencies (cached where possible)...
python -m pip install --upgrade pip >nul 2>&1
IF EXIST requirements.txt (
  pip install -r requirements.txt
)
echo Starting app on http://localhost:8050 (or configured port) ...
echo Press Ctrl+C in this window to stop.
python app.py

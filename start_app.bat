@echo off
REM Thin wrapper kept for backward compatibility; delegates to run_app.bat
SETLOCAL
cd /d %~dp0
IF EXIST run_app.bat (
  call run_app.bat %*
) ELSE (
  ECHO run_app.bat missing. Falling back to python app.py
  IF EXIST .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app.py %*
  ) ELSE (
    python app.py %*
  )
)
ENDLOCAL
@echo off
rem Legacy backup of previous complex launcher before simplification.
copy run_app.bat "run_app_original_%DATE:/=-%_%TIME::=-%.bak" >nul 2>&1
echo Backup captured (best-effort).
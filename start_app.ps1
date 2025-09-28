<#
PowerShell launcher for Sign Estimation Application
Usage examples:
  ./start_app.ps1
  $env:SIGN_APP_PORT=8060; ./start_app.ps1
  $env:SIGN_APP_INITIAL_CSV="Book2.csv"; ./start_app.ps1
#>

param(
  [int]$Port = $env:SIGN_APP_PORT,
  [string]$Database = $env:SIGN_APP_DB,
  [string]$InitialCsv = $env:SIGN_APP_INITIAL_CSV
)

# Resolve script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvPy = Join-Path $ScriptDir '.venv/Windows/Scripts/python.exe'
if (-not (Test-Path $VenvPy)) { $VenvPy = Join-Path $ScriptDir '.venv/Scripts/python.exe' }
if (-not (Test-Path $VenvPy)) { $VenvPy = Join-Path $ScriptDir '.venv/bin/python' }

if (-not (Test-Path $VenvPy)) {
  Write-Host "Virtual environment not found. Create it:" -ForegroundColor Yellow
  Write-Host "python -m venv .venv" -ForegroundColor Gray
  Write-Host ".venv/Scripts/python.exe -m pip install -r requirements.txt" -ForegroundColor Gray
  exit 1
}

if (-not $Port) { $Port = 8050 }
if (-not $Database) { $Database = 'sign_estimation.db' }

Write-Host "--------------------------------------------" -ForegroundColor Cyan
Write-Host "Launching Sign Estimation App" -ForegroundColor Green
Write-Host "Python     : $VenvPy"
Write-Host "Database   : $Database"
if ($InitialCsv) { Write-Host "Initial CSV: $InitialCsv" }
Write-Host "Port       : $Port"
Write-Host "Working Dir: $ScriptDir"
Write-Host "--------------------------------------------" -ForegroundColor Cyan

# Pass env vars through for the app to consume
$env:SIGN_APP_PORT = $Port
$env:SIGN_APP_DB = $Database
if ($InitialCsv) { $env:SIGN_APP_INITIAL_CSV = $InitialCsv }

& $VenvPy app.py
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Host "App exited with code $code" -ForegroundColor Red
} else {
  Write-Host "App exited normally" -ForegroundColor Green
}
exit $code

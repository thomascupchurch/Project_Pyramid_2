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
  [string]$InitialCsv = $env:SIGN_APP_INITIAL_CSV,
  [switch]$ForceReinstall,
  [switch]$HideEnvNotice
)

# Resolve script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ------------------------------------------------------------------
# Per-user virtual environment management (outside synced directory)
# ------------------------------------------------------------------
$AppName = 'SignEstimator'
$UserBase = Join-Path $env:LOCALAPPDATA $AppName
if (-not (Test-Path $UserBase)) { New-Item -ItemType Directory -Path $UserBase | Out-Null }
$UserVenv = Join-Path $UserBase 'venv'
$MarkerDir = Join-Path $UserVenv 'markers'
if (-not (Test-Path $MarkerDir)) { New-Item -ItemType Directory -Path $MarkerDir | Out-Null }

$ReqFile = Join-Path $ScriptDir 'requirements.txt'
if (-not (Test-Path $ReqFile)) { Write-Host 'requirements.txt missing – aborting.' -ForegroundColor Red; exit 1 }

# Compute hash of requirements to decide rebuild
function Get-FileHashString {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return '' }
  (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()
}

$ReqHash = Get-FileHashString -Path $ReqFile
$ReqMarker = Join-Path $MarkerDir ("requirements_" + $ReqHash + '.ok')

function New-PerUserVenv {
  param([string]$Path)
  Write-Host "[venv] Creating per-user venv at $Path" -ForegroundColor Yellow
  try {
    python -m venv "$Path"
  } catch {
    Write-Host "[venv] Failed to create venv: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
  }
  & (Join-Path $Path 'Scripts/python.exe') -m pip install --upgrade pip setuptools wheel
}

if ($ForceReinstall -and (Test-Path $UserVenv)) {
  Write-Host '[venv] ForceReinstall specified – removing existing venv' -ForegroundColor Yellow
  Remove-Item -Recurse -Force $UserVenv
}

if (-not (Test-Path (Join-Path $UserVenv 'Scripts/python.exe'))) {
  New-PerUserVenv -Path $UserVenv
}

$PerUserPy = Join-Path $UserVenv 'Scripts/python.exe'
if (-not (Test-Path $PerUserPy)) { Write-Host '[venv] Python executable missing after creation.' -ForegroundColor Red; exit 3 }

# Install / update dependencies if hash marker absent
if (-not (Test-Path $ReqMarker)) {
  Write-Host '[deps] Installing / updating dependencies...' -ForegroundColor Cyan
  try {
    & $PerUserPy -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) { throw "pip exited with code $LASTEXITCODE" }
  } catch {
    Write-Host "[deps] pip install failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 4
  }
  # Cleanup old markers (best effort)
  Get-ChildItem $MarkerDir -Filter 'requirements_*.ok' -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }
  New-Item -ItemType File -Path $ReqMarker -ErrorAction SilentlyContinue | Out-Null
  Write-Host "[deps] Dependencies synced (hash $ReqHash)" -ForegroundColor Green
} else {
  Write-Host '[deps] Requirements unchanged – skipping reinstall.' -ForegroundColor DarkGray
}

$VenvPy = $PerUserPy

if (-not $Port) { $Port = 8050 }
if (-not $Database) { $Database = 'sign_estimation.db' }

Write-Host "--------------------------------------------" -ForegroundColor Cyan
Write-Host "Launching Sign Estimation App" -ForegroundColor Green
Write-Host "Python     : $VenvPy (per-user)"
Write-Host "Database   : $Database"
if ($InitialCsv) { Write-Host "Initial CSV: $InitialCsv" }
Write-Host "Port       : $Port"
Write-Host "Working Dir: $ScriptDir"
if ($HideEnvNotice) { Write-Host "(Env Notice suppressed)" -ForegroundColor DarkYellow }
Write-Host "--------------------------------------------" -ForegroundColor Cyan

# --- Optional Cairo runtime injection (for cairosvg SVG->PNG support) ---
$cairoRuntime = Join-Path $ScriptDir 'cairo_runtime'
if (Test-Path $cairoRuntime) {
  if (-not ($env:PATH.Split(';') -contains $cairoRuntime)) {
    $env:PATH = "$cairoRuntime;$env:PATH"
    Write-Host "[cairo] Prepended $cairoRuntime to PATH" -ForegroundColor DarkCyan
  } else {
    Write-Host "[cairo] Runtime path already in PATH" -ForegroundColor DarkCyan
  }
} else {
  Write-Host "[cairo] No local cairo_runtime directory (skipping)" -ForegroundColor DarkGray
}

# Prefer pycairo backend if present; can help on Windows when cairocffi DLL lookup fails
if (-not $env:CAIROSVG_BACKEND) { $env:CAIROSVG_BACKEND = 'pycairo' }
# To disable SVG rendering entirely (fallback to text/logo PNG), uncomment:
# $env:DISABLE_SVG_RENDER = '1'

# Pass env vars through for the app to consume
$env:SIGN_APP_PORT = $Port
$env:SIGN_APP_DB = $Database
if ($InitialCsv) { $env:SIGN_APP_INITIAL_CSV = $InitialCsv }
if ($HideEnvNotice) { $env:SIGN_APP_HIDE_ENV_NOTICE = '1' }

& $VenvPy app.py
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Host "App exited with code $code" -ForegroundColor Red
} else {
  Write-Host "App exited normally" -ForegroundColor Green
}
exit $code

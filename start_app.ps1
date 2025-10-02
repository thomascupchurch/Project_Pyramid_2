<#
PowerShell launcher for Sign Estimation Application

Primary goals:
  1. Seamless coworker launch from shared OneDrive (no manual Python setup needed).
  2. Prefer PyInstaller bundle if present AND healthy.
  3. Fallback to source + per-user venv (outside OneDrive) if bundle missing or incomplete.
  4. Provide clear guidance when execution policy blocks the script.

If you see: "running scripts is disabled" run PowerShell as Administrator once:
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

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
  [switch]$HideEnvNotice,
  [switch]$NoBrowser,
  [switch]$Minimized
)

# Resolve script directory & switch
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ---------------------------------------------------------------
# Bundle preference & health validation
# ---------------------------------------------------------------
$BundleRoot = Join-Path $ScriptDir 'bundle'
$GuiBundle = Join-Path $BundleRoot 'sign_estimator'
$ConsoleBundle = Join-Path $BundleRoot 'sign_estimator_console'
$BundleExe = Join-Path $GuiBundle 'sign_estimator.exe'
$ConsoleExe = Join-Path $ConsoleBundle 'sign_estimator_console.exe'

function Test-CytoResource {
  param([string]$BundleDir)
  if (-not (Test-Path $BundleDir)) { return $false }
  $cy = Join-Path $BundleDir 'dash_cytoscape/package.json'
  return (Test-Path $cy)
}

function Use-Bundle {
  param([string]$ExePath)
  Write-Host "Launching bundled executable: $ExePath" -ForegroundColor Green
  Start-Process -FilePath $ExePath
  exit 0
}

$PreferredExe = $null
$PreferredDir = $null
if (Test-Path $BundleExe) { $PreferredExe = $BundleExe; $PreferredDir = $GuiBundle }
elseif (Test-Path $ConsoleExe) { $PreferredExe = $ConsoleExe; $PreferredDir = $ConsoleBundle }

if ($PreferredExe) {
  if (Test-CytoResource -BundleDir $PreferredDir) {
    Write-Host '[bundle] Cytoscape assets present ✔' -ForegroundColor DarkGreen
    Use-Bundle -ExePath $PreferredExe
  } else {
    Write-Host '[bundle][warn] Cytoscape assets missing – falling back to source environment.' -ForegroundColor Yellow
  }
} else {
  Write-Host '[bundle] No bundle found – using source launch.' -ForegroundColor Yellow
}

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

if (-not $Minimized) {
  Write-Host "--------------------------------------------" -ForegroundColor Cyan
  Write-Host "Launching Sign Estimation App (source mode)" -ForegroundColor Green
  Write-Host "Python     : $VenvPy (per-user)"
  Write-Host "Database   : $Database"
  if ($InitialCsv) { Write-Host "Initial CSV: $InitialCsv" }
  Write-Host "Port       : $Port"
  Write-Host "Working Dir: $ScriptDir"
  if ($HideEnvNotice) { Write-Host "(Env Notice suppressed)" -ForegroundColor DarkYellow }
  if ($NoBrowser) { Write-Host "(Auto browser launch disabled)" -ForegroundColor DarkGray }
  if ($Minimized) { Write-Host "(Minimized output mode)" -ForegroundColor DarkGray }
  Write-Host "--------------------------------------------" -ForegroundColor Cyan
}

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

if ($Minimized) {
  # Start the server in a background job to allow browser open without clutter
  Start-Job -ScriptBlock { param($py) & $py run_server.py } -ArgumentList $VenvPy | Out-Null
} else {
  & $VenvPy run_server.py
}
$code = $LASTEXITCODE

# Optional lightweight health probe (wait a few seconds then query /health if port reachable)
Start-Sleep -Seconds 6
try {
  $url = "http://127.0.0.1:$Port/health"
  $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
  if ($resp.StatusCode -eq 200) {
    if (-not $Minimized) { Write-Host "[health] App responded OK" -ForegroundColor DarkGreen }
    if (-not $NoBrowser) {
      try {
        $baseUrl = "http://127.0.0.1:$Port/"
        Start-Process $baseUrl
        if (-not $Minimized) { Write-Host "[open] Launched default browser -> $baseUrl" -ForegroundColor Green }
      } catch {
        if (-not $Minimized) { Write-Host "[open][warn] Failed to open browser: $($_.Exception.Message)" -ForegroundColor Yellow }
      }
    }
  } else {
    if (-not $Minimized) { Write-Host "[health] Non-200 status: $($resp.StatusCode)" -ForegroundColor Yellow }
  }
} catch {
  if (-not $Minimized) { Write-Host "[health] Probe failed (app may still be initializing): $($_.Exception.Message)" -ForegroundColor DarkGray }
}

if (-not $Minimized) {
  if ($code -ne 0 -and -not $Minimized) {
    Write-Host "App exited with code $code" -ForegroundColor Red
    exit $code
  } else {
    Write-Host "App started (monitor console for logs)." -ForegroundColor Green
    exit 0
  }
} else {
  # In minimized mode we just keep the job running; optionally exit 0 quickly.
  Write-Host "App background job started. Use Get-Job to inspect." -ForegroundColor DarkGreen
  exit 0
}

<#
.SYNOPSIS
  Windows setup and launch script for Sign Package Estimator (parity with setup_mac.sh)

.PARAMETER Python
  Optional explicit python executable (e.g. C:\Python311\python.exe)

.PARAMETER VenvDir
  Virtual environment directory name (default .venv)

.PARAMETER InstallCairoSvg
  Switch to force install of cairosvg + attempt winget/Chocolatey native cairo guidance.

Usage examples:
  powershell -ExecutionPolicy Bypass -File setup_windows.ps1
  powershell -File setup_windows.ps1 -Python py -VenvDir .venv-win -InstallCairoSvg
#>
param(
  [string]$Python = 'py',
  [string]$VenvDir = '.venv',
  [switch]$InstallCairoSvg
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($m){ Write-Host "[setup] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[warn] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[error] $m" -ForegroundColor Red }

Push-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Info "Python selector: $Python"

if ($Python -eq 'py') {
  if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Warn "'py' launcher not found; falling back to 'python'"
    $Python = 'python'
  }
}

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
  Write-Err "Python command '$Python' not found in PATH. Install Python 3.11+ first."; exit 2
}

Write-Info "Python version: $(& $Python -c "import sys; print(sys.version)")"

$venvPy = Join-Path $VenvDir 'Scripts/python.exe'
if (-not (Test-Path $venvPy)) {
  Write-Info "Creating virtual environment in $VenvDir"
  & $Python -3 -m venv $VenvDir 2>$null | Out-Null
  if (-not (Test-Path $venvPy)) {
    # Retry without -3 if initial failed
    & $Python -m venv $VenvDir
  }
}
if (-not (Test-Path $venvPy)) { Write-Err "Failed to create virtual environment ($VenvDir)"; exit 3 }

Write-Info "Upgrading pip"
& $venvPy -m pip install --upgrade pip setuptools wheel | Out-Null

if (Test-Path 'requirements.txt') {
  Write-Info "Installing requirements"
  & $venvPy -m pip install -r requirements.txt
} else {
  Write-Warn "requirements.txt not found; skipping dependency sync"
}

if ($InstallCairoSvg) {
  Write-Info "Attempting cairosvg/native Cairo setup guidance"
  Write-Warn "Automated native cairo install not implemented (use MSYS2: pacman -S mingw-w64-ucrt-x86_64-cairo)."
  & $venvPy -m pip install --force-reinstall cairosvg
}

Write-Info "Verifying environment"
try { & $venvPy scripts/verify_env.py --json } catch { Write-Warn "verify_env failed: $($_.Exception.Message)" }

Write-Info "Launching app"
& $venvPy app.py

Pop-Location
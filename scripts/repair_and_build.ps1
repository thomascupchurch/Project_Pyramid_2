param(
  [string]$PythonPath,
  [string]$Version = '3.11'
)
$ErrorActionPreference = 'Stop'
Write-Host "[repair] Starting repair-and-build..." -ForegroundColor Cyan

function Find-Python {
  param([string]$Preferred, [string]$Ver)
  if ($Preferred) {
    if (Test-Path $Preferred) { return $Preferred }
    Write-Warning "Preferred Python not found: $Preferred"
  }
  # Registry search for InstallPath/ExecutablePath
  $roots = @('HKLM:','HKCU:')
  $subkeys = @('SOFTWARE\Python\PythonCore','SOFTWARE\WOW6432Node\Python\PythonCore')
  foreach ($r in $roots) {
    foreach ($s in $subkeys) {
      $base = Join-Path $r $s
      try {
        if (Test-Path (Join-Path $base $Ver)) {
          $ip = Join-Path (Join-Path $base $Ver) 'InstallPath'
          if (Test-Path $ip) {
            $p = (Get-ItemProperty -Path $ip -ErrorAction SilentlyContinue)
            if ($p -and $p.ExecutablePath -and (Test-Path $p.ExecutablePath)) { return $p.ExecutablePath }
            if ($p -and $p.("(default)") -and (Test-Path (Join-Path $p."(default)" 'python.exe'))) { return (Join-Path $p."(default)" 'python.exe') }
            if ($p -and $p.InstallPath -and (Test-Path (Join-Path $p.InstallPath 'python.exe'))) { return (Join-Path $p.InstallPath 'python.exe') }
          }
        }
      } catch {}
    }
  }
  # Common paths
  $majorMinor = $Ver -replace '\\.', ''
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python$majorMinor\python.exe",
    "C:\\Program Files\\Python$majorMinor\\python.exe",
    "C:\\Program Files (x86)\\Python$majorMinor\\python.exe"
  )
  foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
  return $null
}

$py = Find-Python -Preferred $PythonPath -Ver $Version
if (-not $py) {
  Write-Host "[error] Could not find Python 3.11 at common locations." -ForegroundColor Red
  Write-Host "Provide a path explicitly, e.g.:" -ForegroundColor Yellow
  Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/repair_and_build.ps1 -PythonPath 'C:\\Path\\to\\Python311\\python.exe'"
  exit 1
}

Write-Host "[repair] Using Python: $py" -ForegroundColor DarkCyan
try { & $py -V } catch { Write-Host "[error] Failed invoking $py" -ForegroundColor Red; exit 1 }

Write-Host "[repair] Rebuilding .venv with specified Python..." -ForegroundColor DarkCyan
& $py scripts/rebuild_venv.py --yes --force --python $py
if ($LASTEXITCODE -ne 0) { Write-Host "[error] venv rebuild failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[repair] Installing/upgrading pip and PyInstaller in .venv..." -ForegroundColor DarkCyan
& .\.venv\Scripts\python.exe -m pip install -U pip pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Host "[error] pip/pyinstaller install failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[repair] Building one-file bundle..." -ForegroundColor DarkCyan
cmd /c scripts\build_bundle.bat --onefile
if ($LASTEXITCODE -ne 0) { Write-Host "[error] build failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[repair] Done. dist\\sign_estimator.exe should be updated and shortcuts refreshed." -ForegroundColor Green

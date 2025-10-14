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

Write-Host "[repair] Upgrading pip in .venv..." -ForegroundColor DarkCyan
& .\.venv\Scripts\python.exe -m pip install -U pip
if ($LASTEXITCODE -ne 0) { Write-Host "[warn] pip upgrade failed (rc=$LASTEXITCODE); continuing" -ForegroundColor Yellow }

Write-Host "[repair] Installing PyInstaller (pinned) in .venv..." -ForegroundColor DarkCyan
& .\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps pyinstaller==6.11.0
if ($LASTEXITCODE -ne 0) {
  Write-Host "[warn] PyInstaller install failed; attempting cleanup of stale files..." -ForegroundColor Yellow
  try {
    $sp = Join-Path $PSScriptRoot "..\..\.venv\Lib\site-packages"
    if (-not (Test-Path $sp)) { $sp = ".\.venv\Lib\site-packages" }
    $scriptsDir = ".\.venv\Scripts"
    # Remove PyInstaller package folders
    Get-ChildItem -Path $sp -Filter "PyInstaller*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    # Remove dist-info/egg-info remnants
    Get-ChildItem -Path $sp -Filter "pyinstaller*.*-info" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    # Remove console entry points
    foreach ($name in @('pyinstaller.exe','pyi-archive_viewer.exe','pyi-bindepend.exe','pyi-grab_version.exe','pyi-makespec.exe','pyi-set_version.exe')) {
      $p = Join-Path $scriptsDir $name; if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue }
    }
  } catch {
    Write-Warning "Cleanup encountered an issue: $($_.Exception.Message)"
  }
  Write-Host "[repair] Retrying PyInstaller install with --ignore-installed..." -ForegroundColor DarkCyan
  & .\.venv\Scripts\python.exe -m pip install --ignore-installed --no-deps pyinstaller==6.11.0
  if ($LASTEXITCODE -ne 0) { Write-Host "[error] pyinstaller install failed after cleanup (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }
}

Write-Host "[repair] Ensuring pywin32-ctypes is installed (force clean)..." -ForegroundColor DarkCyan
# Force a clean install because this package is prone to uninstall-no-record-file issues under OneDrive
& .\.venv\Scripts\python.exe -m pip install --ignore-installed --no-deps --force-reinstall pywin32-ctypes==0.2.3
if ($LASTEXITCODE -ne 0) { Write-Host "[error] pywin32-ctypes force install failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

# Validate minimal import (only win32ctypes.pywin32.pywintypes) before proceeding
& .\.venv\Scripts\python.exe -c "import importlib; importlib.import_module('win32ctypes.pywin32.pywintypes')" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "[error] win32ctypes.pywin32.pywintypes import failed after install; aborting build." -ForegroundColor Red; exit 1 }

Write-Host "[repair] Ensuring pywin32 is installed..." -ForegroundColor DarkCyan
& .\.venv\Scripts\python.exe -m pip install -U pywin32
if ($LASTEXITCODE -ne 0) { Write-Host "[warn] pywin32 install reported an error; continuing" -ForegroundColor Yellow }

# Full validation now that pywin32 is present
& .\.venv\Scripts\python.exe .\scripts\check_win32_imports.py | Out-Host

Write-Host "[repair] Ensuring pefile is installed (required by PyInstaller on Windows)..." -ForegroundColor DarkCyan
& .\.venv\Scripts\python.exe -m pip install -U pefile==2023.2.7
if ($LASTEXITCODE -ne 0) { Write-Host "[error] pefile install failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[repair] Building one-file bundle..." -ForegroundColor DarkCyan
cmd /c scripts\build_bundle.bat --onefile
if ($LASTEXITCODE -ne 0) { Write-Host "[error] build failed (rc=$LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[repair] Done. dist\\sign_estimator.exe should be updated and shortcuts refreshed." -ForegroundColor Green

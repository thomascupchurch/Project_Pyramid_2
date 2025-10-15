<#!
Fetch minimal Cairo runtime DLLs for Windows into a local cairo_runtime/ folder.
This script tries multiple sources in order:
  1. Pre-packaged zip (if you host one internally) - placeholder URL variable
  2. Winget (if available) to install GTK (user scope) and copy required DLLs
  3. MSYS2 fallback guidance if automatic fetch fails
#>
param(
  [string]$Destination = 'cairo_runtime',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
$destPath = Join-Path $ScriptDir $Destination

function Ensure-Dir($p) { if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null } }

if ((Test-Path $destPath) -and -not $Force) {
  Write-Host "[cairo] Destination $destPath already exists. Use -Force to overwrite." -ForegroundColor Yellow
  exit 0
}
Ensure-Dir $destPath

# List of DLLs typically required
$dlls = @(
  'libcairo-2.dll','libpng16-16.dll','zlib1.dll','libpixman-1-0.dll','libfreetype-6.dll','libfontconfig-1.dll'
)

# Placeholder: Pre-packaged archive URL (user can customize)
$ArchiveUrl = $env:CAIRO_RUNTIME_ZIP
if ($ArchiveUrl) {
  try {
    Write-Host "[cairo] Attempting download from $ArchiveUrl" -ForegroundColor Cyan
    $tmpZip = New-TemporaryFile
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $tmpZip -UseBasicParsing
    Expand-Archive -Path $tmpZip -DestinationPath $destPath -Force
    Remove-Item $tmpZip -Force
    $found = @(Get-ChildItem $destPath -Recurse -Include $dlls -ErrorAction SilentlyContinue)
    if ($found.Count -ge 2) {
      Write-Host "[cairo] Extracted archive; DLLs present." -ForegroundColor Green
      exit 0
    } else { Write-Host "[cairo] Archive extracted but DLLs not found, proceeding to next method" -ForegroundColor Yellow }
  } catch {
    Write-Host "[cairo] Archive method failed: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

# Winget GTK runtime attempt
try {
  $winget = (Get-Command winget -ErrorAction SilentlyContinue)
  if ($winget) {
    Write-Host '[cairo] Attempting winget install of GTK runtime (user scope)' -ForegroundColor Cyan
    # Non-interactive install; may require user acceptance in some environments
    winget install --id=Gnome.Gtk3 --scope=user -e --accept-package-agreements --accept-source-agreements | Out-Null
    $gtkDir = Join-Path $env:LOCALAPPDATA 'Programs\GTK3-Runtime'  # typical path
    if (Test-Path $gtkDir) {
      $binDir = Join-Path $gtkDir 'bin'
      $copies = 0
      foreach ($dll in $dlls) {
        $src = Join-Path $binDir $dll
        if (Test-Path $src) { Copy-Item $src -Destination $destPath -Force; $copies++ }
      }
      if ($copies -gt 0) {
        Write-Host "[cairo] Copied $copies DLL(s) from GTK runtime" -ForegroundColor Green
        exit 0
      } else { Write-Host '[cairo] GTK installed but DLLs not located' -ForegroundColor Yellow }
    } else { Write-Host '[cairo] GTK runtime directory not found after winget install' -ForegroundColor Yellow }
  } else { Write-Host '[cairo] winget not available; skipping GTK install attempt' -ForegroundColor DarkGray }
} catch {
  Write-Host "[cairo] winget method failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host @'
[cairo] Automatic retrieval unsuccessful.
Manual fallback options:
  1) Install MSYS2 (https://www.msys2.org/), then in MSYS2 shell run:
       pacman -Sy --noconfirm
       pacman -S --noconfirm mingw-w64-x86_64-cairo mingw-w64-x86_64-libpng mingw-w64-x86_64-freetype
     Then copy the listed DLLs from C:\msys64\mingw64\bin into cairo_runtime/.
  2) Install GTK runtime manually and copy its bin/*.dll files listed above.
  3) Obtain a pre-packaged zip and set CAIRO_RUNTIME_ZIP to its URL, re-run this script.
'@
exit 2

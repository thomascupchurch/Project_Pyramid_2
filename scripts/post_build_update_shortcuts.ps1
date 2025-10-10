param(
  [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$ShortcutScript = Join-Path $Root 'scripts/create_shortcuts.ps1'
if (-not (Test-Path $ShortcutScript)) {
  Write-Host "Missing create_shortcuts.ps1 at $ShortcutScript" -ForegroundColor Red
  exit 1
}

try {
  Write-Host "[post-build] Updating Desktop/Start Menu shortcuts..." -ForegroundColor Cyan
  powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File $ShortcutScript -ExeTarget -Force | Out-Null
  if (-not $Quiet) { Write-Host "[post-build] Shortcuts updated." -ForegroundColor Green }
} catch {
  Write-Warning "[post-build] Failed to update shortcuts: $($_.Exception.Message)"
  exit 1
}

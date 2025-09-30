param(
  [switch]$Force,
  [switch]$Yes,
  [switch]$DryRun,
  [switch]$Json
)
$ArgsList = @()
if ($Force) { $ArgsList += '--force' }
if ($Yes) { $ArgsList += '--yes' }
if ($DryRun) { $ArgsList += '--dry-run' }
if ($Json) { $ArgsList += '--json' }
Write-Host "Rebuilding virtual environment (wrapper)..." -ForegroundColor Cyan
python scripts/rebuild_venv.py @ArgsList

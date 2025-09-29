<#
.SYNOPSIS
 Full featured deployment wrapper (PowerShell version).
.DESCRIPTION
 Runs scripts/deploy.py with the standard robust flag set:
   --backup-db --backup-retention 7 --collect-logs --prune --archive
 Detects local virtual environment automatically. Supports --no-defaults to
 suppress defaults and pass only user arguments.
.EXAMPLE
 ./deploy_full.ps1
.EXAMPLE
 ./deploy_full.ps1 --force
.EXAMPLE
 ./deploy_full.ps1 --no-defaults --backup-db
#>

param(
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]] $ArgsPassThru
)

$ErrorActionPreference = 'Stop'

Write-Host '--- Deploy (full) ---'

# Resolve repo root (this script expected under scripts/)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir '..') | Select-Object -ExpandProperty Path
Push-Location $repoRoot

# Candidate interpreters
$venv1 = Join-Path $repoRoot '.venv/Scripts/python.exe'
$venv2 = Join-Path $repoRoot 'activate/Scripts/python.exe'
$python = $null
if (Test-Path $venv1) { $python = $venv1 }
elseif (Test-Path $venv2) { $python = $venv2 }
else {
  $python = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Path
}
if (-not $python) {
  Write-Error 'Could not locate a Python interpreter (.venv, activate, or system).'
}

$defaultFlags = @('--backup-db','--backup-retention','7','--collect-logs','--prune','--archive')
$useDefaults = $true

if ($ArgsPassThru.Count -gt 0 -and $ArgsPassThru[0] -eq '--no-defaults') {
  $useDefaults = $false
  $ArgsPassThru = $ArgsPassThru[1..($ArgsPassThru.Count-1)]
}

$cmd = @($python,'scripts/deploy.py')
if ($useDefaults) { $cmd += $defaultFlags }
if ($ArgsPassThru) { $cmd += $ArgsPassThru }

Write-Host "Repo Root: $repoRoot"
Write-Host "Python   : $python"
if ($useDefaults) {
  Write-Host "Defaults : $($defaultFlags -join ' ')"
} else {
  Write-Host 'Defaults : (suppressed)'
}
Write-Host "Extra    : $($ArgsPassThru -join ' ')"
Write-Host '------------------------------'

# Execute
& $cmd[0] $cmd[1..($cmd.Count-1)]
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
  Write-Host "[deploy_full.ps1] Deployment FAILED (exit $exitCode)" -ForegroundColor Red
} else {
  Write-Host '[deploy_full.ps1] Deployment completed successfully.' -ForegroundColor Green
}

Pop-Location
exit $exitCode

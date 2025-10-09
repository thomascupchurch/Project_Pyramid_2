<#!
.SYNOPSIS
  Ensures a Windows Defender Firewall inbound rule exists for the Sign Estimator app.

.DESCRIPTION
  Detects the intended port (SIGN_APP_PORT env var or default 8050) and optional python/program path.
  If no existing *enabled* allow rule is found for that port, offers to create one (or auto creates with -Auto).
  Uses add_firewall_rule.ps1 if creation is needed.

.PARAMETER Auto
  Automatically create the rule without prompting (non-interactive / silent).

.PARAMETER Port
  Override port detection (otherwise SIGN_APP_PORT or 8050).

.PARAMETER Program
  Optional explicit program path for rule restriction.

.PARAMETER Silent
  Suppress normal informational output (warnings still shown).

.EXAMPLE
  ./ensure_firewall_rule.ps1

.EXAMPLE
  ./ensure_firewall_rule.ps1 -Auto -Program C:\\Path\\To\\sign_estimator.exe

.NOTES
  Run elevated when creating rules. Safe to run multiple times (idempotent).
#>
[CmdletBinding()] param(
  [switch]$Auto,
  [int]$Port = $( if($env:SIGN_APP_PORT){ [int]$env:SIGN_APP_PORT } else { 8050 } ),
  [string]$Program,
  [switch]$Silent
)

function WInfo($m){ if(-not $Silent){ Write-Host "[fw-check] $m" -ForegroundColor Cyan } }
function WWarn($m){ Write-Host "[fw-check][warn] $m" -ForegroundColor Yellow }

if($Port -lt 1 -or $Port -gt 65535){ WWarn "Invalid port: $Port"; exit 1 }

# Detect existing rules that allow inbound TCP for this port
$rules = Get-NetFirewallRule -Action Allow -Direction Inbound -Enabled True -ErrorAction SilentlyContinue |
  Where-Object { $_.Profile -ne 'Any' -or $_.Profile -ne 'None' }

# Get associated filters for port matching
$matched = @()
foreach($r in $rules){
  $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $r -ErrorAction SilentlyContinue
  if($portFilter -and $portFilter.Protocol -eq 'TCP' -and $portFilter.LocalPort -eq $Port){
    $appFilter = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $r -ErrorAction SilentlyContinue
    $matched += [pscustomobject]@{
      Name = $r.DisplayName
      Program = ($appFilter.Program -join ',')
      Enabled = $r.Enabled
      Profile = $r.Profile
    }
  }
}

if($matched.Count -gt 0){
  $names = ($matched | ForEach-Object { $_.Name } | Sort-Object | Select-Object -Unique) -join ', '
  WInfo "Firewall rule present for port ${Port}: $names" 
  exit 0
}

WInfo "No inbound allow rule found for TCP port $Port." 

# If program path not passed, try to detect python exe relative to per-user venv usage
if(-not $Program){
  $localApp = Join-Path $env:LOCALAPPDATA 'SignEstimator/venv/Scripts/python.exe'
  if(Test-Path $localApp){ $Program = $localApp }
}

if($Auto){
  WInfo "Auto mode: creating rule."
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'add_firewall_rule.ps1') -Port $Port -Program $Program
  $ec = $LASTEXITCODE
  if($ec -ne 0){ WWarn "Firewall rule creation failed (exit $ec). Try running elevated or use netsh command."; exit $ec }
  # Re-check
  $verify = Get-NetFirewallRule -DisplayName 'SignEstimator Inbound' -ErrorAction SilentlyContinue
  if(-not $verify){ WWarn 'Rule still not found after creation attempt. (Permissions?)'; exit 3 }
  WInfo 'Rule verified.'
  exit 0
}

$resp = Read-Host "Create inbound firewall rule 'SignEstimator Inbound' for port $Port now? [Y/n]"
if($resp -match '^(y|yes|)$'){ 
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'add_firewall_rule.ps1') -Port $Port -Program $Program
  $ec = $LASTEXITCODE
  if($ec -ne 0){ WWarn "Firewall rule creation failed (exit $ec). Run PowerShell as Administrator and retry."; exit $ec }
  $verify = Get-NetFirewallRule -DisplayName 'SignEstimator Inbound' -ErrorAction SilentlyContinue
  if(-not $verify){ WWarn 'Rule still not found after creation attempt. (Permissions?)'; exit 3 }
  WInfo 'Rule verified.'
  exit 0
} else {
  WWarn "Skipped creating rule. Remote machines will not reach this port unless a rule is added later."
  exit 2
}

<#!
.SYNOPSIS
  Adds (or updates) a Windows Defender Firewall inbound rule to allow LAN access to the Sign Estimation app.

.DESCRIPTION
  Creates a TCP inbound allow rule for the configured port (default 8050) and optional specific program path.
  If a rule with the same name already exists, you can use -Force to remove and recreate it.

.PARAMETER Port
  TCP port to allow. Defaults to value in SIGN_APP_PORT environment variable or 8050.

.PARAMETER Program
  Optional full path to the executable (python.exe or bundled sign_estimator.exe). If omitted, rule applies to any program on that port.

.PARAMETER Name
  Custom rule name. Defaults to "SignEstimator Inbound".

.PARAMETER Profile
  Comma-separated firewall profiles to enable: Domain,Private,Public. Default: Domain,Private.

.PARAMETER Force
  Remove an existing rule of the same name before recreating.

.EXAMPLE
  # Allow default port 8050 for any program on Domain & Private LAN
  ./add_firewall_rule.ps1

.EXAMPLE
  # Allow custom port and restrict to specific python interpreter
  ./add_firewall_rule.ps1 -Port 8060 -Program "C:\\Users\\me\\AppData\\Local\\Microsoft\\WindowsApps\\Python.exe"

.EXAMPLE
  # Force recreate with a custom name and include Public profile (NOT recommended normally)
  ./add_firewall_rule.ps1 -Name "SignEstimator Public" -Profile Domain,Private,Public -Force

.NOTES
  Run PowerShell as Administrator to create system-wide firewall rules.
#>
[CmdletBinding()] param(
  [int]$Port = $( if($env:SIGN_APP_PORT){ [int]$env:SIGN_APP_PORT } else { 8050 } ),
  [string]$Program,
  [string]$Name = 'SignEstimator Inbound',
  [string[]]$Profiles = @('Domain','Private'),
  [switch]$Force
)

function Write-Info($msg){ Write-Host "[add-firewall] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[add-firewall][warn] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[add-firewall][error] $msg" -ForegroundColor Red }

if(-not ([bool]([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) ){
  Write-Warn "Script not running elevated. Attempting rule creation may fail. Right-click PowerShell and 'Run as administrator'."
}

if($Port -lt 1 -or $Port -gt 65535){ Write-Err "Invalid port: $Port"; exit 1 }

$existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
if($existing){
  if($Force){
    Write-Info "Removing existing rule '$Name' (Force specified)."
    $existing | Remove-NetFirewallRule -ErrorAction Stop
  } else {
    Write-Warn "Rule '$Name' already exists. Use -Force to recreate. Exiting."
    return
  }
}

$commonParams = @{
  DisplayName = $Name
  Direction   = 'Inbound'
  Action      = 'Allow'
  Protocol    = 'TCP'
  LocalPort   = $Port
  Profile     = ($Profiles -join ',')
}

if($Program){
  if(-not (Test-Path $Program)){ Write-Warn "Program path '$Program' does not exist; continuing without program restriction." } else { $commonParams['Program'] = $Program }
}

try {
  New-NetFirewallRule @commonParams -ErrorAction Stop | Out-Null
  # Verification step
  $verify = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
  if(-not $verify){
    Write-Err "Rule creation returned no error but rule not found afterward. (Likely permissions issue)"
    exit 2
  }
  Write-Info "Created firewall rule '$Name' allowing TCP port $Port on profiles: $($Profiles -join ', ') $( if($commonParams.ContainsKey('Program')){" for program '$Program'"} )."
  Write-Info "Verify: Get-NetFirewallRule -DisplayName '$Name' | Get-NetFirewallApplicationFilter"
} catch {
  Write-Err "Failed creating firewall rule: $($_.Exception.Message)"
  if($_.Exception.HResult -eq -2147024891){
    Write-Warn "Access denied. Re-run PowerShell as Administrator or use: netsh advfirewall firewall add rule name=\"$Name\" dir=in action=allow protocol=TCP localport=$Port"
  }
  exit 1
}

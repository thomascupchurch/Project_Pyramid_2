<#
Launch two instances of the Sign Estimation App on separate ports, suitable for LAN sharing.

Usage examples:
  # Default ports 8050 and 8060
  ./start_both_apps.ps1

  # Custom ports
  ./start_both_apps.ps1 -PortA 8050 -PortB 8060

  # Expect LAN: ensures firewall rules and binds to 0.0.0.0
  $env:SIGN_APP_EXPECT_LAN=1; ./start_both_apps.ps1
#>
[CmdletBinding()]
param(
  [int]$PortA = 8050,
  [int]$PortB = 8060,
  [switch]$NoBrowser
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$startScript = Join-Path $ScriptDir 'start_app.ps1'
if(-not (Test-Path $startScript)){
  Write-Host 'start_app.ps1 not found. Cannot continue.' -ForegroundColor Red
  exit 1
}

# Bind to all interfaces for LAN sharing (aligns with config.py default)
if(-not $env:SIGN_APP_HOST){ $env:SIGN_APP_HOST = '0.0.0.0' }

function Launch-OneWindow {
  param([int]$Port)
  $noBrowserArg = if($NoBrowser){ '-NoBrowser' } else { '' }
  $cmd = "$env:SIGN_APP_PORT=$Port; & `"$startScript`" $noBrowserArg"
  Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command', $cmd) -WindowStyle Minimized | Out-Null
}

Launch-OneWindow -Port $PortA
Launch-OneWindow -Port $PortB

Write-Host ("Started two app instances on ports {0} and {1}." -f $PortA,$PortB) -ForegroundColor Green

if(-not $NoBrowser){
  try {
    Start-Process ("http://127.0.0.1:" + $PortA + "/")
    Start-Process ("http://127.0.0.1:" + $PortB + "/")
  } catch {
    Write-Host ("[open][warn] Failed to open browsers: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
  }
}

Write-Host 'Two PowerShell windows were started minimized; each hosts one app instance.' -ForegroundColor DarkGray

<#!
Creates Desktop and Start Menu shortcuts for the Sign Estimation App launcher.
Usage:
  powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcuts.ps1 [-Force] [-NoBrowser]
Options:
  -Force      Recreate shortcuts even if they already exist.
  -NoBrowser  Adds -NoBrowser flag to shortcut target to suppress auto-open.
  -Minimized  Launch minimized (suppresses most console output).
!>
param(
  [switch]$Force,
  [switch]$NoBrowser,
  [switch]$Minimized
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Launcher = Join-Path $Root 'start_app.ps1'
if (-not (Test-Path $Launcher)) { Write-Host "start_app.ps1 not found at $Launcher" -ForegroundColor Red; exit 1 }

$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$StartMenu = Join-Path $env:APPDATA 'Microsoft/Windows/Start Menu/Programs'
$AppFolder = Join-Path $StartMenu 'Sign Estimator'
if (-not (Test-Path $AppFolder)) { New-Item -ItemType Directory -Path $AppFolder | Out-Null }

$IconCandidate = Join-Path $Root 'assets/LSI_Logo.ico'
if (-not (Test-Path $IconCandidate)) { $IconCandidate = $null }

$Flags = @()
if ($NoBrowser) { $Flags += '-NoBrowser' }
if ($Minimized) { $Flags += '-Minimized' }
$FlagString = $Flags -join ' '

function New-AppShortcut {
  param(
    [string]$Path,
    [string]$Description
  )
  if ((Test-Path $Path) -and -not $Force) {
    Write-Host "Shortcut exists: $Path (use -Force to recreate)" -ForegroundColor DarkGray
    return
  }
  if (Test-Path $Path) { Remove-Item $Path -Force }
  $sc = $Shell.CreateShortcut($Path)
  $psExe = (Get-Command powershell.exe).Source
  $sc.TargetPath = $psExe
  $sc.Arguments = "-ExecutionPolicy Bypass -NoLogo -NoProfile -File `"$Launcher`" $FlagString"
  $sc.Description = $Description
  if ($IconCandidate) { $sc.IconLocation = $IconCandidate }
  $sc.WorkingDirectory = $Root
  $sc.Save()
  Write-Host "Created shortcut: $Path" -ForegroundColor Green
}

$DesktopShortcut = Join-Path $Desktop 'Sign Estimator.lnk'
$MenuShortcut = Join-Path $AppFolder 'Sign Estimator.lnk'

New-AppShortcut -Path $DesktopShortcut -Description 'Launch Sign Estimator'
New-AppShortcut -Path $MenuShortcut -Description 'Launch Sign Estimator'

Write-Host 'Done.' -ForegroundColor Green

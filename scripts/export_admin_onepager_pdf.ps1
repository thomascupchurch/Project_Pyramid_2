<#!
.SYNOPSIS
  Exports the admin firewall one‑pager to PDF using Microsoft Edge (headless).

.DESCRIPTION
  Launches Edge in headless mode to print docs/admin_firewall_rule_onepager.html to a PDF in the project root.
  Requires Microsoft Edge installed and available on PATH.

.PARAMETER Output
  Optional custom output path for the PDF. Defaults to ./admin_firewall_rule_onepager.pdf

.EXAMPLE
  ./scripts/export_admin_onepager_pdf.ps1

.EXAMPLE
  ./scripts/export_admin_onepager_pdf.ps1 -Output C:\\Temp\\SignEstimator_Firewall_OnePager.pdf
#>
[CmdletBinding()] param(
  [string]$Output = (Join-Path (Split-Path -Parent $PSScriptRoot) 'admin_firewall_rule_onepager.pdf')
)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[pdf] $m" -ForegroundColor Cyan }
function Err($m){ Write-Host "[pdf][error] $m" -ForegroundColor Red }

$docs = Join-Path (Split-Path -Parent $PSScriptRoot) 'docs'
$html = Join-Path $docs 'admin_firewall_rule_onepager.html'
if(-not (Test-Path $html)){ Err "Missing $html"; exit 1 }

# Edge location lookup (common paths) if not on PATH
$cmd = Get-Command msedge -ErrorAction SilentlyContinue
if($cmd){ $edge = $cmd.Source } else { $edge = $null }
if(-not $edge){
  $cand1 = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  $cand2 = "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
  if(Test-Path $cand1){ $edge = $cand1 }
  elseif(Test-Path $cand2){ $edge = $cand2 }
}
if(-not $edge){ Err "Microsoft Edge not found. Ensure msedge is installed and on PATH."; exit 2 }

# Ensure output directory exists
$OutDir = Split-Path -Parent $Output
if($OutDir -and -not (Test-Path $OutDir)){ New-Item -ItemType Directory -Path $OutDir | Out-Null }

# Build file:/// URI (Edge expects a URL; paths with spaces must be quoted)
$resolved = (Resolve-Path $html).Path
$fileUri = 'file:///' + $resolved.Replace('\\','/').Replace(' ','%20')

# Headless print to PDF (quote output path inside the arg to preserve spaces)
$cmdArgs = @(
  "--headless",
  "--disable-gpu",
  "--print-to-pdf=$Output",
  "--no-sandbox",
  "$fileUri"
)

Info "Using Edge at: $edge"
Info "Writing PDF: $Output"
Info "Source: $fileUri"

$proc = Start-Process -FilePath $edge -ArgumentList $cmdArgs -PassThru -WindowStyle Hidden
$proc.WaitForExit()

if(-not (Test-Path $Output)){
  $code = $proc.ExitCode
  Err "Failed to generate PDF (output not found). Edge exit code: $code"
  exit 3
}

Info "PDF generated successfully."

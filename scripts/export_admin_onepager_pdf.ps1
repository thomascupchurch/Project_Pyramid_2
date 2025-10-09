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
  [string]$Output,
  [string]$SourceHtml
)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[pdf] $m" -ForegroundColor Cyan }
function Err($m){ Write-Host "[pdf][error] $m" -ForegroundColor Red }
function Warn($m){ Write-Host "[pdf][warn] $m" -ForegroundColor Yellow }

# Resolve script and repo paths robustly (PWSH 5.1 safe)
$scriptDir = $PSScriptRoot
if(-not $scriptDir -or $scriptDir -eq ''){ $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$repoRoot = Split-Path -Parent $scriptDir

$docs = Join-Path $repoRoot 'docs'

# Determine source HTML
if(-not $SourceHtml -or $SourceHtml -eq ''){
  $html = Join-Path $docs 'admin_firewall_rule_onepager.html'
} else {
  if([System.IO.Path]::IsPathRooted($SourceHtml)){
    $html = $SourceHtml
  } else {
    $html = Join-Path $repoRoot $SourceHtml
  }
}

if(-not $Output -or $Output -eq ''){
  # Default output filename derived from html name
  $base = [System.IO.Path]::GetFileNameWithoutExtension($html)
  $Output = Join-Path $repoRoot ($base + '.pdf')
}
if(-not (Test-Path $html)){ Err "Missing source HTML: $html"; exit 1 }

# Edge location lookup (common paths) if not on PATH
$cmd = Get-Command msedge -ErrorAction SilentlyContinue
if($cmd){ $edge = $cmd.Source } else { $edge = $null }
if(-not $edge){
  # Prefer 64-bit Edge if present
  $cand64 = "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
  $cand32 = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  if(Test-Path $cand64){ $edge = $cand64 }
  elseif(Test-Path $cand32){ $edge = $cand32 }
}
if(-not $edge){ Warn "Microsoft Edge not found. Will try Google Chrome / Chromium." }

# Ensure output directory exists
$OutDir = Split-Path -Parent $Output
if($OutDir -and -not (Test-Path $OutDir)){ New-Item -ItemType Directory -Path $OutDir | Out-Null }

# Build file:/// URI (Edge expects a URL; paths with spaces must be quoted)
$resolved = (Resolve-Path $html).Path
# Build a robust file URI via .NET to avoid slash/space pitfalls
$fileUri = ([System.Uri]::new($resolved)).AbsoluteUri

# Headless print to PDF (quote output path inside the arg to preserve spaces)
# Build print arg with quoted path to survive spaces
$printArg = ('--print-to-pdf="' + $Output + '"')
$cmdArgs = @(
  "--headless",
  "--disable-gpu",
  $printArg,
  "--print-to-pdf-no-header",
  "--no-sandbox",
  "$fileUri"
)

function Invoke-Renderer($exe, $argList){
  Info "Using browser at: $exe"
  Info "Writing PDF: $Output"
  Info "Source: $fileUri"
  if(-not $argList){ return 87 } # invalid parameter guard
  $p = Start-Process -FilePath $exe -ArgumentList $argList -PassThru -WindowStyle Hidden
  $p.WaitForExit(); return $p.ExitCode
}

$exitCode = $null
$used = $null
if($edge){ $exitCode = Invoke-Renderer -exe $edge -argList $cmdArgs; $used = 'Edge' }

if(-not (Test-Path $Output)){
  if(-not $edge -or $exitCode -ne 0){ Warn "Primary attempt failed (browser: $used, exit: $exitCode). Trying fallback..." }
  # Retry: copy HTML to a temp path without spaces
  $tmpHtml = Join-Path $env:TEMP 'admin_onepager.html'
  Copy-Item -Path $html -Destination $tmpHtml -Force
  $tmpUri = 'file:///' + (Resolve-Path $tmpHtml).Path.Replace('\\','/').Replace(' ','%20')
  $printArg2 = ('--print-to-pdf="' + $Output + '"')
  $cmdArgs2 = @(
    "--headless",
    "--disable-gpu",
    $printArg2,
    "--print-to-pdf-no-header",
    "--no-sandbox",
    "$tmpUri"
  )
  Info "Retry Source: $tmpUri"
  if($edge){ $exitCode = Invoke-Renderer -exe $edge -argList $cmdArgs2; $used = 'Edge (temp)' }

  # Chrome fallback if still no file
    if(-not (Test-Path $Output)){
      $chrome = $null
      $cmdChrome = Get-Command chrome -ErrorAction SilentlyContinue
      $chromeCandidates = @()
      if($cmdChrome){ $chromeCandidates += $cmdChrome.Source }
      $chromeCandidates += @(
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Chromium\\Application\\chrome.exe'
      )
      $cands = @($chromeCandidates | Where-Object { $_ -and (Test-Path $_) })
      if($cands -and $cands.Count -gt 0){
        $first = $cands[0]
        if((Test-Path $first) -and ($first -like '*.exe')){ $chrome = $first }
      }
      if($chrome){
        Info "Trying Chrome/Chromium fallback..."
        $chPrint = ('--print-to-pdf="' + $Output + '"')
        $chArgs = @(
          "--headless",
          "--disable-gpu",
          $chPrint,
          "$tmpUri"
        )
        $exitCode = Invoke-Renderer -exe $chrome -argList $chArgs; $used = 'Chrome/Chromium'
      }
  }

  if(-not (Test-Path $Output)){
    Err "Failed to generate PDF (output not found). Last renderer: $used, exit code: $exitCode"
    exit 3
  }
}

Info "PDF generated successfully."

[CmdletBinding()]
param(
  [string]$Output
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'docs/admin_firewall_rules_two_apps.html'

$exporter = Join-Path $PSScriptRoot 'export_admin_onepager_pdf.ps1'

if(-not (Test-Path $exporter)){
  Write-Error "Missing exporter at $exporter"; exit 1
}

$params = @{ SourceHtml = $source }
if($Output -and $Output -ne ''){ $params['Output'] = $Output }

& $exporter @params
exit $LASTEXITCODE

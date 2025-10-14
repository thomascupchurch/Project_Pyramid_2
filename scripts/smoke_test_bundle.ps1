$ErrorActionPreference = 'Stop'

function Get-ShortcutInfo($path) {
    $ws = New-Object -ComObject WScript.Shell
    if (Test-Path $path) {
        $l = $ws.CreateShortcut($path)
        [PSCustomObject]@{
            Path   = $path
            Target = $l.TargetPath
            Args   = $l.Arguments
            Icon   = $l.IconLocation
        }
    } else {
        [PSCustomObject]@{ Path=$path; Target='(missing)'; Args=''; Icon='' }
    }
}

Write-Host '[smoke] Starting bundle smoke test...'
$repoRoot = Split-Path -Path $PSScriptRoot -Parent
$exePath = Join-Path -Path $repoRoot -ChildPath 'dist\sign_estimator.exe'
if (-not (Test-Path -LiteralPath $exePath)) { throw "EXE not found at $exePath" }
Write-Host "[smoke] EXE: $exePath"

# Minimize side-effects in tray
$env:SIGN_APP_NO_TOAST = '1'
$env:SIGN_APP_DEBUG = '0'

$p = Start-Process -FilePath $exePath -PassThru -WindowStyle Hidden
try {
    $hostName = '127.0.0.1'
    $port = 8050
    $uri = "http://${hostName}:${port}/health"
    $ok = $false
    $content = $null
    for ($i=0; $i -lt 25; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; $content = $r.Content; break }
        } catch { }
        Start-Sleep -Milliseconds 800
    }
    Write-Host "[smoke] HEALTH_OK=$ok"
    if ($ok -and $content) { $content | Write-Output }
}
finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
}

# Shortcuts
$desktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sign Estimator.lnk'
$startLnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Sign Estimator\Sign Estimator.lnk'
Write-Host '[smoke] Shortcut targets:'
Get-ShortcutInfo $desktopLnk | Format-List | Out-String | Write-Output
Get-ShortcutInfo $startLnk   | Format-List | Out-String | Write-Output

Write-Host '[smoke] Done.'

# Rebuild the live monitor. Safe to run from Windows Task Scheduler:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\update_live.ps1"
# If the download fails, `oilbeta live` keeps serving the last good snapshot and marks the page as such.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force (Join-Path $repo "live") | Out-Null
$log = Join-Path $repo "live\update.log"
"--- $(Get-Date -Format s)" | Out-File -FilePath $log -Append -Encoding utf8
$ErrorActionPreference = "Continue"
$output = & python -m oilbeta.cli live 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$output | Out-File -FilePath $log -Append -Encoding utf8
exit $code

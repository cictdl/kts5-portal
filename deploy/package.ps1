<#
.SYNOPSIS
  Build a deployable zip of the KTS 5.0 portal (code, templates, static files,
  Thirukkural data, deploy scripts) without local data, uploads or caches.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\package.ps1
  -> dist\kts5-portal-YYYYMMDD-HHMM.zip
#>
[CmdletBinding()]
param(
  [string]$OutDir = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutDir) { $OutDir = Join-Path $root "dist" }
$stage = Join-Path $env:TEMP ("kts5-stage-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& robocopy $root $stage /E /NFL /NDL /NJH /NJS /NP `
  /XD instance uploads dist logs venv .venv __pycache__ .claude .pytest_cache .git `
  /XF *.pyc *.sqlite3 *.sqlite3-wal *.sqlite3-shm *.zip secret.key | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$zip = Join-Path $OutDir ("kts5-portal-" + $stamp + ".zip")
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Package: $zip ($size MB)"
Write-Host "Next: copy the zip to the server and run deploy\setup-iis.ps1 there (see deploy\DEPLOY.md)."
exit 0

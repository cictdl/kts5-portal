<#
.SYNOPSIS
  Vendor the portal's pure-Python dependencies into .\lib so the repository
  runs on a server that has only python.exe (no pip, no internet).
  Run after changing requirements.txt, then commit lib\.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\vendor.ps1
#>
[CmdletBinding()]
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$lib = Join-Path $root "lib"
if (Test-Path $lib) { Remove-Item $lib -Recurse -Force }
& $Python -m pip install --quiet --no-compile --upgrade --target $lib flask waitress xlsxwriter qrcode pypng
if ($LASTEXITCODE -ne 0) { throw "pip install --target failed" }
# keep it Python-version independent: drop compiled extensions (MarkupSafe falls back to pure Python) and caches
Get-ChildItem $lib -Recurse -Include *.pyd, *.so | Remove-Item -Force
Get-ChildItem $lib -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
if (Test-Path (Join-Path $lib "bin")) { Remove-Item (Join-Path $lib "bin") -Recurse -Force }
$names = (Get-ChildItem $lib -Directory | Where-Object { $_.Name -notlike "*.dist-info" } | ForEach-Object { $_.Name }) -join ", "
Write-Host "lib\ refreshed: $names"
exit 0

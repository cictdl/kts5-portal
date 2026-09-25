<#
.SYNOPSIS
  Build the self-contained package for Plesk-managed IIS hosting:
  the portal, its Python dependencies vendored into lib\ (pure Python, so any
  Python 3.11+ on the server works without pip), the Plesk web.config, and
  empty instance\, uploads\ and logs\ folders. Extract the zip into the
  subdomain's document root (httpdocs) with the Plesk File Manager.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\package-plesk.ps1
  -> dist\kts5-portal-plesk-YYYYMMDD-HHMM.zip
#>
[CmdletBinding()]
param(
  [string]$OutDir = "",
  [string]$Python = "python",
  [string]$BaseUrl = "https://kts5.digitalarchives.cict.in"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutDir) { $OutDir = Join-Path $root "dist" }
$stage = Join-Path $env:TEMP ("kts5-plesk-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# 1. application files (no local data, caches or previous packages)
& robocopy $root $stage /E /NFL /NDL /NJH /NJS /NP `
  /XD instance uploads dist logs venv .venv lib __pycache__ .claude .pytest_cache .git `
  /XF *.pyc *.sqlite3 *.sqlite3-wal *.sqlite3-shm *.zip secret.key | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

# 2. vendored pure-Python dependencies
$lib = Join-Path $stage "lib"
& $Python -m pip install --quiet --no-compile --upgrade --target $lib flask waitress xlsxwriter qrcode pypng
if ($LASTEXITCODE -ne 0) { throw "pip install --target failed" }
Get-ChildItem $lib -Recurse -Include *.pyd, *.so | Remove-Item -Force          # keep it version-independent (MarkupSafe falls back to pure Python)
Get-ChildItem $lib -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
if (Test-Path (Join-Path $lib "bin")) { Remove-Item (Join-Path $lib "bin") -Recurse -Force }

# 3. Plesk web.config and the data folders
$wc = Get-Content (Join-Path $root "deploy\plesk\web.config") -Raw
$wc = [regex]::Replace($wc, 'name="KTS_BASE_URL" value="[^"]*"', ('name="KTS_BASE_URL" value="' + $BaseUrl + '"'))
[System.IO.File]::WriteAllText((Join-Path $stage "web.config"), $wc, (New-Object System.Text.UTF8Encoding($false)))   # UTF-8 without BOM
foreach ($d in @("instance", "uploads", "logs")) {
  $p = Join-Path $stage $d
  New-Item -ItemType Directory -Force -Path $p | Out-Null
  Set-Content -Path (Join-Path $p ".keep") -Value "" -Encoding ASCII
}

# 4. zip
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$zip = Join-Path $OutDir ("kts5-portal-plesk-" + $stamp + ".zip")
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force
$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Package: $zip ($size MB)"
Write-Host "Upload it with the Plesk File Manager into the subdomain's httpdocs and extract it there (see deploy\PLESK.md)."
exit 0

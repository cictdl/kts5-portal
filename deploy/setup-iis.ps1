<#
.SYNOPSIS
  Install or update the Kashi Tamil Sangamam 5.0 portal on an IIS server.

.DESCRIPTION
  Run this ON THE SERVER in an elevated PowerShell. It
    1. unpacks the package into the install folder (keeping instance\, uploads\ and logs\ from a previous install),
    2. creates a Python virtual environment and installs the requirements,
    3. writes web.config for the chosen mode,
    4. creates the application pool and the IIS site (or an application under an existing site),
    5. grants the pool identity write access to the data folders,
    6. starts everything and calls /healthz.

  Modes
    HttpPlatform (default)  IIS starts serve.py itself through the HttpPlatformHandler module.
    Proxy                   The portal runs as a Windows service; IIS forwards to it with URL Rewrite + ARR.

.EXAMPLE
  .\setup-iis.ps1 -Package C:\temp\kts5-portal-20260925-1300.zip -HostName kts5.cict.in
.EXAMPLE
  .\setup-iis.ps1 -Package C:\temp\kts5.zip -HostName kts5.cict.in -CertThumbprint 3F2A...  # with https binding
.EXAMPLE
  .\setup-iis.ps1 -Package C:\temp\kts5.zip -ParentSite "digitalarchives.cict.in" -AppPath /kts5 -HostName www.digitalarchives.cict.in
.EXAMPLE
  .\setup-iis.ps1 -Package C:\temp\kts5.zip -HostName kts5.cict.in -Mode Proxy
#>
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string]$Package,
  [string]$InstallDir = "C:\inetpub\kts5",
  [string]$SiteName = "KTS5",
  [string]$HostName = "kts5.cict.in",
  [string]$AppPath = "",
  [string]$ParentSite = "Default Web Site",
  [string]$Python = "",
  [string]$BaseUrl = "",
  [string]$CertThumbprint = "",
  [ValidateSet("HttpPlatform", "Proxy")] [string]$Mode = "HttpPlatform",
  [int]$ProxyPort = 8905,
  [switch]$NoHttps
)
$ErrorActionPreference = "Stop"
Import-Module WebAdministration
$inetsrv = Join-Path $env:SystemRoot "System32\inetsrv"
$AppPath = $AppPath.Trim()
if ($AppPath -and -not $AppPath.StartsWith("/")) { $AppPath = "/" + $AppPath }
$AppPath = $AppPath.TrimEnd("/")
$httpsFlag = "1"; if ($NoHttps) { $httpsFlag = "0" }
if (-not $BaseUrl) { $scheme = "https"; if ($NoHttps) { $scheme = "http" }; $BaseUrl = "$scheme`://$HostName$AppPath" }

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

# ---- 0. prerequisites -------------------------------------------------------
Step "Checking prerequisites"
if (-not (Test-Path $Package)) { throw "Package not found: $Package" }
if (-not $Python) {
  foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "python")) {
    try {
      $exe = $candidate.Split(" ")[0]; $args = @(); if ($candidate.Contains(" ")) { $args = @($candidate.Split(" ")[1]) }
      $path = & $exe @args -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $path) { $Python = $path.Trim(); break }
    } catch {}
  }
}
if (-not $Python -or -not (Test-Path $Python)) { throw "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/windows/ (tick 'Add to PATH' and 'Install for all users'), then re-run, or pass -Python C:\Python313\python.exe" }
$ver = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.11") { throw "Python $ver found at $Python; 3.11 or newer is required." }
Write-Host "Python $ver at $Python"
if ($Mode -eq "HttpPlatform" -and -not (Test-Path (Join-Path $inetsrv "HttpPlatformHandler.dll"))) {
  throw "The HttpPlatformHandler IIS module is not installed. Install it from https://www.iis.net/downloads/microsoft/httpplatformhandler (x64) and re-run, or use -Mode Proxy if URL Rewrite + ARR are available."
}
if ($Mode -eq "Proxy") {
  if (-not (Test-Path (Join-Path $inetsrv "rewrite.dll"))) { throw "URL Rewrite is not installed (https://www.iis.net/downloads/microsoft/url-rewrite)." }
  if (-not (Test-Path (Join-Path $inetsrv "requestRouter.dll")) -and -not (Get-ChildItem "$env:ProgramFiles\IIS" -Recurse -Filter "requestRouter.dll" -ErrorAction SilentlyContinue)) { throw "Application Request Routing (ARR) is not installed (https://www.iis.net/downloads/microsoft/application-request-routing)." }
}

# ---- 1. files ---------------------------------------------------------------
Step "Unpacking $Package into $InstallDir"
$tmp = Join-Path $env:TEMP ("kts5-unpack-" + [guid]::NewGuid().ToString("N"))
Expand-Archive -Path $Package -DestinationPath $tmp -Force
$src = $tmp
if (-not (Test-Path (Join-Path $src "serve.py"))) {
  $inner = Get-ChildItem $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName "serve.py") } | Select-Object -First 1
  if ($inner) { $src = $inner.FullName } else { throw "serve.py not found inside the package." }
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
& robocopy $src $InstallDir /MIR /NFL /NDL /NJH /NJS /NP /XD instance uploads logs venv | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
Remove-Item $tmp -Recurse -Force
foreach ($d in @("instance", "uploads", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $d) | Out-Null }

# ---- 2. python environment --------------------------------------------------
Step "Preparing the virtual environment"
$venvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { & $Python -m venv (Join-Path $InstallDir "venv") }
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $InstallDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed. If the server has no internet access, build a wheelhouse on a connected machine: pip download -r requirements.txt -d wheels, copy it, then pip install --no-index --find-links wheels -r requirements.txt" }
Write-Host "Dependencies installed."

# ---- 3. web.config ----------------------------------------------------------
Step "Writing web.config ($Mode mode)"
$templateName = "web.config.template"; if ($Mode -eq "Proxy") { $templateName = "web.config.proxy.template" }
$template = Get-Content (Join-Path $InstallDir "deploy\$templateName") -Raw
$cfg = $template
foreach ($pair in @(@("__PYTHON__", $venvPython), @("__HOME__", $InstallDir), @("__BASE_URL__", $BaseUrl), @("__PREFIX__", $AppPath), @("__PORT__", "$ProxyPort"), @("__HTTPS__", $httpsFlag))) {
  $cfg = $cfg.Replace($pair[0], $pair[1])
}
Set-Content -Path (Join-Path $InstallDir "web.config") -Value $cfg -Encoding UTF8

# ---- 4. IIS objects ---------------------------------------------------------
Step "Configuring IIS"
$pool = $SiteName
if (-not (Test-Path "IIS:\AppPools\$pool")) { New-WebAppPool -Name $pool | Out-Null }
Set-ItemProperty "IIS:\AppPools\$pool" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$pool" -Name startMode -Value "AlwaysRunning"
Set-ItemProperty "IIS:\AppPools\$pool" -Name processModel.idleTimeout -Value ([TimeSpan]::Zero)
Set-ItemProperty "IIS:\AppPools\$pool" -Name recycling.periodicRestart.time -Value ([TimeSpan]::Zero)

if ($AppPath) {
  if (-not (Test-Path "IIS:\Sites\$ParentSite")) { throw "Parent site '$ParentSite' does not exist. Existing sites: " + ((Get-ChildItem IIS:\Sites | ForEach-Object { $_.Name }) -join ", ") }
  $appName = $AppPath.TrimStart("/")
  if (Test-Path "IIS:\Sites\$ParentSite\$appName") { Remove-WebApplication -Site $ParentSite -Name $appName }
  New-WebApplication -Name $appName -Site $ParentSite -PhysicalPath $InstallDir -ApplicationPool $pool | Out-Null
  Write-Host "Application $AppPath created under site '$ParentSite'."
} else {
  if (Test-Path "IIS:\Sites\$SiteName") {
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $InstallDir
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name applicationPool -Value $pool
  } else {
    New-Website -Name $SiteName -PhysicalPath $InstallDir -ApplicationPool $pool -HostHeader $HostName -Port 80 | Out-Null
  }
  if ($CertThumbprint) {
    $cert = Get-Item "Cert:\LocalMachine\My\$CertThumbprint" -ErrorAction Stop
    if (-not (Get-WebBinding -Name $SiteName -Protocol https -HostHeader $HostName -ErrorAction SilentlyContinue)) {
      New-WebBinding -Name $SiteName -Protocol https -Port 443 -HostHeader $HostName -SslFlags 1 | Out-Null
    }
    $binding = Get-WebBinding -Name $SiteName -Protocol https -HostHeader $HostName
    $binding.AddSslCertificate($CertThumbprint, "My")
    Write-Host "https binding for $HostName uses certificate $($cert.Subject)"
  }
  Write-Host "Site '$SiteName' -> $InstallDir (host $HostName)"
}

if ($Mode -eq "Proxy") {
  Set-WebConfigurationProperty -PSPath "MACHINE/WEBROOT/APPHOST" -Filter "system.webServer/proxy" -Name enabled -Value $true
  foreach ($v in @("HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST")) {
    $existing = Get-WebConfiguration -PSPath "MACHINE/WEBROOT/APPHOST" -Filter "system.webServer/rewrite/allowedServerVariables/add[@name='$v']"
    if (-not $existing) { Add-WebConfiguration -PSPath "MACHINE/WEBROOT/APPHOST" -Filter "system.webServer/rewrite/allowedServerVariables" -Value @{name = $v } }
  }
  & (Join-Path $InstallDir "deploy\install-service.ps1") -InstallDir $InstallDir -Port $ProxyPort -BaseUrl $BaseUrl -Prefix $AppPath -Https $httpsFlag
}

# ---- 5. permissions ---------------------------------------------------------
Step "Granting permissions to IIS AppPool\$pool"
& icacls $InstallDir /grant "IIS AppPool\${pool}:(OI)(CI)RX" /Q | Out-Null
foreach ($d in @("instance", "uploads", "logs")) {
  & icacls (Join-Path $InstallDir $d) /grant "IIS AppPool\${pool}:(OI)(CI)M" /Q | Out-Null
}

# ---- 6. start + health check -----------------------------------------------
Step "Starting"
if ((Get-WebAppPoolState $pool).Value -ne "Started") { Start-WebAppPool $pool } else { Restart-WebAppPool $pool }
if (-not $AppPath) { if ((Get-WebsiteState $SiteName).Value -ne "Started") { Start-Website $SiteName } }
Start-Sleep -Seconds 6
$probeHost = $HostName; if ($AppPath) { $probeHost = $HostName }
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1$AppPath/healthz" -Headers @{ Host = $probeHost } -UseBasicParsing -TimeoutSec 60
  Write-Host "Health check: HTTP $($r.StatusCode) $($r.Content)" -ForegroundColor Green
} catch {
  Write-Warning "Health check failed: $($_.Exception.Message)"
  Write-Warning "Look at $InstallDir\logs\stdout*.log (HttpPlatform) or logs\service.log (Proxy), and the Windows Application event log."
}

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Cyan
Write-Host "  1. DNS: point $HostName to this server (A record) if it is a new host name."
Write-Host "  2. TLS: bind a certificate (re-run with -CertThumbprint, or use win-acme for Let's Encrypt)."
Write-Host "  3. Sign in at $BaseUrl/console/login as admin@kts5.local (password Admin@KTS5) and change the password immediately."
Write-Host "  4. Settings: registration and test dates, banner, helpdesk contact; then generate the question bank."
Write-Host "  5. Mail: fill the KTS_SMTP_* variables in $InstallDir\web.config (or run-service.cmd) and restart the pool."
Write-Host "  6. Back up $InstallDir\instance and $InstallDir\uploads (see deploy\DEPLOY.md)."

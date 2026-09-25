<#
.SYNOPSIS
  One-time server preparation for the KTS 5.0 portal on the CICT Plesk/IIS server.

.DESCRIPTION
  Run ON THE SERVER as Administrator (Remote Desktop -> PowerShell, right-click "Run as administrator"):

      Set-ExecutionPolicy -Scope Process Bypass
      cd C:\temp
      .\server-setup.ps1

  What it does (each step is skipped when already satisfied):
    1. Python 3.11+ for all users, on PATH (installs Python 3.13.7 x64 from python.org if none is found).
    2. Microsoft HttpPlatformHandler v1.2 x64 IIS module (downloaded from microsoft.com and installed silently).
    3. Unlocks the IIS configuration sections the portal's web.config uses, server-wide and for the site:
       system.webServer/handlers, httpErrors, httpPlatform, security/requestFiltering.
    4. Points the site's web.config processPath at the absolute python.exe.
    5. Grants the application pool identity write access to instance\, uploads\, logs\.
    6. Keeps the application pool always running (no idle time-out).
    7. Restarts IIS and requests /healthz locally, printing IIS's detailed error if it still fails.

  Nothing else on the server is changed. Existing sites keep working; the module is
  only used by sites whose web.config asks for it.

.PARAMETER HostName   Host name of the portal site (default kts5.digitalarchives.cict.in).
.PARAMETER SitePath   Physical folder of the site; auto-detected from IIS when empty.
.EXAMPLE
  .\server-setup.ps1
.EXAMPLE
  .\server-setup.ps1 -HostName kts5.digitalarchives.cict.in -SitePath "C:\Inetpub\vhosts\digitalarchives.cict.in\kts5.digitalarchives.cict.in"
#>
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [string]$HostName = "kts5.digitalarchives.cict.in",
  [string]$SitePath = "",
  [switch]$SkipPython,
  [switch]$SkipHandler,
  [switch]$NoReset
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$inetsrv = Join-Path $env:SystemRoot "System32\inetsrv"
$appcmd = Join-Path $inetsrv "appcmd.exe"
$work = Join-Path $env:TEMP "kts5-setup"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$PythonUrl = "https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe"
$HandlerLinks = @("https://go.microsoft.com/fwlink/?LinkId=690721", "https://go.microsoft.com/fwlink/?LinkId=690722")  # HttpPlatformHandler v1.2, x64 and x86 (iis.net)
$report = New-Object System.Collections.Generic.List[string]

function Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Note($m) { Write-Host "    $m" }
function Warn($m) { Write-Warning $m; $script:report.Add("WARNING: $m") }

function Get-PythonPath {
  $cands = @()
  foreach ($c in (Get-Command python.exe -All -ErrorAction SilentlyContinue)) { if ($c.Source -notlike "*WindowsApps*") { $cands += $c.Source } }
  try { $p = & py -3 -c "import sys;print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { $cands += $p.Trim() } } catch {}
  foreach ($d in @("C:\Program Files\Python313", "C:\Program Files\Python312", "C:\Program Files\Python311", "C:\Python313", "C:\Python312", "C:\Python311")) {
    if (Test-Path (Join-Path $d "python.exe")) { $cands += (Join-Path $d "python.exe") }
  }
  foreach ($c in ($cands | Select-Object -Unique)) {
    try {
      $v = & $c -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -eq 0 -and $v -and ([version]$v.Trim() -ge [version]"3.11")) { return $c }
    } catch {}
  }
  return $null
}

function Get-DetailedIisError($exception) {
  $resp = $exception.Response
  if (-not $resp) { return "" }
  try {
    $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
    $html = $sr.ReadToEnd()
    $text = [regex]::Replace($html, "<script.*?</script>|<style.*?</style>", " ", "Singleline, IgnoreCase")
    $text = [regex]::Replace($text, "<[^>]+>", " ")
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    $text = [regex]::Replace($text, "[ \t]+", " ")
    $lines = $text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $keep = $lines | Where-Object { $_ -match "HTTP Error|Module|Notification|Handler|Error Code|Config Error|Config File|Requested URL|Physical Path|Logon|Most likely|bad module|cannot be used|locked" } | Select-Object -First 14
    return ($keep -join "`n    ")
  } catch { return "" }
}

# ---------------------------------------------------------------- 0. IIS site
Step "Locating the IIS site for $HostName"
Import-Module WebAdministration
$site = $null
foreach ($s in (Get-Website)) {
  foreach ($b in $s.bindings.Collection) { if ($b.bindingInformation -like "*:$HostName") { $site = $s; break } }
  if ($site) { break }
}
if (-not $site) { $site = Get-Website -Name $HostName -ErrorAction SilentlyContinue }
if ($site) {
  if (-not $SitePath) { $SitePath = [Environment]::ExpandEnvironmentVariables($site.physicalPath) }
  $pool = $site.applicationPool
  Note "site '$($site.name)' -> $SitePath (app pool '$pool')"
} else {
  Warn "No IIS site with a binding for $HostName was found. Site-level steps will be skipped; server-level steps still run."
  $pool = $null
}
if ($SitePath -and -not (Test-Path (Join-Path $SitePath "serve.py"))) { Warn "serve.py not found in $SitePath - is the portal package extracted there?" }

# ---------------------------------------------------------------- 1. Python
Step "Python"
$py = Get-PythonPath
if ($py) { Note "found $py" }
elseif ($SkipPython) { Warn "Python 3.11+ not found and -SkipPython given." }
else {
  $exe = Join-Path $work "python-installer.exe"
  Note "downloading $PythonUrl"
  Invoke-WebRequest -Uri $PythonUrl -OutFile $exe -UseBasicParsing
  Note "installing for all users (quiet) ..."
  $p = Start-Process -FilePath $exe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0" -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Python installer exited with code $($p.ExitCode)" }
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
  $py = Get-PythonPath
  if (-not $py) { throw "Python was installed but could not be located afterwards; open a new PowerShell and re-run." }
  Note "installed $py"
  $report.Add("Python installed: $py")
}
if ($py) { $report.Add("Python: $py (" + (& $py -c "import sys;print(sys.version.split()[0])") + ")") }

# ---------------------------------------------------------------- 2. HttpPlatformHandler
Step "HttpPlatformHandler IIS module"
$dll = Join-Path $inetsrv "HttpPlatformHandler.dll"
$schema = Join-Path $inetsrv "config\schema\httpplatform_schema.xml"
if ((Test-Path $dll) -and (Test-Path $schema)) { Note "already installed ($dll)" }
elseif ($SkipHandler) { Warn "HttpPlatformHandler not installed and -SkipHandler given." }
else {
  $msi = $null
  foreach ($link in $HandlerLinks) {
    try {
      $head = Invoke-WebRequest -Uri $link -Method Head -UseBasicParsing -MaximumRedirection 10
      $final = $head.BaseResponse.ResponseUri.AbsoluteUri
      if ($final -match "amd64|x64") { $msi = Join-Path $work "httpPlatformHandler_amd64.msi"; Note "downloading $final"; Invoke-WebRequest -Uri $final -OutFile $msi -UseBasicParsing; break }
    } catch { Note "link check failed for $link : $($_.Exception.Message)" }
  }
  if (-not $msi) {
    # fall back: the larger of the two files is the x64 build
    $best = $null; $bestLen = 0
    foreach ($link in $HandlerLinks) {
      $f = Join-Path $work ("hph-" + [IO.Path]::GetRandomFileName() + ".msi")
      Invoke-WebRequest -Uri $link -OutFile $f -UseBasicParsing
      $len = (Get-Item $f).Length
      if ($len -gt $bestLen) { $best = $f; $bestLen = $len }
    }
    $msi = $best
  }
  Note "installing $msi (quiet) ..."
  $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$msi`" /qn /norestart /l*v `"$work\httpPlatformHandler-install.log`"" -Wait -PassThru
  if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "HttpPlatformHandler installer exited with code $($p.ExitCode); see $work\httpPlatformHandler-install.log" }
  if (-not (Test-Path $dll)) { throw "Installer finished but $dll is missing; open $work\httpPlatformHandler-install.log" }
  Note "installed"
  $report.Add("HttpPlatformHandler installed")
}
$global = & $appcmd list config -section:system.webServer/globalModules 2>$null | Select-String -Pattern "httpPlatformHandler" -SimpleMatch
if ($global) { Note "registered as a global module" } else { Warn "httpPlatformHandler is not listed in system.webServer/globalModules; the MSI normally registers it - check $work\httpPlatformHandler-install.log" }
$report.Add("HttpPlatformHandler: " + $(if (Test-Path $dll) { "present" } else { "MISSING" }))

# ---------------------------------------------------------------- 3. unlock sections
Step "Unlocking IIS configuration sections for web.config"
$sections = @("system.webServer/handlers", "system.webServer/httpErrors", "system.webServer/httpPlatform", "system.webServer/security/requestFiltering")
foreach ($sec in $sections) {
  try { $out = & $appcmd unlock config -section:$sec 2>&1; Note "server: $sec -> $out" } catch { Note "server: $sec -> $($_.Exception.Message)" }
  if ($site) {
    try { $out = & $appcmd unlock config "$($site.name)" -section:$sec /commit:apphost 2>&1; Note "site  : $sec -> $out" } catch { Note "site  : $sec -> $($_.Exception.Message)" }
  }
}
$report.Add("Sections unlocked: " + ($sections -join ", "))

# ---------------------------------------------------------------- 4. web.config processPath
Step "Site web.config"
if ($SitePath) {
  $wc = Join-Path $SitePath "web.config"
  if (-not (Test-Path $wc)) { Warn "No web.config in $SitePath - upload deploy\plesk\web.config from the portal package there." }
  else {
    $x = Get-Content $wc -Raw
    if ($x -notmatch "<httpPlatform") { Warn "web.config in $SitePath is not the portal's (no <httpPlatform> element) - replace it with deploy\plesk\web.config." }
    elseif ($py -and $x -match 'processPath="python\.exe"') {
      $x = $x -replace 'processPath="python\.exe"', ('processPath="' + $py + '"')
      [IO.File]::WriteAllText($wc, $x, (New-Object System.Text.UTF8Encoding($false)))
      Note "processPath set to $py"
      $report.Add("web.config processPath: $py")
    } else { Note "web.config present" }
  }
  foreach ($d in @("instance", "uploads", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $SitePath $d) | Out-Null }
}

# ---------------------------------------------------------------- 5. permissions + 6. app pool
if ($site) {
  Step "Permissions and application pool"
  $identity = $null
  try {
    $pm = Get-ItemProperty "IIS:\AppPools\$pool" -Name processModel
    if ($pm.identityType -eq "SpecificUser" -and $pm.userName) { $identity = $pm.userName } else { $identity = "IIS AppPool\$pool" }
  } catch { $identity = "IIS AppPool\$pool" }
  Note "pool identity: $identity"
  try {
    & icacls "$SitePath" /grant "${identity}:(OI)(CI)RX" /Q | Out-Null
    foreach ($d in @("instance", "uploads", "logs")) { & icacls (Join-Path $SitePath $d) /grant "${identity}:(OI)(CI)M" /Q | Out-Null }
    Note "write access granted on instance\, uploads\, logs\"
  } catch { Warn "icacls failed for $identity : $($_.Exception.Message)" }
  try {
    Set-ItemProperty "IIS:\AppPools\$pool" -Name processModel.idleTimeout -Value ([TimeSpan]::Zero)
    Set-ItemProperty "IIS:\AppPools\$pool" -Name startMode -Value "AlwaysRunning"
    Note "app pool: idle time-out 0, start mode AlwaysRunning"
  } catch { Note "app pool settings unchanged: $($_.Exception.Message)" }
}

# ---------------------------------------------------------------- 7. restart + check
Step "Restarting IIS and checking the site"
if (-not $NoReset) { & iisreset /noforce | Out-Null; Start-Sleep -Seconds 6 }
elseif ($site) { Restart-WebAppPool $pool; Start-Sleep -Seconds 6 }
[Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
$ok = $false
foreach ($url in @("https://127.0.0.1/healthz", "http://127.0.0.1/healthz")) {
  try {
    $r = Invoke-WebRequest -Uri $url -Headers @{ Host = $HostName } -UseBasicParsing -TimeoutSec 150 -MaximumRedirection 0 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { Write-Host "    $url -> HTTP 200 $($r.Content)" -ForegroundColor Green; $ok = $true; break }
    Note "$url -> HTTP $($r.StatusCode)"
  } catch {
    $code = ""
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    if ($code -eq 301 -or $code -eq 302) { Note "$url -> HTTP $code (Plesk redirect to https; configuration accepted)"; continue }
    Note "$url -> $code $($_.Exception.Message)"
    $detail = Get-DetailedIisError $_.Exception
    if ($detail) { Write-Host "    IIS says:`n    $detail" -ForegroundColor Yellow; $report.Add("Health check failed; IIS detail:`n$detail") }
  }
}
if ($ok) { $report.Add("Health check: OK") }
elseif ($SitePath) { Note "If the portal process failed to start, read the newest file in $SitePath\logs (stdout*.log)." }

Write-Host ""
Write-Host "================ Summary ================" -ForegroundColor Cyan
$report | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Next: open https://$HostName/healthz in a browser, then https://$HostName/console/login (admin@kts5.local / Admin@KTS5, change it at once)."

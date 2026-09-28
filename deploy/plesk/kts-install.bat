@echo off
rem ============================================================================
rem  KTS 5.0 portal - one-step installation and update for the CICT server
rem
rem  WITH ADMINISTRATOR RIGHTS (Remote Desktop on the server: double-click this
rem  file and accept the question of Windows):
rem    1. finds the IIS site of kts.cict.in and its folder
rem    2. downloads the portal from GitHub (cictdl/kts5-portal, branch main)
rem    3. keeps a copy of the files it is about to replace
rem    4. copies the portal into the site folder; the database, the uploads
rem       and the logs of an existing installation are never touched
rem    5. prepares the server: Python, the HttpPlatformHandler IIS module,
rem       IIS permissions, write access (deploy\plesk\server-setup.ps1)
rem    6. restarts the portal and checks that it answers
rem    7. checks the https certificate and says what is left to do
rem
rem  WITHOUT ADMINISTRATOR RIGHTS (started by Plesk: Tools and Settings,
rem  Scheduled Tasks, "Run a command", with the option -Unattended) nothing is
rem  installed on the server. The portal then brings its own Python, kept in
rem  the folder of the site, and is started by the ASP.NET Core Module that
rem  Plesk has already installed in IIS. Only the folder of kts.cict.in is
rem  written to.
rem
rem  Running the file again later updates the portal to the newest version.
rem
rem  Options (after the file name):
rem    -HostName kts.cict.in     another host name
rem    -SitePath "D:\path"       the site folder, if it cannot be found
rem    -RestartIIS               restart the whole of IIS at the end (every
rem                              website on the server stops for some seconds;
rem                              administrator rights only)
rem    -Unattended               ask nothing and do not wait for a key
rem    -Portable                 install as described under WITHOUT, although
rem                              administrator rights are there
rem  Everything that is shown is also written to install-*.log in the folder
rem  kts5-setup and, once the site folder is known, to its logs\ folder.
rem ============================================================================
setlocal
title KTS 5.0 portal - installation

set "KTS_UNATTENDED="
echo %* | "%SystemRoot%\System32\findstr.exe" /i /c:"-Unattended" >nul && set "KTS_UNATTENDED=1"

rem  fltmc answers only to an administrator
set "KTS_ADMIN=1"
fltmc >nul 2>&1
if %errorlevel% neq 0 set "KTS_ADMIN="

if not defined KTS_ADMIN if not defined KTS_UNATTENDED (
  echo Administrator rights are needed. Windows will ask for permission now.
  if "%~1"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  ) else (
    echo With options, start this file from a Command Prompt opened with "Run as administrator".
    pause
  )
  exit /b
)

if defined KTS_ADMIN (set "KTS_WORK=%SystemDrive%\kts5-setup") else (set "KTS_WORK=%TEMP%\kts5-setup")
if not exist "%KTS_WORK%" mkdir "%KTS_WORK%"
set "KTS_PS1=%KTS_WORK%\kts-install.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t = [IO.File]::ReadAllText('%~f0'); $i = $t.IndexOf('#PS-' + 'BEGIN'); [IO.File]::WriteAllText('%KTS_PS1%', $t.Substring($i))"
if not exist "%KTS_PS1%" (
  echo STOPPED: could not write %KTS_PS1%. Nothing was changed.
  if defined KTS_UNATTENDED exit 1
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%KTS_PS1%" %*
set "KTS_RESULT=%errorlevel%"
echo.
if "%KTS_RESULT%"=="0" (echo FINISHED.) else (echo FINISHED WITH PROBLEMS - read the messages above.)
echo.
if defined KTS_UNATTENDED exit %KTS_RESULT%
pause
exit /b %KTS_RESULT%

#PS-BEGIN  -- everything below is PowerShell; the lines above write it to kts5-setup\kts-install.ps1
param(
  [string]$HostName = "kts.cict.in",
  [string]$SitePath = "",
  [string]$Repository = "cictdl/kts5-portal",
  [string]$Branch = "main",
  [string]$PythonPackage = "https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip",
  [switch]$RestartIIS,
  [switch]$Unattended,   # ask nothing: for a run without a screen (Plesk scheduled task)
  [switch]$Portable,     # install without administrator rights (chosen by itself when there are none)
  [switch]$TestOnly      # rehearsal on another computer: needs -SitePath, touches neither IIS nor the website
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { $Portable = $true }
if (-not [Environment]::UserInteractive) { $Unattended = $true }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = Join-Path $env:TEMP "kts5-setup"
if ($isAdmin -and -not $TestOnly) { $work = Join-Path $env:SystemDrive "kts5-setup" }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$problems = New-Object System.Collections.Generic.List[string]
$todo = New-Object System.Collections.Generic.List[string]
$steps = 7
if ($Portable) { $steps = 8 }

function Step($n, $text) { Write-Host ""; Write-Host "[$n/$steps] $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "      $text" }
function Good($text) { Write-Host "      $text" -ForegroundColor Green }
function Bad($text) { Write-Host "      $text" -ForegroundColor Yellow; $script:problems.Add($text) }
function Save-Record {
  try { Stop-Transcript | Out-Null } catch {}
  # a second copy where the Plesk file manager can open it; logs\ is not served to visitors
  if ($script:SitePath -and (Test-Path (Join-Path $script:SitePath "logs"))) {
    try { Copy-Item (Join-Path $work "install-$stamp.log") (Join-Path $script:SitePath "logs\install-$stamp.log") -Force } catch {}
  }
}
function Stop-Here($text) {
  Write-Host ""
  Write-Host "STOPPED: $text" -ForegroundColor Red
  Write-Host "Nothing further was changed."
  Save-Record
  exit 1
}

# The check of the portal must also work while the certificate is still Plesk's own, untrusted one.
Add-Type -TypeDefinition @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public static class KtsCertificates {
    private static bool Accept(object sender, X509Certificate certificate, X509Chain chain, SslPolicyErrors errors) { return true; }
    public static void AcceptAny() { ServicePointManager.ServerCertificateValidationCallback = Accept; }
    public static void Strict() { ServicePointManager.ServerCertificateValidationCallback = null; }
}
"@

function Get-IisExplanation($exception) {
  # IIS explains a failure in the page it sends to a visitor on the server itself.
  if (-not $exception.Response) { return "" }
  try {
    $reader = New-Object System.IO.StreamReader($exception.Response.GetResponseStream())
    $html = $reader.ReadToEnd()
    $plain = [regex]::Replace($html, "<script.*?</script>|<style.*?</style>", " ", "Singleline, IgnoreCase")
    $plain = [regex]::Replace($plain, "<[^>]+>", "`n")
    $plain = [System.Net.WebUtility]::HtmlDecode($plain)
    $lines = $plain -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $keep = $lines | Where-Object { $_ -match "HTTP Error|Module|Notification|Handler|Error Code|Config Error|Config File|Physical Path|Most likely|bad module|cannot be used|locked|ANCM|failed to start|Failed to" } | Select-Object -First 14
    return ($keep -join "`n        ")
  } catch { return "" }
}

function Test-Portal($name, $addresses, $seconds) {
  # Asks for /healthz as a visitor of $name would: by name first, then by the addresses IIS listens on.
  [KtsCertificates]::AcceptAny()
  $result = @{ ok = $false; detail = ""; iis = ""; code = "" }
  $tries = @("https://$name/healthz", "http://$name/healthz")
  foreach ($a in $addresses) { $tries += "http://$a/healthz" }
  foreach ($url in $tries) {
    try {
      $headers = @{}
      if ($url -notlike "*//$name/*") { $headers["Host"] = $name }
      $r = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec $seconds -ErrorAction Stop
      if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"') { $result.ok = $true; $result.code = "200"; $result.detail = "$url -> 200 $($r.Content)"; break }
      $result.code = [string]$r.StatusCode
      $result.detail = "$url -> HTTP $($r.StatusCode), but not the portal's answer"
    } catch {
      $code = ""
      if ($_.Exception.Response) { $code = [string][int]$_.Exception.Response.StatusCode }
      $result.code = $code
      $result.detail = "$url -> $code $($_.Exception.Message)"
      $explanation = Get-IisExplanation $_.Exception
      if ($explanation) { $result.iis = $explanation }
    }
  }
  [KtsCertificates]::Strict()
  return $result
}

function Find-SiteFolder($name) {
  # Without administrator rights IIS cannot be asked; Plesk keeps a site in a folder named after it.
  $roots = @()
  if ($env:plesk_vhosts) { $roots += $env:plesk_vhosts.TrimEnd("\") }
  $roots += (Join-Path $env:SystemDrive "Inetpub\vhosts")
  $labels = $name -split "\."
  foreach ($root in ($roots | Select-Object -Unique)) {
    $candidates = @((Join-Path $root "$name\httpdocs"))
    for ($i = 1; $i -lt ($labels.Count - 1); $i++) {
      $parent = ($labels[$i..($labels.Count - 1)] -join ".")
      $candidates += (Join-Path $root "$parent\$name")
    }
    $candidates += (Join-Path $root $name)
    foreach ($c in $candidates) { if (Test-Path $c -PathType Container) { return $c } }
  }
  return ""
}

function Test-Writable($folder) {
  $probe = Join-Path $folder ("kts-write-test-" + $stamp + ".tmp")
  try { Set-Content -Path $probe -Value "x" -ErrorAction Stop; Remove-Item $probe -Force; return $true } catch { return $false }
}

function Invoke-Program($file, $arguments, $folder, $variables) {
  # Runs a program and returns its exit code and everything it wrote; never stops the script.
  $info = New-Object System.Diagnostics.ProcessStartInfo
  $info.FileName = $file
  $info.Arguments = $arguments
  $info.WorkingDirectory = $folder
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  if ($variables) { foreach ($key in $variables.Keys) { $info.EnvironmentVariables[$key] = [string]$variables[$key] } }
  $result = @{ code = -1; text = "" }
  try {
    $p = [System.Diagnostics.Process]::Start($info)
    $out = $p.StandardOutput.ReadToEndAsync()
    $err = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit(120000)) { try { $p.Kill() } catch {}; $result.text = "no end after two minutes"; return $result }
    $result.code = $p.ExitCode
    $result.text = (($out.Result + "`n" + $err.Result).Trim())
  } catch {
    $result.text = $_.Exception.Message
  }
  return $result
}

function Get-FreePort {
  $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $port = $listener.LocalEndpoint.Port
  $listener.Stop()
  return $port
}

function Write-PortableConfig($path, $python, $module, $full) {
  # web.config that lets the ASP.NET Core Module of IIS start the portal with the Python of the site folder
  $model = ""
  if ($module -eq "AspNetCoreModuleV2") { $model = ' hostingModel="outofprocess"' }
  $lines = @(
    '<?xml version="1.0" encoding="utf-8"?>',
    '<!--',
    '  KTS 5.0 portal: written by deploy\plesk\kts-install.bat for a server on which nothing could be',
    '  installed. IIS starts serve.py through its ASP.NET Core Module, with the Python kept in the',
    '  folder python\ of this site, and hands every request to it.',
    '-->',
    '<configuration>',
    '  <system.webServer>',
    '    <handlers>',
    ('      <add name="aspNetCore" path="*" verb="*" modules="' + $module + '" resourceType="Unspecified" />'),
    '    </handlers>',
    ('    <aspNetCore processPath="' + $python + '" arguments="serve.py" stdoutLogEnabled="true" stdoutLogFile=".\logs\stdout"' + $model + ' startupTimeLimit="120" requestTimeout="00:10:00">'),
    '      <environmentVariables>',
    '        <environmentVariable name="KTS_HOST" value="127.0.0.1" />',
    '        <environmentVariable name="KTS_THREADS" value="8" />',
    '        <environmentVariable name="KTS_HTTPS" value="1" />',
    '        <environmentVariable name="KTS_BEHIND_PROXY" value="1" />',
    ('        <environmentVariable name="KTS_BASE_URL" value="https://' + $HostName + '" />'),
    '        <environmentVariable name="PYTHONIOENCODING" value="utf-8" />',
    '        <environmentVariable name="PYTHONUNBUFFERED" value="1" />',
    '        <environmentVariable name="PYTHONDONTWRITEBYTECODE" value="1" />',
    '        <!-- Outgoing mail: fill in, save, and the site restarts by itself.',
    '        <environmentVariable name="KTS_SMTP_HOST" value="smtp.example.gov.in" />',
    '        <environmentVariable name="KTS_SMTP_PORT" value="587" />',
    '        <environmentVariable name="KTS_SMTP_USER" value="office@cict.in" />',
    '        <environmentVariable name="KTS_SMTP_PASSWORD" value="" />',
    '        <environmentVariable name="KTS_SMTP_FROM" value="office@cict.in" />',
    '        -->',
    '      </environmentVariables>',
    '    </aspNetCore>'
  )
  if ($full) {
    $lines += @(
      '    <security>',
      '      <requestFiltering>',
      '        <requestLimits maxAllowedContentLength="26214400" />',
      '        <!-- never let IIS serve source, data or uploads directly -->',
      '        <hiddenSegments>',
      '          <add segment="kts" />',
      '          <add segment="lib" />',
      '          <add segment="python" />',
      '          <add segment="data" />',
      '          <add segment="templates" />',
      '          <add segment="instance" />',
      '          <add segment="uploads" />',
      '          <add segment="logs" />',
      '          <add segment="deploy" />',
      '          <add segment="tools" />',
      '          <add segment="tests" />',
      '        </hiddenSegments>',
      '      </requestFiltering>',
      '    </security>'
    )
  }
  $lines += @('  </system.webServer>', '</configuration>')
  [IO.File]::WriteAllText($path, ($lines -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

try { Start-Transcript -Path (Join-Path $work "install-$stamp.log") | Out-Null } catch {}
Write-Host "KTS 5.0 portal - installation for $HostName" -ForegroundColor Cyan
Write-Host "Started $(Get-Date -Format 'dd-MM-yyyy HH:mm') as $($identity.Name)"
if ($Portable) {
  Write-Host "Without administrator rights: nothing is installed on the server, the portal brings its own Python." -ForegroundColor Cyan
}

# ------------------------------------------------------------------ 1. the site
Step 1 "Looking for the website $HostName"
$site = $null
$pool = $null
$addresses = @()
if ($TestOnly) {
  if (-not $SitePath) { Stop-Here "a rehearsal needs -SitePath." }
  New-Item -ItemType Directory -Force -Path $SitePath | Out-Null
} elseif ($Portable) {
  if (-not $SitePath) { $SitePath = Find-SiteFolder $HostName }
  if (-not $SitePath) { Stop-Here "the folder of $HostName was not found under $env:plesk_vhosts. Give it with -SitePath ""C:\Inetpub\vhosts\...""." }
  if ($SitePath -notlike "*$HostName*") { Stop-Here "the folder $SitePath does not carry the name $HostName; without administrator rights it cannot be verified that it belongs to this website alone." }
} else {
  try { Import-Module WebAdministration -ErrorAction Stop } catch { Stop-Here "IIS is not installed on this computer (the WebAdministration module is missing). Run this file on the web server." }
  foreach ($s in (Get-Website)) {
    foreach ($b in $s.bindings.Collection) {
      $boundHost = ($b.bindingInformation -split ":")[-1]
      if ($boundHost -ieq $HostName) { $site = $s }
    }
  }
  if (-not $site) { $site = Get-Website | Where-Object { $_.Name -ieq $HostName } | Select-Object -First 1 }
  if ($site) {
    $pool = $site.applicationPool
    if (-not $SitePath) { $SitePath = [Environment]::ExpandEnvironmentVariables($site.physicalPath) }
    Note "site '$($site.Name)', application pool '$pool'"
    # The folder must belong to this host name alone: the portal replaces web.config,
    # and any other website served from the same folder would stop working.
    $others = @()
    foreach ($b in $site.bindings.Collection) {
      $parts = $b.bindingInformation -split ":"
      $boundHost = $parts[-1]
      if ($boundHost -and ($boundHost -ine $HostName) -and ($boundHost -ine "www.$HostName") -and ($boundHost -notlike "*.$HostName")) { $others += $boundHost }
      # where IIS listens for plain http, for the check of the portal
      if ($b.protocol -eq "http" -and $parts.Count -ge 3) {
        $ip = ($parts[0..($parts.Count - 3)] -join ":")
        if (-not $ip -or $ip -eq "*") { $ip = "127.0.0.1" }
        if ($ip -like "*:*") { $ip = "[$ip]" }
        $addresses += "$($ip):$($parts[-2])"
      }
    }
    $addresses = @($addresses | Select-Object -Unique)
    $others = @($others | Select-Object -Unique)
    if ($others.Count -gt 0) {
      Stop-Here ("the IIS site of $HostName also serves: " + ($others -join ", ") + ". The portal needs a website of its own. In Plesk, create $HostName as a separate subdomain (not as an alias), then run this file again.")
    }
  } elseif (-not $SitePath) {
    Stop-Here "no website with the name $HostName exists in IIS. Create the subdomain in Plesk first (Websites & Domains, Add Subdomain), or give the folder: kts-install.bat -SitePath ""D:\folder"""
  }
}
if (-not (Test-Path $SitePath)) { Stop-Here "the folder $SitePath does not exist." }
$SitePath = (Resolve-Path $SitePath).Path.TrimEnd("\")
if (-not (Test-Writable $SitePath)) { Stop-Here "the folder $SitePath cannot be written to by $($identity.Name)." }
Good "folder: $SitePath"
$existing = Test-Path (Join-Path $SitePath "serve.py")
if ($existing) { Note "the portal is already installed here: this run updates it" }

# ------------------------------------------------------------------ 2. download
Step 2 "Downloading the portal from GitHub ($Repository, branch $Branch)"
$zip = Join-Path $work "portal-$stamp.zip"
$unpacked = Join-Path $work "src-$stamp"
$url = "https://github.com/$Repository/archive/refs/heads/$Branch.zip"
try {
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 600
} catch {
  Stop-Here "the download of $url failed: $($_.Exception.Message). The server needs access to github.com."
}
Note ("downloaded {0:N1} MB" -f ((Get-Item $zip).Length / 1MB))
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpacked)
$source = Get-ChildItem -Path $unpacked -Directory | Select-Object -First 1
if (-not $source) { Stop-Here "the downloaded file is empty." }
$source = $source.FullName
foreach ($must in @("serve.py", "web.config", "kts\__init__.py", "lib", "templates", "static", "data\i18n\en.json", "deploy\plesk\server-setup.ps1")) {
  if (-not (Test-Path (Join-Path $source $must))) { Stop-Here "the download is incomplete: $must is missing." }
}
$languages = @(Get-ChildItem (Join-Path $source "data\i18n") -Filter *.json).Count
Good "complete: portal with $languages interface languages"

# ------------------------------------------------------------------ 3. safety copy
Step 3 "Keeping a copy of the files that will be replaced"
$backup = Join-Path $work "before-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$keepConfig = $false
$config = Join-Path $SitePath "web.config"
if (Test-Path $config) {
  Copy-Item $config (Join-Path $backup "web.config") -Force
  $text = [IO.File]::ReadAllText($config)
  if (-not $Portable -and $text -match "<httpPlatform" -and $text -match [regex]::Escape("https://$HostName")) {
    # the portal's own file, possibly with the mail settings or the path of Python entered by hand
    $keepConfig = $true
    Note "web.config of the portal is kept as it is (mail settings and the like stay)"
  } else {
    Note "web.config is replaced; the old one is in $backup"
  }
}
foreach ($name in @("index.html", "index.htm", "default.htm", "iisstart.htm")) {
  $page = Join-Path $SitePath $name
  if (Test-Path $page) { Move-Item $page (Join-Path $backup $name) -Force; Note "$name moved to $backup" }
}
if ($existing) {
  foreach ($folder in @("kts", "templates")) {
    if (Test-Path (Join-Path $SitePath $folder)) { Copy-Item (Join-Path $SitePath $folder) (Join-Path $backup $folder) -Recurse -Force }
  }
  foreach ($file in @("config.py", "serve.py")) {
    if (Test-Path (Join-Path $SitePath $file)) { Copy-Item (Join-Path $SitePath $file) (Join-Path $backup $file) -Force }
  }
  $database = Join-Path $SitePath "instance\kts5.sqlite3"
  if (Test-Path $database) {
    Copy-Item $database (Join-Path $backup "kts5.sqlite3") -Force
    Note ("the database ({0:N1} MB) was copied to $backup as well" -f ((Get-Item $database).Length / 1MB))
  }
}
Good "copy kept in $backup"

# ------------------------------------------------------------------ 4. copy
Step 4 "Copying the portal into $SitePath"
$skipFiles = @(".gitignore", ".gitattributes", "*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "secret.key")
if ($keepConfig -or $Portable) { $skipFiles += "web.config" }
$arguments = @($source, $SitePath, "/E", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NP", "/XD",
  (Join-Path $source "instance"), (Join-Path $source "uploads"), (Join-Path $source "logs"), (Join-Path $source ".git"), (Join-Path $source ".github"), (Join-Path $source ".claude"),
  "/XF") + $skipFiles
& robocopy @arguments | Out-Host
if ($LASTEXITCODE -ge 8) { Stop-Here "copying failed (robocopy code $LASTEXITCODE). A file may be in use or the folder is not writable." }
foreach ($folder in @("instance", "uploads", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $SitePath $folder) | Out-Null }
if ($keepConfig) { Copy-Item (Join-Path $source "web.config") (Join-Path $SitePath "web.config.from-github") -Force }
Good "files in place"

if ($TestOnly -and -not $Portable) {
  Write-Host ""
  Write-Host "Rehearsal finished: files copied to $SitePath, nothing else was done." -ForegroundColor Green
  Save-Record
  exit 0
}

$check = @{ ok = $false; detail = ""; iis = ""; code = "" }

if ($Portable) {
  # ---------------------------------------------------------------- 5. Python of its own
  Step 5 "Python for the portal, inside the site folder"
  $pythonFolder = Join-Path $SitePath "python"
  $python = Join-Path $pythonFolder "python.exe"
  if (-not (Test-Path $python)) {
    # what an interrupted run left behind would stand in the way of unpacking
    if (Test-Path $pythonFolder) { Remove-Item $pythonFolder -Recurse -Force }
    $package = Join-Path $work "python-embed.zip"
    try {
      Invoke-WebRequest -Uri $PythonPackage -OutFile $package -UseBasicParsing -TimeoutSec 900
    } catch {
      Stop-Here "the download of $PythonPackage failed: $($_.Exception.Message)"
    }
    Note ("downloaded {0:N1} MB from python.org" -f ((Get-Item $package).Length / 1MB))
    New-Item -ItemType Directory -Force -Path $pythonFolder | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($package, $pythonFolder)
  } else {
    Note "already there"
  }
  # This Python looks for modules only where its ._pth file says: its own files, the portal and lib\.
  $pth = Get-ChildItem $pythonFolder -Filter "python*._pth" | Select-Object -First 1
  if (-not $pth) { Stop-Here "the Python package is not the embeddable one (no ._pth file in $pythonFolder)." }
  $library = Get-ChildItem $pythonFolder -Filter "python*.zip" | Select-Object -First 1
  [IO.File]::WriteAllText($pth.FullName, (@($library.Name, ".", $SitePath, (Join-Path $SitePath "lib")) -join "`r`n") + "`r`n", (New-Object System.Text.ASCIIEncoding))
  $test = Invoke-Program $python "-c ""import sys, sqlite3, ssl, json; import flask, waitress, jinja2, werkzeug; print(sys.version.split()[0] + ', SQLite ' + sqlite3.sqlite_version)""" $SitePath $null
  if ($test.code -ne 0) {
    Stop-Here "Python does not work from $python : $($test.text) . The server may forbid programs in the folders of websites."
  }
  Good "Python $($test.text)"

  # ---------------------------------------------------------------- 6. write access for IIS
  Step 6 "Write access of the website to instance\, uploads\ and logs\"
  $names = @()
  try {
    $names = @((Get-Acl $SitePath).Access | ForEach-Object { $_.IdentityReference.Value } | Select-Object -Unique)
  } catch { Note "the permissions of the folder could not be read: $($_.Exception.Message)" }
  $workers = @($names | Where-Object { $_ -match "IWPD_|IWAM_|IUSR|IIS APPPOOL|IIS_IUSRS" })
  if ($workers.Count -eq 0) {
    Note ("no account of IIS is named in the permissions of the folder (found: " + ($names -join "; ") + ")")
    $todo.Add("If the portal cannot write: in Plesk, Websites & Domains > $HostName > Hosting Settings, tick 'Additional write/modify permissions'.")
  }
  foreach ($worker in $workers) {
    $granted = $true
    foreach ($folder in @("instance", "uploads", "logs")) {
      $grant = Invoke-Program (Join-Path $env:SystemRoot "System32\icacls.exe") ("""" + (Join-Path $SitePath $folder) + """ /grant """ + $worker + ":(OI)(CI)M"" /T /C /Q") $SitePath $null
      if ($grant.code -ne 0) { $granted = $false; Note "$folder for $worker : $($grant.text)" }
    }
    if ($granted) { Note "may write: $worker" }
  }

  # The portal is first started without IIS: whatever fails here has nothing to do with IIS.
  $port = Get-FreePort
  $direct = $false
  $errors = Join-Path $work "direct-$stamp.err"
  $process = $null
  try {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = Join-Path $env:SystemRoot "System32\cmd.exe"
    $info.Arguments = "/c """"" + $python + """ serve.py 1>""" + (Join-Path $work "direct-$stamp.out") + """ 2>""" + $errors + """"""
    $info.WorkingDirectory = $SitePath
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.EnvironmentVariables["KTS_PORT"] = [string]$port
    $info.EnvironmentVariables["KTS_HOST"] = "127.0.0.1"
    $info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $process = [System.Diagnostics.Process]::Start($info)
    for ($i = 0; $i -lt 40 -and -not $direct; $i++) {
      Start-Sleep -Seconds 2
      if ($process.HasExited) { break }
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"') { $direct = $true }
      } catch {}
    }
  } catch {
    Note "the portal could not be started: $($_.Exception.Message)"
  } finally {
    # cmd.exe and the Python it started
    if ($process -and -not $process.HasExited) {
      [void](Invoke-Program (Join-Path $env:SystemRoot "System32\taskkill.exe") ("/PID " + $process.Id + " /T /F") $SitePath $null)
    }
  }
  if ($direct) {
    Good "started by itself, the portal answers (database and keys are in instance\)"
  } else {
    Bad "started by itself, the portal does not answer"
    if (Test-Path $errors) { Get-Content $errors -Tail 25 | ForEach-Object { Write-Host "        $_" } }
    Stop-Here "the portal itself does not start on this server; the messages above say why. The website was left as it was, apart from the copied files."
  }

  if ($TestOnly) {
    Write-PortableConfig (Join-Path $SitePath "web.config") $python "AspNetCoreModuleV2" $true
    Write-Host ""
    Write-Host "Rehearsal finished: files and Python in $SitePath, the portal starts; IIS was not touched." -ForegroundColor Green
    Save-Record
    exit 0
  }

  # ---------------------------------------------------------------- 7. IIS starts the portal
  Step 7 "Letting IIS start the portal (ASP.NET Core Module)"
  $attempts = @(
    @{ module = "AspNetCoreModuleV2"; full = $true; name = "module V2, with protected folders" },
    @{ module = "AspNetCoreModuleV2"; full = $false; name = "module V2, shortest form" },
    @{ module = "AspNetCoreModule"; full = $false; name = "module V1, shortest form" }
  )
  $used = ""
  foreach ($attempt in $attempts) {
    Write-PortableConfig $config $python $attempt.module $attempt.full
    Note "trying: $($attempt.name)"
    Start-Sleep -Seconds 3
    $check = Test-Portal $HostName $addresses 150
    if (-not $check.ok) { Start-Sleep -Seconds 10; $check = Test-Portal $HostName $addresses 150 }
    if ($check.ok) { $used = $attempt.name; break }
    Note "  no: $($check.detail)"
    if ($check.iis) { Write-Host "        IIS says: $($check.iis)" -ForegroundColor Yellow }
  }
  if ($check.ok) {
    Good "the portal answers through IIS ($used): $($check.detail)"
  } else {
    Bad "IIS does not start the portal with any of the three forms of web.config"
    $log = Get-ChildItem (Join-Path $SitePath "logs") -Filter "stdout*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log -and $log.Length -gt 0) {
      Note "last lines of $($log.Name):"
      Get-Content $log.FullName -Tail 15 | ForEach-Object { Write-Host "        $_" }
    }
    # a website that answers every address with an error is worse than Plesk's own page
    if (Test-Path (Join-Path $backup "web.config")) { Copy-Item (Join-Path $backup "web.config") $config -Force } else { Remove-Item $config -Force -ErrorAction SilentlyContinue }
    foreach ($name in @("index.html", "index.htm")) {
      if (Test-Path (Join-Path $backup $name)) { Copy-Item (Join-Path $backup $name) (Join-Path $SitePath $name) -Force }
    }
    Note "web.config was taken back, so that the website shows what it showed before"
  }
} else {
  # ------------------------------------------------------------------ 5. the server
  Step 5 "Preparing the server (Python, IIS module, permissions)"
  $setup = Join-Path $SitePath "deploy\plesk\server-setup.ps1"
  $setupArguments = @{ HostName = $HostName; SitePath = $SitePath }
  if (-not $RestartIIS) { $setupArguments["NoReset"] = $true }
  try {
    & $setup @setupArguments
  } catch {
    Bad "the server preparation stopped: $($_.Exception.Message)"
  }

  # ------------------------------------------------------------------ 6. does it answer?
  Step 6 "Checking that the portal answers"
  Start-Sleep -Seconds 3
  $check = Test-Portal $HostName $addresses 120
  if (-not $check.ok) {
    # the first start creates the database and may take a little longer
    Start-Sleep -Seconds 15
    $check = Test-Portal $HostName $addresses 120
  }
  if (-not $check.ok -and -not $RestartIIS) {
    Note "no answer yet: $($check.detail)"
    Write-Host ""
    Write-Host "      A newly installed IIS module sometimes needs IIS itself to be restarted." -ForegroundColor Yellow
    Write-Host "      That stops EVERY website on this server for about ten seconds." -ForegroundColor Yellow
    if ($Unattended) {
      Note "IIS was not restarted, because nobody could be asked. To allow it, run this file again with -RestartIIS"
      $todo.Add("If the portal does not answer: run kts-install.bat again with the option -RestartIIS added (every website on the server stops for about ten seconds).")
    } else {
      $answer = Read-Host "      Restart IIS now? Type Y and Enter to restart, anything else to leave it"
      if ($answer -match "^[Yy]") {
        & iisreset /noforce | Out-Host
        Start-Sleep -Seconds 10
        $check = Test-Portal $HostName $addresses 120
      }
    }
  }
  if ($check.ok) {
    Good "the portal answers: $($check.detail)"
  } else {
    Bad "the portal does not answer: $($check.detail)"
    if ($check.iis) {
      Write-Host "      IIS says:" -ForegroundColor Yellow
      Write-Host "        $($check.iis)" -ForegroundColor Yellow
    }
    $log = Get-ChildItem (Join-Path $SitePath "logs") -Filter "stdout*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log -and $log.Length -gt 0) {
      Note "last lines of $($log.FullName):"
      Get-Content $log.FullName -Tail 15 | ForEach-Object { Write-Host "        $_" }
    } else {
      Note "the portal wrote no log, so IIS did not start it; the lines marked 'IIS says' above give the reason"
    }
  }
}

# ------------------------------------------------------------------ certificate
Step $steps "Checking the https certificate of $HostName"
$trusted = $false
try {
  $r = Invoke-WebRequest -Uri "https://$HostName/healthz" -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop
  if ($r.StatusCode -eq 200) { $trusted = $true }
} catch {
  $message = $_.Exception.Message
  if ($_.Exception.InnerException) { $message = $message + " " + $_.Exception.InnerException.Message }
  if ($message -match "trust|certificate|SSL|TLS") {
    Note "the certificate is not trusted yet"
  } else {
    Note "could not be checked from this machine ($message)"
  }
}
if ($trusted) {
  Good "https://$HostName works with a valid certificate"
} else {
  $todo.Add("Certificate: in Plesk open Websites & Domains > $HostName > SSL/TLS Certificates, install the free Let's Encrypt certificate, then tick 'Permanent SEO-safe 301 redirect from HTTP to HTTPS' in Hosting Settings. Signing in works only over https.")
}
if ($check.ok) {
  $todo.Add("First sign-in: https://$HostName/console/login with the administrator account named in README.md; the portal makes you set a new password at once.")
  $todo.Add("Then, in the console: Settings (dates, contact), Question bank > Generate, Notices.")
  if ($Portable) { $todo.Add("Do not connect this folder to Git in Plesk: the web.config of the repository is written for a server with the HttpPlatformHandler module. To update the portal, run this task again.") }
}

Write-Host ""
Write-Host "================ Result ================" -ForegroundColor Cyan
if ($check.ok) { Write-Host "  The portal is installed and running in $SitePath" -ForegroundColor Green } else { Write-Host "  The files are installed in $SitePath, but the portal does not run yet." -ForegroundColor Yellow }
foreach ($p in $problems) { Write-Host "  PROBLEM: $p" -ForegroundColor Yellow }
if ($todo.Count -gt 0) {
  Write-Host ""
  Write-Host "  Still to do by hand:" -ForegroundColor Cyan
  $n = 0
  foreach ($t in $todo) { $n++; Write-Host "   $n. $t" }
}
Write-Host ""
Write-Host "  Copy of the replaced files: $backup"
Write-Host "  Record of this run:         logs\install-$stamp.log in the site folder (Plesk, Files)"
Save-Record
if ($check.ok) { exit 0 } else { exit 2 }

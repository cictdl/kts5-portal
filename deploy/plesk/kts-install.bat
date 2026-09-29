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
rem  written to. The folders deploy, tests, tools and dist are not copied
rem  then, and the run makes sure that the new version is the one that answers.
rem
rem  Running the file again later updates the portal to the newest version.
rem  An update never touches instance\ (database, keys, portal.env with the
rem  settings of the installation, first-admin.txt), uploads\ and logs\.
rem  Without administrator rights, visitors see a page that says so while
rem  an update replaces the files, and a run that stops after it has
rem  replaced files puts the files of before back from its safety copy: the
rem  website then runs the version it ran. With administrator rights there
rem  is no such page, and a new version that does not start stays in place:
rem  the files of before are in the safety copy.
rem
rem  Options (after the file name):
rem    -HostName kts.cict.in     another host name
rem    -SitePath "D:\path"       the site folder, if it cannot be found
rem    -SourcePath "D:\folder"   take the portal from this folder instead of
rem                              downloading it from GitHub (for rehearsals)
rem    -RestartIIS               restart the whole of IIS at the end (every
rem                              website on the server stops for some seconds;
rem                              administrator rights only)
rem    -Unattended               ask nothing and do not wait for a key
rem    -Portable                 install as described under WITHOUT, although
rem                              administrator rights are there
rem    -TestOnly                 rehearsal on another computer: needs -SitePath,
rem                              touches neither IIS nor the website
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
  [string]$SourcePath = "",  # take the portal from this folder instead of downloading it (rehearsals)
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
$backup = Join-Path $work "before-$stamp"
$problems = New-Object System.Collections.Generic.List[string]
$todo = New-Object System.Collections.Generic.List[string]
$stale = $false   # the portal answers, but with the code of before the update
$offline = $false   # this run put the page 'being updated' in place and has not taken it away yet
$replaced = $false   # this run replaces the files of an installed portal, and the new version does not answer yet
$configWritten = $false   # this run has written web.config, or replaced it
$takenBack = $false   # the run put the files of before back
$keptFolders = @()   # what the safety copy holds of the installed portal: folders of the program ...
$keptFiles = @()   # ... and files of the site's root
$movedPages = @()   # start pages of the hosting that step 3 moved into the safety copy
$oldVersion = ""   # the version of the files before this run
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
function Restore-Config {
  # The web.config of before the run is put back; one that this run wrote where there was none is
  # taken away. Says which of the two was done, or nothing when neither worked.
  $config = Join-Path $script:SitePath "web.config"
  $kept = Join-Path $script:backup "web.config"
  for ($turn = 1; $turn -le 5; $turn++) {
    try {
      if (Test-Path $kept) { Copy-Item $kept $config -Force -ErrorAction Stop; return "web.config of before this run was put back" }
      if (Test-Path $config) { Remove-Item $config -Force -ErrorAction Stop }
      return "web.config of this run was taken away (there was none before)"
    } catch { Start-Sleep -Seconds 2 }
  }
  return ""
}

function Undo-Update {
  # For a run that ends without the new version. The files of the version that ran before are put back
  # from the safety copy (what only the new version has may stay), and only then the page 'being
  # updated' is taken away, so that IIS starts the program of before and not the one that failed.
  # Says what it did and never stops the script: Stop-Here, the trap and step 7 call it.
  $folder = $script:SitePath
  $files = $script:replaced
  $done = @()
  $failed = @()
  try {
    if ($files) {
      $script:replaced = $false
      $script:takenBack = $true
      if ($script:configWritten -and -not $script:offline -and $Portable) {
        # IIS may have started the new program: it is stopped while its files are taken away
        $script:offline = $true
        try { Write-OfflinePage $folder; Start-Sleep -Seconds 3 } catch {}
      }
      foreach ($name in $script:keptFolders) {
        # /IS /IT /IM: every file of the copy, also one that looks the same by size and time. A robocopy
        # that does not know /IM yet copies nothing and says 16: it is asked again without.
        & robocopy (Join-Path $script:backup $name) (Join-Path $folder $name) /E /IS /IT /IM /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 16) { & robocopy (Join-Path $script:backup $name) (Join-Path $folder $name) /E /IS /IT /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null }
        if ($LASTEXITCODE -ge 8) { $failed += "$name\" }
      }
      foreach ($name in $script:keptFiles) {
        try { Copy-Item (Join-Path $script:backup $name) (Join-Path $folder $name) -Force -ErrorAction Stop } catch { $failed += $name }
      }
      # kts\version.py says which version the files are: one that only the new version brought does not stay
      $number = Join-Path $folder "kts\version.py"
      if (($script:keptFolders -contains "kts") -and (Test-Path $number) -and -not (Test-Path (Join-Path $script:backup "kts\version.py"))) {
        try { Remove-Item $number -Force -ErrorAction Stop } catch { $failed += "kts\version.py (it names the new version and has to be deleted)" }
      }
    }
    if ($script:configWritten) {
      $script:configWritten = $false
      $said = Restore-Config
      if ($said) { $done += $said } else { $failed += "web.config" }
    }
    foreach ($name in $script:movedPages) {
      try { Copy-Item (Join-Path $script:backup $name) (Join-Path $folder $name) -Force -ErrorAction Stop; $done += "$name was put back" } catch { $failed += $name }
    }
    $script:movedPages = @()
  } catch { $failed += "($($_.Exception.Message))" }
  $gone = $true
  # also a page that an earlier try of this run could not take away
  if ($script:offline -or ($folder -and ($files -or $done.Count -gt 0) -and (Test-Path (Join-Path $folder "app_offline.htm")))) {
    $script:offline = $false
    try { $gone = Remove-OfflinePage $folder } catch { $gone = $false }
  }
  if (-not ($files -or $done.Count -gt 0 -or $failed.Count -gt 0)) {
    if (-not $gone) { Bad "app_offline.htm could not be removed from $folder : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
    Write-Host "Nothing further was changed."
    return
  }
  if ($files) { Note "the files of the version that ran before this run were put back from $($script:backup); other files that only the new version has were left in place" }
  foreach ($said in $done) { Note $said }
  if ($failed.Count -gt 0) { Bad ("could not be put back from $($script:backup) : " + ($failed -join ", ") + ". Run the task again; until then the website may not work") }
  if (-not $gone) { Bad "app_offline.htm could not be removed from $folder : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
  if ($files -and (Test-Path (Join-Path $folder "instance\first-admin.txt"))) {
    Note "the account of the administrator and its first password are in instance\first-admin.txt (Plesk: Files > instance > first-admin.txt)"
  }
  if (-not $files) {
    if ($failed.Count -eq 0) { Note "the website shows what it showed before this run; the files of the portal stay in $folder" }
    return
  }
  if ($TestOnly -or -not $Portable) { Note "the website was not asked whether it answers"; return }
  Start-Sleep -Seconds 3
  $now = Test-Portal $HostName $script:addresses 150
  $named = "version $($now.version)"
  if (-not $now.version) { $named = "a version that does not name its number, so one older than 1.1.0" }
  if ($now.ok -and $now.version -eq $script:oldVersion) { Good "the website runs the version it ran before this run ($named): $($now.detail)" }
  elseif ($now.ok) { Bad "the website answers as $named, the files that were put back are version '$($script:oldVersion)': the program was not started anew. In Plesk recycle the IIS application pool of $HostName" }
  else { Bad "after the files were put back the website does not answer: $($now.detail)" }
}

function Confirm-Update {
  # The new version stays: from here on a run that ends puts nothing back.
  $script:replaced = $false
  $script:configWritten = $false
  $script:movedPages = @()
}

function Stop-Here($text) {
  Write-Host ""
  Write-Host "STOPPED: $text" -ForegroundColor Red
  Undo-Update
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
    # Invoke-WebRequest has read an answer that names its length to the end already
    $stream = $exception.Response.GetResponseStream()
    if ($stream.CanSeek) { $stream.Position = 0 }
    $reader = New-Object System.IO.StreamReader($stream)
    $html = $reader.ReadToEnd()
    $plain = [regex]::Replace($html, "<script.*?</script>|<style.*?</style>", " ", "Singleline, IgnoreCase")
    $plain = [regex]::Replace($plain, "<[^>]+>", "`n")
    $plain = [System.Net.WebUtility]::HtmlDecode($plain)
    $lines = $plain -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $keep = $lines | Where-Object { $_ -match "HTTP Error|Module|Notification|Handler|Error Code|Config Error|Config File|Physical Path|Most likely|bad module|cannot be used|locked|ANCM|failed to start|Failed to" } | Select-Object -First 14
    return ($keep -join "`n        ")
  } catch { return "" }
}

function Get-Version($content) {
  # the version that an answer of /healthz names; empty when it names none (a portal older than 1.1.0)
  if ([string]$content -match '"version"\s*:\s*"([^"]*)"') { return $Matches[1] }
  return ""
}

function Get-FileVersion($folder) {
  # the version of the files in the folder: the line VERSION = "1.1.0" of kts\version.py
  $file = Join-Path $folder "kts\version.py"
  if (-not (Test-Path $file)) { return "" }
  foreach ($line in (Get-Content $file)) {
    if ($line -match '^\s*VERSION\s*=\s*["'']([^"'']+)["'']') { return $Matches[1] }
  }
  return ""
}

function Test-Portal($name, $addresses, $seconds) {
  # Asks for /healthz as a visitor of $name would: by name first, then by the addresses IIS listens on.
  # content is what the portal answered, version the version it names there.
  [KtsCertificates]::AcceptAny()
  $result = @{ ok = $false; detail = ""; iis = ""; code = ""; content = ""; version = "" }
  $tries = @("https://$name/healthz", "http://$name/healthz")
  foreach ($a in $addresses) { $tries += "http://$a/healthz" }
  foreach ($url in $tries) {
    try {
      $headers = @{}
      if ($url -notlike "*//$name/*") { $headers["Host"] = $name }
      $r = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec $seconds -ErrorAction Stop
      if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"') {
        $result.ok = $true; $result.code = "200"; $result.detail = "$url -> 200 $($r.Content)"
        $result.content = [string]$r.Content; $result.version = Get-Version $r.Content
        break
      }
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

function Write-OfflinePage($folder) {
  # While app_offline.htm lies in the site folder, the ASP.NET Core Module stops the portal and shows this page.
  $lines = @(
    '<!DOCTYPE html>',
    '<html lang="en">',
    '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>KTS 5.0</title></head>',
    '<body style="font-family: sans-serif; text-align: center; padding: 15% 1em 0 1em">',
    '<p>The portal is being updated. Please try again in a minute.</p>',
    '<p lang="ta">&#2951;&#2979;&#3016;&#2991;&#2980;&#2995;&#2990;&#3021; &#2986;&#3009;&#2980;&#3009;&#2986;&#3021;&#2986;&#3007;&#2965;&#3021;&#2965;&#2986;&#3021;&#2986;&#2975;&#3009;&#2965;&#3007;&#2993;&#2980;&#3009;. &#2962;&#2992;&#3009; &#2984;&#3007;&#2990;&#3007;&#2975;&#2990;&#3021; &#2965;&#2996;&#3007;&#2980;&#3021;&#2980;&#3009; &#2990;&#3008;&#2979;&#3021;&#2975;&#3009;&#2990;&#3021; &#2990;&#3009;&#2991;&#2993;&#3021;&#2970;&#3007;&#2965;&#3021;&#2965;&#2997;&#3009;&#2990;&#3021;.</p>',
    '</body>',
    '</html>'
  )
  [IO.File]::WriteAllText((Join-Path $folder "app_offline.htm"), ($lines -join "`r`n") + "`r`n", (New-Object System.Text.ASCIIEncoding))
}

function Remove-OfflinePage($folder) {
  # app_offline.htm must never stay: as long as it is there, no visitor reaches the portal.
  $page = Join-Path $folder "app_offline.htm"
  for ($i = 0; $i -lt 5 -and (Test-Path $page); $i++) {
    if ($i -gt 0) { Start-Sleep -Seconds 2 }
    try { Remove-Item $page -Force -ErrorAction Stop } catch {}
  }
  return (-not (Test-Path $page))
}

function Restart-Portal($folder, $name, $addresses) {
  # The module ends python.exe while the page is in place (it waits up to ten seconds for it) and starts
  # it again, with the files that are in the folder now, at the first request after the page is gone.
  $seen = ""
  $placed = $false
  $removed = $true
  try {
    Write-OfflinePage $folder
    $placed = $true
    Start-Sleep -Seconds 8
    $seen = (Test-Portal $name $addresses 10).code
    Start-Sleep -Seconds 4
  } catch {
    Note "the page 'being updated' could not be put in place: $($_.Exception.Message)"
  } finally {
    $removed = Remove-OfflinePage $folder
  }
  if ($seen -eq "503") { Note "IIS showed the page 'being updated' and stopped the portal" }
  elseif ($placed) { Note "while the page 'being updated' was in place, IIS answered: '$seen' (503 was expected)" }
  if (-not $removed) { Bad "app_offline.htm could not be removed from $folder : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
  Start-Sleep -Seconds 3
  $again = Test-Portal $name $addresses 150
  if (-not $again.ok) { Start-Sleep -Seconds 10; $again = Test-Portal $name $addresses 150 }
  return $again
}

function Confirm-NewCode($folder, $name, $addresses, $check, $settingsChanged) {
  # Python reads its code once, at start. After an update the portal that answers must name the version
  # of the files; if it does not, it is restarted, once, and asked again.
  $expected = Get-FileVersion $folder
  if ($expected -and $check.version -eq $expected -and -not $settingsChanged) {
    Good "the portal that answers is version $expected, the version of the files"
    return $check
  }
  if ($expected -and $check.version -eq $expected) { Note "instance\portal.env was changed after the last run: the portal is restarted so that it reads the settings" }
  elseif ($check.version) { Note "the portal that answers is version $($check.version), the files are version '$expected': the portal is restarted" }
  else { Note "the portal that answers does not name its version: it is restarted, so that the files of this run are the ones in use" }
  $again = Restart-Portal $folder $name $addresses
  if (-not $again.ok) {
    Bad "after the restart the portal does not answer: $($again.detail)"
    return $again
  }
  if ($again.version -eq $expected) {
    if ($expected) { Good "restarted: the portal that answers is now version $expected, the version of the files" }
    else { Note "restarted; these files do not name a version (no kts\version.py), so there is nothing to compare" }
  } else {
    $script:stale = $true
    Bad "after the restart the portal still answers as version '$($again.version)', the files are version '$expected': the old program is still running, and with the templates of the new version its pages may answer with an error"
    $script:todo.Add("The new version is not running yet: in Plesk recycle the IIS application pool of $name (Websites & Domains > $name > Dedicated IIS Application Pool for Website > Recycle), then open https://$name/healthz and read ""version"".")
  }
  return $again
}

function Write-SettingsFile($file) {
  # instance\portal.env, written once and with comments only: nothing is set until somebody enters it
  $lines = @(
    '# KTS 5.0 portal - settings of this installation',
    '#',
    '# One setting on a line, written NAME=value : no quotation marks, no spaces around the = sign.',
    '# Names in capital letters. Nothing may follow the value on its line: no comment, no semicolon.',
    '# A line that begins with # is a comment. The portal reads this file when it starts; a name that',
    '# the web server defines itself (web.config) is taken from there. No update replaces this file.',
    '# After a change run the installation again (Plesk, Scheduled Tasks): the portal is restarted.',
    '#',
    '# Outgoing mail. Without it, mails wait in Console > Mail outbox.',
    '# KTS_SMTP_HOST=smtp.example.gov.in',
    '# KTS_SMTP_PORT=587',
    '# KTS_SMTP_USER=office@cict.in',
    '# KTS_SMTP_PASSWORD=',
    '# KTS_SMTP_FROM=office@cict.in',
    '# KTS_SMTP_TLS=1',
    '#',
    '# Limits, with the values that apply when nothing is set. Per address of the visitor, in one hour:',
    '# KTS_RATE_REGISTER_PER_HOUR=100',
    '# KTS_RATE_CONTACT_PER_HOUR=10',
    '# Failed attempts in 15 minutes, per address: status check, staff sign-in, candidate sign-in.',
    '# KTS_RATE_STATUS_FAILS=300',
    '# KTS_RATE_LOGIN_FAILS=12',
    '# KTS_RATE_CANDIDATE_FAILS_IP=600',
    '# Failed attempts in 15 minutes for one application number from one address, counted for the',
    '# candidate sign-in and, apart from it, for the status check:',
    '# KTS_RATE_CANDIDATE_FAILS_APP=6',
    '#',
    '# Strict-Transport-Security. Set 1 only after the real certificate is installed, and only if HSTS',
    '# is not switched on in Plesk: never in both places.',
    '# KTS_HSTS=0'
  )
  [IO.File]::WriteAllText($file, ($lines -join "`r`n") + "`r`n", (New-Object System.Text.ASCIIEncoding))
}

function Get-SettingNames($file) {
  # the names that a settings file defines; comment lines define nothing
  $names = @()
  if (Test-Path $file) {
    foreach ($line in (Get-Content $file)) {
      if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { $names += $Matches[1].ToUpper() }
    }
  }
  return $names
}

function Add-Setting($file, $name, $value) {
  # one more line NAME=value, in the encoding the file has (Notepad may have saved it as UTF-16)
  $bytes = [IO.File]::ReadAllBytes($file)
  $encoding = New-Object System.Text.UTF8Encoding($false)
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { $encoding = New-Object System.Text.UnicodeEncoding($false, $false) }
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) { $encoding = New-Object System.Text.UnicodeEncoding($true, $false) }
  $line = $name + "=" + $value + "`r`n"
  $before = [IO.File]::ReadAllText($file)
  if ($before -and -not $before.EndsWith("`n")) { $line = "`r`n" + $line }
  [IO.File]::AppendAllText($file, $line, $encoding)
}

function Get-MailSettings($text) {
  # KTS_SMTP_ entries that somebody entered into a web.config by hand; what stands inside a comment does not count
  $found = [ordered]@{}
  $plain = [regex]::Replace([string]$text, "<!--.*?-->", "", "Singleline")
  # a value in quotation marks may hold the sign > : the tag ends at the first > outside of them
  foreach ($tag in [regex]::Matches($plain, "<environmentVariable\b(?:[^>""']|""[^""]*""|'[^']*')*>", "IgnoreCase")) {
    $n = [regex]::Match($tag.Value, '\bname\s*=\s*(?:"([^"]*)"|''([^'']*)'')')
    $v = [regex]::Match($tag.Value, '\bvalue\s*=\s*(?:"([^"]*)"|''([^'']*)'')')
    if (-not ($n.Success -and $v.Success)) { continue }
    $name = ($n.Groups[1].Value + $n.Groups[2].Value).Trim().ToUpper()
    $value = [System.Net.WebUtility]::HtmlDecode($v.Groups[1].Value + $v.Groups[2].Value)
    if ($name -match '^KTS_SMTP_[A-Z0-9_]+$' -and $value.Trim()) { $found[$name] = $value }
  }
  return $found
}

function Get-SignInNote($folder, $name) {
  # Says where the first password is, never what it is: this text goes into the record of the run.
  if (Test-Path (Join-Path $folder "instance\first-admin.txt")) {
    return "First sign-in: https://$name/console/login . The account and its first password are in the file instance\first-admin.txt of the site folder; open it in Plesk (Files > instance > first-admin.txt). The portal asks for a new password at once and removes the file afterwards."
  }
  if (-not (Get-FileVersion $folder)) {
    # a portal older than 1.1.0 does not write the file, so its absence says nothing
    return "Sign-in: https://$name/console/login ."
  }
  return "Sign-in: https://$name/console/login . The administrator password has already been set (there is no instance\first-admin.txt)."
}

function Test-Refused($text) {
  # true when a run has recorded in this web.config that the hosting refused the hardened form
  return ([string]$text -match "<!--[^>]*this hosting refused the strictest form of this file[^>]*-->")
}

function Get-Attempts($oldConfig) {
  # Module and form of web.config, in the order in which step 7 tries them. A hosting that refused the
  # hardened form is not asked again by later runs: the run that saw it writes a line into the
  # web.config it keeps, and only that line in the web.config of before makes a run leave the form out.
  # (Delete the line in web.config to have the form tried once more.)
  $attempts = @(
    @{ module = "AspNetCoreModuleV2"; form = "hardened"; name = "module V2, with protected folders and without the headers that name the software" },
    @{ module = "AspNetCoreModuleV2"; form = "full"; name = "module V2, with protected folders" },
    @{ module = "AspNetCoreModuleV2"; form = "short"; name = "module V2, shortest form" },
    @{ module = "AspNetCoreModule"; form = "short"; name = "module V1, shortest form" }
  )
  if (Test-Refused $oldConfig) { $attempts = @($attempts | Where-Object { $_.form -ne "hardened" }) }
  return $attempts
}

function Copy-Database($database, $kept, $python) {
  # The safety copy of the database. Made by SQLite itself, with the Python of the site, it also holds
  # what the portal has not yet written into the main file (kts5.sqlite3-wal); where that does not work,
  # the main file is copied as it is. Says true when the copy was made by SQLite.
  if (Test-Path $python) {
    $copy = Invoke-Program $python ('-B -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" "' + $database + '" "' + $kept + '"') (Split-Path $python -Parent) $null
    if ($copy.code -eq 0 -and (Test-Path $kept)) { return $true }
    Note "the copy of the database through SQLite did not work ($($copy.text)): the file is copied as it is"
  }
  Copy-Item $database $kept -Force
  return $false
}

function Write-InstanceConfig($path) {
  # instance\web.config: IIS serves no file of that folder, whatever the web.config of the site says
  # and also when there is none. Written once; no run replaces it or takes it away.
  $lines = @(
    '<?xml version="1.0" encoding="utf-8"?>',
    '<!--',
    '  KTS 5.0 portal: written once by deploy\plesk\kts-install.bat. This folder holds the database, the',
    '  keys, the settings and, until it is changed, the first password: IIS serves no file of it.',
    '-->',
    '<configuration>',
    '  <system.webServer>',
    '    <security>',
    '      <requestFiltering>',
    '        <fileExtensions allowUnlisted="false" />',
    '      </requestFiltering>',
    '    </security>',
    '  </system.webServer>',
    '</configuration>'
  )
  [IO.File]::WriteAllText($path, ($lines -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Write-PortableConfig($path, $python, $module, $form, $refused) {
  # web.config that lets the ASP.NET Core Module of IIS start the portal with the Python of the site folder.
  # $form: "hardened" (request limits, hidden folders, no Server and X-Powered-By headers),
  #        "full" (request limits and hidden folders), "short" (neither, for hostings that lock those sections)
  # $refused: the hosting has refused the hardened form; the file then carries the record of it
  $model = ""
  if ($module -eq "AspNetCoreModuleV2") { $model = ' hostingModel="outofprocess"' }
  $lines = @(
    '<?xml version="1.0" encoding="utf-8"?>',
    '<!--',
    '  KTS 5.0 portal: written by deploy\plesk\kts-install.bat for a server on which nothing could be',
    '  installed. IIS starts serve.py through its ASP.NET Core Module, with the Python kept in the',
    '  folder python\ of this site, and hands every request to it.',
    '-->'
  )
  if ($refused) {
    # the line that Test-Refused looks for in a later run
    $lines += '<!-- Record of kts-install.bat: this hosting refused the strictest form of this file (without the headers that name the software). That form is not tried again as long as this line stands here. -->'
  }
  $lines += @(
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
    '        <!-- Settings of this installation (outgoing mail, limits) belong into instance\portal.env,',
    '             which no update replaces. This file is written anew by every run of kts-install.bat. -->',
    '      </environmentVariables>',
    '    </aspNetCore>'
  )
  if ($form -eq "hardened" -or $form -eq "full") {
    $filtering = '      <requestFiltering>'
    if ($form -eq "hardened") { $filtering = '      <requestFiltering removeServerHeader="true">' }
    $lines += @(
      '    <security>',
      $filtering,
      '        <!-- 30 MB, above the 25 MB of the portal: a larger file is then refused by the portal, in the language of the visitor -->',
      '        <requestLimits maxAllowedContentLength="31457280" />',
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
  if ($form -eq "hardened") {
    $lines += @(
      '    <httpProtocol>',
      '      <customHeaders>',
      '        <remove name="X-Powered-By" />',
      '      </customHeaders>',
      '    </httpProtocol>'
    )
  }
  $lines += @('  </system.webServer>', '</configuration>')
  $text = ($lines -join "`r`n") + "`r`n"
  # another program may hold the file for a moment
  for ($turn = 1; ; $turn++) {
    try { [IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false))); return }
    catch { if ($turn -ge 5) { throw }; Start-Sleep -Seconds 2 }
  }
}

# An error that nobody catches must not leave the website behind the page 'being updated' or with the
# files of two versions.
trap {
  Write-Host ""
  Write-Host "STOPPED by an error that was not expected: $($_.Exception.Message)" -ForegroundColor Red
  try { Write-Host ("      " + (([string]$_.InvocationInfo.PositionMessage) -replace "`r?`n", "`n      ")) } catch {}
  try { Undo-Update } catch {}
  try { Save-Record } catch {}
  exit 1
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
# A page 'being updated' that an interrupted run left behind would keep every visitor away.
if (Test-Path (Join-Path $SitePath "app_offline.htm")) {
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  try { Copy-Item (Join-Path $SitePath "app_offline.htm") (Join-Path $backup "app_offline.htm") -Force } catch {}
  if (Remove-OfflinePage $SitePath) { Note "app_offline.htm, left behind by an earlier run, was taken out of the site folder" }
  else { Bad "app_offline.htm could not be removed from $SitePath : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
}

# ------------------------------------------------------------------ 2. download
Add-Type -AssemblyName System.IO.Compression.FileSystem
if ($SourcePath) {
  Step 2 "Taking the portal from the folder $SourcePath (nothing is downloaded)"
  if (-not (Test-Path $SourcePath -PathType Container)) { Stop-Here "the folder $SourcePath does not exist." }
  $source = (Resolve-Path $SourcePath).Path.TrimEnd("\")
  $from = $source + "\"
  $to = $SitePath + "\"
  if ($from.StartsWith($to, [StringComparison]::OrdinalIgnoreCase) -or $to.StartsWith($from, [StringComparison]::OrdinalIgnoreCase)) {
    Stop-Here "the folder of -SourcePath and the site folder lie inside each other."
  }
} else {
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
  [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpacked)
  $source = Get-ChildItem -Path $unpacked -Directory | Select-Object -First 1
  if (-not $source) { Stop-Here "the downloaded file is empty." }
  $source = $source.FullName
}
foreach ($must in @("serve.py", "web.config", "kts\__init__.py", "kts\version.py", "lib", "templates", "static", "data\i18n\en.json", "deploy\plesk\server-setup.ps1")) {
  if (-not (Test-Path (Join-Path $source $must))) { Stop-Here "the portal is incomplete: $must is missing in $source." }
}
$languages = @(Get-ChildItem (Join-Path $source "data\i18n") -Filter *.json).Count
$newVersion = Get-FileVersion $source
if ($newVersion) { Good "complete: portal version $newVersion with $languages interface languages" }
else { Good "complete: portal with $languages interface languages" }

# ------------------------------------------------------------------ 3. safety copy
Step 3 "Keeping a copy of the files that will be replaced"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
# what step 4 never takes from the source, and so never replaces in the site folder
$skipFiles = @(".gitignore", ".gitattributes", "*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "secret.key", "first-admin.txt", "portal.env", "app_offline.htm", "*.pyc")
$keepConfig = $false
$oldConfig = ""
$config = Join-Path $SitePath "web.config"
if (Test-Path $config) {
  Copy-Item $config (Join-Path $backup "web.config") -Force
  $text = [IO.File]::ReadAllText($config)
  $oldConfig = $text
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
  if (Test-Path $page) { Move-Item $page (Join-Path $backup $name) -Force; $movedPages += $name; Note "$name moved to $backup" }
}
if ($existing) {
  # Everything that step 4 replaces, so that a run that stops can put the version of before back: the
  # folders of the program and the files of the site's root that the source has as well. Never
  # instance\, uploads\, logs\ and python\, which no run replaces.
  $oldVersion = Get-FileVersion $SitePath
  foreach ($folder in @("kts", "templates", "static", "data", "lib")) {
    if (-not (Test-Path (Join-Path $SitePath $folder) -PathType Container)) { continue }
    & robocopy (Join-Path $SitePath $folder) (Join-Path $backup $folder) /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { Stop-Here "the folder $folder\ could not be copied to $backup (robocopy code $LASTEXITCODE). Without that copy a failed update could not be taken back, so no file of the portal was replaced." }
    $keptFolders += $folder
  }
  foreach ($file in (Get-ChildItem $source -File -Force)) {
    $name = $file.Name
    if ($name -ieq "web.config" -or -not (Test-Path (Join-Path $SitePath $name) -PathType Leaf)) { continue }
    if (@($skipFiles | Where-Object { $name -like $_ }).Count -gt 0) { continue }
    Copy-Item (Join-Path $SitePath $name) (Join-Path $backup $name) -Force
    $keptFiles += $name
  }
  Note ("kept, to be put back if the run stops: " + ((@($keptFolders | ForEach-Object { "$_\" }) + $keptFiles) -join ", "))
  $database = Join-Path $SitePath "instance\kts5.sqlite3"
  if (Test-Path $database) {
    $kept = Join-Path $backup "kts5.sqlite3"
    if (Copy-Database $database $kept (Join-Path $SitePath "python\python.exe")) {
      Note ("the database ({0:N1} MB) was copied to $backup as well, through SQLite: the copy is complete" -f ((Get-Item $kept).Length / 1MB))
    } else {
      Note ("the main file of the database ({0:N1} MB) was copied to $backup as well; what the portal had not yet written into it (kts5.sqlite3-wal) is not in the copy" -f ((Get-Item $database).Length / 1MB))
    }
  }
}
# Without administrator rights the running portal is all that the site folder needs: the scripts of the
# installation, the tests, the tools and packages are left out, and what an earlier run copied is taken
# out. (A web.config of the repository inside deploy\plesk made IIS answer every address below it with 500.)
# Nothing is taken out of a folder in which no portal is installed yet, and dist\ is never taken out:
# no run has ever copied it.
$leaveOut = @()
if ($Portable) { $leaveOut = @("deploy", "tests", "tools", "dist") }
foreach ($folder in @($leaveOut | Where-Object { $existing -and $_ -ne "dist" })) {
  $old = Join-Path $SitePath $folder
  if (-not (Test-Path $old -PathType Container)) { continue }
  # robocopy also moves from one drive to another, which Move-Item does not do with a folder
  & robocopy $old (Join-Path $backup $folder) /E /MOVE /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
  $code = $LASTEXITCODE
  if ((Test-Path $old) -and -not (Get-ChildItem $old -Recurse -Force | Where-Object { -not $_.PSIsContainer })) {
    # only empty folders are left
    try { Remove-Item $old -Recurse -Force -ErrorAction Stop } catch {}
  }
  if ($code -ge 8 -or (Test-Path $old)) { Bad "the folder $folder\ could not be moved out of the site folder completely (robocopy code $code): delete $folder in Plesk (Files)" }
  else { Note "$folder\ is not needed by the running portal: moved to $backup" }
}
Good "copy kept in $backup"

# ------------------------------------------------------------------ 4. copy
Step 4 "Copying the portal into $SitePath"
if ($keepConfig -or $Portable) { $skipFiles += "web.config" }
$skipFolders = @("instance", "uploads", "logs", ".git", ".github", ".claude") + $leaveOut | ForEach-Object { Join-Path $source $_ }
# caches of Python, which a folder given with -SourcePath may hold; by name, wherever they are
$skipFolders += @("__pycache__", ".pytest_cache")
$arguments = @($source, $SitePath, "/E", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NP", "/XD") + $skipFolders + @("/XF") + $skipFiles
if ($Portable -and $existing) {
  # The program that is running reads its templates anew at every request, its code only at start: with
  # the new templates it would answer 500 on every page. While the page is in place, the module stops
  # the program and shows the page; the new program starts with the new files.
  $offline = $true
  try {
    Write-OfflinePage $SitePath
    Note "visitors see the page 'being updated' until the new version starts"
    Start-Sleep -Seconds 3
  } catch { Note "the page 'being updated' could not be put in place: $($_.Exception.Message)" }
}
# from here on a run that stops puts back what it has replaced (Undo-Update)
if ($existing) { $replaced = $true }
if ($skipFiles -notcontains "web.config") { $configWritten = $true }
& robocopy @arguments | Out-Host
if ($LASTEXITCODE -ge 8) { Stop-Here "copying failed (robocopy code $LASTEXITCODE). A file may be in use or the folder is not writable." }
foreach ($folder in @("instance", "uploads", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $SitePath $folder) | Out-Null }
# instance\ is closed to visitors by a web.config of its own, before the portal writes anything into it
$closed = Join-Path $SitePath "instance\web.config"
if (-not (Test-Path $closed)) {
  try { Write-InstanceConfig $closed; Note "instance\web.config written: IIS serves no file of instance\ to a visitor" }
  catch { Note "instance\web.config could not be written: $($_.Exception.Message)" }
}
if ($keepConfig) { Copy-Item (Join-Path $source "web.config") (Join-Path $SitePath "web.config.from-github") -Force }
Good "files in place"

# The settings of the installation: instance\portal.env. An existing file stays as it is; the one thing
# ever added to it is a mail setting that was entered by hand into the web.config that is now replaced.
$settings = Join-Path $SitePath "instance\portal.env"
$settingsChanged = $false
$record = Get-ChildItem (Join-Path $SitePath "logs") -Filter "install-*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($existing -and $record -and (Test-Path $settings) -and (Get-Item $settings).LastWriteTime -gt $record.LastWriteTime) { $settingsChanged = $true }
try {
  if (-not (Test-Path $settings)) {
    Write-SettingsFile $settings
    Note "instance\portal.env created: the place for the settings of this installation (mail, limits); it sets nothing yet"
  }
  if ($oldConfig -and -not $keepConfig) {
    $carried = Get-MailSettings $oldConfig
    $defined = @(Get-SettingNames $settings)
    $added = @()
    foreach ($key in $carried.Keys) {
      if ($defined -contains $key) { continue }
      Add-Setting $settings $key $carried[$key]
      $added += $key
    }
    if ($added.Count -gt 0) {
      $settingsChanged = $true
      Note ("mail settings that were entered into the old web.config were carried over to instance\portal.env: " + ($added -join ", ") + " (values are not shown)")
    }
  }
} catch {
  Bad "instance\portal.env could not be written: $($_.Exception.Message)"
}

if ($TestOnly -and -not $Portable) {
  Confirm-Update
  Write-Host ""
  Write-Host "Rehearsal finished: files copied to $SitePath, nothing else was done." -ForegroundColor Green
  Save-Record
  exit 0
}

$check = @{ ok = $false; detail = ""; iis = ""; code = ""; content = ""; version = "" }

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
  $directVersion = ""
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
    # the first start writes instance\first-admin.txt, which names the sign-in page
    $info.EnvironmentVariables["KTS_BASE_URL"] = "https://$HostName"
    $info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $process = [System.Diagnostics.Process]::Start($info)
    for ($i = 0; $i -lt 40 -and -not $direct; $i++) {
      Start-Sleep -Seconds 2
      if ($process.HasExited) { break }
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"') { $direct = $true; $directVersion = Get-Version $r.Content }
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
    $expected = Get-FileVersion $SitePath
    if (-not $expected) { Note "these files do not name a version (no kts\version.py)" }
    elseif ($directVersion -eq $expected) { Note "it answers as version $expected, the version of the files" }
    else { Note "it answers as version '$directVersion', but kts\version.py says $expected" }
  } else {
    Bad "started by itself, the portal does not answer"
    if (Test-Path $errors) { Get-Content $errors -Tail 25 | ForEach-Object { Write-Host "        $_" } }
    Stop-Here "the portal itself does not start on this server; the messages above say why. No web.config was written."
  }

  if ($TestOnly) {
    $configWritten = $true
    Write-PortableConfig (Join-Path $SitePath "web.config") $python "AspNetCoreModuleV2" "hardened" $false
    if ($offline) {
      $offline = $false
      if (-not (Remove-OfflinePage $SitePath)) { Bad "app_offline.htm could not be removed from $SitePath : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
    }
    Confirm-Update
    Note (Get-SignInNote $SitePath $HostName)
    Write-Host ""
    Write-Host "Rehearsal finished: files and Python in $SitePath, the portal starts; IIS was not touched." -ForegroundColor Green
    foreach ($p in $problems) { Write-Host "  PROBLEM: $p" -ForegroundColor Yellow }
    Write-Host "  Copy of the replaced files: $backup"
    Save-Record
    exit 0
  }

  # ---------------------------------------------------------------- 7. IIS starts the portal
  Step 7 "Letting IIS start the portal (ASP.NET Core Module)"
  # A hosting may have locked a section of the configuration: IIS then answers 500.19 and the next,
  # shorter form is tried. The second form is the one that was accepted on the CICT server.
  $attempts = @(Get-Attempts $oldConfig)
  $refused = Test-Refused $oldConfig
  if ($refused) { Note "web.config holds the record of an earlier run that this hosting refused the strictest form: it is not tried again" }
  $used = ""
  $written = 0
  foreach ($attempt in $attempts) {
    # a form that could not be written is not tested: the file in place would answer in its name
    $configWritten = $true
    try { Write-PortableConfig $config $python $attempt.module $attempt.form $refused }
    catch { Note "web.config could not be written ($($attempt.name)): $($_.Exception.Message)"; continue }
    $written++
    if ($offline) {
      # the new files and the first web.config are in place: from here on IIS starts the new version
      $offline = $false
      if (-not (Remove-OfflinePage $SitePath)) { Bad "app_offline.htm could not be removed from $SitePath : delete it in Plesk (Files), no visitor reaches the portal while it is there" }
    }
    Note "trying: $($attempt.name)"
    Start-Sleep -Seconds 3
    $check = Test-Portal $HostName $addresses 150
    # IIS names a locked section as the cause: the hosting refuses the form, and waiting does not help
    $no = (-not $check.ok -and $attempt.form -eq "hardened" -and $check.code -eq "500" -and $check.iis -match "cannot be used at this path|is locked")
    if (-not $check.ok -and -not $no) {
      # anything else is asked a second time; a 500 that is still there then is a refusal as well
      $first = $check.code
      Start-Sleep -Seconds 10; $check = Test-Portal $HostName $addresses 150
      $no = (-not $check.ok -and $attempt.form -eq "hardened" -and $first -eq "500" -and $check.code -eq "500")
    }
    if ($check.ok) { $used = $attempt.name; break }
    Note "  no: $($check.detail)"
    if ($check.iis) { Write-Host "        IIS says: $($check.iis)" -ForegroundColor Yellow }
    if ($no) {
      $refused = $true
      Note "  the hosting refuses this form"
    }
  }
  if ($check.ok) {
    Confirm-Update
    Good "the portal answers through IIS ($used): $($check.detail)"
    if ($refused -and -not (Test-Refused $oldConfig)) { Note "web.config records that the strictest form was refused: later runs do not try it again" }
    $check = Confirm-NewCode $SitePath $HostName $addresses $check $settingsChanged
  } else {
    if ($written -eq 0) { Bad "web.config could not be written in any of its forms: the file is in use or protected against writing" }
    else { Bad "IIS does not start the portal with any of the $written forms of web.config that were tried" }
    $log = Get-ChildItem (Join-Path $SitePath "logs") -Filter "stdout*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log -and $log.Length -gt 0) {
      Note "last lines of $($log.Name):"
      Get-Content $log.FullName -Tail 15 | ForEach-Object { Write-Host "        $_" }
    }
    # a website that answers every address with an error is worse than what it showed before
    Undo-Update
  }
} else {
  # ------------------------------------------------------------------ 5. the server
  # with administrator rights nothing is put back by itself: the preparation of the server restarts the
  # application pool, and whoever runs this file can reach the safety copy
  Confirm-Update
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
    # the application pool was restarted by the preparation of the server, so the new files are in use
    $expected = Get-FileVersion $SitePath
    if ($expected -and $check.version -ne $expected) {
      $stale = $true
      Bad "the portal answers as version '$($check.version)', the files are version '$expected'. Recycle the application pool of $HostName in IIS"
    }
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
if ($takenBack) { $todo.Add("The new version is not installed. Read the messages above, remove the cause and run this task again.") }
if ($check.ok) {
  $todo.Add((Get-SignInNote $SitePath $HostName))
  $todo.Add("Then, in the console: Settings (dates, contact), Question bank > Generate, Notices.")
  if ($Portable) { $todo.Add("Do not connect this folder to Git in Plesk: the web.config of the repository is written for a server with the HttpPlatformHandler module. To update the portal, run this task again.") }
}

Write-Host ""
Write-Host "================ Result ================" -ForegroundColor Cyan
if ($check.ok -and $stale) { Write-Host "  The files of the new version are in $SitePath, but the program that answers is the one of before." -ForegroundColor Yellow }
elseif ($check.ok) { Write-Host "  The portal is installed and running in $SitePath" -ForegroundColor Green }
elseif ($takenBack) { Write-Host "  The update was taken back: $SitePath holds the files of the version that ran before this run." -ForegroundColor Yellow }
else { Write-Host "  The files are installed in $SitePath, but the portal does not run yet." -ForegroundColor Yellow }
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
Write-Host "  Settings (mail, limits):    instance\portal.env in the site folder; run this file again after a change"
Save-Record
if ($check.ok -and -not $stale) { exit 0 } else { exit 2 }

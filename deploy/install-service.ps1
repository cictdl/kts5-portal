<#
.SYNOPSIS
  Run the KTS 5.0 portal as a background service (reverse-proxy mode).
  Uses NSSM when available (nssm.exe on PATH or next to this script);
  otherwise registers a Scheduled Task that starts at boot and restarts
  on failure. setup-iis.ps1 -Mode Proxy calls this for you.

.EXAMPLE
  .\install-service.ps1 -InstallDir C:\inetpub\kts5 -Port 8905 -BaseUrl https://kts5.cict.in
#>
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [string]$InstallDir = "C:\inetpub\kts5",
  [string]$ServiceName = "KTS5Portal",
  [int]$Port = 8905,
  [string]$BaseUrl = "https://kts5.cict.in",
  [string]$Prefix = "",
  [string]$Https = "1"
)
$ErrorActionPreference = "Stop"
$python = Join-Path $InstallDir "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment not found at $python. Run setup-iis.ps1 first." }
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "logs") | Out-Null

# wrapper script with the environment
$template = Get-Content (Join-Path $PSScriptRoot "run-service.cmd.template") -Raw
$cmd = $template
foreach ($pair in @(@("__HOME__", $InstallDir), @("__PORT__", "$Port"), @("__PYTHON__", $python), @("__BASE_URL__", $BaseUrl), @("__PREFIX__", $Prefix), @("__HTTPS__", $Https))) {
  $cmd = $cmd.Replace($pair[0], $pair[1])
}
$wrapper = Join-Path $InstallDir "run-service.cmd"
Set-Content -Path $wrapper -Value $cmd -Encoding ASCII

# data folders must be writable by the service account
foreach ($d in @("instance", "uploads", "logs")) {
  $p = Join-Path $InstallDir $d
  New-Item -ItemType Directory -Force -Path $p | Out-Null
  & icacls $p /grant "NT AUTHORITY\LOCAL SERVICE:(OI)(CI)M" /Q | Out-Null
}
& icacls $InstallDir /grant "NT AUTHORITY\LOCAL SERVICE:(OI)(CI)RX" /Q | Out-Null

$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm -and (Test-Path (Join-Path $PSScriptRoot "nssm.exe"))) { $nssm = Get-Item (Join-Path $PSScriptRoot "nssm.exe") }
if ($nssm) {
  $exe = $nssm.Source; if (-not $exe) { $exe = $nssm.FullName }
  & $exe stop $ServiceName 2>$null | Out-Null
  & $exe remove $ServiceName confirm 2>$null | Out-Null
  & $exe install $ServiceName "cmd.exe" "/c `"$wrapper`"" | Out-Null
  & $exe set $ServiceName AppDirectory $InstallDir | Out-Null
  & $exe set $ServiceName DisplayName "KTS 5.0 portal (Waitress)" | Out-Null
  & $exe set $ServiceName Start SERVICE_AUTO_START | Out-Null
  & $exe set $ServiceName ObjectName "NT AUTHORITY\LocalService" | Out-Null
  & $exe set $ServiceName AppRestartDelay 5000 | Out-Null
  & $exe start $ServiceName | Out-Null
  Write-Host "Installed Windows service $ServiceName via NSSM (running as LocalService on port $Port)."
} else {
  $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$wrapper`"" -WorkingDirectory $InstallDir
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\LOCAL SERVICE" -LogonType ServiceAccount -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Unregister-ScheduledTask -TaskName $ServiceName -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $ServiceName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "KTS 5.0 portal (Waitress on 127.0.0.1:$Port)" | Out-Null
  Start-ScheduledTask -TaskName $ServiceName
  Write-Host "Registered start-up task $ServiceName (no NSSM found). It is running now and restarts at boot."
}

Start-Sleep -Seconds 5
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Prefix/healthz" -UseBasicParsing -TimeoutSec 15
  Write-Host "Health check: $($r.StatusCode) $($r.Content)"
} catch {
  Write-Warning "Health check failed: $($_.Exception.Message). See $InstallDir\logs\service.log"
}

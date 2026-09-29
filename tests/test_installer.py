"""
The installer deploy/plesk/kts-install.bat and what is published around it.

The file is a batch head followed by PowerShell after the line that starts with #PS-BEGIN. The
server downloads it as it is and runs the PowerShell part with Windows PowerShell 5.1, so it has
to stay pure ASCII with Windows line endings and must not use anything newer than 5.1. The tests
that need powershell.exe are skipped where it does not exist.

The functions of the installer are taken out of it and run one by one; its main flow, which needs
IIS, is read as text: the order of its steps is what the tests of the update path look at.

    python -m pytest tests/test_installer.py -q
"""
import ast
import ctypes
import html
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "deploy" / "plesk" / "kts-install.bat"
SERVER_SETUP = ROOT / "deploy" / "plesk" / "server-setup.ps1"
MARK = b"#PS-BEGIN"
POWERSHELL = shutil.which("powershell.exe")
needs_powershell = pytest.mark.skipif(not POWERSHELL, reason="powershell.exe is not available")

# module and form of web.config, in the order in which the installer tries them
ATTEMPTS = [("AspNetCoreModuleV2", "hardened"), ("AspNetCoreModuleV2", "full"),
            ("AspNetCoreModuleV2", "short"), ("AspNetCoreModule", "short")]
HIDDEN = {"instance", "uploads", "logs", "python", "lib", "kts", "data", "templates"}
# what an update replaces and its safety copy therefore holds; what no run ever replaces
REPLACED = ["kts", "templates", "static", "data", "lib"]
NEVER = ["instance", "uploads", "logs", "python"]
ROWS = 40

PARSE = r"""
param([string]$Script)
$tokens = $null
$errors = $null
$text = [IO.File]::ReadAllText($Script)
$null = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$errors)
Write-Output ("version " + $PSVersionTable.PSVersion.ToString())
foreach ($e in $errors) { Write-Output ("line " + $e.Extent.StartLineNumber + ": " + $e.Message) }
exit $errors.Count
"""

# Takes the functions out of a script, without running it.
LOAD = r"""
function Get-Functions($file) {
  $tokens = $null
  $errors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors)
  if ($errors.Count -gt 0) { Write-Output "$file does not parse"; exit 3 }
  return $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)
}
"""

# Lets the functions of the installer write into $Out.
FUNCTIONS = r"""
param([string]$Script, [string]$Setup, [string]$Out, [string]$Python)
$ErrorActionPreference = "Stop"
__LOAD__
foreach ($f in (Get-Functions $Script)) { . ([scriptblock]::Create($f.Extent.Text)) }
$HostName = "kts.cict.in"
$stamp = "tests"
$problems = New-Object System.Collections.Generic.List[string]
$todo = New-Object System.Collections.Generic.List[string]
$processPath = "C:\Inetpub\vhosts\cict.in\kts.cict.in\python\python.exe"

foreach ($attempt in @(__ATTEMPTS__)) {
  $module, $form = $attempt -split " "
  Write-PortableConfig (Join-Path $Out "$module-$form.config") $processPath $module $form $false
}

# ---- a hosting that refused the hardened form: the record, and the forms of a later run
Write-PortableConfig (Join-Path $Out "refused-full.config") $processPath "AspNetCoreModuleV2" "full" $true
Write-PortableConfig (Join-Path $Out "refused-short.config") $processPath "AspNetCoreModule" "short" $true
$lines = @()
foreach ($case in @("none", "old-web.config", "AspNetCoreModuleV2-hardened.config", "AspNetCoreModuleV2-full.config", "refused-full.config", "refused-short.config")) {
  $text = ""
  if ($case -ne "none") { $text = [IO.File]::ReadAllText((Join-Path $Out $case)) }
  $lines += ($case + ": " + ((@(Get-Attempts $text) | ForEach-Object { $_.module + " " + $_.form }) -join ", "))
}
[IO.File]::WriteAllLines((Join-Path $Out "attempts.txt"), $lines)

$site = Join-Path $Out "site"
New-Item -ItemType Directory -Force -Path (Join-Path $site "instance"), (Join-Path $site "kts") | Out-Null
[IO.File]::WriteAllText((Join-Path $site "kts\version.py"), "VERSION = `"7.8.9`"`n")
[IO.File]::WriteAllText((Join-Path $Out "version.txt"), (Get-FileVersion $site) + "|" + (Get-Version '{"ok": true, "version": "7.8.9"}') + "|" + (Get-Version '{"ok": true}') + "|")

Write-OfflinePage $site
Copy-Item (Join-Path $site "app_offline.htm") (Join-Path $Out "app_offline.htm")
$gone = Remove-OfflinePage $site
[IO.File]::WriteAllText((Join-Path $Out "offline-removed.txt"), [string]($gone -and -not (Test-Path (Join-Path $site "app_offline.htm"))))

[IO.File]::WriteAllText((Join-Path $Out "note-without.txt"), (Get-SignInNote $site "kts.cict.in"))
[IO.File]::WriteAllText((Join-Path $site "instance\first-admin.txt"), "E-mail:   somebody@example.org`r`nPassword: Kept-To-Itself-42`r`n")
[IO.File]::WriteAllText((Join-Path $Out "note-with.txt"), (Get-SignInNote $site "kts.cict.in"))

$settings = Join-Path $site "instance\portal.env"
Write-SettingsFile $settings
Copy-Item $settings (Join-Path $Out "portal-new.env")
$old = [IO.File]::ReadAllText((Join-Path $Out "old-web.config"))
$carried = Get-MailSettings $old
$defined = @(Get-SettingNames $settings)
foreach ($key in $carried.Keys) { if ($defined -notcontains $key) { Add-Setting $settings $key $carried[$key] } }
Copy-Item $settings (Join-Path $Out "portal-carried.env")

Write-InstanceConfig (Join-Path $Out "instance-web.config")

# ---- the safety copy of the database, with a Python and without one
$made = Copy-Database (Join-Path $Out "db\kts5.sqlite3") (Join-Path $Out "db\copy-sqlite.sqlite3") $Python
$plain = Copy-Database (Join-Path $Out "db\kts5.sqlite3") (Join-Path $Out "db\copy-file.sqlite3") (Join-Path $Out "no-such-folder\python.exe")
[IO.File]::WriteAllText((Join-Path $Out "database.txt"), "$made|$plain")

# ---- the page of IIS about a failure, as Invoke-WebRequest leaves it: read to its end
$page = "<html><head><style>p { color: red }</style></head><body><h2>HTTP Error 500.19 - Internal Server Error</h2><table><tr><th>Module</th><td>IIS Web Core</td></tr><tr><th>Config Error</th><td>This configuration section cannot be used at this path.</td></tr></table></body></html>"
$script:stream = New-Object System.IO.MemoryStream(, [Text.Encoding]::UTF8.GetBytes($page))
$response = New-Object psobject
$response | Add-Member -MemberType ScriptMethod -Name GetResponseStream -Value { return $script:stream }
$failure = New-Object psobject -Property @{ Response = $response }
$script:stream.Position = $script:stream.Length
[IO.File]::WriteAllText((Join-Path $Out "iis-says.txt"), [string](Get-IisExplanation $failure))
foreach ($f in (Get-Functions $Setup)) { if ($f.Name -eq "Get-DetailedIisError") { . ([scriptblock]::Create($f.Extent.Text)) } }
$script:stream.Position = $script:stream.Length
[IO.File]::WriteAllText((Join-Path $Out "iis-says-setup.txt"), [string](Get-DetailedIisError $failure))

# ---- a run that stops after the copy: the site folder holds the new version, the safety copy the one of before
$SitePath = Join-Path $Out "stopped\site"
$backup = Join-Path $Out "stopped\before"
foreach ($folder in @("kts", "templates\public")) { New-Item -ItemType Directory -Force -Path (Join-Path $SitePath $folder), (Join-Path $backup $folder) | Out-Null }
New-Item -ItemType Directory -Force -Path (Join-Path $SitePath "instance") | Out-Null
foreach ($name in @("kts\__init__.py", "templates\public\home.html", "serve.py", "web.config")) {
  [IO.File]::WriteAllText((Join-Path $backup $name), "old")
  [IO.File]::WriteAllText((Join-Path $SitePath $name), "new")
  # the same size and the same time: only the content tells the two apart
  (Get-Item (Join-Path $SitePath $name)).LastWriteTime = (Get-Item (Join-Path $backup $name)).LastWriteTime
}
[IO.File]::WriteAllText((Join-Path $SitePath "kts\version.py"), "VERSION = `"9.9.9`"`n")
[IO.File]::WriteAllText((Join-Path $SitePath "kts\added.py"), "new")
[IO.File]::WriteAllText((Join-Path $SitePath "instance\kept.txt"), "never touched")
[IO.File]::WriteAllText((Join-Path $backup "index.html"), "page of the hosting")
Write-OfflinePage $SitePath
$TestOnly = $true
$Portable = $true
$offline = $true
$replaced = $true
$configWritten = $true
$takenBack = $false
$keptFolders = @("kts", "templates")
$keptFiles = @("serve.py")
$movedPages = @("index.html")
$oldVersion = ""
Undo-Update
$state = @()
foreach ($name in @("kts\__init__.py", "templates\public\home.html", "serve.py", "web.config", "index.html", "instance\kept.txt")) {
  $state += ($name + "=" + [IO.File]::ReadAllText((Join-Path $SitePath $name)))
}
foreach ($name in @("kts\added.py", "kts\version.py", "app_offline.htm")) { $state += ($name + "=" + (Test-Path (Join-Path $SitePath $name))) }
$state += "flags=$offline $replaced $configWritten $takenBack"
[IO.File]::WriteAllLines((Join-Path $Out "stopped.txt"), $state)
# a second call finds nothing left to do
Undo-Update
exit 0
"""

# Writes web.config while another program holds the file.
HELD = r"""
param([string]$Script, [string]$Path, [string]$Started)
$ErrorActionPreference = "Stop"
__LOAD__
foreach ($f in (Get-Functions $Script)) { . ([scriptblock]::Create($f.Extent.Text)) }
$HostName = "kts.cict.in"
$clock = [System.Diagnostics.Stopwatch]::StartNew()
[IO.File]::WriteAllText($Started, "now")
try { Write-PortableConfig $Path "C:\site\python\python.exe" "AspNetCoreModuleV2" "full" $false }
catch { Write-Output ("failed: " + $_.Exception.Message); exit 5 }
Write-Output ("written after " + [int]$clock.Elapsed.TotalMilliseconds + " ms")
exit 0
"""

# Runs step 7 of the installer with the answers that a case gives it: nothing is written, nobody is
# asked and no time passes.
STEP_7 = r"""
param([string]$Script, [string]$Step, [string]$Out)
$ErrorActionPreference = "Stop"
__LOAD__
foreach ($f in (Get-Functions $Script)) { . ([scriptblock]::Create($f.Extent.Text)) }
$HostName = "kts.cict.in"
Write-PortableConfig (Join-Path $Out "recorded.config") "C:\site\python\python.exe" "AspNetCoreModuleV2" "full" $true
$recorded = [IO.File]::ReadAllText((Join-Path $Out "recorded.config"))
$body = [scriptblock]::Create([IO.File]::ReadAllText($Step))

function Start-Sleep { param([int]$Seconds) $script:said += "sleep $Seconds" }
function Note($text) { $script:said += "note " + $text.Trim() }
function Good($text) { $script:said += "good " + $text }
function Bad($text) { $script:said += "bad " + $text }
function Write-PortableConfig($path, $python, $module, $form, $refused) { $script:said += "write $module $form record=$refused" }
function Remove-OfflinePage($folder) { return $true }
function Confirm-Update { $script:said += "confirmed" }
function Confirm-NewCode($folder, $name, $addresses, $check, $settingsChanged) { return $check }
function Undo-Update { $script:said += "undone" }
function Test-Portal($name, $addresses, $seconds) {
  $answer = $script:answers[$script:asked]
  $script:asked++
  $result = @{ ok = $false; detail = "answer $answer"; iis = ""; code = $answer.Substring(0, 3); content = ""; version = "" }
  if ($answer -eq "200") { $result.ok = $true; $result.version = "1.1.0" }
  # what Get-IisExplanation keeps of the page of IIS
  if ($answer -eq "500 locked") { $result.iis = "HTTP Error 500.19 - Internal Server Error`n        This configuration section cannot be used at this path." }
  if ($answer -eq "500 other words") { $result.iis = "HTTP Error 500.19 - Internal Server Error`n        Config Error" }
  return $result
}

$lines = @()
foreach ($case in @(__CASES__)) {
  $name, $before, $list = $case -split "/"
  $script:answers = @($list -split ",")
  $script:asked = 0
  $script:said = @()
  $oldConfig = ""
  if ($before -eq "recorded") { $oldConfig = $recorded }
  $SitePath = $Out
  $config = Join-Path $Out "web.config"
  $python = "C:\site\python\python.exe"
  $addresses = @()
  $offline = $false
  $configWritten = $false
  $settingsChanged = $false
  $check = @{ ok = $false; detail = ""; iis = ""; code = ""; content = ""; version = "" }
  . $body
  $lines += ($name + "/" + $refused + "/" + $script:asked + "/" + ($script:said -join "/"))
}
[IO.File]::WriteAllLines((Join-Path $Out "step-7.txt"), $lines)
exit 0
"""

# name of the case / web.config of before / what /healthz answers, in the order of the requests
STEP_7_CASES = ["plain//200", "passing//500,200", "locked//500 locked,200", "lasting//500,500,200",
                "other words//500 other words,500 other words,200", "another error first//502,500,200",
                "later run/recorded/200", "none//500 locked,500,500,500,500,500,500"]

OLD_WEB_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <aspNetCore processPath="python.exe" arguments="serve.py">
      <environmentVariables>
        <environmentVariable name="KTS_HOST" value="127.0.0.1" />
        <environmentVariable name="KTS_SMTP_HOST" value="smtp.entered-by-hand.example" />
        <environmentVariable value="a&amp;b" name="KTS_SMTP_USER" />
        <environmentVariable name="KTS_SMTP_PASSWORD" value="made>up/>for the 'test'" />
        <environmentVariable name="KTS_SMTP_FROM" value="" />
        <!-- Outgoing mail: fill in, save, and the site restarts by itself.
        <environmentVariable name="KTS_SMTP_PORT" value="587" />
        <environmentVariable name="KTS_SMTP_TLS" value="inside-a-comment" />
        -->
      </environmentVariables>
    </aspNetCore>
  </system.webServer>
</configuration>
"""


def powershell(script, *arguments):
    return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
                          + [str(a) for a in arguments], capture_output=True, text=True, timeout=300)


def powershell_part():
    data = INSTALLER.read_bytes()
    return data[data.index(MARK):]


def installer_text():
    return powershell_part().decode("ascii").replace("\r\n", "\n")


def main_flow():
    """The installer after its functions: the steps in the order in which they run."""
    text = installer_text()
    return text[text.index("try { Start-Transcript"):]


def function_text(name):
    text = installer_text()
    start = text.index(f"function {name}")
    return text[start:text.index("\n}\n", start)]


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """What the functions of the installer write, produced by one run of powershell.exe."""
    folder = tmp_path_factory.mktemp("installer")
    script = folder / "kts-install.ps1"
    script.write_bytes(powershell_part())
    out = folder / "out"
    (out / "db").mkdir(parents=True)
    (out / "old-web.config").write_text(OLD_WEB_CONFIG, encoding="utf-8")
    attempts = ", ".join(f'"{module} {form}"' for module, form in ATTEMPTS)
    (folder / "functions.ps1").write_text(FUNCTIONS.replace("__LOAD__", LOAD).replace("__ATTEMPTS__", attempts), encoding="ascii")
    # a database in use: what was stored last is still in kts5.sqlite3-wal, not in the main file
    portal = sqlite3.connect(out / "db" / "kts5.sqlite3")
    try:
        portal.execute("PRAGMA journal_mode=WAL")
        portal.execute("PRAGMA wal_autocheckpoint=0")
        portal.execute("CREATE TABLE application (number TEXT)")
        portal.executemany("INSERT INTO application VALUES (?)", [(f"KTS5-2026-{n:06d}",) for n in range(ROWS)])
        portal.commit()
        done = powershell(folder / "functions.ps1", "-Script", script, "-Setup", SERVER_SETUP, "-Out", out, "-Python", sys.executable)
    finally:
        portal.close()
    assert done.returncode == 0, done.stdout + done.stderr
    (out / "output.txt").write_text(done.stdout, encoding="utf-8")
    return out


def settings_of(path):
    """Names and values of a settings file, read the way config.py reads it."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def rows_of(path):
    """The number of applications in a copy of the database; 0 when the copy does not even hold the table."""
    copy = sqlite3.connect(path)
    try:
        return copy.execute("SELECT COUNT(*) FROM application").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        copy.close()


# ---- the file itself ---------------------------------------------------------

def test_ascii_and_windows_line_endings():
    data = INSTALLER.read_bytes()
    strange = sorted({byte for byte in data if byte > 126 or (byte < 32 and byte not in (10, 13))})
    assert not strange, strange
    assert data.endswith(b"\r\n")
    # a line end is CR LF, and neither of the two occurs alone
    assert b"\r" not in data.replace(b"\r\n", b"") and b"\n" not in data.replace(b"\r\n", b"")


def test_one_marker_line():
    data = INSTALLER.read_bytes()
    lines = [line for line in data.split(b"\r\n") if line.startswith(MARK)]
    assert len(lines) == 1
    # the batch head cuts the file at the first place where the marker occurs, wherever that is
    assert data.count(MARK) == 1
    head = data[:data.index(MARK)].decode("ascii")
    assert head.startswith("@echo off") and "'#PS-' + 'BEGIN'" in head
    for option in ("-HostName", "-SitePath", "-SourcePath", "-RestartIIS", "-Unattended", "-Portable", "-TestOnly"):
        assert option in head, f"{option} is not explained in the head of the file"
    assert powershell_part().split(b"\r\n")[1].startswith(b"param(")


def test_head_tells_the_two_kinds_of_run_apart():
    head = INSTALLER.read_bytes().split(MARK)[0].decode("ascii")
    words = " ".join(line[3:].strip() for line in head.splitlines() if line.startswith("rem"))
    # the page 'being updated' and the putting back belong to a run without administrator rights
    assert "Without administrator rights, visitors see a page that says so while an update replaces the files" in words
    assert "With administrator rights there is no such page, and a new version that does not start stays in place" in words
    assert "While an update replaces the files, visitors see a page" not in words
    # cmd.exe reads these lines
    assert "%" not in words
    # as the steps do it: the page only without administrator rights, and with them nothing is put back
    flow = main_flow()
    assert flow.count("Write-OfflinePage $SitePath") == 1
    assert "if ($Portable -and $existing) {" in flow[:flow.index("Write-OfflinePage $SitePath")]
    rights = flow[flow.index("5. the server"):]
    assert rights.index("Confirm-Update") < rights.index('Step 5 "Preparing the server')


@needs_powershell
def test_powershell_part_parses(tmp_path):
    script = tmp_path / "kts-install.ps1"
    script.write_bytes(powershell_part())
    (tmp_path / "parse.ps1").write_text(PARSE, encoding="ascii")
    done = powershell(tmp_path / "parse.ps1", "-Script", script)
    assert done.returncode == 0, done.stdout + done.stderr
    # the server has Windows PowerShell 5.1; powershell.exe is never a newer one
    assert re.search(r"version 5\.1\.", done.stdout), done.stdout


def test_order_of_the_attempts():
    text = powershell_part().decode("ascii")
    block = text[text.index("$attempts = @("):]
    block = block[:block.index("\r\n  )")]
    assert re.findall(r'module = "(\w+)"; form = "(\w+)"', block) == ATTEMPTS


def test_a_source_must_have_the_version_file():
    flow = main_flow()
    must = re.search(r"foreach \(\$must in @\(([^)]*)\)\)", flow)
    names = re.findall(r'"([^"]+)"', must.group(1))
    assert r"kts\version.py" in names and "serve.py" in names and r"kts\__init__.py" in names
    # an incomplete source stops in step 2, before a copy is kept and before anything is copied
    assert must.start() < flow.index("3. safety copy") < flow.index("& robocopy @arguments")


# ---- web.config ----------------------------------------------------------------

@needs_powershell
@pytest.mark.parametrize("module,form", ATTEMPTS)
def test_web_config(written, module, form):
    path = written / f"{module}-{form}.config"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "byte order mark"
    server = ET.fromstring(raw).find("system.webServer")
    assert server.find("handlers/add").get("modules") == module
    start = server.find("aspNetCore")
    assert start.get("arguments") == "serve.py" and start.get("processPath").endswith(r"\python\python.exe")
    assert start.get("hostingModel") == ("outofprocess" if module.endswith("V2") else None)
    names = [e.get("name") for e in start.iter("environmentVariable")]
    assert {"KTS_HOST", "KTS_HTTPS", "KTS_BEHIND_PROXY", "KTS_BASE_URL"} <= set(names)
    # settings of the installation are not kept here, not even as a comment to fill in
    assert b"KTS_SMTP" not in raw and b"KTS_ADMIN" not in raw
    assert rb"instance\portal.env" in raw
    # no refusal was seen, so none is recorded
    assert b"this hosting refused" not in raw

    filtering = server.find("security/requestFiltering")
    remove = server.find("httpProtocol/customHeaders/remove")
    if form == "short":
        assert server.find("security") is None and server.find("httpProtocol") is None
        return
    hidden = {e.get("segment") for e in filtering.iter("add")}
    assert HIDDEN <= hidden, HIDDEN - hidden
    # above the 25 MB of the portal, so that the portal can refuse a larger file in its own words
    assert int(filtering.find("requestLimits").get("maxAllowedContentLength")) == 30 * 1024 * 1024
    if form == "hardened":
        assert filtering.get("removeServerHeader") == "true"
        assert remove is not None and remove.get("name") == "X-Powered-By"
    else:
        assert filtering.get("removeServerHeader") is None and remove is None


@needs_powershell
def test_refused_form_is_recorded_and_not_tried_again(written):
    every = ", ".join(f"{module} {form}" for module, form in ATTEMPTS)
    without = ", ".join(f"{module} {form}" for module, form in ATTEMPTS if form != "hardened")
    cases = dict(line.split(": ", 1) for line in (written / "attempts.txt").read_text().splitlines())
    # no web.config, one entered by hand, and the forms of a run that saw no refusal: the hardened form comes first
    for case in ("none", "old-web.config", "AspNetCoreModuleV2-hardened.config", "AspNetCoreModuleV2-full.config"):
        assert cases[case] == every, case
    # the record in the web.config of before, whatever its form, leaves the hardened form out
    for case in ("refused-full.config", "refused-short.config"):
        assert cases[case] == without, case
        raw = (written / case).read_bytes()
        assert ET.fromstring(raw).find("system.webServer/aspNetCore") is not None
        assert raw.count(b"<!-- Record of kts-install.bat: this hosting refused the strictest form of this file") == 1
        # the record does not name what was refused in the words of IIS
        assert b"removeServerHeader" not in raw and b"customHeaders" not in raw
    # apart from the record the file is the one of its form
    plain = (written / "AspNetCoreModuleV2-full.config").read_bytes().split(b"\r\n")
    recorded = (written / "refused-full.config").read_bytes().split(b"\r\n")
    assert [line for line in recorded if b"Record of kts-install.bat" not in line] == plain


def test_step_7_does_not_wait_for_a_refused_form():
    flow = main_flow()
    step = flow[flow.index("7. IIS starts the portal"):flow.index("5. the server")]
    assert "$attempts = @(Get-Attempts $oldConfig)" in step and "$refused = Test-Refused $oldConfig" in step
    # a form that could not be written is not tested
    assert re.search(r"try \{ Write-PortableConfig \$config \$python \$attempt\.module \$attempt\.form \$refused \}\n\s+catch \{ Note [^\n]*; continue \}", step)
    # a 500 that names a locked section is not asked a second time; any other 500 is, and counts as a
    # refusal only when the second answer is 500 as well. The refusal goes into the next file
    first = ('$no = (-not $check.ok -and $attempt.form -eq "hardened" -and $check.code -eq "500" '
             '-and $check.iis -match "cannot be used at this path|is locked")')
    second = '$no = (-not $check.ok -and $attempt.form -eq "hardened" -and $first -eq "500" -and $check.code -eq "500")'
    again = "Start-Sleep -Seconds 10; $check = Test-Portal $HostName $addresses 150"
    assert step.count("$no = ") == 2 and step.count(again) == 1
    assert step.index(first) < step.index("if (-not $check.ok -and -not $no) {") < step.index("$first = $check.code") < step.index(again) < step.index(second)
    assert re.search(r"if \(\$no\) \{\n\s+\$refused = \$true", step)
    # the record is named where it exists: after a form was accepted, by the run that saw the refusal
    assert 'Note "  the hosting refuses this form"\n' in step and "the web.config that is kept will say so" not in step
    assert re.search(r'Good "the portal answers through IIS [^\n]*\n\s+if \(\$refused -and -not \(Test-Refused \$oldConfig\)\) '
                     r'\{ Note "web.config records that the strictest form was refused: later runs do not try it again" \}', step)
    # when no form answers, everything is put back; nothing of it is done by hand in the step
    assert step.count("Undo-Update") == 1 and "Copy-Item" not in step and "Remove-Item" not in step


@pytest.fixture(scope="module")
def step_7(tmp_path_factory):
    """What step 7 does with the answers of STEP_7_CASES: {name: (refused, requests, [what it did and said])}."""
    folder = tmp_path_factory.mktemp("step-7")
    script = folder / "kts-install.ps1"
    script.write_bytes(powershell_part())
    flow = main_flow()
    start = flow.index("  $attempts = @(Get-Attempts $oldConfig)")
    body = flow[start:flow.index("\n} else {\n  # ------------------------------------------------------------------ 5. the server", start)]
    (folder / "step.ps1").write_text(body, encoding="ascii")
    cases = ", ".join(f'"{case}"' for case in STEP_7_CASES)
    (folder / "run.ps1").write_text(STEP_7.replace("__LOAD__", LOAD).replace("__CASES__", cases), encoding="ascii")
    done = powershell(folder / "run.ps1", "-Script", script, "-Step", folder / "step.ps1", "-Out", folder)
    assert done.returncode == 0, done.stdout + done.stderr
    results = {}
    for line in (folder / "step-7.txt").read_text().splitlines():
        name, refused, asked, *said = line.split("/")
        results[name] = (refused == "True", int(asked), said)
    assert list(results) == [case.split("/")[0] for case in STEP_7_CASES]
    return results


def forms_of(said):
    return [entry[len("write "):] for entry in said if entry.startswith("write ")]


def waits_of(said):
    return [int(entry[len("sleep "):]) for entry in said if entry.startswith("sleep ")]


RECORD_NOTE = "note web.config records that the strictest form was refused: later runs do not try it again"
REFUSAL_NOTE = "note the hosting refuses this form"


@needs_powershell
def test_a_passing_error_500_is_no_refusal(step_7):
    # nothing in the way: the hardened form is accepted at the first request
    refused, asked, said = step_7["plain"]
    assert (refused, asked) == (False, 1) and forms_of(said) == ["AspNetCoreModuleV2 hardened record=False"]
    assert waits_of(said) == [3] and "confirmed" in said
    # an error 500 that is gone ten seconds later: asked twice, accepted, no record
    refused, asked, said = step_7["passing"]
    assert (refused, asked) == (False, 2) and forms_of(said) == ["AspNetCoreModuleV2 hardened record=False"]
    assert waits_of(said) == [3, 10] and "confirmed" in said
    # another error first and 500 at the second request: the next form is tried, without a record
    refused, asked, said = step_7["another error first"]
    assert (refused, asked) == (False, 3)
    assert forms_of(said) == ["AspNetCoreModuleV2 hardened record=False", "AspNetCoreModuleV2 full record=False"]
    for name in ("plain", "passing", "another error first"):
        said = step_7[name][2]
        assert REFUSAL_NOTE not in said and RECORD_NOTE not in said, name
        assert "undone" not in said, name


@needs_powershell
def test_a_refusal_is_recorded_by_the_run_that_saw_it(step_7):
    accepted = ["AspNetCoreModuleV2 hardened record=False", "AspNetCoreModuleV2 full record=True"]
    # IIS names a locked section: refused at once, without the wait of ten seconds
    refused, asked, said = step_7["locked"]
    assert (refused, asked) == (True, 2) and forms_of(said) == accepted and waits_of(said) == [3, 3]
    # any other error 500 that is still there after ten seconds, whether the words of IIS were read or not
    for name in ("lasting", "other words"):
        refused, asked, said = step_7[name]
        assert (refused, asked) == (True, 3) and forms_of(said) == accepted and waits_of(said) == [3, 10, 3], name
    for name in ("locked", "lasting", "other words"):
        said = step_7[name][2]
        assert said.count(REFUSAL_NOTE) == 1 and said.count(RECORD_NOTE) == 1, name
        # the record is named after the form that holds it was accepted
        assert said.index(REFUSAL_NOTE) < said.index("confirmed") < said.index(RECORD_NOTE), name
    # a later run finds the record: the hardened form is left out, and nothing new is recorded
    refused, asked, said = step_7["later run"]
    assert (refused, asked) == (True, 1) and forms_of(said) == ["AspNetCoreModuleV2 full record=True"]
    assert RECORD_NOTE not in said and REFUSAL_NOTE not in said
    assert any(entry.startswith("note web.config holds the record of an earlier run") for entry in said)
    # no form is accepted: everything is put back, so no record is promised
    refused, asked, said = step_7["none"]
    assert asked == 7 and [form.split(" record=")[0] for form in forms_of(said)] == [f"{module} {form}" for module, form in ATTEMPTS]
    assert said.count(REFUSAL_NOTE) == 1 and RECORD_NOTE not in said
    assert "undone" in said and "confirmed" not in said
    assert any(entry.startswith("bad IIS does not start the portal with any of the 4 forms") for entry in said)


@needs_powershell
@pytest.mark.skipif(os.name != "nt", reason="needs the file sharing of Windows")
def test_web_config_is_written_although_the_file_is_held(tmp_path):
    script = tmp_path / "kts-install.ps1"
    script.write_bytes(powershell_part())
    (tmp_path / "held.ps1").write_text(HELD.replace("__LOAD__", LOAD), encoding="ascii")
    config = tmp_path / "web.config"
    config.write_text("the file of before", encoding="ascii")
    started = tmp_path / "started.txt"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                   ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # open for reading; others may read, not write
    handle = kernel.CreateFileW(str(config), 0x80000000, 0x00000001, None, 3, 0, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    try:
        run = subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(tmp_path / "held.ps1"),
                                "-Script", str(script), "-Path", str(config), "-Started", str(started)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(600):
            if started.exists() or run.poll() is not None:
                break
            time.sleep(0.1)
        time.sleep(2.5)
    finally:
        kernel.CloseHandle(handle)
    output = run.communicate(timeout=120)[0]
    assert run.returncode == 0, output
    # the first try met the held file, so the file was written by a later one
    assert int(re.search(r"written after (\d+) ms", output).group(1)) >= 2000, output
    assert ET.fromstring(config.read_bytes()).find("system.webServer/security/requestFiltering/hiddenSegments") is not None


def test_write_of_web_config_gives_up_after_five_tries():
    body = function_text("Write-PortableConfig")
    assert "catch { if ($turn -ge 5) { throw }; Start-Sleep -Seconds 2 }" in body
    assert body.count("WriteAllText") == 1
    # the same five tries when the web.config of before is put back
    body = function_text("Restore-Config")
    assert "for ($turn = 1; $turn -le 5; $turn++)" in body and "catch { Start-Sleep -Seconds 2 }" in body
    assert 'return ""' in body


@needs_powershell
def test_instance_folder_is_closed_by_a_web_config_of_its_own(written):
    raw = (written / "instance-web.config").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "byte order mark"
    filtering = ET.fromstring(raw).find("system.webServer/security/requestFiltering")
    assert filtering.find("fileExtensions").get("allowUnlisted") == "false"
    # nothing else: an entry 'instance' of hiddenSegments here would be a second one beside that of the site
    assert [e.tag for e in filtering] == ["fileExtensions"] and list(filtering.find("fileExtensions")) == []


def test_instance_web_config_is_written_once_and_never_taken_away():
    flow = main_flow()
    write = flow.index("Write-InstanceConfig $closed")
    assert '$closed = Join-Path $SitePath "instance\\web.config"' in flow
    assert "if (-not (Test-Path $closed)) {" in flow[:write]
    # after the three folders are made, before the portal is started for the first time
    assert flow.index('foreach ($folder in @("instance", "uploads", "logs")) { New-Item') < write < flow.index("[System.Diagnostics.Process]::Start($info)")
    assert installer_text().count("Write-InstanceConfig $") == 1   # this one call
    for line in installer_text().splitlines():
        if "$closed" in line or "instance\\web.config" in line:
            assert not re.search(r"Remove-Item|Move-Item|Copy-Item|robocopy", line), line
    # the copy of step 4 leaves the folder instance of the source out
    assert re.search(r'\$skipFolders = @\("instance", "uploads", "logs"', flow)


# ---- the update path -------------------------------------------------------------

@needs_powershell
def test_versions_are_read(written):
    assert (written / "version.txt").read_text() == "7.8.9|7.8.9||"


def test_version_file_is_readable_by_the_installer():
    path = ROOT / "kts" / "version.py"
    if not path.exists():
        pytest.skip("kts/version.py does not exist yet")
    # the pattern of Get-FileVersion in the installer
    lines = [m for m in (re.match(r"""^\s*VERSION\s*=\s*["']([^"']+)["']""", line)
                         for line in path.read_text(encoding="utf-8").splitlines()) if m]
    assert lines and re.fullmatch(r"\d+\.\d+\.\d+", lines[0].group(1))


@needs_powershell
def test_page_while_the_portal_restarts(written):
    raw = (written / "app_offline.htm").read_bytes()
    assert max(raw) < 127
    text = html.unescape(raw.decode("ascii"))
    assert "The portal is being updated. Please try again in a minute." in text
    tamil = re.search(r'<p lang="ta">([^<]+)</p>', text).group(1)
    assert all("\u0b80" <= letter <= "\u0bff" or letter in " ." for letter in tamil), tamil
    assert (written / "offline-removed.txt").read_text() == "True"


def test_page_is_never_left_behind():
    text = installer_text()
    flow = main_flow()
    # put in place at three spots: the restart, the copy of an update, the taking back
    assert re.findall(r"Write-OfflinePage (\$\w+)", text) == ["$folder", "$folder", "$SitePath"]
    # the restart: inside a try whose finally takes it away again
    restart = function_text("Restart-Portal")
    assert re.search(r"try \{\s+Write-OfflinePage \$folder.*?\} finally \{\s+\$removed = Remove-OfflinePage \$folder", restart, re.S)
    # the two others: the flag is set before the page is written, so that every way out takes the page away
    assert re.search(r"\$offline = \$true\n\s+try \{\n\s+Write-OfflinePage \$SitePath", flow)
    undo = function_text("Undo-Update")
    assert re.search(r"\$script:offline = \$true\n\s+try \{ Write-OfflinePage \$folder", undo)
    assert re.search(r"if \(\$script:offline -or [^\n]*\) \{\n\s+\$script:offline = \$false\n\s+try \{ \$gone = Remove-OfflinePage \$folder \}", undo)
    # and one that an interrupted run left behind goes before anything is downloaded or copied
    assert text.index('Join-Path $SitePath "app_offline.htm"') < text.index("2. download")
    # the restart is tried once, never in a loop
    confirm = function_text("Confirm-NewCode")
    assert confirm.count("Restart-Portal ") == 1 and not re.search(r"\b(while|for|foreach|do)\b\s*[({]", confirm)


def test_update_shows_the_page_from_the_copy_to_the_first_web_config():
    flow = main_flow()
    page = flow.index("Write-OfflinePage $SitePath")
    copy = flow.index("& robocopy @arguments")
    # directly before the copy, and only when a portal is already installed
    assert flow.rindex("if (", 0, page) == flow.index("if ($Portable -and $existing) {\n  # The program that is running")
    assert page < flow.index("if ($existing) { $replaced = $true }") < copy
    assert "Start-Sleep" in flow[page:copy]
    # taken away directly after the first web.config is written, before IIS is asked
    step = flow[flow.index("7. IIS starts the portal"):]
    written = step.index("Write-PortableConfig $config $python $attempt.module $attempt.form $refused")
    gone = step.index("Remove-OfflinePage $SitePath")
    assert written < gone < step.index("Test-Portal $HostName $addresses 150")
    assert "$offline = $false" in step[written:gone]
    # and before a rehearsal ends
    rehearsal = flow[flow.index("  if ($TestOnly) {"):flow.index("Rehearsal finished: files and Python")]
    assert "Write-PortableConfig" in rehearsal and "Remove-OfflinePage $SitePath" in rehearsal and "Confirm-Update" in rehearsal
    # once the new version answers, nothing is put back any more: neither files nor web.config nor start pages
    assert re.search(r"if \(\$check\.ok\) \{\n\s+Confirm-Update\n\s+Good \"the portal answers through IIS", step)
    confirm = function_text("Confirm-Update")
    for flag in ("$script:replaced = $false", "$script:configWritten = $false", "$script:movedPages = @()"):
        assert flag in confirm, flag


def test_every_way_out_puts_the_version_of_before_back():
    text = installer_text()
    stop = function_text("Stop-Here")
    assert stop.index("Undo-Update") < stop.index("Save-Record") < stop.index("exit 1")
    # an error that nobody catches: the trap stands before the first step and ends with a code that is not 0
    trap = text[text.index("\ntrap {"):]
    trap = trap[:trap.index("\n}\n")]
    assert text.index("\ntrap {") < text.index("try { Start-Transcript")
    assert "try { Undo-Update } catch {}" in trap and trap.rstrip().endswith("exit 1")
    # the flags exist before any step can stop
    head = text[:text.index("function Step(")]
    for flag in ("$offline = $false", "$replaced = $false", "$configWritten = $false", "$takenBack = $false"):
        assert flag in head, flag
    # no sentence promises more than was done
    assert "left as it was" not in text
    assert "The update was taken back" in text and "The new version is not installed." in text


def test_safety_copy_holds_what_the_copy_replaces():
    flow = main_flow()
    step = flow[flow.index("3. safety copy"):flow.index("4. copy")]
    kept = re.search(r'foreach \(\$folder in @\(([^)]*)\)\) \{\n[^\n]*\n\s+& robocopy \(Join-Path \$SitePath \$folder\) \(Join-Path \$backup \$folder\)', step)
    assert re.findall(r'"(\w+)"', kept.group(1)) == REPLACED
    for name in NEVER:
        assert f'"{name}"' not in kept.group(1)
    # a copy that could not be made stops the run before anything is replaced
    assert re.search(r"if \(\$LASTEXITCODE -ge 8\) \{ Stop-Here \"the folder \$folder\\ could not be copied", step)
    # the files of the site's root that the source has as well, without those that are never copied
    assert "foreach ($file in (Get-ChildItem $source -File -Force)) {" in step
    assert "$skipFiles | Where-Object { $name -like $_ }" in step
    # every folder of the tree that step 4 copies is in the safety copy
    leave = set(re.findall(r'"(\w+)"', re.search(r'\$leaveOut = @\(("[^)]*)\)', step).group(1)))
    copied = {p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")
              and p.name not in leave | set(NEVER) | {"__pycache__"}}
    assert copied == set(REPLACED), f"step 4 copies {sorted(copied)}, the safety copy of step 3 holds {REPLACED}"


@needs_powershell
def test_a_stopped_run_puts_the_files_of_before_back(written):
    state = dict(line.split("=", 1) for line in (written / "stopped.txt").read_text().splitlines())
    # what the update had replaced is the version of before again, also where size and time are the same
    for name in (r"kts\__init__.py", r"templates\public\home.html", "serve.py", "web.config"):
        assert state[name] == "old", name
    assert state["index.html"] == "page of the hosting"
    # what only the new version has may stay, apart from the file that names the version
    assert state[r"kts\added.py"] == "True" and state[r"kts\version.py"] == "False"
    assert state[r"instance\kept.txt"] == "never touched"
    assert state["app_offline.htm"] == "False"
    # offline, replaced, configWritten are over; takenBack is what the result of the run reads
    assert state["flags"] == "False False False True"
    output = (written / "output.txt").read_text(encoding="utf-8")
    assert "the files of the version that ran before this run were put back" in output
    assert "web.config of before this run was put back" in output and "index.html was put back" in output
    # a rehearsal has no website to ask, and the second call had nothing left to do
    assert "the website was not asked whether it answers" in output
    assert output.count("Nothing further was changed.") == 1


def test_files_are_put_back_before_the_page_is_taken_away():
    undo = function_text("Undo-Update")
    # every file of the copy, also one that has the size and the time of the file it replaces
    back = undo.index("& robocopy (Join-Path $script:backup $name) (Join-Path $folder $name) /E /IS /IT /IM ")
    again = undo.index("if ($LASTEXITCODE -ge 16) { & robocopy (Join-Path $script:backup $name) (Join-Path $folder $name) /E /IS /IT /R:2")
    assert back < again < undo.index("Restore-Config") < undo.index("$gone = Remove-OfflinePage $folder") < undo.index("Test-Portal")
    # nothing is ever deleted by the putting back: no /MIR, no /PURGE
    assert "/MIR" not in undo and "/PURGE" not in undo
    # what it says about the website is what the website answered
    assert undo.index("Test-Portal") < undo.index("the website runs the version it ran before this run")


def test_start_test_names_the_address_of_the_website():
    flow = main_flow()
    start = flow[flow.index('$info.FileName = Join-Path $env:SystemRoot "System32\\cmd.exe"'):flow.index("[System.Diagnostics.Process]::Start($info)")]
    names = re.findall(r'\$info\.EnvironmentVariables\["(\w+)"\]', start)
    assert names == ["KTS_PORT", "KTS_HOST", "KTS_BASE_URL", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE"]
    # the value that web.config gives the portal, so that instance\first-admin.txt names the real sign-in page
    assert '$info.EnvironmentVariables["KTS_BASE_URL"] = "https://$HostName"' in start
    assert """'        <environmentVariable name="KTS_BASE_URL" value="https://' + $HostName + '" />'""" in installer_text()


def test_folders_of_the_owner_stay_at_a_first_installation():
    flow = main_flow()
    assert 'if ($Portable) { $leaveOut = @("deploy", "tests", "tools", "dist") }' in flow
    # moved out only where a portal is installed, and dist never; all four are still left out of the copy
    assert 'foreach ($folder in @($leaveOut | Where-Object { $existing -and $_ -ne "dist" })) {' in flow
    assert "foreach ($folder in $leaveOut)" not in flow
    assert '$skipFolders = @("instance", "uploads", "logs", ".git", ".github", ".claude") + $leaveOut' in flow


@needs_powershell
def test_safety_copy_of_the_database(written):
    assert (written / "database.txt").read_text() == "True|False"
    # made by SQLite, the copy holds what was still in kts5.sqlite3-wal
    assert rows_of(written / "db" / "copy-sqlite.sqlite3") == ROWS
    # without a Python the main file is copied, and the installer says what that copy lacks
    assert (written / "db" / "copy-file.sqlite3").exists() and rows_of(written / "db" / "copy-file.sqlite3") < ROWS
    flow = main_flow()
    assert 'if (Copy-Database $database $kept (Join-Path $SitePath "python\\python.exe")) {' in flow
    assert "through SQLite: the copy is complete" in flow and "(kts5.sqlite3-wal) is not in the copy" in flow


@needs_powershell
def test_explanation_of_iis_is_read(written):
    for name in ("iis-says.txt", "iis-says-setup.txt"):
        said = (written / name).read_text()
        assert "HTTP Error 500.19 - Internal Server Error" in said and "Config Error" in said, name
        assert "color: red" not in said


# ---- settings and first sign-in ----------------------------------------------------

@needs_powershell
def test_settings_file(written):
    new = written / "portal-new.env"
    assert settings_of(new) == {}, "a new settings file must set nothing"
    text = new.read_text(encoding="ascii")
    for name in ("KTS_SMTP_HOST", "KTS_SMTP_PORT", "KTS_SMTP_USER", "KTS_SMTP_PASSWORD", "KTS_SMTP_FROM", "KTS_SMTP_TLS"):
        assert re.search(rf"^# {name}=", text, re.M), name
    for line in ("KTS_RATE_REGISTER_PER_HOUR=100", "KTS_RATE_CONTACT_PER_HOUR=10", "KTS_RATE_STATUS_FAILS=300",
                 "KTS_RATE_LOGIN_FAILS=12", "KTS_RATE_CANDIDATE_FAILS_IP=600", "KTS_RATE_CANDIDATE_FAILS_APP=6", "KTS_HSTS=0"):
        assert re.search(rf"^# {re.escape(line)}\r?$", text, re.M), line
    assert "# Names in capital letters. Nothing may follow the value on its line: no comment, no semicolon." in text
    assert "for one application number from one address" in text
    # what was entered by hand into the old web.config is carried over, a value that holds > as well;
    # comments and empty values are not
    assert settings_of(written / "portal-carried.env") == {"KTS_SMTP_HOST": "smtp.entered-by-hand.example",
                                                           "KTS_SMTP_USER": "a&b",
                                                           "KTS_SMTP_PASSWORD": "made>up/>for the 'test'"}


def test_old_web_config_of_the_tests_is_well_formed():
    values = {e.get("name"): e.get("value") for e in ET.fromstring(OLD_WEB_CONFIG).iter("environmentVariable")}
    assert values["KTS_SMTP_PASSWORD"] == "made>up/>for the 'test'" and "KTS_SMTP_TLS" not in values


def test_defaults_named_in_the_settings_file():
    text = powershell_part().decode("ascii")
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    defaults = dict(re.findall(r'_int_env\("(KTS_RATE_\w+)", (\d+)\)', source))
    if not defaults:
        pytest.skip("config.py does not read the limits from the environment yet")
    for name, value in defaults.items():
        assert f"'# {name}={value}'" in text, name


@needs_powershell
def test_first_sign_in_note(written):
    without = (written / "note-without.txt").read_text()
    with_file = (written / "note-with.txt").read_text()
    assert "already been set" in without
    assert r"instance\first-admin.txt" in with_file and "Files > instance > first-admin.txt" in with_file
    assert "removes the file" in with_file
    for note in (without, with_file):
        assert "https://kts.cict.in/console/login" in note and "README" not in note
        # where the password is, never what it is
        assert "Kept-To-Itself" not in note and "somebody@example.org" not in note


def test_first_admin_file_is_never_read():
    reading = re.compile(r"Get-Content|ReadAll|OpenText|OpenRead|Copy-Item|Move-Item|Select-String|\btype\b|\bcat\b|\bgc\b", re.I)
    for line in installer_text().splitlines():
        if "first-admin.txt" in line and not line.lstrip().startswith("#"):
            # the installer asks whether the file exists and says where it is; it never opens or copies it
            assert not reading.search(line), line
            assert "Test-Path" in line or "return " in line or "$skipFiles" in line or line.lstrip().startswith("Note "), line
    assert '"first-admin.txt"' in re.search(r"\$skipFiles = @\(([^)]*)\)", installer_text()).group(1)


# ---- what is published ---------------------------------------------------------------

def retired_password():
    """The constant of kts/db.py, read without importing the portal; None while it does not exist."""
    tree = ast.parse((ROOT / "kts" / "db.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "RETIRED_FIRST_PASSWORD" for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def published_files():
    """
    Every file of the tree, whether git knows it or not. Left out: what is not the portal's own text
    (libraries, a Python of the site), what an installation writes (instance, uploads, logs), packages
    and caches, and kts/db.py, the one place where the retired password stands.
    """
    leave = {".git", "lib", "instance", "uploads", "logs", "dist", "python", "__pycache__", ".pytest_cache"}
    for folder, folders, files in os.walk(ROOT):
        folders[:] = sorted(name for name in folders if name not in leave)
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix == ".pyc" or path == ROOT / "kts" / "db.py":
                continue
            yield path


def test_retired_password_is_not_published():
    word = retired_password()
    if not word:
        pytest.skip("kts/db.py has no RETIRED_FIRST_PASSWORD yet")
    # on bytes: UTF-8, and UTF-16 for a file that PowerShell or Notepad wrote
    forms = [word.encode("utf-8"), word.encode("utf-16-le"), word.encode("utf-16-be")]
    files = list(published_files())
    assert ROOT / "README.md" in files and ROOT / "templates" / "base.html" in files and ROOT / "tests" / "conftest.py" in files
    assert ROOT / "kts" / "db.py" not in files
    printed = []
    for path in files:
        data = path.read_bytes()
        if any(form in data for form in forms):
            printed.append(str(path.relative_to(ROOT)))
    assert not printed, printed


def test_documents_describe_the_first_password():
    for name in ("README.md", "deploy/PLESK.md", "deploy/DEPLOY.md", "deploy/setup-iis.ps1", "deploy/plesk/server-setup.ps1"):
        assert "first-admin.txt" in (ROOT / name).read_text(encoding="utf-8"), name
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in ("KTS_TRUSTED_PROXY", "KTS_HSTS", "KTS_RATE_REGISTER_PER_HOUR", "KTS_RATE_CONTACT_PER_HOUR",
                 "KTS_RATE_STATUS_FAILS", "KTS_RATE_LOGIN_FAILS", "KTS_RATE_CANDIDATE_FAILS_IP",
                 "KTS_RATE_CANDIDATE_FAILS_APP", "portal.env", "## Behind a web server"):
        assert name in readme, name
    plesk = (ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8")
    assert r"C:\Windows\System32\cmd.exe" in plesk
    assert (r"/c curl.exe -s -L -o %TEMP%\kts-install.bat https://raw.githubusercontent.com/cictdl/kts5-portal/main/"
            r"deploy/plesk/kts-install.bat && %TEMP%\kts-install.bat -Unattended") in plesk
    # the entry that the server refuses is described in a sentence, not shown as something to paste
    assert r"v1.0\powershell.exe" not in plesk and "DownloadFile" not in plesk


def test_documents_name_the_limits_of_the_portal():
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    defaults = dict(re.findall(r'_int_env\("(KTS_RATE_\w+)", (\d+)\)', source))
    if not defaults:
        pytest.skip("config.py does not read the limits from the environment yet")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, value in defaults.items():
        assert re.search(rf"^\| `{name}` \| `{value}` \|", readme, re.M), name
    # what the count per application number and address protects against, and what it does not
    words = " ".join(readme.replace("*", "").split())
    assert "per application number and address" in words and "for his own address only" in words
    assert "bounded per address, not in total" in words
    sentence = "Names in capital letters. Nothing may follow the value on its line: no comment, no semicolon."
    for name in ("README.md", "deploy/PLESK.md"):
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        assert sentence in text, name


def test_documents_describe_the_release_of_an_update():
    plesk = " ".join((ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8").split())
    assert "### Releasing an update" in plesk
    release = plesk[plesk.index("### Releasing an update"):].replace("*", "").replace("`", "").replace("→", ">")
    for words in ("After the push wait ten minutes", "raw.githubusercontent.com", "If the line names no version, the old installer ran",
                  "run the task once more", "Files > instance > first-admin.txt"):
        assert words in release, words
    # the line of step 2, as the installer prints it
    assert re.search(r"complete: portal version \d+\.\d+\.\d+ with 23 interface languages", release)
    assert 'Good "complete: portal version $newVersion with $languages interface languages"' in installer_text()
    assert "ends with the line that says which version answers" not in plesk
    for name in ("README.md", "deploy/DEPLOY.md"):
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        # behind nginx: the name of the website and the address of the visitor are handed on, the portal listens on this machine only
        assert "proxy_set_header Host $host;" in text and "KTS_HOST=127.0.0.1" in text, name
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "`KTS_PORT` is read from the environment only" in readme
    deploy = " ".join((ROOT / "deploy" / "DEPLOY.md").read_text(encoding="utf-8").split())
    assert "KTS5Portal" in deploy
    assert 'if ($Mode -eq "Proxy")' in (ROOT / "deploy" / "setup-iis.ps1").read_text(encoding="utf-8").split("Done. Next steps:")[1]


def test_documents_say_when_the_strictest_form_counts_as_refused():
    plesk = " ".join((ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8").split()).replace("`", "")
    assert "is asked once" not in plesk
    for words in ("names a locked section of the configuration, the form is refused at once",
                  "is asked a second time after ten seconds and counts only when it is still there",
                  "If no form is accepted, the web.config of before is put back and nothing is recorded",
                  "Record of kts-install.bat: this hosting refused the strictest form of this file"):
        assert words in plesk, words
    # the ten seconds of the guide are the ten seconds of step 7
    assert "Start-Sleep -Seconds 10; $check = Test-Portal $HostName $addresses 150" in main_flow()


def test_documents_describe_the_first_start_of_this_version():
    for name in ("README.md", "deploy/PLESK.md"):
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split()).replace("*", "").replace("`", "")
        # every account with the published password, also one that went through the change form
        assert "every active account that still has that password receives a new first password" in text, name
        assert "whether or not the account had gone through the change form before" in text, name
        # the sentence of the installer, and what it means when nobody of the institute has signed in
        assert '"The administrator password has already been set"' in text, name
        assert "although nobody of the institute has signed in yet, somebody else has" in text, name
        assert "Users & roles" in text and "Audit log" in text, name
        # a registration drive of a college
        assert "registers more than 100 students within an hour through one connection" in text, name
        assert "KTS_RATE_REGISTER_PER_HOUR raised in" in text and "before the drive" in text, name
    assert "The administrator password has already been set (there is no instance\\first-admin.txt)." in function_text("Get-SignInNote")
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split()).replace("`", "")
    assert "a limit for failed attempts can be passed by up to KTS_THREADS - 1 (7 as delivered) in one window" in readme
    assert '<environmentVariable name="KTS_THREADS" value="8" />' in installer_text()
    plesk = " ".join((ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8").split()).replace("`", "")
    release = plesk[plesk.index("### Releasing an update"):]
    assert "names the sign-in page in general words" in release and "writes the address in at its next start" in release
    assert "localhost" not in release


def test_documented_command_for_a_new_administrator_is_the_one_of_manage_py():
    source = (ROOT / "manage.py").read_text(encoding="utf-8")
    block = source[source.index('add_parser("create-user")'):]
    block = block[:block.index("add_parser(", 10)]
    options = set(re.findall(r'add_argument\("(--[\w-]+)"', block))
    required = set(re.findall(r'add_argument\("(--[\w-]+)", required=True', block))
    assert required and '"superadmin"' in re.search(r'"--role"[^\n]*choices=\[([^\]]*)\]', block).group(1)
    for name in ("README.md", "deploy/PLESK.md"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        commands = [line.strip() for line in lines if "manage.py create-user" in line and "--role superadmin" in line and "..." not in line]
        assert len(commands) == 1, name
        used = set(re.findall(r"(?<!\S)(--[\w-]+)", commands[0]))
        assert required <= used <= options, (name, commands[0])
        # the portal makes the password: none stands in a document or in a task of Plesk
        assert "--password" not in used, name
    # the task of Plesk starts the Python of the site folder, inside the site folder
    plesk = (ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8")
    assert '/c cd /d "<site folder>" && python\\python.exe manage.py create-user --email ' in plesk


def test_secrets_of_an_installation_cannot_be_committed():
    git = shutil.which("git")
    if not git or not (ROOT / ".git").exists():
        pytest.skip("not a git working tree")
    for name in ("instance/first-admin.txt", "instance/portal.env"):
        done = subprocess.run([git, "-C", str(ROOT), "check-ignore", "-q", name], capture_output=True, timeout=60)
        assert done.returncode == 0, f"{name} is not ignored by git"

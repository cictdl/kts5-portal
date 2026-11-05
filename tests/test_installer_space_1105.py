"""
The installer no longer fills the disk of the server (1.2.163). On 5 November 2026 the disk of the CICT server was full: every run
of deploy/plesk/kts-install.bat had left its download (206 MB), the unpacked copy and the safety copy (about 250 MB each) in its
work folder kts5-setup. Now a run removes what earlier runs left there (keeping the two newest safety copies), stops before it
changes anything when the disk is short of room, deletes its download once unpacked and the unpacked copy at the end.

    python -m pytest tests/test_installer_space_1105.py -q
"""
from test_installer import LOAD, installer_text, main_flow, needs_powershell, powershell, powershell_part

RUN = r"""
param([string]$Script, [string]$Work)
$ErrorActionPreference = "Stop"
__LOAD__
foreach ($f in (Get-Functions $Script)) { if (@("Remove-OldRuns", "Get-FreeMegabytes") -contains $f.Name) { . ([scriptblock]::Create($f.Extent.Text)) } }
$current = Join-Path $Work "before-20261105-150000"
$freed = Remove-OldRuns $Work 2 $current
Write-Output ("freed=" + $freed)
Write-Output ("left=" + ((Get-ChildItem -Path $Work -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join ","))
Write-Output ("free=" + (Get-FreeMegabytes $Work))
Write-Output ("nowhere=" + (Get-FreeMegabytes (Join-Path $Work "no-such-folder")))
$again = Remove-OldRuns $Work 2 $current
Write-Output ("again=" + $again)
"""

MB = 1024 * 1024


@needs_powershell
def test_what_earlier_runs_left_is_removed(tmp_path):
    script = tmp_path / "kts-install.ps1"
    script.write_bytes(powershell_part())
    work = tmp_path / "kts5-setup"
    work.mkdir()
    # two downloads and an unpacked copy (3 MB and 1 MB)
    (work / "portal-20261101-100000.zip").write_bytes(b"z" * (2 * MB))
    (work / "portal-20261105-140000.zip").write_bytes(b"z" * MB)
    (work / "src-20261101-100000" / "kts5-portal-main").mkdir(parents=True)
    (work / "src-20261101-100000" / "kts5-portal-main" / "big.bin").write_bytes(b"s" * MB)
    # four safety copies of earlier runs, 1 MB each, and the one of this run
    for stamp in ("20261101-100000", "20261103-100000", "20261104-100000", "20261105-100000", "20261105-150000"):
        (work / f"before-{stamp}").mkdir()
        (work / f"before-{stamp}" / "kts5.sqlite3").write_bytes(b"d" * MB)
    # the records of the runs and the script itself stay
    (work / "install-20261105-100000.log").write_text("record", encoding="ascii")
    (work / "kts-install.ps1").write_text("script", encoding="ascii")
    run = tmp_path / "run.ps1"
    run.write_text(RUN.replace("__LOAD__", LOAD), encoding="ascii")
    done = powershell(run, "-Script", script, "-Work", work)
    assert done.returncode == 0, done.stdout + done.stderr
    out = dict(line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
    # the downloads, the unpacked copy and the two oldest safety copies: 3 + 1 + 2 MB
    assert out["freed"] == "6"
    assert out["left"].split(",") == ["before-20261104-100000", "before-20261105-100000", "before-20261105-150000",
                                      "install-20261105-100000.log", "kts-install.ps1"]
    assert int(out["free"]) > 0 and out["nowhere"] == "-1"
    # a second run finds nothing more to remove
    assert out["again"] == "0"


def test_room_is_made_and_checked_before_anything_changes():
    flow = main_flow()
    prune = flow.index("$freed = Remove-OldRuns $work 2 $backup")
    stop_work = flow.index('Stop-Here "only $freeWork MB are free on the drive of $work')
    stop_site = flow.index('Stop-Here "only $freeSite MB are free on the drive of $SitePath')
    # after the site folder is known, before the download, the safety copy and the page "being updated"
    assert flow.index('Step 1 "Looking for the website $HostName"') < prune < stop_work < stop_site
    assert stop_site < flow.index('Step 2 "Downloading the portal from GitHub') < flow.index('Step 3 "Keeping a copy')
    assert stop_site < flow.index("Write-OfflinePage")
    assert "if ($freeWork -ge 0 -and $freeWork -lt 1000) {" in flow and "if ($freeSite -ge 0 -and $freeSite -lt 500) {" in flow
    assert flow.count("Nothing was changed.\"") == 2


def test_the_download_and_its_copy_do_not_stay():
    flow = main_flow()
    unpack = flow.index("[IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpacked)")
    assert flow.index("try { Remove-Item -LiteralPath $zip -Force -ErrorAction Stop } catch {}", unpack) - unpack < 120
    # the unpacked copy at the end, after the last step that reads it, before the result
    end = flow.index("if ($unpacked -and (Test-Path -LiteralPath $unpacked)) {")
    assert flow.index('Step $steps "Checking the https certificate of $HostName"') < end < flow.index('"================ Result ================"')
    # the safety copy of this run is never removed by the run itself
    assert "Remove-Item -LiteralPath $backup" not in installer_text()


def test_the_guide_says_so():
    from test_installer import ROOT
    guide = (ROOT / "deploy" / "PLESK.md").read_text(encoding="utf-8")
    assert "every run first removes what earlier runs left in\n  `kts5-setup`" in guide.replace("\r\n", "\n")
    assert "less than 1,000 MB free or the drive of the site less than 500 MB" in guide.replace("\r\n", "\n").replace("\n  ", " ")

# Deploying the KTS 5.0 portal on the CICT IIS server

The portal is a Python (Flask) application. The CICT web server
(`103.186.184.129`, Windows Server with IIS 10, currently serving the static
Digital Archives site) can host it in either of two standard ways; both are
automated by `deploy\setup-iis.ps1`.

| Mode | How it works | Needs on the server |
|---|---|---|
| **HttpPlatform** (recommended) | IIS itself starts `serve.py` (Waitress) on a private port and forwards requests to it; the app restarts with the app pool | Python 3.11+, the free Microsoft **HttpPlatformHandler** IIS module |
| **Proxy** | The portal runs as a Windows service on `127.0.0.1:8905`; IIS forwards to it with URL Rewrite + Application Request Routing | Python 3.11+, **URL Rewrite** and **ARR** modules (NSSM optional) |

Both modes keep the data (`instance\kts5.sqlite3`, `uploads\`) inside the
install folder and preserve it across updates.

## 1. Build the package (on this PC)

```powershell
cd "D:\KTS 5.0\portal"
powershell -ExecutionPolicy Bypass -File deploy\package.ps1
```

Produces `dist\kts5-portal-YYYYMMDD-HHMM.zip` (~10 MB) containing the code,
templates, static files, the Thirukkural data and the `deploy\` scripts. Local
data, uploads and caches are excluded.

## 2. Copy the package to the server

Use whatever route the CICT web team uses to reach the server (RDP with
clipboard or a mapped drive, the hosting panel's file manager, SFTP). Put the
zip in, for example, `C:\temp\`.

## 3. Prepare the server (once)

1. Install **Python 3.11 or newer** (64-bit) from python.org: tick *Install
   for all users* and *Add python.exe to PATH*.
2. Install **HttpPlatformHandler** (x64) from
   <https://www.iis.net/downloads/microsoft/httpplatformhandler>
   (for Proxy mode instead: URL Rewrite and ARR from iis.net, then enable the
   proxy in ARR; the script does the enabling).
3. Decide the address:
   * **Own host name** `kts5.cict.in` (recommended): add an A record pointing
     to the server, and obtain a certificate for it (the existing wildcard or
     a new one; `win-acme` gives a free Let's Encrypt certificate on IIS).
   * **Or a path under the existing site**, e.g.
     `https://www.digitalarchives.cict.in/kts5/` (no DNS change; the
     existing certificate covers it).

## 4. Install (on the server, elevated PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
Expand-Archive C:\temp\kts5-portal-20260925-1300.zip C:\temp\kts5-unpack -Force
cd C:\temp\kts5-unpack\deploy
```

Own host name:

```powershell
.\setup-iis.ps1 -Package C:\temp\kts5-portal-20260925-1300.zip -HostName kts5.cict.in -CertThumbprint <thumbprint>
```

Under the existing site (replace the site name with the one shown in IIS
Manager):

```powershell
.\setup-iis.ps1 -Package C:\temp\kts5-portal-20260925-1300.zip -ParentSite "digitalarchives.cict.in" -AppPath /kts5 -HostName www.digitalarchives.cict.in
```

Proxy mode (when HttpPlatformHandler cannot be installed):

```powershell
.\setup-iis.ps1 -Package C:\temp\kts5-portal-20260925-1300.zip -HostName kts5.cict.in -Mode Proxy
```

The script prints a health check (`HTTP 200 {"ok": true, ...}`) at the end.
The default install folder is `C:\inetpub\kts5` (`-InstallDir` to change).

## 5. First sign-in

1. Open `https://kts5.cict.in/console/login` (or `/kts5/console/login`).
2. Sign in as `admin@kts5.local` / `Admin@KTS5`; you are forced to set a new
   password. Then create named accounts for the secretariat (Users and roles)
   and disable or rename the default one.
3. Settings: registration window, test date and login window, banner text,
   helpdesk contact, public counts.
4. Question bank → Generate from the corpus (all languages) and review.
5. Mail: edit the `KTS_SMTP_*` lines in `C:\inetpub\kts5\web.config`
   (Proxy mode: `run-service.cmd`) and recycle the application pool; until
   then mails wait in Console → Mail outbox.
6. Optional demo data for a walkthrough: `venv\Scripts\python.exe manage.py seed-demo`
   (never on the live database once registration opens).

## 6. Updating

Build a new package, copy it over and re-run the same `setup-iis.ps1` command.
Code is mirrored, `instance\`, `uploads\`, `logs\` and `venv\` are kept, the
app pool is recycled. Roll back by re-running with the previous zip.

## 7. Backups

The whole state is `instance\kts5.sqlite3` (WAL mode) plus `uploads\`.
Nightly job (Task Scheduler, run as SYSTEM):

```powershell
$d = "D:\backups\kts5\" + (Get-Date -Format yyyyMMdd)
New-Item -ItemType Directory -Force $d | Out-Null
C:\inetpub\kts5\venv\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect(r'C:\inetpub\kts5\instance\kts5.sqlite3'); d=sqlite3.connect(r'$d\kts5.sqlite3'); s.backup(d); d.close()"
robocopy C:\inetpub\kts5\uploads "$d\uploads" /MIR /NFL /NDL /NJH /NJS
```

Keep copies off the server. Restore = stop the app pool, put the files back,
start the pool.

## 8. Troubleshooting

| Symptom | Where to look |
|---|---|
| HTTP 500.19 / "handler not found" | HttpPlatformHandler not installed, or web.config references a wrong python path |
| HTTP 502.3 / process failed to start | `C:\inetpub\kts5\logs\stdout*.log`; run `venv\Scripts\python.exe serve.py` by hand in the folder to see the error |
| "unable to open database file" | permissions: `icacls C:\inetpub\kts5\instance /grant "IIS AppPool\KTS5:(OI)(CI)M"` |
| Uploads rejected at 413 | raise `maxAllowedContentLength` in web.config and `MAX_CONTENT_LENGTH` in config.py |
| Wrong links (http instead of https, missing /kts5) | `KTS_BASE_URL`, `KTS_HTTPS`, `KTS_URL_PREFIX` in web.config |
| Slow first request after idle | app pool idle timeout is set to 0 and start mode AlwaysRunning by the script; check they were not reset |

## 9. Security checklist before going live

* Change the default administrator password; create personal accounts.
* Serve only over https (`KTS_HTTPS=1` marks cookies Secure).
* Keep `instance\secret.key` private (it signs sessions); it is generated on first start.
* Restrict RDP/admin access to the server; the portal itself needs no inbound
  port other than 80/443.
* Test the backup restore once.

## 10. Alternative host

If the IIS server cannot run Python, the same package runs on any Linux VPS:
`pip install -r requirements.txt`, `gunicorn -w 4 -b 127.0.0.1:8905 'kts:create_app()'`
behind nginx with `KTS_BEHIND_PROXY=1`, and point `kts5.cict.in` at that VPS.

# Installing the KTS 5.0 portal through Plesk (Windows / IIS)

## The short way: one file

With Remote Desktop access to the server as an administrator, the whole
installation is one file: copy `deploy\plesk\kts-install.bat` to the server
and double-click it (accept the question of Windows about administrator
rights). It

1. finds the IIS website of `kts.cict.in` and its folder, and stops if that
   folder also serves another website;
2. downloads the portal from GitHub;
3. keeps a copy of whatever it replaces in `C:\kts5-setup\before-<date>`;
4. copies the portal into the folder, never touching the database, the
   uploads or the logs of an existing installation, and keeping a `web.config`
   that was edited on the server;
5. prepares the server with `server-setup.ps1` (Python, the
   HttpPlatformHandler module, IIS permissions, write access);
6. restarts the portal and checks that it answers; it asks before it would
   restart the whole of IIS;
7. checks the https certificate and lists what is left to do by hand.

Running the file again later updates the portal to the newest version on
GitHub. Everything shown on the screen is also written to
`C:\kts5-setup\install-<date>.log`. The website `kts.cict.in` must exist in
Plesk beforehand, and the Let's Encrypt certificate is issued in Plesk
afterwards (step 5 below).

### Without Remote Desktop: let Plesk run it

The same file can be started by Plesk itself. With the option `-Unattended`
it asks nothing, waits for no key and stops without changing anything if it
has no administrator rights.

1. Plesk, as administrator: *Tools & Settings* → **Scheduled Tasks** →
   **Add Task**.
2. Task type **Run a command**, and as the command this one line (if Plesk
   shows one box for the program and one for its arguments, the path of
   `powershell.exe` goes into the first and the rest into the second):

   ```
   C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; $f=Join-Path $env:TEMP 'kts-install.bat'; (New-Object Net.WebClient).DownloadFile('https://raw.githubusercontent.com/cictdl/kts5-portal/main/deploy/plesk/kts-install.bat', $f); & cmd.exe /c $f -Unattended; exit $LASTEXITCODE"
   ```

3. *System user*: the administrator entry. Schedule: anything, the task is
   removed again after use.
4. **Run Now**. The first run downloads Python and the IIS module and can
   take ten minutes. Plesk shows what the installer wrote.
5. **Remove the task**, so that it never runs by itself.
6. The record of the run is in *Files* → `kts.cict.in` → `logs` →
   `install-<date>.log`.

If the output is "STOPPED: this run has no administrator rights", Plesk runs
its tasks with a restricted account on this server, and Remote Desktop is the
only way. To let the installer restart the whole of IIS (needed at times
after the IIS module was installed for the first time), add ` -RestartIIS`
after `-Unattended`; every website on the server then stops for about ten
seconds.

The rest of this guide describes the same installation step by step, for
servers without Remote Desktop access and without administrator rights in
Plesk.

## The long way: Plesk panel only

Everything below is done in the Plesk panel and a browser; no remote desktop
or command line on the server is needed. Time: about 30 minutes plus the wait
for DNS.

## What has to be true on the server

The portal is a Python application. IIS starts it through Microsoft's
**HttpPlatformHandler** module and forwards web requests to it. So the server
needs, one time only:

1. **Python 3.11 or newer** installed for all users.
2. The **HttpPlatformHandler** IIS module
   (<https://www.iis.net/downloads/microsoft/httpplatformhandler>, x64).

Both are server-wide components. If you are the Plesk *administrator* you can
check under *Tools & Settings → Server Components / Updates*; if you are a
*customer* login, the probe in step 3 tells you whether they are present, and
the hosting provider installs whichever is missing (it takes them ten
minutes, no reboot).

Python libraries are **not** needed on the server: the Plesk package carries
them in its `lib\` folder.

## 1. Build the package (on this PC)

```powershell
cd "D:\KTS 5.0\portal"
powershell -ExecutionPolicy Bypass -File deploy\package-plesk.ps1
```

Result: `dist\kts5-portal-plesk-<date>.zip` (about 8 MB). It contains the
portal, the vendored libraries, `web.config`, and empty `instance\`,
`uploads\` and `logs\` folders.

## 2. Create the subdomain in Plesk

> **The portal's address is `kts.cict.in`.** The name already resolves to the CICT server and shows Plesk's default page, so the domain exists in Plesk; steps 2.2 and 2.3 are only needed on a new server.
>
> **Where the files go on the CICT server.** Open *Websites & Domains → kts.cict.in → Hosting Settings* and read **Document root**: that folder, and no other, receives the portal. On this server Plesk for Windows uses the subdomain's own folder as its document root: in the File Manager, `Home directory › kts.cict.in` (it contains an `App_Data` folder that Plesk created), with no `httpdocs` inside it. The `httpdocs` folder at the top level of a subscription belongs to the main domain, and nothing of the portal may be placed there.

1. Log in to Plesk → **Websites & Domains**.
2. **Add Subdomain**: name `kts`, parent `cict.in`. Leave the document root
   as `kts.cict.in (the subdomain folder itself)`. Create.
   (If you prefer a separate domain, *Add Domain* works the same way.)
3. If Plesk hosts the DNS of `cict.in`, the A record for `kts.cict.in` is
   created automatically. Otherwise add an **A record `kts` → the server's
   IP** at your DNS provider now; Let's Encrypt in step 5 needs it to resolve.
4. Open the subdomain's **Hosting Settings**: leave PHP/ASP.NET/Python
   scripting support **unticked** (the portal brings its own runtime) and
   *Apply*.

## 3. Probe the server (2 minutes)

1. **Files** (File Manager) → open `kts.cict.in (the subdomain folder itself)`. Delete whatever
   Plesk placed there (index.html, web.config if present).
2. Upload the three files from `deploy\plesk\probe\` on this PC:
   `web.config`, `probe.cmd`, `probe.py`.
3. Open `http://kts.cict.in/` in a browser (once DNS resolves).

| You see | Meaning | What to do |
|---|---|---|
| A JSON page with `"status": "HttpPlatformHandler works and started Python"` | both prerequisites are present; note the `"executable"` path | continue with step 4 |
| JSON with `"version_ok": false` | Python is too old | ask for Python 3.11+ |
| **HTTP Error 500.21** ("bad module … httpPlatformHandler") | the HttpPlatformHandler module is not installed | ask the hosting admin to install it, then reload |
| **HTTP Error 500.19** (config section locked) | Plesk locks the `handlers` section for this subscription | ask the admin to run `appcmd unlock config -section:system.webServer/handlers` |
| **HTTP Error 502.3** | module present, but Python was not found | open `httpdocs/probe-result.txt` in File Manager; if it says "not found", ask for Python to be installed with "Add to PATH" |

## 4. Upload the portal

1. File Manager → `kts.cict.in (the subdomain folder itself)` → delete the three probe files
   (and `probe-result.txt`, `probe-stdout*` if present).
2. **Upload** `kts5-portal-plesk-<date>.zip` into `httpdocs`.
3. Tick the zip → **Extract Files** (into the current folder). You should now
   see `web.config`, `serve.py`, `kts\`, `lib\`, `static\`, `templates\`,
   `data\`, `instance\`, `uploads\`, `logs\` … directly inside `httpdocs`.
   Delete the zip afterwards.
4. Open `http://kts.cict.in/healthz`. Expected: `{"ok": true, "time": "…"}`.
   First start takes 10–20 seconds (it creates the database).
5. If you get **502.3** instead, open `web.config` in the File Manager editor
   and replace the two values with the ones the probe printed:
   `processPath="…"` ← `web_config_processPath`, and
   `arguments="…"` ← `web_config_arguments` (the full path to `serve.py`).
   Save; the site restarts by itself. Any other failure: read the last lines
   of `httpdocs/logs/stdout*.log` in File Manager, they show the Python error.

## 5. Switch on HTTPS

1. Subdomain → **SSL/TLS Certificates** → *Install a free basic certificate
   provided by Let's Encrypt* (tick "Secure the domain name" and, if offered,
   "www"). Requires the DNS A record from step 2.
2. Back in **Hosting Settings**: tick *Permanent SEO-safe 301 redirect from
   HTTP to HTTPS*, and set the certificate. Apply.
3. `web.config` already has `KTS_HTTPS=1` and `KTS_BASE_URL=https://kts.cict.in`
   (edit the base URL if you used another name). Session cookies are marked
   Secure, so **sign-in only works over https** from here on.

## 6. First sign-in and configuration

1. `https://kts.cict.in/console/login` → `admin@kts5.local` / `Admin@KTS5`.
   You are forced to set a new password; do it, then *Users & roles* → create
   personal accounts for the secretariat and deactivate the default one.
2. **Settings**: registration window, test date and login window, duration,
   questions and marks, banner text, helpdesk contact.
3. **Question bank → Generate from the corpus** (all 23 languages, 60 each)
   and review.
4. **Notices / Repository / Events**: publish the call for applications, study
   material and the orientation session slots.
5. Mail: edit the `KTS_SMTP_*` lines in `web.config` (File Manager editor);
   saving `web.config` restarts the portal automatically. Until then mails
   wait in *Console → Mail outbox*.
6. Test a registration yourself and delete it from the console (withdraw).

## 6b. Deploy from GitHub instead of uploading zips

The repository <https://github.com/cictdl/kts5-portal> is laid out to run as
is: `web.config`, `serve.py`, vendored `lib\`, and the data folders are all at
the root. With Plesk's Git feature the subdomain becomes a checkout:

**Before you start**

* *Websites & Domains* → **kts.cict.in** → *Hosting Settings*: note the
  **Document root**. That folder is the target of the deployment. Plesk
  proposes `/httpdocs`, which on this server belongs to the main site: never
  leave that value.
* If **Git** is not among the icons of the domain, install it once:
  *Extensions* → search for *Git* → *Install* (Plesk administrator).

**Connect the repository**

1. *Websites & Domains* → **kts.cict.in** → **Git** (then *Add Repository*
   if a repository already exists).
2. Where the code is stored: **Remote Git hosting like GitHub or BitBucket**.
3. *Remote Git repository*: `https://github.com/cictdl/kts5-portal.git`.
   The repository is public, so no key or password is needed (Plesk for
   Windows cannot sign in over HTTPS; a private repository would need the SSH
   address and the key that Plesk shows).
4. *Your Website* → deployment mode: **Automatic deployment**.
5. *Your Website* → target directory: click the proposed `/httpdocs` and
   choose the document root noted above (the folder `kts.cict.in`).
6. **OK**. Plesk clones the repository and copies the files into the folder.
7. On the Git page check the branch: it must be **main** (*Change branch and
   path* if it is not).
8. *Repository Settings* → tick **Enable additional deploy actions** and
   enter this one line, which restarts the portal after every deployment so
   that new program files and translations are loaded:

   ```
   copy /b web.config +,,
   ```

**Check**

* *Files* → the folder `kts.cict.in` now holds `web.config`, `serve.py`,
  `kts\`, `lib\`, `static\`, `templates\`, `data\`, `instance\`, `uploads\`,
  `logs\`. Delete Plesk's own `index.html` and other default files if they are
  still there.
* Run the one-time server preparation if it has not been run:
  `deploy\plesk\server-setup.ps1`, as Administrator (the script is now on the
  server, inside the folder). Git only delivers the files; Python and the
  HttpPlatformHandler module come from the script, which also gives the site
  write access to `instance\`, `uploads\` and `logs\`.
* Open `https://kts.cict.in/healthz`: `{"ok": true, …}`.

**Later updates**

Push to `main` on GitHub, then *Websites & Domains → Git →* **Pull Updates**.
The runtime files (`instance\kts5.sqlite3`, `uploads\`) are not in git and
are left alone. To make the pull automatic, copy the webhook address from
*Repository Settings* and add it in GitHub: *Settings → Webhooks → Add
webhook*, content type `application/json`, "Just the push event". If the
Plesk panel itself has a self-signed certificate, write the address with
`http://`, as the Plesk manual advises.

## 7. Updating later

Build a new package, upload it into `httpdocs`, extract (overwrite). The
`instance\` database, `uploads\` and `logs\` are not in the package and stay
untouched; saving `web.config` (or the extraction itself) restarts the app.

## 8. Backups

In Plesk: **Backup & Restore** → schedule a daily backup of the subscription
(it includes `httpdocs\instance\kts5.sqlite3` and `uploads\`). Additionally
download `instance\kts5.sqlite3` and `uploads\` before the test day and after
the merit list is published.

## 9. Things that can go wrong

| Problem | Cause / fix |
|---|---|
| `/healthz` gives 502.3 after a `web.config` edit | typo in `processPath`, or the file was saved with a BOM by an editor; re-copy `deploy\plesk\web.config` |
| Pages load but sign-in returns to the login page | you are on `http://`; use `https://` (cookies are Secure) |
| Uploads fail with 413 | raise `maxAllowedContentLength` in `web.config` |
| "unable to open database file" in `logs\stdout*.log` | the site user cannot write to `httpdocs\instance`; in File Manager set the folder's permissions to allow *Modify* for the subscription's system user (Plesk normally grants this already) |
| `/` shows a directory listing or `index.html` | the extraction went into a sub-folder (`httpdocs\kts5-portal-plesk-…\`); move everything one level up |
| Slow first request after a quiet period | Plesk's default idle timeout recycles the app pool; ask the admin to set *Idle Time-out* to 0 for this subscription's pool, or accept a 10-second first load |

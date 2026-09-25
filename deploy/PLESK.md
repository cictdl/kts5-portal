# Installing the KTS 5.0 portal through Plesk (Windows / IIS)

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

> **Where the files go on the CICT server.** Plesk for Windows here uses the subdomain's own folder as its document root: in the File Manager, `Home directory › kts5.digitalarchives.cict.in` (it contains an `App_Data` folder that Plesk created). There is no `httpdocs` inside it. The main domain's document root is the separate `httpdocs` folder at the top level, and nothing of the portal may be placed there.

1. Log in to Plesk → **Websites & Domains**.
2. **Add Subdomain**: name `kts5`, parent `cict.in`. Leave the document root
   as `kts5.digitalarchives.cict.in (the subdomain folder itself)`. Create.
   (If you prefer a separate domain, *Add Domain* works the same way.)
3. If Plesk hosts the DNS of `cict.in`, the A record for `kts5.digitalarchives.cict.in` is
   created automatically. Otherwise add an **A record `kts5` → the server's
   IP** at your DNS provider now; Let's Encrypt in step 5 needs it to resolve.
4. Open the subdomain's **Hosting Settings**: leave PHP/ASP.NET/Python
   scripting support **unticked** (the portal brings its own runtime) and
   *Apply*.

## 3. Probe the server (2 minutes)

1. **Files** (File Manager) → open `kts5.digitalarchives.cict.in (the subdomain folder itself)`. Delete whatever
   Plesk placed there (index.html, web.config if present).
2. Upload the three files from `deploy\plesk\probe\` on this PC:
   `web.config`, `probe.cmd`, `probe.py`.
3. Open `http://kts5.digitalarchives.cict.in/` in a browser (once DNS resolves).

| You see | Meaning | What to do |
|---|---|---|
| A JSON page with `"status": "HttpPlatformHandler works and started Python"` | both prerequisites are present; note the `"executable"` path | continue with step 4 |
| JSON with `"version_ok": false` | Python is too old | ask for Python 3.11+ |
| **HTTP Error 500.21** ("bad module … httpPlatformHandler") | the HttpPlatformHandler module is not installed | ask the hosting admin to install it, then reload |
| **HTTP Error 500.19** (config section locked) | Plesk locks the `handlers` section for this subscription | ask the admin to run `appcmd unlock config -section:system.webServer/handlers` |
| **HTTP Error 502.3** | module present, but Python was not found | open `httpdocs/probe-result.txt` in File Manager; if it says "not found", ask for Python to be installed with "Add to PATH" |

## 4. Upload the portal

1. File Manager → `kts5.digitalarchives.cict.in (the subdomain folder itself)` → delete the three probe files
   (and `probe-result.txt`, `probe-stdout*` if present).
2. **Upload** `kts5-portal-plesk-<date>.zip` into `httpdocs`.
3. Tick the zip → **Extract Files** (into the current folder). You should now
   see `web.config`, `serve.py`, `kts\`, `lib\`, `static\`, `templates\`,
   `data\`, `instance\`, `uploads\`, `logs\` … directly inside `httpdocs`.
   Delete the zip afterwards.
4. Open `http://kts5.digitalarchives.cict.in/healthz`. Expected: `{"ok": true, "time": "…"}`.
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
3. `web.config` already has `KTS_HTTPS=1` and `KTS_BASE_URL=https://kts5.digitalarchives.cict.in`
   (edit the base URL if you used another name). Session cookies are marked
   Secure, so **sign-in only works over https** from here on.

## 6. First sign-in and configuration

1. `https://kts5.digitalarchives.cict.in/console/login` → `admin@kts5.local` / `Admin@KTS5`.
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

1. *Websites & Domains* → **kts5.digitalarchives.cict.in** → **Git** → *Add
   repository*.
2. *Remote Git hosting* → repository URL `https://github.com/cictdl/kts5-portal.git`,
   branch `main`.
3. Deployment: target the subdomain's document root (the folder
   `kts5.digitalarchives.cict.in` itself), mode *Automatic*.
4. Plesk clones the repository into the folder. Existing runtime files
   (`instance\kts5.sqlite3`, `uploads\`) are left alone because they are not
   tracked in git.
5. Later updates: push to `main`, then *Pull updates* in Plesk (or register
   the webhook URL Plesk shows in the GitHub repository settings so pulls are
   automatic). Saving `web.config` through a pull restarts the portal.

The one-time server preparation (`deploy\plesk\server-setup.ps1` as
Administrator) is still required; git only delivers the files.

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

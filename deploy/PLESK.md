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
7. checks the https certificate and lists what is left to do by hand,
   among it where the first password of the administrator is
   (`instance\first-admin.txt`, see *First sign-in* below).

Running the file again later updates the portal to the newest version on
GitHub. Everything shown on the screen is also written to
`C:\kts5-setup\install-<date>.log`. The website `kts.cict.in` must exist in
Plesk beforehand, and the Let's Encrypt certificate is issued in Plesk
afterwards (step 5 below).

### Without Remote Desktop: let Plesk run it

This is how `kts.cict.in` is installed. The same file can be started by Plesk
itself, with the option `-Unattended` (it asks nothing and waits for no key).
Plesk runs such a task as the system user of the subscription, who is no
administrator; the installer notices that and installs **without installing
anything on the server**:

* the portal is copied into the folder of the site, without the folders
  `deploy`, `tests`, `tools` and `dist`, which the running portal does not
  need. Where a portal is already installed, copies of `deploy`, `tests` and
  `tools` that an earlier run left in the site folder are moved to the safety
  copy of the run; `dist` is never moved, and at a first installation nothing
  is moved out of the folder;
* before an update replaces anything, the safety copy of the run receives
  everything that will be replaced: the folders `kts`, `templates`, `static`,
  `data` and `lib` and the files of the site's root (about 27 MB), and the
  database, copied through SQLite itself so that the copy is complete. The
  copy lies in `%TEMP%\kts5-setup\before-<date>` of the system user;
* while an update replaces the files, visitors see the page "The portal is
  being updated" (`app_offline.htm`): IIS stops the running program for that
  time, so that it never answers with the files of two versions. The page is
  taken away as soon as the new files and the new `web.config` are in place;
* a run that stops after it has replaced files (the new version does not
  start, IIS accepts no form of `web.config`, an error nobody expected) puts
  the files of before back from its safety copy, then takes the page away,
  asks the website and says whether it runs the version it ran before.
  Files that only the new version has may stay in the folder;
* Python is not installed but unpacked into `python\` inside that folder
  (the "embeddable package" of python.org, 10 MB);
* IIS starts the portal through the **ASP.NET Core Module**, which Plesk has
  installed for its .NET hosting and which starts any program given to it;
* write access to `instance\`, `uploads\` and `logs\` is given to the IIS
  account of the site;
* `instance\` receives a `web.config` of its own, written once and before
  the portal is started for the first time: IIS then serves no file of that
  folder, whatever the `web.config` of the site says;
* before IIS is involved, the portal is started once by itself, so that a
  fault of the portal and a fault of IIS can be told apart;
* `web.config` is written in up to four forms, the strictest first (protected
  folders, request limit, no `Server` and `X-Powered-By` headers); a form that
  the hosting refuses is followed by the next, shorter one. If IIS refuses all
  four, the previous `web.config` and start page are put back and IIS's
  explanation is shown;
* a hosting that refuses the strictest form is not asked for it again. When
  IIS answers that form with an error 500 and names a locked section of the
  configuration, the form is refused at once. An error 500 that does not name
  a locked section is asked a second time after ten seconds and counts only
  when it is still there, so that a passing error leaves no record; an error
  that lasts that long for another reason is recorded all the same. The run
  that saw the refusal writes a line "Record of kts-install.bat: this hosting
  refused the strictest form of this file" into the `web.config` it keeps,
  and later runs leave that form out as long as the old `web.config` holds
  the line. If no form is accepted, the `web.config` of before is put back
  and nothing is recorded. To have the form tried again, delete the line in
  `web.config` (*Files*) before the task is run;
* when the portal answers through IIS, the installer reads `"version"` from
  `/healthz` and compares it with the version of the files. If they differ,
  or if `instance\portal.env` was changed after the last run, it restarts the
  portal, once: for about fifteen seconds visitors see a page "The portal is
  being updated" (`app_offline.htm`, which the installer removes again), then
  the version is compared once more and the result is reported.

Only the folder of `kts.cict.in` is written to. Found on the CICT server on
28 Sep 2026 (Windows Server 2019): no HttpPlatformHandler, no Python, but the
ASP.NET Core runtimes 2.1 to 10.0, URL Rewrite, ARR and iisnode.

1. Plesk, as administrator: *Tools & Settings* → **Scheduled Tasks** →
   **Add Task**.
2. Task type **Run a command**. The form has two boxes, **Command** and
   **Arguments**, and each part must go into its own: Plesk puts quotation
   marks around the first box, so a whole command line pasted into *Command*
   fails, because it is taken for the name of a program ("… is not recognized
   as an internal or external command").

   **Command** (the program only):

   ```
   C:\Windows\System32\cmd.exe
   ```

   **Arguments** (one line):

   ```
   /c curl.exe -s -L -o %TEMP%\kts-install.bat https://raw.githubusercontent.com/cictdl/kts5-portal/main/deploy/plesk/kts-install.bat && %TEMP%\kts-install.bat -Unattended
   ```

   This is the entry that works on the CICT server. An entry that starts
   `powershell.exe` directly, as earlier versions of this guide showed, is
   refused by the security software of the server ("Access is denied",
   error 5).

3. *System user*: the system user of `kts.cict.in`. Schedule: anything, the
   task is removed again after use.
4. **Run Now**. The run takes a few minutes. Plesk shows what the installer
   wrote.
5. **Remove the task**, so that it never runs by itself. To update the portal
   later, add the task again and run it.
6. The record of the run is in *Files* → `kts.cict.in` → `logs` →
   `install-<date>.log`.

Do not connect a folder installed this way to Git in Plesk: the `web.config`
of the repository is written for a server with the HttpPlatformHandler module
and would replace the one the installer wrote.

**Updating.** Run the same task again (steps 1 to 5); *Releasing an update*
below says what to look at. The installer takes the newest version from
GitHub, keeps a copy of what it replaces, and says under step [7/8] which
version answers; the run ends with the block "Result". Every run restarts
the portal, also when nothing has changed: the page "being updated" stops the
program while the files are replaced, and `web.config` is written anew. This
is what makes the files of the run the ones in use.

**What an update never touches.** `instance\` (the database, the keys
`secret.key` and `stipend.key`, the image of the signature of the certificates
(`certificate-signature.png` or `.jpg`), `portal.env`, `first-admin.txt` and the
`web.config` of that folder), `uploads\` and `logs\`. The `web.config` of the site is written anew by
every run, so nothing should be entered there by hand; mail settings that
somebody did enter there are carried over to `portal.env` by the next run.

**Settings.** *Files* → `kts.cict.in` → `instance` → `portal.env`. The
installer creates the file with comment lines only; it names the settings for
outgoing mail (`KTS_SMTP_HOST`, `KTS_SMTP_PORT`, `KTS_SMTP_USER`,
`KTS_SMTP_PASSWORD`, `KTS_SMTP_FROM`, `KTS_SMTP_TLS`) and the limits
(`KTS_RATE_…`) with their defaults. Write a setting as `NAME=value` on a line
of its own, without the `#`, save, and run the task again: the portal reads
the file when it starts, and the installer restarts the portal when the file
was changed after the last run. Names in capital letters. Nothing may follow
the value on its line: no comment, no semicolon.

A college that registers more than 100 students within an hour through one
connection (a computer room, or a campus behind one address) needs
`KTS_RATE_REGISTER_PER_HOUR` raised in `instance\portal.env` before the
drive, and the task run again so that the portal restarts. A student over
the limit is told "Too many attempts from this connection", and nothing of
his form is stored.

**Stipend (from version 1.2.0).** The selected students give their bank
details at `/candidate/bank` once the merit list is published and the form is
opened in *Console* → *Settings* → *Stipend*; the staff check, approve and pay
in *Console* → *Stipend* (superadmin and admin only). Every download of the
approved entries still to pay is a numbered payment list, kept in the
database with the amount of the day, to be marked as paid once the bank has
carried it out (at that amount) or discarded if it never went to the bank.
The account and Aadhaar numbers are sealed with the key `instance\stipend.key`,
which the portal makes the first time: keep this file with every copy of
`instance\kts5.sqlite3`, because without it the numbers cannot be read by
anybody. The copy of the database that the installer keeps in
`kts5-setup\before-<date>` holds no key: the key stays in `instance\`, which
no run touches. Once entries exist, the portal accepts new entries only under
the key that sealed them, checked against the entries stored last (so that
one damaged entry does not stop the form): a `KTS_STIPEND_KEY` in
`portal.env` must then be that same key (the 64 bytes of `stipend.key`
written as 128 hex digits), and under any other key, or without the file, the
form answers "cannot be saved at the moment" and the entries stored before
cannot be read. Put the old key back (the file from the backup, or remove the
setting) and the module works again.

**First sign-in.** The portal has no built-in password. At its first start it
creates the account `admin@kts5.local` with a random password and writes the
account, the password and the address of the sign-in page to *Files* →
`kts.cict.in` → `instance` → `first-admin.txt`. Sign in with it; the portal
asks for a new password at once and removes the file afterwards. The folder
`instance` is never served to visitors.

**The password published with earlier versions.** Versions before 1.1.0
were published with a first password. At the first start of version 1.1.0
every active account that still has that password receives a new first
password, written to `instance\first-admin.txt` in the same way, and the
published one no longer works. This holds whether or not the account had
gone through the change form before: the change form of earlier versions
accepted the published password as the new one.

**If the installer says "The administrator password has already been set"**
(there is no `instance\first-admin.txt`) **although nobody of the institute
has signed in yet, somebody else has**: the account of the administrator
carries a password that nobody of the institute knows. Then, at once:

1. Create an account of your own. Add a task as in steps 1 to 5 above, with
   the same *Command* (`C:\Windows\System32\cmd.exe`) and these *Arguments*
   (one line). In place of `<site folder>` write the folder that step 1 of
   the installation names in its record (`folder: ...`), and your own
   address and name:

   ```
   /c cd /d "<site folder>" && python\python.exe manage.py create-user --email name@cict.in --name "Name" --role superadmin
   ```

   The output of the task names the temporary password of the account, in
   its line "Created superadmin ..."; the portal asks for a new one at the
   first sign-in. Remove the task. Whoever cannot add the task asks the
   engineer of the server to run `python manage.py create-user --role
   superadmin ...` in the site folder.
2. Sign in with the new account and deactivate the old one: *Users & roles*
   → **Edit** beside the account → untick **Active** → **Save**.
3. Read *Users & roles* and the *Audit log*. Deactivate every account that
   nobody of the institute created. In the audit log the rows `login` and
   `password_changed` name the time and the address of every sign-in, and
   the rows after them say what was done.

**HSTS.** Switch `Strict-Transport-Security` on only after the real
certificate (Let's Encrypt) is installed, and in one place only: either in
Plesk (*SSL/TLS Certificates* → HSTS) or with `KTS_HSTS=1` in `portal.env`,
never in both.

### Releasing an update

A new version reaches the server in two steps: the push to `main` on GitHub,
then the task of Plesk (steps 1 to 5 above).

1. **After the push wait ten minutes** before the task is run. The task
   fetches the installer from `raw.githubusercontent.com`, and that address
   may hand out the previous installer for some minutes after a push, while
   the code already comes in its new version.
2. **Choose a quiet hour**, never the time of an examination. Every run
   restarts the portal, and while the files are replaced visitors see the
   page "The portal is being updated"; a form that is sent in those seconds
   is not stored and has to be sent again.
3. **Read step 2 of the output.** It must read
   `complete: portal version 1.2.39 with 23 interface languages`, with the
   number that `kts\version.py` of the release names. If the line names no
   version, the old installer ran. Nothing is lost and the portal works, with
   the new code; wait ten minutes and run the task once more. That run does
   what the old installer left out (`instance\portal.env`, the new
   `web.config`, the folders `deploy`, `tests` and `tools` moved out of the
   site folder). A `first-admin.txt` that was written during the run of the
   old installer names the sign-in page in general words, because the portal
   had no address then; the portal writes the address in at its next start.
   Account and password in the file are right, and the sign-in page is
   `https://kts.cict.in/console/login`.
4. **Read step 7 and the block "Result".** Step 7 names the version that
   answers through IIS; the result must say "The portal is installed and
   running".
5. **Sign in.** Every active account that still has the password published
   with earlier versions receives a new first password when version 1.1.0
   starts for the first time, and the old one no longer works. The first
   password is in *Files* → `instance` → `first-admin.txt`, together with
   the account and the address of the sign-in page. If the result says "The
   administrator password has already been set" although nobody of the
   institute has signed in yet, somebody else has: see *First sign-in*
   above.

If a run stops ("STOPPED", or the result "The update was taken back"), the
installer has put the files of before back and says whether the website
answers again with the version it ran before. Read the messages above that
line, remove the cause and run the task again. The record of every run is in
*Files* → `kts.cict.in` → `logs` → `install-<date>.log`.

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
4. Open `http://kts.cict.in/healthz`. Expected:
   `{"ok": true, "time": "…", "version": "1.2.39"}`.
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

1. `https://kts.cict.in/console/login`. The account is `admin@kts5.local`;
   its first password is in *Files* → `instance` → `first-admin.txt`, written
   there by the portal at its first start and nowhere else. You are forced to
   set a new password; do it (the portal then removes the file), then
   *Users & roles* → create personal accounts for the secretariat and
   deactivate the first one.
2. **Settings**: registration window, test date and login window, duration,
   questions and marks, banner text, helpdesk contact.
3. **Question bank → Generate from the corpus** (all 23 languages, 150 each: a paper takes 50)
   and review.
4. **Notices / Repository / Events**: publish the call for applications, study
   material and the orientation session slots.
5. Mail: enter the `KTS_SMTP_*` settings in `instance\portal.env` (File
   Manager editor), one `NAME=value` on a line, then restart the portal: run
   the installation task again or, on a server installed the long way, save
   `web.config` once more. Until then mails wait in *Console → Mail outbox*.
   With Google Workspace (as for kts@cict.in): `KTS_SMTP_HOST=smtp.gmail.com`,
   `KTS_SMTP_PORT=587`, `KTS_SMTP_TLS=1`, `KTS_SMTP_USER` and `KTS_SMTP_FROM` the address,
   `KTS_SMTP_PASSWORD` an app password of that account (Google Account → Security →
   2-Step Verification → App passwords; the 16 letters without spaces). *Console → Mail
   outbox* then sends a test message and shows the answer of the server, and sends the
   messages written before mail was configured once more. Google sends at most 2,000
   messages a day from one account. *Check the connection* there tries each step (the name
   of the server, ports 587 and 465, the certificate the server shows, the form of the
   password as read from `portal.env`, the greeting, STARTTLS, the sign-in in its three
   steps) and names the one that fails: a port that cannot be reached is closed by the
   hosting company for outgoing mail; a certificate not issued by Google means something on
   the server (an antivirus or a mail filter) opens the encrypted line and must leave the
   portal alone; a line cut at the sign-in with a genuine certificate points to the same.
   The password is never shown, only whether it has the form of an app password (16 letters).
   On port 465 the connection is encrypted from the start (`KTS_SMTP_PORT=465`).
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
the merit list is published. From version 1.2.0 download `instance\stipend.key`
with the database every time: the bank details cannot be read without it.

## 9. Things that can go wrong

| Problem | Cause / fix |
|---|---|
| `/healthz` gives 502.3 after a `web.config` edit | typo in `processPath`, or the file was saved with a BOM by an editor; re-copy `deploy\plesk\web.config` |
| Pages load but sign-in returns to the login page | you are on `http://`; use `https://` (cookies are Secure) |
| Uploads fail with 413 | raise `maxAllowedContentLength` in `web.config` |
| "unable to open database file" in `logs\stdout*.log` | the site user cannot write to `httpdocs\instance`; in File Manager set the folder's permissions to allow *Modify* for the subscription's system user (Plesk normally grants this already) |
| `/` shows a directory listing or `index.html` | the extraction went into a sub-folder (`httpdocs\kts5-portal-plesk-…\`); move everything one level up |
| Slow first request after a quiet period | Plesk's default idle timeout recycles the app pool; ask the admin to set *Idle Time-out* to 0 for this subscription's pool, or accept a 10-second first load |

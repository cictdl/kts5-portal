# Kashi Tamil Sangamam 5.0 portal · Thirukkural Payilvom

A dedicated web portal for **Kashi Tamil Sangamam 5.0** built for the Central
Institute of Classical Tamil (CICT), Chennai, under the Ministry of Education.
It implements item I.1 of the CICT detailed project report: one place to
**streamline programme administration, participant registration, content
delivery and multi-agency coordination**, modelled on the BHU portal used for
KTS 4.0 (`kashitamil.bhu.edu.in`) but extended for the 1,000-students-from-
1,000-colleges selection and the 21-language orientation.

## What it does

| Area | Features |
|---|---|
| **Public site in 23 languages** (English and the 22 languages of the Eighth Schedule) | Home with key dates, live countdown to the online test, Kural of the Day and live counts · About KTS (journey 1.0–4.0) · Programme page mirroring the DPR (parts I–III) · Notices and circulars · Schedule · Participating agencies · Contact form with helpdesk queue |
| **Participant registration** | Seven-section form (personal, contact, institution with AISHE code, language, faculty mentor, photo + ID upload, declarations), server-side validation, duplicate email/mobile rejection, arithmetic captcha + honeypot + per-IP rate limit, application number `KTS5-2026-nnnnnn`, printable acknowledgement with QR, confirmation mail (outbox) |
| **Candidate portal** | Sign in with application number + date of birth + last 4 digits of mobile · status · acknowledgement · admit card · **timed online MCQ test** in the candidate's language (autosave every answer, palette navigation, auto-submit at time-out, one attempt) · result · orientation sessions and study material for their language |
| **Examination** | Question bank per language (23: the 21 scheduled languages other than Tamil, English, plus Tamil) with **automatic generation from CICT's 22-language Thirukkural corpus** (complete-the-couplet, identify-the-chapter, identify-the-section, general knowledge), CSV import/export, manual editing · test window by date/time or forced open/closed · live monitor, score distribution, per-session answer review |
| **Selection and merit list** | One-click selection: rank by score (tie-breaks: time taken, application time), **best candidate per institution**, top N selected + waitlist · publish/unpublish the public merit list with search and CSV · Excel export with contact and mentor details |
| **Digital repository** | Categorised resources (translations, publications, apps, corpus, video lectures, audiobooks, films, comics, posters, Daily Kural kits, storytelling kits, study material, links) with files or links, language tags, featured items · **Thirukkural browser**: all 1,330 couplets in 22 languages + script variants · **Daily Kural** with a downloadable 200-day school calendar in any language · Orientation page by language |
| **Multi-agency coordination hub** | Agencies (MoE, CICT, IIT Madras, BHU, BBS, CIIL, UGC, AICTE, IRCTC, AAI, NHAI, MoC, CBSE, KVS/NVS, TN and UP governments) · workstream **task board** (open / in progress / blocked / done, priority, due dates, assignees) with progress updates and attachments · shared documents with visibility control · programme calendar · agency users see only their own work |
| **Administration** | Role-based console (superadmin, admin, verifier, content, agency, viewer) · application queue with filters, bulk verify/reject, Excel/CSV export · notices, resources, events/orientation sessions · users with temporary passwords · settings (windows, test pattern, banner, contact) · helpdesk messages · mail outbox · full audit log |

## Stack

Python 3.11+ · Flask 3 · SQLite (WAL) · Jinja2 · vanilla CSS/JS (no build
step, no CDN, works offline) · Waitress for production · Pillow/qrcode for the
acknowledgement QR · XlsxWriter for exports. Everything runs from one folder.

```
portal/
  run.py            development server (http://127.0.0.1:8905)
  serve.py          production server (Waitress)
  manage.py         init-db · create-user · gen-questions · seed-demo · run-selection · export-applications
  config.py         settings, all overridable by KTS_* environment variables
  kts/              application package
    __init__.py     app factory, CSRF guard, security headers, template filters
    db.py           schema, migrations, settings, audit
    i18n.py         interface in 23 languages (reads data/i18n/<code>.json)
    kural.py        Thirukkural corpus, Kural of the Day, question generator
    public.py       public site + registration + repository
    candidate.py    candidate portal + online test
    admin.py        console
    agency.py       coordination hub
    auth.py         staff login, roles, permissions
    utils.py        CSRF, rate limiting, uploads, exports, mail, dates
  templates/        public/ · candidate/ · console/ · hub/
  static/           css/portal.css · js/portal.js · img/ (kts-logo.png, kts-mark.png, thiruvalluvar.jpg, logos/, favicon, lockups)
  tools/make_logo.py  rebuilds the logo set from the originals in tools/logo-src/
  tools/check_i18n.py checks the translations (missing keys, wrong script, lost numbers)
  data/             kurals/ (133 chapter files + meta.json from the CICT app) · i18n/ (one file per interface language) · agencies.json · states.json
  instance/         kts5.sqlite3 (created on first start) · portal.env (settings) · first-admin.txt (first password, until it is changed)
  uploads/          photos/ idproofs/ resources/ notices/ documents/ tasks/
  tests/            pytest smoke test of the whole flow
```

## Quick start

```bash
cd "D:\KTS 5.0\portal"
python -m pip install -r requirements.txt
python run.py                      # http://127.0.0.1:8905
```

First start creates the database and the first administrator,
`admin@kts5.local` (or `KTS_ADMIN_EMAIL`). No password is published: the
portal makes a random one and writes it, with the account and the sign-in
page, to `instance/first-admin.txt`. Sign in at `/console/login` with what
the file says; you are asked to set a new password at once, and the portal
then removes the file. (If `KTS_ADMIN_PASSWORD` is set, that password is used
and no file is written. A portal that is started without `KTS_BASE_URL` names
the sign-in page in general words; the first start that knows the address
writes it into the file.)

**Updating from a version before 1.1.0.** Those versions were published with
a first password. At the first start of version 1.1.0 every active account
that still has that password receives a new first password, written to
`instance/first-admin.txt`, and the published one no longer works. This
holds whether or not the account had gone through the change form before:
the change form of earlier versions accepted the published password as the
new one. If the installer says "The administrator password has already been
set" although nobody of the institute has signed in yet, somebody else has.
Then create an account of your own,

```bash
python manage.py create-user --email name@cict.in --name "Name" --role superadmin
```

(on the server through a scheduled task of Plesk, or ask the engineer of the
server; [deploy/PLESK.md](deploy/PLESK.md), *First sign-in*, has the entry),
sign in with it, deactivate the old account, and read *Users & roles* and
the *Audit log*.

Useful commands:

```bash
python manage.py gen-questions --langs all --count 60     # question bank from the corpus
python manage.py seed-demo --applications 80              # demo data for a walkthrough
python manage.py create-user --email x@ugc.gov.in --name "UGC nodal officer" --role agency --agency UGC
python manage.py run-selection --select 1000 --wait 300
python -m pytest tests -q
```

## Programme workflow

1. **Settings** → registration window, test date and login window, duration,
   questions per paper, marks, banner, contact details.
2. **Publicity** → notices, events, resources; partner tasks in the hub.
3. **Registration** → students apply; the secretariat verifies (single or
   bulk) from the application queue; verification mails go to the outbox.
4. **Question bank** → generate per language, review, disable weak items,
   import hand-written questions by CSV.
5. **Test day** → the window opens automatically at the configured time (or
   force it from the monitor). Candidates sign in, start once, answers autosave,
   the paper auto-submits at time-out. Overdue sessions can be closed from the
   monitor.
6. **Selection** → run once results are in; review the top of the list and the
   state-wise spread; publish. Candidates see rank and outcome on the portal.
7. **Orientation** → create `orientation` events per language with the meeting
   link; upload/link the ten lectures as `video` resources tagged by language.
   Each candidate's portal shows only their language.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `KTS_SECRET_KEY` | a key made at first start, kept in `instance/secret.key` | Session signing key |
| `KTS_BASE_URL` | `http://localhost:8905` | Public URL used in mails and QR codes, e.g. `https://kts.cict.in` |
| `KTS_DATABASE`, `KTS_UPLOAD_DIR`, `KTS_INSTANCE_DIR` | `instance/kts5.sqlite3`, `uploads/`, `instance/` | Storage locations (environment only, not read from `portal.env`) |
| `KTS_HTTPS` | `0` | `1`: the site is served over https; cookies are marked Secure and every link is written with https |
| `KTS_BEHIND_PROXY` | `0` | `1`: a web server on the same machine stands in front of the portal (see *Behind a web server*) |
| `KTS_TRUSTED_PROXY` | `127.0.0.1` | The address from which that web server connects to the portal |
| `KTS_HSTS` | `0` | `1`: send `Strict-Transport-Security`. Only after the real certificate is installed, and only if the web server (Plesk) does not send the header already: never in both places. Needs `KTS_HTTPS=1` |
| `KTS_URL_PREFIX` | none | Path such as `/kts5` when the portal is an application inside another site |
| `KTS_SMTP_HOST`, `KTS_SMTP_PORT`, `KTS_SMTP_USER`, `KTS_SMTP_PASSWORD`, `KTS_SMTP_FROM`, `KTS_SMTP_TLS` | no mail server, port `587`, TLS `1` | Outgoing mail; without them mails stay in the outbox for manual sending |
| `KTS_ADMIN_EMAIL`, `KTS_ADMIN_PASSWORD` | `admin@kts5.local`, no password | First administrator (created only when no user exists). Without a password the portal makes one and writes it to `instance/first-admin.txt` |
| `KTS_RATE_REGISTER_PER_HOUR` | `100` | Registrations from one address in an hour |
| `KTS_RATE_CONTACT_PER_HOUR` | `10` | Messages of the contact form from one address in an hour |
| `KTS_RATE_STATUS_FAILS` | `300` | Failed status checks from one address in 15 minutes |
| `KTS_RATE_LOGIN_FAILS` | `12` | Failed staff sign-ins from one address in 15 minutes |
| `KTS_RATE_CANDIDATE_FAILS_IP` | `600` | Failed candidate sign-ins from one address in 15 minutes |
| `KTS_RATE_CANDIDATE_FAILS_APP` | `6` | Failed attempts for one application number from one address in 15 minutes; counted for the candidate sign-in and, apart from it, for the status check |
| `KTS_HOST`, `KTS_PORT`, `KTS_THREADS` | `0.0.0.0`, `8905`, `8` | Server binding. `KTS_PORT` is read from the environment only, not from `portal.env`; when IIS starts the portal, the port is the one that IIS hands over |

**The settings file `instance/portal.env`.** A name of this table that the
environment does not define, other than the storage names and `KTS_PORT`, is
read from this file: one setting on a line, written `NAME=value`; a line that
begins with `#` is a comment. Names in capital letters. Nothing may follow
the value on its line: no comment, no semicolon.

```
KTS_SMTP_HOST=smtp.example.gov.in
KTS_SMTP_PORT=587
KTS_RATE_REGISTER_PER_HOUR=200
```

The environment wins over the file. The file is read when the portal starts,
so restart the portal after a change. It lies in `instance/`, which no update
replaces and which is neither served to visitors nor committed to git; on the
server it is the place for the mail settings and the limits. The installer
`deploy\plesk\kts-install.bat` creates it with comment lines only.

## Behind a web server

In production a web server (IIS, nginx) receives the visitors and hands each
request to the portal on the same machine, so every connection that the
portal sees comes from that web server. `KTS_BEHIND_PROXY=1` tells the portal
so:

* The **visitor's address** is taken from the last entry of
  `X-Forwarded-For`: the entry that the web server named in
  `KTS_TRUSTED_PROXY` (default `127.0.0.1`) wrote itself. Whatever stands
  before it was sent by the visitor and is not believed.
* **No other forwarded header is trusted.** `X-Forwarded-Proto`, `-Host`,
  `-Port` and `Forwarded` never reach the portal as a visitor wrote them.
* The **scheme comes from `KTS_HTTPS`**, the host name from the `Host` header
  and a path prefix from `KTS_URL_PREFIX`.

Without `KTS_BEHIND_PROXY` the address of the connection itself is used and
`X-Forwarded-For` is ignored. The address found this way is the one written
to the audit log and the one the limits count by.

**Limits.** Registration and the contact form are limited per address and
hour; the status check, the staff sign-in and the candidate sign-in count
*failed* attempts in 15 minutes, so that nobody who signs in correctly is
held up. The limits are counted **per address** because that is all the
portal knows of a visitor who has not signed in; they are generous (600
failed candidate sign-ins, 300 failed status checks) because the students of
one college reach the portal through one public address, and on the day of
the test a computer room full of candidates must not be locked out by the
typing errors of its neighbours. A college that registers more than 100
students within an hour through one connection (a computer room, or a campus
behind one address) needs `KTS_RATE_REGISTER_PER_HOUR` raised in
`instance/portal.env` before the drive, and the portal restarted; on the
server, run the task of Plesk again.

The candidate sign-in and the status check count, each for itself, **per
application number and address** as well: 6 failed attempts in 15 minutes.
Application numbers are consecutive. Counted per number alone, six wrong
attempts from anywhere on the internet would close the sign-in of any
candidate during the hour of the test; counted per number and address, an
outsider closes it for his own address only. The price: guesses against one
application number are bounded per address, not in total. Somebody who
guesses from many addresses has six attempts from each of them. Attempts
that arrive at the same moment are compared before the first of them is
counted: a limit for failed attempts can be passed by up to `KTS_THREADS` - 1
(7 as delivered) in one window. All values can be changed in
`instance/portal.env`.

## Deployment

**Windows / IIS (the CICT web server).** Fully scripted: see
[deploy/DEPLOY.md](deploy/DEPLOY.md). In short, `deploy\package.ps1` builds
`dist\kts5-portal-<stamp>.zip`; on the server an elevated
`deploy\setup-iis.ps1 -Package <zip> -HostName kts.cict.in` unpacks it,
creates the virtual environment, writes `web.config`, creates the app pool and
site (HttpPlatformHandler mode, or `-Mode Proxy` with URL Rewrite + ARR and a
Windows service), sets permissions and runs a health check. The portal can
also live under an existing site as an application (`-AppPath /kts5`); the app
honours `KTS_URL_PREFIX`, `KTS_BEHIND_PROXY` and `KTS_HTTPS` for that.

**Plesk, one file (how `kts.cict.in` is installed).**
[deploy/PLESK.md](deploy/PLESK.md): `deploy\plesk\kts-install.bat`, started by
a scheduled task of Plesk, needs no administrator rights and installs nothing
on the server. It downloads the portal, unpacks a Python of its own into the
site folder, lets the ASP.NET Core Module of IIS start `serve.py`, writes
`web.config` and makes sure that the version answering at `/healthz` is the
version of the files. Running the task again updates the portal; `instance\`
(database, keys, `portal.env`, `first-admin.txt`), `uploads\` and `logs\` are
never touched. While the files are replaced visitors see a page "The portal
is being updated"; a run that stops after it has replaced files puts the
files of before back from its safety copy, so that the website runs the
version it ran. *Releasing an update* in the guide says what to look at.

**Plesk (no shell on the server).** [deploy/PLESK.md](deploy/PLESK.md):
`deploy\package-plesk.ps1` builds a self-contained zip (Python libraries
vendored in `lib\`, Plesk `web.config`) that is uploaded and extracted into
the subdomain's `httpdocs` with the Plesk File Manager; a three-file probe
(`deploy\plesk\probe`) first confirms that the server has Python 3.11+ and
the HttpPlatformHandler module.

**Straight from git (Plesk Git; for a server with Python and the
HttpPlatformHandler module, not for a folder installed by
`kts-install.bat`).** The repository root *is* the
site: `web.config` (HttpPlatformHandler), `serve.py`, the vendored Python
libraries in `lib\`, and the empty `instance\`, `uploads\`, `logs\` folders.
In Plesk: *Websites & Domains* → the subdomain → **Git** → *Add repository* →
remote repository `https://github.com/cictdl/kts5-portal.git`, branch `main`,
deploy to the subdomain's document root, deployment mode *Automatic*. Every
push to `main` (followed by *Pull updates*, or the webhook Plesk shows) updates
the site; `instance\` and `uploads\` are not in git and survive deployments.
The server itself needs Python 3.11+ and the HttpPlatformHandler module once:
`deploy\plesk\server-setup.ps1`, run as Administrator. After changing
`requirements.txt`, refresh the vendored libraries with
`powershell -File tools\vendor.ps1` and commit `lib\`.

**Linux.** `python serve.py` (Waitress) on `127.0.0.1:8905` behind nginx, with
`KTS_HOST=127.0.0.1`, `KTS_BEHIND_PROXY=1` and `KTS_HTTPS=1` (without
`KTS_HOST` the portal listens on every address of the machine); nginx serves
`/static/` directly, proxies the rest, hands on the name of the website
(`proxy_set_header Host $host;`) and adds the visitor's address
(`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`). The portal
takes its own name from the `Host` header: without the first line the pages
would name `127.0.0.1:8905` where they name the website. It is `serve.py`
that reads the second header: under another WSGI server every visitor would
appear with the address of nginx, and the limits would count all visitors as
one.

**Backups.** Copy `instance/kts5.sqlite3` (WAL mode: use `sqlite3 ... ".backup"`
or stop the service first) and the `uploads/` folder. Both are small: ~1 KB
per application plus the photo and ID upload.

**Scale.** SQLite in WAL mode with Waitress threads comfortably serves the
expected load (tens of thousands of applications; a few thousand concurrent
test sessions saving one answer at a time). Put the database on local SSD, not
a network share.

## Security notes

* Every POST is CSRF-protected; sessions are HttpOnly/SameSite=Lax cookies.
* Passwords are hashed with Werkzeug (scrypt/pbkdf2); temporary passwords
  force a change at first sign-in.
* No password is built in or published. The first administrator receives a
  random password, written to `instance/first-admin.txt` and nowhere else; the
  file is removed when that password has been changed.
* Uploads are type-sniffed, size-limited, renamed randomly and served only to
  the owner (candidate) or staff with the right role. Agency users never see
  participant data.
* Rate limits on registration, status checks, contact and sign-in, counted
  per address and, for the candidate sign-in and the status check, per
  application number and address as well (see *Behind a web server*);
  honeypot and arithmetic captcha on public forms (no third-party services).
* Security headers (nosniff, frame-options, referrer-policy); console and
  candidate pages are `no-store`.
* All staff actions are written to the audit log with actor and IP.

## Languages

The public site and the candidate portal are offered in **23 languages**:
English and the 22 languages of the Eighth Schedule. The language is chosen
from the menu at the top of every page (or the list in the footer, or
`/lang/<code>`, or `?lang=<code>` on any address) and is remembered for a year.

| Code | Language | Script | | Code | Language | Script |
|---|---|---|---|---|---|---|
| `en` | English | Latin | | `ml` | Malayalam | Malayalam |
| `as` | Assamese | Bengali-Assamese | | `mni` | Manipuri | Bengali |
| `bn` | Bengali | Bengali | | `mr` | Marathi | Devanagari |
| `brx` | Bodo | Devanagari | | `ne` | Nepali | Devanagari |
| `doi` | Dogri | Devanagari | | `or` | Odia | Odia |
| `gu` | Gujarati | Gujarati | | `pa` | Punjabi | Gurmukhi |
| `hi` | Hindi | Devanagari | | `sa` | Sanskrit | Devanagari |
| `kn` | Kannada | Kannada | | `sat` | Santali | Ol Chiki |
| `ks` | Kashmiri | Perso-Arabic, right to left | | `sd` | Sindhi | Devanagari |
| `kok` | Konkani | Devanagari | | `ta` | Tamil | Tamil |
| `mai` | Maithili | Devanagari | | `te` | Telugu | Telugu |
| | | | | `ur` | Urdu | Perso-Arabic, right to left |

* **One file per language**: `data/i18n/<code>.json`, a flat list of
  `key: text`. English (`en.json`) is the source. A key that a language lacks
  is shown in English, never blank. To correct a translation, edit the file
  and restart the portal; no code changes.
* **Check before publishing**: `python tools/check_i18n.py` (all languages) or
  `python tools/check_i18n.py bn te ur`. It reports missing or unknown keys,
  text left in English or written in the wrong script, numbers that differ
  from the English, and labels that grew too long. The same check runs in
  `python -m pytest tests -q`, together with a rendering of every public page
  in every language.
* **Reviewed and draft languages**: English, Tamil and Hindi are reviewed. The
  other twenty were drafted by machine and must be read by a speaker of the
  language before they are relied on; until then every page in those
  languages carries the note “This translation of the interface is a draft…”
  with a link back to English. After review add the code to `REVIEWED` in
  `kts/i18n.py`; the note can also be switched off in *Console → Settings →
  Site*.
* **Right to left**: Urdu and Kashmiri set `dir="rtl"` on the page; the layout
  mirrors, and couplets, numbers, application numbers, addresses and e-mail
  addresses keep their own direction.
* **Dates** are written `25 Sep 2026` in English and `25-09-2026` with the
  24-hour clock in every other language, so that no month name is left in
  English.
* **What follows the interface language**: the Kural of the Day, the
  Thirukkural browser and the Daily Kural open in the translation of the
  interface language (Kashmiri in the Perso-Arabic script, Konkani in
  Devanagari; the other scripts remain in the language list of the browser).
* **What is translated beyond the labels**: the names of the States and Union
  Territories, the participating agencies and their roles, categories of
  notices and events, error pages and the messages of the online test. The
  default banner, orientation note and the quotation on the home page are
  translated as long as the administrator has not changed them in Settings;
  wording entered in the console (notices, events, resources, a new banner) is
  shown as entered.
* **The staff console and the agencies' hub** remain in English.
* **Online test**: the stems of the generated questions come from the same
  files (`q.chapter`, `q.complete`, `q.section`, `q.none`). Tamil and Hindi
  give their own wording; a draft language gives its wording with the English
  below it; streams of the corpus in a script without an interface translation
  (Kashmiri in Devanagari, Konkani in the Kannada script, Santali in
  Devanagari, Manipuri in Meetei Mayek) keep the English stem.

## Logos and images

All artwork is generated by `tools/make_logo.py` from the originals in
`tools/logo-src/`:

* `static/img/kts-logo.png` (masthead, print headers) and `kts-mark.png`
  (the circle alone: favicon, console, exam header) from the official
  Kashi Tamil Sangamam logo;
* `static/img/logos/<code>.png`: Government of India and Ministry of
  Education (masthead and the organisers' band above the footer), CICT,
  IIT Madras, BHU and BBS (organisers' band, home page and Partners page).
  A logo file named after an agency's code, in lower case, is picked up
  automatically for that agency;
* `static/img/thiruvalluvar.jpg` and `thiruvalluvar-bust.jpg`, the painting of
  Thiruvalluvar (About page and the Kural of the Day card);
* `static/img/pm-thirukkural.jpg`, the Prime Minister presenting the
  Thirukkural in Russian translation, shown on the home page with a quotation.
  The quotation, its attribution and the caption are edited in
  *Console → Settings → Home page*, where the block can also be switched off;
* `kts5-lockup.png/.svg` for letterheads.

## Known limits / next steps

* The twenty draft interface languages need a reading by a speaker of each
  language (see *Languages*). Bodo, Dogri, Kashmiri, Konkani, Maithili,
  Manipuri, Sanskrit, Santali and Sindhi have little published administrative
  vocabulary and deserve the closest reading.
* The general-knowledge questions of the test (`GK` in `kts/kural.py`) exist
  in English, Tamil and Hindi; the other languages receive the English set
  until translators deliver theirs.
* The test and the orientation use the primary stream of each language in the
  corpus: Kashmiri in Devanagari and Konkani in the Kannada script. If
  candidates should choose the script, add the variants (`ksn`, `gom`) to
  `ORIENTATION_LANGS` in `kts/kural.py`.
* **Kashmiri in the Perso-Arabic script (`ksn`).** In the data received from
  the Thirukkural app this stream was one couplet out of place from couplet 93
  to 1330 (entry 93 was a second version of couplet 92). The portal's copy is
  repaired by `tools/fix_ksn_alignment.py`, which records what it did in
  `data/kurals/ksn-repair.json`; couplet 1330 has no text in this script until
  CICT supplies it, and the portal shows the English there. Do not copy the
  chapter files from the app again without running the repair.
* In the Urdu stream several couplets break the line one word early (for
  example couplets 7, 8 and 393), which weakens the "choose the second line"
  question in Urdu; the affected couplets still need to be listed and corrected.
* The candidate sign-in (application number + DOB + mobile last 4) matches the
  BHU practice; if OTP is wanted, add an SMS gateway behind `utils.send_mail`-style
  hooks.
* Photos and ID proofs live on disk; for a multi-server deployment move
  `uploads/` to shared storage or object storage.
* The Thirukkural text and translations are CICT's own corpus (CC BY 4.0), the
  same data as the Thirukkural Multilingual App.

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
| **Public site** (English · தமிழ் · हिन्दी) | Home with key dates, live countdown to the online test, Kural of the Day and live counts · About KTS (journey 1.0–4.0) · Programme page mirroring the DPR (parts I–III) · Notices and circulars · Schedule · Participating agencies · Contact form with helpdesk queue |
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
    i18n.py         interface strings (en / ta / hi)
    kural.py        Thirukkural corpus, Kural of the Day, question generator
    public.py       public site + registration + repository
    candidate.py    candidate portal + online test
    admin.py        console
    agency.py       coordination hub
    auth.py         staff login, roles, permissions
    utils.py        CSRF, rate limiting, uploads, exports, mail, dates
  templates/        public/ · candidate/ · console/ · hub/
  static/           css/portal.css · js/portal.js · img/ (kts-logo.png, kts-mark.png, thiruvalluvar-gold.png, favicon, lockups)
  tools/make_logo.py  rebuilds the KTS 5.0 logo set from the Thiruvalluvar portrait (re-run with a higher-resolution original)
  data/             kurals/ (133 chapter files + meta.json from the CICT app) · agencies.json · states.json
  instance/         kts5.sqlite3 (created on first start)
  uploads/          photos/ idproofs/ resources/ notices/ documents/ tasks/
  tests/            pytest smoke test of the whole flow
```

## Quick start

```bash
cd "D:\KTS 5.0\portal"
python -m pip install -r requirements.txt
python run.py                      # http://127.0.0.1:8905
```

First start creates the database and the first administrator
(`admin@kts5.local` / `Admin@KTS5`, or `KTS_ADMIN_EMAIL` / `KTS_ADMIN_PASSWORD`).
Sign in at `/console/login`; you are asked to set a new password at once.

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

| Variable | Purpose |
|---|---|
| `KTS_SECRET_KEY` | **Required in production.** Session signing key. |
| `KTS_BASE_URL` | Public URL used in mails and QR codes, e.g. `https://kts5.cict.in` |
| `KTS_DATABASE`, `KTS_UPLOAD_DIR`, `KTS_INSTANCE_DIR` | Storage locations |
| `KTS_HTTPS=1` | Mark cookies Secure (behind TLS) |
| `KTS_SMTP_HOST`, `KTS_SMTP_PORT`, `KTS_SMTP_USER`, `KTS_SMTP_PASSWORD`, `KTS_SMTP_FROM`, `KTS_SMTP_TLS` | Outgoing mail; without them mails stay in the outbox for manual sending |
| `KTS_ADMIN_EMAIL`, `KTS_ADMIN_PASSWORD` | First administrator (created only when no user exists) |
| `KTS_HOST`, `KTS_PORT`, `KTS_THREADS` | Server binding |

## Deployment

**Windows / IIS (the CICT web server).** Fully scripted: see
[deploy/DEPLOY.md](deploy/DEPLOY.md). In short, `deploy\package.ps1` builds
`dist\kts5-portal-<stamp>.zip`; on the server an elevated
`deploy\setup-iis.ps1 -Package <zip> -HostName kts5.cict.in` unpacks it,
creates the virtual environment, writes `web.config`, creates the app pool and
site (HttpPlatformHandler mode, or `-Mode Proxy` with URL Rewrite + ARR and a
Windows service), sets permissions and runs a health check. The portal can
also live under an existing site as an application (`-AppPath /kts5`); the app
honours `KTS_URL_PREFIX`, `KTS_BEHIND_PROXY` and `KTS_HTTPS` for that.

**Plesk (no shell on the server).** [deploy/PLESK.md](deploy/PLESK.md):
`deploy\package-plesk.ps1` builds a self-contained zip (Python libraries
vendored in `lib\`, Plesk `web.config`) that is uploaded and extracted into
the subdomain's `httpdocs` with the Plesk File Manager; a three-file probe
(`deploy\plesk\probe`) first confirms that the server has Python 3.11+ and
the HttpPlatformHandler module.

**Linux.** `gunicorn -w 4 -b 127.0.0.1:8905 'kts:create_app()'` (or Waitress)
behind nginx; nginx serves `/static/` directly and proxies the rest.

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
* Uploads are type-sniffed, size-limited, renamed randomly and served only to
  the owner (candidate) or staff with the right role. Agency users never see
  participant data.
* Rate limits on registration, status checks, contact and sign-in; honeypot
  and arithmetic captcha on public forms (no third-party services).
* Security headers (nosniff, frame-options, referrer-policy); console and
  candidate pages are `no-store`.
* All staff actions are written to the audit log with actor and IP.

## Logo

The site uses the official Kashi Tamil Sangamam logo (`static/img/kts-logo.png`
in the masthead and print headers; `kts-mark.png`, the circle alone, for the
favicon, console and exam header) and the golden Thiruvalluvar as the emblem
of *Thirukkural Payilvom – Thirukkural Abhyas Karen* (`thiruvalluvar-gold.png`
on the home page card and the About page). `tools/make_logo.py` regenerates
these, the favicon, the touch icon and the lockups (`kts5-lockup.png/.svg`)
from the originals in `tools/logo-src/`.

## Known limits / next steps

* Question stems are localised for English, Tamil and Hindi; for the other 20
  languages the stem is English while the couplet is in that language. Add
  localised stems in `kts/kural.py` (`STEMS`, `GK`) as translators deliver them.
* The candidate sign-in (application number + DOB + mobile last 4) matches the
  BHU practice; if OTP is wanted, add an SMS gateway behind `utils.send_mail`-style
  hooks.
* Photos and ID proofs live on disk; for a multi-server deployment move
  `uploads/` to shared storage or object storage.
* The Thirukkural text and translations are CICT's own corpus (CC BY 4.0), the
  same data as the Thirukkural Multilingual App.

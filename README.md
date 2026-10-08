# Kashi Tamil Sangamam 5.0 portal · Thirukkural Payilvom

A dedicated web portal for **Kashi Tamil Sangamam 5.0** built for the Central
Institute of Classical Tamil (CICT), Chennai, under the Ministry of Education.
It implements item I.1 of the CICT detailed project report: one place to
**streamline programme administration, participant registration, content
delivery and multi-agency coordination**, modelled on the BHU portal used for
KTS 4.0 (`kashitamil.bhu.edu.in`) but extended for the 1,000-students-from-
1,000-colleges selection and the orientation in 22 languages and English.

## What it does

| Area | Features |
|---|---|
| **Public site in 23 languages** (English and the 22 languages of the Eighth Schedule) | Home with key dates, live countdown to the online test, Kural of the Day and live counts · About KTS (journey 1.0–4.0) · Programme page mirroring the DPR (parts I–III) · Notices and circulars · Schedule · Participating agencies · Contact form with helpdesk queue |
| **Participant registration** | Seven-section form (personal, contact, institution with AISHE code, language, faculty mentor, photo + ID upload, declarations), server-side validation, duplicate email/mobile rejection, arithmetic captcha + honeypot + per-IP rate limit, application number `KTS5-2026-nnnnnn`, printable acknowledgement with QR, confirmation mail (outbox) |
| **Candidate portal** | Sign in with application number + date of birth + last 4 digits of mobile · status · acknowledgement · admit card · **timed online MCQ test** in the candidate's language (autosave every answer, palette navigation, auto-submit at time-out, one attempt) · result · orientation sessions and study material for their language |
| **Examination** | Question bank per language (23: the 22 scheduled languages, Tamil among them, and English) with **automatic generation from CICT's 22-language Thirukkural corpus** (complete-the-couplet, identify-the-chapter, identify-the-section, general knowledge), CSV import/export, manual editing · test window by date/time or forced open/closed · live monitor, score distribution, per-session answer review |
| **Selection and merit list** | One-click selection: rank by score (tie-breaks: time taken, application time), **best candidate per institution**, top N selected + waitlist · publish/unpublish the public merit list with search and CSV · Excel export with contact and mentor details |
| **Digital repository** | Categorised resources (translations, publications, apps, corpus, video lectures, audiobooks, films, comics, posters, Daily Kural kits, storytelling kits, study material, links) with files or links, language tags, featured items; the entries of `data/resources.json` (CICT's apps and archives, and the prosody workbench யாப்புக் கலம் served by the portal itself from `static/yappu/`) are put in once for each database, so a deleted entry stays deleted · **Thirukkural browser**: all 1,330 couplets in 22 languages + script variants · **Daily Kural** with a downloadable 200-day school calendar in any language · Orientation page by language |
| **CICT on social media** | Nine links (X, Instagram, YouTube, Facebook, Threads, WhatsApp, LinkedIn, Telegram, Arattai) in the footer of every page and on the contact page; the addresses are the settings `social.*` (Console → Settings → Social media): change one there, or empty it to hide that link |
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
    stipend.py      stipend: the bank details of the selected students, both sides
    secure.py       seals the account and Aadhaar numbers (key instance/stipend.key)
    quiz.py         classroom quiz: a live Thirukkural quiz on the projector, answered on phones
    papers.py       research papers of the delegates: submission, versions, review
    agency.py       coordination hub
    auth.py         staff login, roles, permissions
    utils.py        CSRF, rate limiting, uploads, exports, mail, dates
  templates/        public/ · candidate/ · console/ · hub/ · quiz/
  static/           css/portal.css · js/portal.js · img/ (kts-logo.png, kts-mark.png, thiruvalluvar.jpg, logos/, favicon, lockups)
  tools/make_logo.py  rebuilds the logo set from the originals in tools/logo-src/
  tools/check_i18n.py checks the translations (missing keys, wrong script, lost numbers)
  data/             kurals/ (133 chapter files + meta.json from the CICT app) · i18n/ (one file per interface language) · agencies.json · states.json
  instance/         kts5.sqlite3 (created on first start) · stipend.key (the key of the stipend module: in every backup with the database) · portal.env (settings) · first-admin.txt (first password, until it is changed)
  uploads/          photos/ idproofs/ bankproofs/ resources/ notices/ documents/ tasks/
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
8. **Stipend** → open the form for the bank details (*Settings → Stipend*),
   check every entry against its proof, approve it, export a payment list
   for the bank, and mark that list as paid when the bank has made the
   transfers. See the next section.

## Certificates of recognition and of merit, confirmation letter

The student delegates (the selected students of the published merit list) attend the
inauguration of KTS 5.0 online and receive a certificate of participation (from 1.2.10):
`/certificate/inaugural/<application number>/<seal>`, number `KTS5/CP/…`, the same sheet in
green. It is issued once the attendance is recorded (table `inaug_attendance`): by the student,
on the candidate portal, with the attendance code announced during the live stream (settings
`inaug.code` and `inaug.link`; the code is accepted from the day of the inauguration,
`kts.start`, while it is set), or in *Console → Certificate* from a list of application numbers,
where the attendance is also removed and downloaded as CSV. Setting `cert.inaug_on`.

Every selected student also receives a confirmation letter on the letterhead
of CICT (from 1.2.5): `/letter/<application number>/<seal>`, an A4 page with
reference number `CICT/KTS5/CL/…`, the rank, the faculty mentor and the
language of the application, the dates of the internship, of the research
paper and of the presentation (settings `letter.date`, `internship.start`,
`papers.due`, `present.due`), the stipend and the days of the Sangamam,
signed like the certificates, with a copy to the head of the institution.
Issued once the merit list is published (setting `letter.on`); linked from
the status page and the candidate portal.

Every student who registers receives a certificate of recognition, signed by
the head of the institute (from version 1.2.2, `kts/certificate.py`). Every
student of the published merit list, selected or waitlisted, receives, in addition, a
certificate of merit with the rank (from 1.2.3): the same sheet in gold,
`/certificate/merit/<application number>/<seal>`, number `KTS5/CM/…`, issued
on the day of the selection, linked from the status page and the candidate
portal; that of a waitlisted student says "waiting list" and has no number
of students chosen (from 1.2.4); none after a withdrawal, none while
`cert.merit_on` is `0`. It is a
page of the portal laid out as an A4 sheet on its side, which the student
prints or saves as PDF: `/certificate/<application number>/<seal>`, where the
seal is a keyed digest of the number (made with the secret key of the
installation), so that nobody reaches the certificate of another student by
changing the number. The QR code on the sheet opens that same page on the
portal, which is the proof that the certificate is genuine. The page is kept
out of search engines and shared caches.

The student finds it on the page shown after registration, in the
registration e-mail, on the status page and in the candidate portal.
Rejected and withdrawn applications have none, and none is issued while the
setting `cert.on` is `0` (*Console → Certificate*). The sheet is in English;
the toolbar above it is in the language of the page.

Signatory: the name and designation of the head of the institute in the
settings (`director.name`, `director.designation`, also shown on the contact
page). The image of the signature is uploaded in *Console → Certificate*
(PNG or JPG under 1 MB) and kept as `instance/certificate-signature.png` (or
`.jpg`), outside the web folder; it is written into each certificate page
itself. Without it the certificates show the name above an empty line.

## Reels and shorts

From 1.2.23 the programme page lists, under the card "Reels and shorts" of part II (`/programme#reels`),
the short videos of CICT on YouTube in which scholars and students explain the Thirukkural in their
own languages. The list is `data/reels.json` (YouTube id, language in English, its own name,
presenter), in the order of CICT's list; the page groups it by language and links each video to
`https://www.youtube.com/shorts/<id>`. To add a video, add a line to the file. Only YouTube links
are listed, not Facebook ones.

## Nomination at registration

From 1.2.22 registration follows the nomination process of the Ministry: the Faculty
Supervisor/Guide (name, designation, e-mail, mobile) is required, and the nomination form signed
and sealed by the Director, Registrar, Principal or Head of the Institution is uploaded (PDF, JPG
or PNG up to 4 MB, `applications.nomination_path`, folder `uploads/nominations/`, seen by the
staff who see applications). The blank form is `static/KTS5-nomination-form.pdf`, linked from
the registration page (from 1.2.28 also in a box at the top of the form and on the page shown
before registration opens): since 1.2.27 it is CICT's own design (made in Canva, one A4 page). To change
the form, replace that file with the new PDF under the same name. Applications registered
before 1.2.22 have no form; the console says so.

## Nodal Higher Educational Institutions

From 1.2.22 the partners page (`/partners#nodal`) lists the 31 State/UT-wise Nodal Higher
Educational Institutions designated by the Ministry (`data/nodal_heis.json`: state, type, name;
the names stay in English, the States in the language of the page) and explains in four points
how the programme reaches the institutions: the role of the Nodal Institution (up to 50
institutions in its State/UT, a State/UT Nodal Officer), nomination and registration (one
student and one Faculty Supervisor/Guide per institution, endorsed by its head), the selection
of 1,000 students, and the campus activities with their report.

## Gallery

From 1.2.20 (`kts/gallery.py`): photographs of the programme in albums on the public page
*Gallery* (`/gallery`, a tab per album). Staff of the content role upload them in *Console →
Gallery*, several at once (JPG, PNG or WebP of up to 8 MB each), with the album (the event), a
caption and a date, and hide, re-caption or delete each one. The files lie in `uploads/gallery/`
and are served at `/files/gallery/…` while published. No thumbnail is made: the live server has
no image library, so photographs should be uploaded at web size (about 1,600 pixels wide).

## Contact form

Every message of the contact form is kept in *Console → Messages* and, from 1.2.19, also sent
by e-mail to the address of the setting `contact.notify` (*Settings → Contact*; kts@cict.in by
default, empty for none), with the visitor's name, address and message and a link to the
console. The mail goes from the portal's own account; the helpdesk replies to the visitor from
its own mail.

## Classroom quiz

A live Thirukkural quiz for a class (from 1.2.8, `kts/quiz.py`), made for the presentation that
each selected student gives in his or her college. The host opens *Host a quiz* (`/quiz/host`),
chooses the language of the questions (the 23 of the test), the questions (the whole Thirukkural,
one section or one chapter), 5 to 20 questions and 20 to 60 seconds for each, and shows the quiz
on the projector: the address, a six-digit code and a QR code. The students join on their phones
at `/quiz` with the code and a name, without an account. Each question is shown alone for five
seconds, then with its four answers (coloured, each with its own shape) and the time; a correct
answer earns 1,000 points at once and 500 at the last moment. The answer, the couplet in Tamil and
in the language of the quiz, a leaderboard after each question and a podium at the end follow; the
host downloads the results as CSV. The pages are in the 23 interface languages, in a light theme. The quiz stands in the Resources
(from 1.2.9, seed `classroom-quiz` of `data/resources.json`).

The questions are made from the corpus when the quiz is created, in the kinds of the question
generator of the test; they are never those of the question bank. The screens ask the portal for
the state every second (projector) or second and a half (phones): no socket, so nothing holds a
thread of Waitress. Who hosts: CICT staff signed in to the console, and the selected students
signed in to the candidate portal once the merit list is published (a card on their page). The
console lists every quiz (*Classroom quiz*); under *Settings → Classroom quiz* an administrator
closes the quiz (`quiz.on`), stops the hosting by students (`quiz.candidates`) or limits the
players of one quiz (`quiz.max_players`, 200). A host has one quiz at a time; a quiz that is not
ended closes after six hours. The names of the players are deleted with their answers after 30
days; the line of the quiz (host, language, number of players) stays.

## Videos in the repository

From 1.2.12 the repository has three tabs for the videos of CICT: *Thirukkural videos*
(`video_kural`), *Thiruvalluvar videos* (`video_valluvar`) and *Thirukkural in sign language*
(`video_sign`). The 44 parts of the Thirukkural in Indian Sign Language come with the portal (seeds
`kural-sign-01` to `kural-sign-44` of `data/resources.json`, from the catalogue of CICT); a video
of the other two is added in *Console → Repository → New resource* with its YouTube address and
the category. A tab stands on the public page once it holds a published entry. The videos open
on YouTube; nothing of YouTube is loaded by the portal itself.

From 1.2.13 a tab *Music* (`music`) holds *திருக்குறள் இசைத் தமிழ் · Thirukkural Isai Tamil*, the
complete musical version of the Thirukkural in six volumes, MP3 files on cict.in (seeds
`kural-isai-1` to `kural-isai-6`).

From 1.2.14 the tab *Thirukkural videos* holds five lectures of Dr. Divya Sripada from the channel
of CICT (seeds `yt-<video id>`); from 1.2.15 the other videos on the Thirukkural and Thiruvalluvar in
the playlists of the channel: 16 more under *Thirukkural videos* (Prof. P. Marudhanayagam; Prof.
Jayaprakasam in Telugu) and 57 under *Thiruvalluvar videos* (the 49 parts of வள்ளுவத்தைச்
சிந்திப்போம் by Dr. K. Balaraman; Prof. P. Marudhanayagam). Titles are taken as YouTube gives them; YouTube itself cannot be
reached from every machine, and noembed.com returns the title and the channel of a video.

## Research papers of the delegates

From 1.2.11 (`kts/papers.py`). Each selected student sends a research paper on the Thirukkural on
the candidate portal (*Research paper*, `/candidate/paper`): title, language (the 23 of the test),
abstract (at most 3,000 characters), keywords and couplets studied (optional), the faculty mentor
(taken from the application, may be corrected), the paper as PDF or Word (DOCX) of up to 10 MB, and
a declaration that it is the student's own work. Number `KTS5/RP/…`. The period runs from
`internship.start` to `papers.due` (setting `papers.open`: `auto`, `1` open, `0` closed); until the
review the student may replace the paper or correct its details. A returned paper may be sent
again after the last date, unless `papers.open` is `0`. Every file is kept with its version
(`paper_files`), in `uploads/papers/`, which the web server never serves.

*Console → Research papers* lists the delegates with their papers (filters, Excel and CSV of the
list as shown), shows each paper with its versions and its abstract, and records the review:
accept, or return with remarks (required), with an optional score out of 100. The student is told
by e-mail on receipt, return and acceptance. Roles: `papers.view` (administrators, verifiers,
content, viewers) and `papers.review` (all but viewers). Settings → Internship: `papers.note` (a note
above the form) and `papers.guide_url` (a link to the guidelines).

## Stipend: bank details of the selected students

Each of the 1,000 selected students receives a stipend (setting
`stipend.amount`, Rs. 10,000) by bank transfer to his or her own account.
The module was added in version 1.2.0 (`kts/stipend.py`, `kts/secure.py`). The public page
`/stipend` (from 1.2.1) tells the students the steps, in every language of the portal, and
whether the form is open; the home page, the programme page, the footer and the form link to it.

**What the student does.** Once the merit list is published
(`merit.published = 1`) and the form is open (`stipend.open = 1`), a student
whose application has the status *selected* finds a card *Bank details for the
stipend* on the candidate page, with the state of the entry in a word and a
line that says what the state means, and the form at `/candidate/bank`: name
of the account holder (with the registered name above it for comparison),
account number typed twice (9 to 18 digits), IFSC, bank, branch, type of
account, the Aadhaar number (when it is asked for), a photo or PDF of a
cancelled cheque or of the first page of the passbook (PDF, JPG or PNG up to
2 MB; a JPEG that Windows saved as `.jfif` is taken as well, the name of the
file may be in any script, and both at once: a `.jfif` named in Tamil is a
JPEG) and three declarations. Everything is typed in English; spaces in the
IFSC and in the Aadhaar number are removed. Anybody else who signs in as a
candidate is told that the form is for the students of the final selected
list, and sees nothing else; only a payment made before a student left that
list stays on his or her page (see below). The form closes after
`stipend.last_date` for students who have sent nothing; an entry that the
staff returned may be sent again after that date too. `stipend.open = 0`
stops every entry.

**Once sent, an entry is locked.** The student sees it with the last four
digits only (`XXXXXX1234`) and the state: being checked, returned for
correction (with the remark of the staff and the form again; the two numbers
are typed again, the proof may be kept or replaced), approved, paid (with date
and reference; the sum that was paid stands in the mail of the payment and on
the console, not on the student's page, since no text key of the module
carries an amount). Every submission and
every change of state is mailed to the registered e-mail address, with the
last four digits of the account only and the request to write to CICT at once
if the student did not send it. The sign-in of a candidate is weak (a
classmate may know application number, date of birth and mobile number),
which is why nobody but the staff can change an entry once it is sent, why
nothing is paid without the staff's approval against the proof, and why the
mails go out. At most 10 submissions per hour are taken from one application
and address. A student whose entry is paid sees the paid state on
`/candidate/bank` and on the card of the candidate page whatever the status
of the application has become since (withdrawn, or waitlisted after a
selection that was run again); an entry in any other state is shown to a
student of the selected list only.

**What the staff do** (*Console → Stipend*, permission `stipend`: superadmin
and admin only). The list shows every selected student with the state of the
entry, the masked account number and the IFSC; counts, a filter by state and
a search by name, application number or college, 100 to a page. An account
number that is also given for another application is marked *same account*.
The page of one entry shows the registered name beside the name of the account
holder, the full account number, IFSC, bank, branch, type, the full Aadhaar
number, the link to the proof, the other applications with the same account,
the number of the payment list the entry stands in, and the history: the
changes of state and, apart from them, how often the staff opened the entry
and the proof. From there: **Approve** (from submitted), **Return to the
student** (from submitted or approved; the remark is required and is mailed),
**Mark as paid** (from approved; reference and date required), **Undo 'paid'**
(superadmin only). Every action is mailed to the student. Three rules guard
the actions:

* *One stipend for one account.* An entry is not approved while another entry
  with the same account number is approved or paid: the page says so, and the
  staff return the wrong one first. No payment list holds one account twice.
  The comparison is by the digits of the number alone (zeros in front left
  out), so the same digits at another bank, under another IFSC, count as the
  same account and are refused as well: two students of two banks whose
  numbers happen to share the digits cannot both be approved through the
  portal. A known limit, rare among 1,000 students, and the page names the
  other application with its IFSC so that the staff see what is happening.
* *No action from an old page.* Every action form carries the version of the
  entry as the page showed it. When the entry was changed in the meantime (a
  colleague returned it and the student sent it again, say), the action is
  refused with "The entry was changed in the meantime. Nothing was done: check
  it again."
* *No number in a remark or a reference.* A remark or a payment reference that
  holds the account or Aadhaar number of the entry is refused, because both
  are mailed and shown to the student. The check reads the digits alone:
  whatever stands between groups of digits (spaces, hyphens, dots, slashes,
  commas, underscores or any other mark) is taken out first, as statements
  and passbooks print long numbers, while letters keep two numbers apart, and
  the number counts with and without its zeros in front. The reference of a
  payment list is checked against every entry of that list, also against
  those that are left out when the list is paid.

Entries of students who are no longer in the selected list (withdrawn, or a
selection that was run again) are not approved, put in a payment list or paid
any more. An entry that was paid before the student left the list stays paid:
it is counted, it stays in the exports of paid entries, its page says so, and
the student still sees the payment.

**How the staff pay: payment lists.** A download of *Approved, not yet paid*
(the `due` export) that has rows makes a numbered payment list (table
`stipend_batches`: which entries went into the file and in which version, the
amount per student at that moment, who made it and when). It is the download
that makes the list: a HEAD request, with which a download manager asks for
the headers of the file, makes none, and an export without rows makes none.
The number stands in the name of the file
(`KTS5-stipend-due-list<N>-<date>.xlsx`) and in the audit row `bank_exported`.
The stipend page shows the lists that are not settled yet as a small table:
number, made on, by whom, rows, amount, and *Excel* and *CSV* to download the
list again (`/console/stipend/list/<N>.xlsx` or `.csv`): the same entries in
the order of the list, as they are now and at the amount the list went out
with, without the Aadhaar column and with a last column *Changed since the
list* that says *yes* where an entry was changed after the list went out
(returned, sent again, approved again, paid one by one) and *no longer
selected* where the student left the list, an audit row `bank_exported` with
the number of the list, and no new list. A second download of the export, on
the other hand, makes a list of its own: to have the file again, download the
list, not the export. The staff send the file to the bank; when the bank has
made the transfers, *Mark a payment list as paid* on the stipend page (the
list, one reference and one date) marks the entries of that list as paid:
only those that are unchanged since the export (still approved, in the same
version), at the amount recorded with the list, whatever the setting says by
then; that amount is mailed to each of them, and the page says how many were
left out. The select offers every list that is not settled, newest first,
however many downloads came after it, each with its number, date and time,
rows and amount per student, and none is chosen in advance: pick the number
that stands in the name of the file the bank received. The list is then
settled, once: when two staff mark the same list at the same moment, the
second is told "Payment list N was marked as paid a moment ago by somebody
else. Nothing was done." (or "was discarded a moment ago") and no entry is
touched. Nothing else can be marked paid in bulk: an entry approved after the
export waits for the next list, a returned entry goes into a later list once
it is approved again, an entry paid one by one is left out, and a paid entry
never enters a list again. A list that did not go to the bank (a look at the
due list, a download made twice) is **discarded** with the button beside the
select, after a question: the list is settled with the reference `discarded`
and nothing marked paid, an audit row `bank_list_discarded` is written, and
its entries no longer name that list and go into the next one. An entry that
stands in a list that is not settled yet (approved, or paid one by one since)
is shown with the number of that list on its page; returning it needs the
ticked confirmation that the bank has not paid this entry from payment list
no. N, and so does the undo of a payment made one by one while the entry
stands in such a list: the audit row says so in both cases, and after the
undo the entry still names its list, because the file at the bank holds its
account. The mails of a payment list are queued in the outbox and sent by a
thread of their own.

Two limits are known and left as they are. The version of an entry in a list
is the second in which it was last changed: an entry returned, sent again
with another account and approved again within the same second as the
approval that went into the list would still count as unchanged. Two members
of staff and a student cannot do that by hand; a script could, and the audit
rows would show it. And, as said above, the same digits at another bank count
as one account.

**The exports** (`/console/stipend/export.xlsx` or `.csv`, with
`?which=due`, `paid`, `all` or `none`): *due* (the default) is approved and
not yet paid, of students in the selected list, and its download makes a
payment list when it has rows; *paid* is the paid entries, also those of
students who have since left the list; *all* is both; *none* is the selected
students who have not submitted, with e-mail and mobile and no bank column,
for a reminder. Never an entry that has not been approved. Columns: serial
number, application number, name, account holder, account number, IFSC, bank,
branch, account type, amount, college, State, e-mail, mobile, status, payment
reference, payment date, approved by, approved on, and the Aadhaar number, as
the last column, only when *Include Aadhaar numbers* is ticked; a payment
list downloaded again has *Changed since the list* there instead, and never
the Aadhaar column. The amount of
a paid row is the amount that was paid (kept with the entry as
`paid_amount`: for a payment list the amount of that list, for an entry
marked as paid one by one the amount of the list it stands in while that
list is not settled, else the setting of the day); a row still to pay shows the setting, which the payment list
then records. An entry whose numbers cannot be read with the key in use is
left out, with a message that names it and `left_out` in the audit row; the
rest of the list is exported all the same. The audit row `bank_exported`
holds the number of rows, the total, what was chosen and, for a payment
list, its number, also when the list is downloaded again; the sheet holds
data rows only, so that an upload at the bank takes nothing else for a payee.
In the Excel file the account numbers are text cells in the format Text: the
zeros in front stay and no digit is lost. A CSV file cannot say that a column
is text; the account and Aadhaar numbers are written there as
`="000123456789"`, which Excel shows as the text `000123456789`. Opened in
another program, the cell shows the characters `="…"` around the number. Use
the Excel file for the bank. A cell that a student typed and that begins with
`=`, `+`, `-` or `@` gets an apostrophe in front in the CSV file, so that no
spreadsheet takes it for a formula.

**What is stored and how.** Table `bank_details`, one row per application,
with the amount paid (`paid_amount`) once the entry is paid; table
`stipend_batches`, one row per payment list (the entries and their versions,
the number of rows, the amount per student when the list went out, who made
it and when, and the reference, date and time of its settlement, or
`discarded`). The account number and the Aadhaar number are sealed
(`kts/secure.py`, standard library only: HMAC-SHA256 key stream with a random
16-byte nonce and an HMAC-SHA256 tag that is checked before anything is
opened); in plain text stand the last four digits of each. A keyed look-up
value of the account number (zeros in front left out) finds one account given
twice without reading the numbers. Full numbers are shown only on the page of
one entry and in the export, to superadmin and admin, and each time a row is
written to the audit log (`bank_viewed`, `bank_exported`, `bank_proof_opened`
when the proof is opened). The rows `bank_*` of the audit log are shown on
the application page and on the dashboard to users with the permission only.
No full number goes into the audit log, a log line, a message, a mail or an
address. The proofs lie in `uploads/bankproofs/` and are served only through
`/console/files/bankproofs/<file>` to the same two roles, only under the
exact name that an entry holds and always whole (no partial requests), so
that every opening is one row `bank_proof_opened`.

**The key: `instance/stipend.key`.** 64 random bytes, made by the portal the
first time a number is sealed: written whole under a name of its own and only
then named `stipend.key`, so that no half-written key file ever exists, and
never over a file that is there. Instead of the file, the setting
`KTS_STIPEND_KEY` (128 hex digits, in the environment or in
`instance/portal.env`) may hold the key: before the first entry, or the key
in use written as the 128 hex digits of its 64 bytes. **The key is bound to
the stored entries.** Before a number is sealed, the portal checks that the
key in use opens the entry stored last or, when that one fails, one of the
three stored before it (an entry that is being sent again does not count: what
is sealed now takes its place); the key counts as wrong only when every entry
tried fails, so that one damaged entry does not close the form for everybody
(the staff clear it by returning that entry). When a single entry stands in the
way, nothing tells a damaged entry from another key: the log then names the
application number of that entry instead of blaming the key, and says to
return it to the student if the key is the right one. When the key is wrong
(the file is missing or
damaged, the setting names another key, a key file of another installation
was put in its place), the portal makes no new key and seals nothing: the
form answers HTTP 503 with "Your details cannot be saved at the moment",
nothing is stored, the uploaded proof is not kept, and the log names the file
and the setting to put back. The entries stored before show on the console
as unreadable, cannot be approved or paid, and are left out of the exports.
To recover, put the old key back: the file from the backup, or remove or
correct the setting. **The database and this key belong together in every
backup: without the key the numbers cannot be read, by anybody.** The file
lies in `instance/`, which is never served (the `web.config` of the site
hides the folder, and the installer gives the folder a `web.config` of its
own that serves nothing), never committed (`.gitignore`) and never touched by
the installer's update; the safety copy of the database that the installer
keeps at each update (`kts5-setup\before-<date>`) holds no key.

**Settings** (*Settings → Stipend*): `stipend.open` (the form is open; `0`
when the portal is installed), `stipend.last_date` (optional, `YYYY-MM-DD`),
`stipend.amount` (`10000`; a payment list records the amount of the day it
went out and is paid at that amount), `stipend.aadhaar` (`1`: ask for the
Aadhaar number; `0` switches the question and its consent line off, and an
entry that is sent again afterwards drops the number it had; numbers given
before are kept and shown as before).

**Languages.** The texts of the form are the keys `bank.*` of
`data/i18n/en.json`, translated into the 22 other interface languages (each
translation read by a second reader); `tools/check_i18n.py` reports no
missing key.

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
| `KTS_STIPEND_KEY` | a key made at first need, kept in `instance/stipend.key` | 128 hex digits: the key that seals the account and Aadhaar numbers of the stipend module. Once entries exist it must be the key of `instance/stipend.key` written as hex, or unset: under any other key the portal accepts no entry (see *Stipend*). Kept with every backup of the database |
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
per application plus the photo and ID upload. Copy `instance/stipend.key` with
the database, every time: without it the bank account and Aadhaar numbers of
the stipend cannot be read again. The safety copy that
`deploy\plesk\kts-install.bat` keeps at each update holds the database, not
the key.

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
* Bank account and Aadhaar numbers of the stipend are sealed in the database
  and shown in full to superadmin and admin only, each time with a row in the
  audit log (see *Stipend*).

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

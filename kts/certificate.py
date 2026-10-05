"""
Certificates signed by the Director of CICT: of recognition, for every student who registers,
and of merit, for the students of the published merit list, selected or waitlisted; and the
letter that confirms the selection of a selected student (/letter/<application number>/<seal>).

A certificate is a page of the portal, laid out as an A4 sheet (landscape) that the student
prints or saves as PDF: /certificate/<application number>/<seal> and
/certificate/merit/<application number>/<seal>. The seal is a keyed digest of the kind and the
number, so nobody reaches the certificate of another student by changing the number in the
address, nor a certificate of merit from the address of one of recognition. The QR code on the
sheet opens that same page on the portal: the page itself is the proof that it is genuine.

The student delegates who attend the inauguration of KTS 5.0 online receive a certificate of
participation, /certificate/inaugural/<application number>/<seal>, once their attendance is
recorded: by the student, with the code announced during the live stream (setting inaug.code),
on the candidate portal, or by staff in the console from a list of application numbers.

Who signs: the head of the institute in the settings (director.name, director.designation). The
image of the signature is uploaded by an administrator in the console and kept in the instance
folder, which the web server never serves; it is written into the page itself.
"""
import base64
import hashlib
import hmac
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, url_for

from .admin import bp as console
from .auth import candidate_required, current_user, login_required
from .candidate import bp as candidate
from .db import all_settings, audit, execute, query, set_setting, utcnow
from .i18n import t
from .public import bp as public
from .utils import client_ip, csv_bytes, fmt_date, limiter, now_ist, qr_data_uri, to_ist

# applications that receive no certificate
NOT_ISSUED = ("rejected", "withdrawn")
SIGNATURE_NAME = "certificate-signature"
SIGNATURE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
SIGNATURE_MAX_BYTES = 1024 * 1024
ORGANISER = "Central Institute of Classical Tamil, Chennai"
AUTONOMOUS = "An autonomous Institution under the Ministry of Education, Government of India"
# the students of the merit list who receive a certificate of merit
MERIT_OUTCOMES = ("selected", "waitlisted")
# the two kinds: the code in the number of a certificate, and what its seal is made from
KINDS = {"recognition": ("CR", "kts5-certificate"), "merit": ("CM", "kts5-merit"), "letter": ("CL", "kts5-letter"),
         "inaugural": ("CP", "kts5-inaugural")}
# application numbers in a list pasted into the console
APP_NO = re.compile(r"KTS5-\d{4}-\d{6}", re.I)


def _seal(app_no, kind="recognition"):
    key = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(key, f"{KINDS[kind][1]}|{app_no}".encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def issued(app, settings=None):
    """True when this application has a certificate: issuing is on, and it is not rejected or withdrawn."""
    settings = settings if settings is not None else all_settings()
    return settings.get("cert.on") == "1" and bool(app["app_no"]) and app["status"] not in NOT_ISSUED


def certificate_link(app, external=False):
    """
    Address of the certificate of an application, or None when it has none. The full address
    (for the QR code and the mail) is made with the address of the portal, as in the other mails.
    """
    if app is None or not issued(app):
        return None
    if external:
        return f"{current_app.config['BASE_URL'].rstrip('/')}/certificate/{app['app_no']}/{_seal(app['app_no'])}"
    return url_for("public.certificate", app_no=app["app_no"], seal=_seal(app["app_no"]))


def merit_issued(app, settings=None):
    """
    True when this application has a certificate of merit: issuing is on, the merit list is
    published and the student stands in it, selected or waitlisted (and not withdrawn since).
    """
    settings = settings if settings is not None else all_settings()
    return (settings.get("cert.merit_on") == "1" and settings.get("merit.published") == "1"
            and bool(app["app_no"]) and app["status"] in MERIT_OUTCOMES)


def merit_link(app, external=False):
    """Address of the certificate of merit of an application, or None when it has none."""
    if app is None or not merit_issued(app):
        return None
    seal = _seal(app["app_no"], "merit")
    if external:
        return f"{current_app.config['BASE_URL'].rstrip('/')}/certificate/merit/{app['app_no']}/{seal}"
    return url_for("public.merit_certificate", app_no=app["app_no"], seal=seal)


def letter_issued(app, settings=None):
    """
    True when this application has a confirmation letter: issuing is on, the merit list is
    published and the student is selected in it (a waitlisted student receives one when moved up).
    """
    settings = settings if settings is not None else all_settings()
    return (settings.get("letter.on") == "1" and settings.get("merit.published") == "1"
            and bool(app["app_no"]) and app["status"] == "selected")


def letter_link(app, external=False):
    """Address of the confirmation letter of an application, or None when it has none."""
    if app is None or not letter_issued(app):
        return None
    seal = _seal(app["app_no"], "letter")
    if external:
        return f"{current_app.config['BASE_URL'].rstrip('/')}/letter/{app['app_no']}/{seal}"
    return url_for("public.confirmation_letter", app_no=app["app_no"], seal=seal)


def _delegate(app, settings):
    """A student delegate: selected in the published merit list."""
    return settings.get("merit.published") == "1" and bool(app["app_no"]) and app["status"] == "selected"


def attendance(app):
    """The recorded attendance of an application at the inauguration, or None."""
    return query("SELECT * FROM inaug_attendance WHERE application_id = ?", (app["id"],), one=True)


def inaug_issued(app, settings=None):
    """
    True when this application has a certificate of participation: issuing is on, the student is a
    delegate (selected in the published merit list) and the attendance at the inauguration is recorded.
    """
    settings = settings if settings is not None else all_settings()
    return settings.get("cert.inaug_on") == "1" and _delegate(app, settings) and attendance(app) is not None


def inaug_link(app, external=False):
    """Address of the certificate of participation of an application, or None when it has none."""
    if app is None or not inaug_issued(app):
        return None
    seal = _seal(app["app_no"], "inaugural")
    if external:
        return f"{current_app.config['BASE_URL'].rstrip('/')}/certificate/inaugural/{app['app_no']}/{seal}"
    return url_for("public.inaugural_certificate", app_no=app["app_no"], seal=seal)


def _plain_code(value):
    return "".join((value or "").split()).casefold()


def inaug_open(settings):
    """The students may record their attendance: a code is set and the day of the inauguration has come."""
    start = (settings.get("kts.start") or "")[:10]
    return bool(_plain_code(settings.get("inaug.code"))) and bool(start) and now_ist().date().isoformat() >= start


def inaug_state(app, settings):
    """What the card of the inauguration shows a delegate; None for any other student."""
    if not _delegate(app, settings):
        return None
    return {"date": settings.get("kts.start") or "", "link": (settings.get("inaug.link") or "").strip(),
            "attended": attendance(app) is not None, "open": inaug_open(settings), "certificate": inaug_link(app)}


def number_of(app_no, kind="recognition"):
    """KTS5-2026-000123 -> KTS5/CR/2026/000123 (recognition) or KTS5/CM/2026/000123 (merit)."""
    parts = app_no.split("-")
    return "/".join([parts[0], KINDS[kind][0]] + parts[1:]) if len(parts) == 3 else app_no


def _signature_file():
    folder = Path(current_app.config["INSTANCE_DIR"])
    for ext in SIGNATURE_TYPES:
        path = folder / f"{SIGNATURE_NAME}.{ext}"
        if path.is_file():
            return path
    return None


def signature_data():
    """The uploaded signature as a data URI, or '' when none was uploaded."""
    path = _signature_file()
    if path is None:
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return f"data:{SIGNATURE_TYPES[path.suffix[1:].lower()]};base64,{base64.b64encode(data).decode('ascii')}"


def _long_date(value):
    """2026-11-28 -> 28 November 2026; '' when the setting is empty or cannot be read."""
    try:
        return datetime.fromisoformat((value or "")[:10]).strftime("%d %B %Y")
    except ValueError:
        return ""


def _sheet(name, college, place, number, issued_on, link, kind="recognition", rank=None, waitlisted=False):
    """The certificate page for these details."""
    settings = all_settings()
    selected = str(settings.get("merit.select_count") or "").strip()
    return render_template(
        "public/certificate.html", name=name, college=college, place=place, number=number, issued_on=issued_on,
        kind=kind, rank=rank, waitlisted=waitlisted, test_date=_long_date(settings.get("exam.date")),
        selected="{:,}".format(int(selected)) if selected.isdigit() and int(selected) > 0 else "",
        kts_start=_long_date(settings.get("kts.start")), kts_end=_long_date(settings.get("kts.end")),
        qr=qr_data_uri(link), link=link, host=urlsplit(link).netloc, signature=signature_data(),
        signatory=(settings.get("director.name") or "").strip(),
        designation=(settings.get("director.designation") or "").strip(), organiser=ORGANISER, autonomous=AUTONOMOUS)


@public.route("/certificate/<app_no>/<seal>")
def certificate(app_no, seal):
    app = query("SELECT * FROM applications WHERE app_no = ?", (app_no,), one=True)
    if app is None or not hmac.compare_digest(seal, _seal(app_no)) or not issued(app):
        abort(404)
    response = current_app.make_response(_sheet(
        app["full_name"], app["college_name"], app["college_state"] or app["state"], number_of(app_no),
        fmt_date(to_ist(app["created_at"])), certificate_link(app, external=True)))
    # a page with the name of a student: kept out of search engines and shared caches
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@public.route("/certificate/merit/<app_no>/<seal>")
def merit_certificate(app_no, seal):
    app = query("SELECT * FROM applications WHERE app_no = ?", (app_no,), one=True)
    if app is None or not hmac.compare_digest(seal, _seal(app_no, "merit")) or not merit_issued(app):
        abort(404)
    entry = query("SELECT * FROM merit_list WHERE application_id = ? ORDER BY id DESC LIMIT 1", (app["id"],), one=True)
    # issued on the day of the selection that put the student in the list
    issued_on = fmt_date(to_ist(entry["created_at"])) if entry else fmt_date(now_ist())
    response = current_app.make_response(_sheet(
        app["full_name"], app["college_name"], app["college_state"] or app["state"], number_of(app_no, "merit"),
        issued_on, merit_link(app, external=True), kind="merit", rank=(entry["rank"] if entry else app["exam_rank"]),
        waitlisted=app["status"] == "waitlisted"))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@public.route("/certificate/inaugural/<app_no>/<seal>")
def inaugural_certificate(app_no, seal):
    app = query("SELECT * FROM applications WHERE app_no = ?", (app_no,), one=True)
    if app is None or not hmac.compare_digest(seal, _seal(app_no, "inaugural")) or not inaug_issued(app):
        abort(404)
    # issued on the day the attendance was recorded
    issued_on = fmt_date(to_ist(attendance(app)["marked_at"]))
    response = current_app.make_response(_sheet(
        app["full_name"], app["college_name"], app["college_state"] or app["state"], number_of(app_no, "inaugural"),
        issued_on, inaug_link(app, external=True), kind="inaugural"))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@candidate.route("/inauguration", methods=["POST"])
@candidate_required
def record_attendance():
    """A delegate records the attendance at the inauguration with the code announced during the live stream."""
    cand = g.candidate
    settings = all_settings()
    if not _delegate(cand, settings) or not inaug_open(settings):
        flash(t("inaug.later"), "warning")
    elif attendance(cand) is None:
        key = str(cand["id"])
        if limiter.blocked("inaug_code", key, 10, 15 * 60):
            flash(t("reg.err_rate"), "error")
        elif _plain_code(request.form.get("code")) != _plain_code(settings.get("inaug.code")):
            limiter.hit("inaug_code", key, 15 * 60)
            flash(t("inaug.wrong"), "error")
        else:
            execute("INSERT OR IGNORE INTO inaug_attendance(application_id, via, marked_at) VALUES(?, 'code', ?)",
                    (cand["id"], utcnow()))
            audit("inaug_attendance", "application", cand["id"], detail="code", ip=client_ip())
            flash(t("inaug.recorded"), "success")
    return redirect(url_for("candidate.home") + "#inaug-card")


def _letter(app, rank, link):
    """The confirmation letter of an application (or of the invented student of the sample)."""
    from . import kural as K
    settings = all_settings()
    selected = str(settings.get("merit.select_count") or "").strip()
    mentor = (app["mentor_name"] or "").strip()
    if mentor and (app["mentor_designation"] or "").strip():
        mentor = f"{mentor}, {app['mentor_designation'].strip()}"
    info = K.lang_info(app["pref_lang"]) if app["pref_lang"] else None
    return render_template(
        "public/letter.html", name=app["full_name"], college=app["college_name"], place=app["college_state"] or app["state"],
        app_no=app["app_no"], number="/".join(["CICT"] + number_of(app["app_no"], "letter").split("/")),
        letter_date=_long_date(settings.get("letter.date")) or fmt_date(now_ist()), rank=rank,
        selected="{:,}".format(int(selected)) if selected.isdigit() and int(selected) > 0 else "",
        test_date=_long_date(settings.get("exam.date")), internship_start=_long_date(settings.get("internship.start")),
        papers_due=_long_date(settings.get("papers.due")), present_due=_long_date(settings.get("present.due")),
        stipend_last=_long_date(settings.get("stipend.last_date")),
        kts_start=_long_date(settings.get("kts.start")), kts_end=_long_date(settings.get("kts.end")),
        mentor=mentor, lang_name=info["name"] if info else "",
        qr=qr_data_uri(link), link=link, host=urlsplit(link).netloc, signature=signature_data(),
        signatory=(settings.get("director.name") or "").strip(),
        designation=(settings.get("director.designation") or "").strip(), organiser=ORGANISER, autonomous=AUTONOMOUS,
        address=(settings.get("contact.address") or "").strip(), email=(settings.get("contact.email") or "").strip(),
        phone=(settings.get("contact.phone") or "").strip())


@public.route("/letter/<app_no>/<seal>")
def confirmation_letter(app_no, seal):
    app = query("SELECT * FROM applications WHERE app_no = ?", (app_no,), one=True)
    if app is None or not hmac.compare_digest(seal, _seal(app_no, "letter")) or not letter_issued(app):
        abort(404)
    entry = query("SELECT rank FROM merit_list WHERE application_id = ? ORDER BY id DESC LIMIT 1", (app["id"],), one=True)
    response = current_app.make_response(_letter(app, entry["rank"] if entry else app["exam_rank"],
                                                 letter_link(app, external=True)))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ---- console ------------------------------------------------------------------

@console.route("/certificate", methods=["GET", "POST"])
@login_required("settings")
def certificate_settings():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action")
        folder = Path(current_app.config["INSTANCE_DIR"])
        if action in ("on", "off"):
            set_setting("cert.on", "1" if action == "on" else "0")
            audit("certificate_" + action, "settings", None, user=user, ip=client_ip())
            flash("Certificates of recognition are issued." if action == "on"
                  else "Certificates of recognition are no longer issued.", "success")
        elif action in ("letter_on", "letter_off"):
            set_setting("letter.on", "1" if action == "letter_on" else "0")
            audit("certificate_" + action, "settings", None, user=user, ip=client_ip())
            flash("Confirmation letters are issued." if action == "letter_on"
                  else "Confirmation letters are no longer issued.", "success")
        elif action in ("merit_on", "merit_off"):
            set_setting("cert.merit_on", "1" if action == "merit_on" else "0")
            audit("certificate_" + action, "settings", None, user=user, ip=client_ip())
            flash("Certificates of merit are issued." if action == "merit_on"
                  else "Certificates of merit are no longer issued.", "success")
        elif action in ("inaug_on", "inaug_off"):
            set_setting("cert.inaug_on", "1" if action == "inaug_on" else "0")
            audit("certificate_" + action, "settings", None, user=user, ip=client_ip())
            flash("Certificates of participation are issued." if action == "inaug_on"
                  else "Certificates of participation are no longer issued.", "success")
        elif action in ("inaug_mark", "inaug_unmark"):
            numbers = list(dict.fromkeys(n.upper() for n in APP_NO.findall(request.form.get("numbers") or "")))
            done, skipped = [], []
            for number in numbers:
                row = query("SELECT id, status FROM applications WHERE app_no = ?", (number,), one=True)
                if action == "inaug_unmark":
                    if row is not None and query("SELECT 1 FROM inaug_attendance WHERE application_id = ?", (row["id"],), one=True):
                        execute("DELETE FROM inaug_attendance WHERE application_id = ?", (row["id"],))
                        done.append(number)
                    else:
                        skipped.append(number)
                elif row is None or row["status"] != "selected":
                    skipped.append(number)
                else:
                    execute("INSERT OR IGNORE INTO inaug_attendance(application_id, via, marked_at, marked_by) VALUES(?, 'staff', ?, ?)",
                            (row["id"], utcnow(), user["id"]))
                    done.append(number)
            audit("inaug_attendance_" + ("removed" if action == "inaug_unmark" else "recorded"), "application", None,
                  detail={"numbers": done}, user=user, ip=client_ip())
            if not numbers:
                flash("No application number (KTS5-2026-000123) was found in the list.", "error")
            else:
                verb = "removed" if action == "inaug_unmark" else "recorded"
                flash(f"Attendance {verb} for {len(done)} application(s)."
                      + (f" Left out, not {'recorded' if action == 'inaug_unmark' else 'a selected delegate'} or unknown: "
                         + ", ".join(skipped[:20]) + (" …" if len(skipped) > 20 else "") if skipped else ""),
                      "success" if done else "warning")
        elif action == "signature":
            upload = request.files.get("signature")
            name = (upload.filename or "") if upload else ""
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            data = upload.read(SIGNATURE_MAX_BYTES + 1) if upload else b""
            good = (data[:8] == b"\x89PNG\r\n\x1a\n") if ext == "png" else (data[:3] == b"\xff\xd8\xff")
            if ext not in SIGNATURE_TYPES or not data or not good:
                flash("Choose a PNG or JPG image of the signature.", "error")
            elif len(data) > SIGNATURE_MAX_BYTES:
                flash("The image is larger than 1 MB.", "error")
            else:
                folder.mkdir(parents=True, exist_ok=True)
                for old in SIGNATURE_TYPES:
                    (folder / f"{SIGNATURE_NAME}.{old}").unlink(missing_ok=True)
                (folder / f"{SIGNATURE_NAME}.{'jpg' if ext == 'jpeg' else ext}").write_bytes(data)
                audit("certificate_signature_set", "settings", None, detail=f"{len(data)} bytes", user=user, ip=client_ip())
                flash("The signature is on every certificate now.", "success")
        elif action == "remove":
            for old in SIGNATURE_TYPES:
                (folder / f"{SIGNATURE_NAME}.{old}").unlink(missing_ok=True)
            audit("certificate_signature_removed", "settings", None, user=user, ip=client_ip())
            flash("The signature was removed.", "warning")
        return redirect(url_for("admin.certificate_settings"))
    settings = all_settings()
    counts = query("SELECT COUNT(*) AS n FROM applications WHERE status NOT IN ('rejected', 'withdrawn')", one=True)
    selected = query("SELECT COUNT(*) AS n FROM applications WHERE status IN ('selected', 'waitlisted')", one=True)
    return render_template("console/certificate.html", on=settings.get("cert.on") == "1", signature=signature_data(),
                           signatory=settings.get("director.name") or "", designation=settings.get("director.designation") or "",
                           count=counts["n"], merit_on=settings.get("cert.merit_on") == "1",
                           published=settings.get("merit.published") == "1", selected=selected["n"],
                           letter_on=settings.get("letter.on") == "1",
                           chosen=query("SELECT COUNT(*) AS n FROM applications WHERE status = 'selected'", one=True)["n"],
                           inaug_on=settings.get("cert.inaug_on") == "1", inaug_open=inaug_open(settings),
                           inaug_code=bool(_plain_code(settings.get("inaug.code"))), inaug_date=settings.get("kts.start") or "",
                           attended=query("SELECT COUNT(*) AS n FROM inaug_attendance a JOIN applications p ON p.id = a.application_id "
                                          "WHERE p.status = 'selected'", one=True)["n"])


def _csv_text(value):
    """A cell as a spreadsheet shows it: never read as a formula."""
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@console.route("/certificate/attendance.csv")
@login_required("settings")
def attendance_csv():
    """The recorded attendance at the inauguration, for the records of the institute."""
    rows = query("SELECT p.app_no, p.full_name, p.college_name, p.college_state, p.state, p.status, a.via, a.marked_at "
                 "FROM inaug_attendance a JOIN applications p ON p.id = a.application_id ORDER BY a.marked_at, p.app_no")
    body = csv_bytes(["Application number", "Name", "College", "State", "Status", "Recorded by", "Recorded at (IST)"],
                     [(r["app_no"], _csv_text(r["full_name"]), _csv_text(r["college_name"]), r["college_state"] or r["state"],
                       r["status"], "student (code)" if r["via"] == "code" else "staff",
                       to_ist(r["marked_at"]).strftime("%d-%m-%Y %H:%M")) for r in rows])
    audit("inaug_attendance_export", "settings", None, detail=f"{len(rows)} rows", user=current_user(), ip=client_ip())
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="kts5-inauguration-attendance.csv"'})


@console.route("/certificate/sample")
@login_required("settings")
def certificate_sample():
    """A certificate as a student receives it (?kind=merit for one of merit), with the details of an invented student."""
    if request.args.get("kind") == "letter":
        sample = {"full_name": "Sample Student Name", "college_name": "Government Arts College, Sample Town",
                  "college_state": "Tamil Nadu", "state": "Tamil Nadu", "app_no": "KTS5-2026-000000", "pref_lang": "hi",
                  "mentor_name": "Dr. A. Sample", "mentor_designation": "Associate Professor of Tamil"}
        response = current_app.make_response(_letter(sample, 1, current_app.config["BASE_URL"].rstrip("/") + "/"))
        response.headers["Cache-Control"] = "private, no-store"
        return response
    kind = request.args.get("kind") if request.args.get("kind") in ("merit", "inaugural") else "recognition"
    response = current_app.make_response(_sheet(
        "Sample Student Name", "Government Arts College, Sample Town", "Tamil Nadu", f"KTS5/{KINDS[kind][0]}/2026/000000",
        fmt_date(now_ist()), current_app.config["BASE_URL"].rstrip("/") + "/", kind=kind, rank=1 if kind == "merit" else None,
        waitlisted=request.args.get("waitlisted") == "1"))
    response.headers["Cache-Control"] = "private, no-store"
    return response

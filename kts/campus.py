"""
The participating institutions' own area, and the online assessment they conduct (version 1.2.43).

The D.O. letter of the Ministry of Education of 9 October 2026 (Annexure-III) puts the assessment
of the students with the participating institutions: each institution conducts a test, or any other
suitable mode of assessment, on the theme of the Thirukkural, selects one student as the winner on
merit, and registers that student's details on the portal. CICT consolidates the selected students.

* The Institutional Coordinator (or the Head of the Institution) signs in at /institution/login
  with the e-mail address given when the institution registered: the portal mails a six-digit
  code, valid for CODE_MINUTES (60 since 1.2.212); signed in on that device for DEVICE_DAYS. No password is kept.
  Since 1.2.216 the code is mailed only while the setting inst.code_mail is on. While it is off, as it is by default (CICT,
  26 November 2026: "i want sign-in codes stopped"), the coordinator or the Head signs in with that e-mail address and the
  mobile number of the coordinator given at registration, and no mail is sent.
* /institution is the institution's page: its status, the steps and dates of the programme, the
  online assessment, the students who took it with their scores, the winner, and the registration
  of the winner.
* The online assessment: the coordinator switches it on, chooses the days (within camp.from and
  camp.to) and gives the students the link /assessment/<slug> and the access code. A student signs
  up (name, roll number, e-mail, mobile, language), takes the paper of exam.questions questions in
  exam.duration_min minutes once, as the candidates' test of earlier versions did (the same question
  bank, in the language chosen, the same page and the same scoring), and sees the result when
  camp.show_score is on. The coordinator sees every student, ranked by score and time.
* The winner: the coordinator selects a student of the list, or enters one assessed in another way.
  The coordinator, signed in, submits the nomination with the link of the institution, the only way to
  /register since 1.2.182 (no student fills in the form); the institution of the application is fixed by it, and
  the score of the online assessment goes with the application (exam_sessions), so that the status
  page, the selection and the merit list work as before.
"""
import hashlib
import hmac
import json
import random
import re
import secrets
import sqlite3
from datetime import date, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

from . import kural as K
from .candidate import _build_paper, _load_paper
from .db import all_settings, audit, execute, get_db, get_setting, query, utcnow
from .i18n import dates_public, t
from .utils import (INST_CODE_SUBJECT, check_captcha, client_ip, inst_code_mail, limiter, new_captcha, now_ist, parse_iso,
                    plain_english, send_mail, valid_email, valid_mobile, xlsx_bytes)

bp = Blueprint("campus", __name__)

# 60 minutes since 1.2.212 (CICT, 24 November 2026: the codes come late when the mail of the portal reaches Google's limit)
CODE_MINUTES = 60
# a coordinator who signs in with the code stays signed in on that device so many days (1.2.212): the cookie DEVICE_COOKIE
DEVICE_DAYS = 30
DEVICE_COOKIE = "kts_inst"
CODE_TRIES = 5
LOGIN_PER_HOUR = 12          # codes asked for from one address in an hour
MOBILE_TRIES = 20            # sign-ins without a code that fail, from one address of the network in an hour (1.2.216)
MOBILE_ERROR = ("The e-mail address and the mobile number do not match the registration of an institution. Enter the e-mail address "
                "of the Institutional Coordinator or of the Head of the Institution, and the mobile number of the Institutional "
                "Coordinator, as given when the institution registered.")
MOBILE_WAIT = ("Too many tries from this connection in the last hour. Please try again after an hour, or write to CICT with the name "
               "and the reference number of the institution.")
MOBILE_ASKED = ("No code is mailed any more. Enter the mobile number of the Institutional Coordinator as well, as given when the "
                "institution registered.")
SIGNUP_PER_HOUR = 60         # sign-ups of students from one address in an hour
RANK_SQL = "ORDER BY CASE WHEN t.status IN ('submitted', 'expired') THEN 0 ELSE 1 END, t.score DESC, t.time_taken_sec ASC, s.id ASC"


# ---- the institution and its coordinator ------------------------------------------------------------------

def _email_matches(inst, email):
    return email and email in (inst["coord_email"], inst["head_email"])


def institutions_of(email):
    """The institutions whose coordinator or head has this e-mail address, the accepted first."""
    return query("SELECT * FROM institutions WHERE (coord_email = ? OR head_email = ?) AND status != 'declined' "
                 "ORDER BY CASE status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, id", (email, email))


def _ten_digits(value):
    """
    A phone number of India as ten digits 0-9, or '' when it is none: with +91, 0091 or a 0 before it, with spaces and hyphens in
    it, and also when it is typed with the digits of an Indian script, as a keyboard of Hindi, Bengali or Tamil gives them (1.2.216).
    """
    import unicodedata
    digits = re.sub(r"\D", "", "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in value or ""))
    for prefix in ("0091", "910", "091", "91", "0"):
        if len(digits) == 10 + len(prefix) and digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    return digits if len(digits) == 10 and digits[0] != "0" else ""


def _coordinator_numbers(inst):
    """
    The mobile numbers of the Institutional Coordinator of this institution, each as ten digits: the field as it is, and its parts
    where it holds more than one number, as a correction in the Console may have left it ("98765 43210 / 91234 56780") (1.2.216).
    """
    value = inst["coord_mobile"] or ""
    numbers = []
    for part in [value] + re.split(r"[,;/|]|\bor\b", value):
        number = _ten_digits(part)
        if number and number not in numbers:
            numbers.append(number)
    return numbers


def _number_mark(number):
    """
    A keyed mark of a mobile number of ten digits, for the session and the cookie of the device: they carry the mark, never the
    number (1.2.216).
    """
    key = current_app.config["SECRET_KEY"]
    key = key.encode("utf-8") if isinstance(key, str) else key
    return hmac.new(key, b"kts-institution-mobile|" + number.encode("ascii"), hashlib.sha256).hexdigest()[:32]


def _opens(inst, email, mark=None):
    """
    This sign-in opens this institution: the address is that of its coordinator or of its Head, and it is not declined; and, for a
    sign-in with the mobile number (1.2.216: the mark of the number that was proved), that number is its coordinator's. So an
    address alone opens no other institution that carries it - anybody can register an institution with somebody else's address,
    and until 1.2.215 the code went to the mailbox of that address. A sign-in with the mailed code has no mark. A number corrected
    in the Console ends the sign-ins made with the old one.
    """
    if inst is None or not _email_matches(inst, email) or inst["status"] == "declined":
        return False
    if mark:
        return any(hmac.compare_digest(_number_mark(number).encode("ascii"), str(mark).encode("utf-8"))
                   for number in _coordinator_numbers(inst))
    return True


def _device_signer():
    """The signer of the cookie of the device (1.2.212): the key of the portal, a salt of its own."""
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="kts-institution-device")


def _device_sign_in():
    """
    The sign-in of the device (1.2.212): the address and the institution of a valid cookie of the device, not older than DEVICE_DAYS,
    put back in the session of the portal; nothing for a cookie that cannot be read.
    """
    from itsdangerous import BadSignature
    value = request.cookies.get(DEVICE_COOKIE)
    if not value:
        return
    try:
        data = _device_signer().loads(value, max_age=DEVICE_DAYS * 24 * 3600)
        email, iid = str(data["e"]), int(data["i"])
        mark = str(data["m"]) if data.get("m") else None      # the cookie of a sign-in with the mobile number (1.2.216)
    except (BadSignature, KeyError, TypeError, ValueError, AttributeError):
        return
    session["inst_email"], session["inst_id"] = email, iid
    if mark:
        session["inst_m"] = mark
    else:
        session.pop("inst_m", None)
    session.permanent = True


def current_institution():
    """The institution signed in, or None; with the cookie of the device when the session is over (1.2.212)."""
    if "inst" in g:
        return g.inst
    inst = None
    from flask import has_request_context
    if not (session.get("inst_id") and session.get("inst_email")) and has_request_context():
        _device_sign_in()
    iid, email = session.get("inst_id"), session.get("inst_email")
    if iid and email:
        inst = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
        if not _opens(inst, email, session.get("inst_m")):      # with the number that was proved, where there is one (1.2.216)
            inst = None
    g.inst = inst
    return inst


def _code_hash(email, code):
    return hashlib.sha256(f"{email}|{code}|{current_app.config['SECRET_KEY']}".encode("utf-8")).hexdigest()


def _signed_in(email, iid, by="", number=""):
    """
    The institution is signed in, after the mailed code or (1.2.216) the mobile number: the session of the portal, and the cookie of
    the device for DEVICE_DAYS days (1.2.212). A sign-in with the mobile number carries the mark of that number, in the session and
    in the cookie: it opens the institutions of that number only (_opens).
    """
    session.pop("inst_login", None)
    session.pop("uid", None)
    session["inst_email"] = email
    session["inst_id"] = iid
    device = {"e": email, "i": iid}
    if number:
        session["inst_m"] = device["m"] = _number_mark(number)
    else:
        session.pop("inst_m", None)
    session.permanent = True
    audit("institution_login", "institution", iid, detail=f"{email} ({by})" if by else email, ip=client_ip())
    response = redirect(url_for("campus.home"))
    # signed in on this device for DEVICE_DAYS days (1.2.212): no new sign-in each day
    response.set_cookie(DEVICE_COOKIE, _device_signer().dumps(device),
                        max_age=DEVICE_DAYS * 24 * 3600, httponly=True, samesite="Lax", path="/",
                        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return response


def _mobile_matches(inst, typed):
    """The number typed, as ten digits, is a mobile number of the Institutional Coordinator of this institution (1.2.216)."""
    return bool(typed) and any(hmac.compare_digest(number.encode("ascii"), typed.encode("ascii"))
                               for number in _coordinator_numbers(inst))


def _login_by_mobile(email, ip):
    """
    The sign-in without a mail (1.2.216; CICT, 26 November 2026: "i want sign-in codes stopped"): the e-mail address of the
    Institutional Coordinator or of the Head of the Institution, and the mobile number of the coordinator, as the institution gave
    them when it registered. Only the tries that fail count against the address of the network. An e-mail address that belongs to
    no institution is answered as a wrong number is, and noted in the audit log as one: the page does not say which addresses the
    portal knows.
    """
    error, note, status = None, None, 400
    if limiter.blocked("inst_mobile", ip, MOBILE_TRIES, 3600):
        error, status = MOBILE_WAIT, 429
    elif not valid_email(email):
        error = t("reg.err_email")
    elif "mobile" not in request.form:
        # the form of before 1.2.216, still open in a browser, had the address alone: the number is asked for, nothing is counted
        note, status = MOBILE_ASKED, 200
    else:
        typed = _ten_digits(request.form.get("mobile"))
        known = institutions_of(email)
        rows = [r for r in known if _mobile_matches(r, typed)]
        if rows:
            return _signed_in(email, rows[0]["id"], "e-mail address and mobile number", typed)
        limiter.hit("inst_mobile", ip, 3600)
        audit("institution_login_refused", "institution", known[0]["id"] if known else None, detail=email[:160], ip=ip)
        error = MOBILE_ERROR
    return render_template("campus/login.html", error=error, note=note, sent=None, by_code=False, email=email[:160],
                           settings=all_settings()), status


@bp.route("/institution/login", methods=["GET", "POST"])
def login():
    if current_institution():
        return redirect(url_for("campus.home"))
    error = sent = None
    by_code = inst_code_mail()
    if request.method == "POST":
        ip = client_ip()
        email = (request.form.get("email") or "").strip().lower()
        if not by_code:
            return _login_by_mobile(email, ip)      # no code is mailed (1.2.216)
        if limiter.blocked("inst_login", ip, LOGIN_PER_HOUR, 3600):
            error = t("reg.err_rate")
        elif not valid_email(email):
            error = t("reg.err_email")
        else:
            limiter.hit("inst_login", ip, 3600)
            rows = institutions_of(email)
            if rows:
                code = f"{secrets.randbelow(1_000_000):06d}"
                session["inst_login"] = {"email": email, "hash": _code_hash(email, code),
                                         "until": (now_ist() + timedelta(minutes=CODE_MINUTES)).isoformat(), "tries": 0}
                names = "; ".join(r["name"] for r in rows[:3])
                send_mail(email, INST_CODE_SUBJECT,
                          f"Dear Sir/Madam,\n\nYour code to sign in to the institution's page of the KTS 5.0 portal "
                          f"({names}):\n\n    {code}\n\nIt is valid for {CODE_MINUTES} minutes. If you did not ask for it, "
                          f"ignore this mail.\n\nCentral Institute of Classical Tamil, Chennai",
                          urgent=True)      # at once, outside the queue and its limits (1.2.207)
                audit("institution_code_sent", "institution", rows[0]["id"], detail=email, ip=ip)
            # an address that belongs to no institution is answered in the same way: the page does not say which
            # addresses the portal knows
            sent = email
    return render_template("campus/login.html", error=error, sent=sent, by_code=by_code, settings=all_settings())


@bp.route("/institution/code", methods=["POST"])
def code():
    pending = session.get("inst_login") or {}
    typed = (request.form.get("code") or "").strip().replace(" ", "")
    error = None
    if not pending or pending.get("until", "") < now_ist().isoformat():
        error = "The code has expired: ask for a new one."
    elif pending.get("tries", 0) >= CODE_TRIES or limiter.blocked("inst_code", str(pending.get("hash")), CODE_TRIES, CODE_MINUTES * 60):
        error = "Too many wrong codes: ask for a new one."
    elif _code_hash(pending["email"], typed) != pending["hash"]:
        pending["tries"] = pending.get("tries", 0) + 1
        session["inst_login"] = pending
        limiter.hit("inst_code", str(pending.get("hash")), CODE_MINUTES * 60)
        error = "The code is wrong."
    if error:
        if "expired" in error or "Too many" in error:
            session.pop("inst_login", None)
        return render_template("campus/login.html", error=error, sent=pending.get("email") if not error.startswith(("The code has", "Too")) else None,
                               by_code=inst_code_mail(), settings=all_settings()), 400
    rows = institutions_of(pending["email"])
    session.pop("inst_login", None)
    if not rows:
        return render_template("campus/login.html", error="No institution is registered with this e-mail address.", sent=None,
                               by_code=inst_code_mail(), settings=all_settings()), 400
    return _signed_in(pending["email"], rows[0]["id"])


@bp.route("/institution/switch/<int:iid>")
def switch(iid):
    inst = current_institution()
    if inst is None:
        return redirect(url_for("campus.login"))
    other = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
    if not _opens(other, session.get("inst_email"), session.get("inst_m")):
        abort(404)
    session["inst_id"] = other["id"]
    audit("institution_switch", "institution", other["id"], detail=session.get("inst_email") or "", ip=client_ip())
    return redirect(url_for("campus.home"))


@bp.route("/institution/logout", methods=["POST"])
def logout():
    session.pop("inst_id", None)
    session.pop("inst_email", None)
    session.pop("inst_m", None)
    response = redirect(url_for("public.home"))
    # ... and on this device (1.2.212)
    response.delete_cookie(DEVICE_COOKIE, path="/", samesite="Lax", httponly=True,
                           secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return response


def institution_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_institution() is None:
            return redirect(url_for("campus.login"))
        return fn(*args, **kwargs)
    return wrapper


# ---- the online assessment ---------------------------------------------------------------------------------

def _day(value):
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def assessment_period(settings=None):
    """(from, to) of the institution-level assessments, as dates."""
    settings = settings or all_settings()
    return _day(settings.get("camp.from")), _day(settings.get("camp.to"))


def assessment_state(inst, settings=None):
    """'open', 'off' (the institution has not switched it on, or the portal offers none), 'not_yet', 'over' or 'not_accepted'."""
    settings = settings or all_settings()
    if inst["status"] != "accepted":
        return "not_accepted"
    if settings.get("camp.on") != "1" or not inst["test_on"]:
        return "off"
    today = now_ist().date()
    start, end = _day(inst["test_from"]), _day(inst["test_to"])
    if start and today < start:
        return "not_yet"
    if end and today > end:
        return "over"
    return "open"


def _new_slug():
    while True:
        slug = secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]
        if not query("SELECT 1 FROM institutions WHERE test_slug = ?", (slug,), one=True):
            return slug


def _new_code():
    return f"{secrets.randbelow(900_000) + 100_000}"


def students_of(inst):
    return query("SELECT s.*, t.status AS t_status, t.score, t.correct_count, t.time_taken_sec, t.started_at, t.submitted_at "
                 "FROM campus_students s LEFT JOIN campus_attempts t ON t.student_id = s.id WHERE s.institution_id = ? " + RANK_SQL,
                 (inst["id"],))


def _winner(inst):
    if not inst["winner_id"]:
        return None
    return query("SELECT s.*, t.status AS t_status, t.score, t.time_taken_sec FROM campus_students s "
                 "LEFT JOIN campus_attempts t ON t.student_id = s.id WHERE s.id = ?", (inst["winner_id"],), one=True)


@bp.route("/institution")
@institution_required
def home():
    inst = current_institution()
    settings = all_settings()
    # the other institutions that this sign-in opens (1.2.216: with the mobile number, those of that number)
    others = [r for r in institutions_of(session["inst_email"])
              if r["id"] != inst["id"] and _opens(r, session["inst_email"], session.get("inst_m"))]
    winner = _winner(inst)
    application = query("SELECT * FROM applications WHERE id = ?", (inst["application_id"],), one=True) if inst["application_id"] else None
    start, end = assessment_period(settings)
    base = current_app.config["BASE_URL"]
    return render_template("campus/home.html", inst=inst, others=others, settings=settings, students=students_of(inst),
                           winner=winner, application=application, state=assessment_state(inst, settings),
                           period=(start, end), reg_end=_day(settings.get("reg.end")),
                           test_url=f"{base}/assessment/{inst['test_slug']}" if inst["test_slug"] else "",
                           reg_url=f"{base}/register?token={inst['reg_token']}" if inst["reg_token"] and not application else "",
                           presentation=presentation_of(inst),
                           langs=[K.lang_info(c) | {"code": c} for c in K.ORIENTATION_LANGS])


@bp.route("/institution/assessment", methods=["POST"])
@institution_required
def assessment():
    inst = current_institution()
    if inst["status"] != "accepted":
        abort(403)
    action = request.form.get("action")
    settings = all_settings()
    start, end = assessment_period(settings)
    now = utcnow()
    if action == "on":
        a, b = _day(request.form.get("test_from")), _day(request.form.get("test_to"))
        if not a or not b or a > b:
            flash("Choose the first and the last day of the assessment.", "error")
            return redirect(url_for("campus.home"))
        if (start and a < start) or (end and b > end):
            flash(f"The assessment must fall between {start:%d %b %Y} and {end:%d %b %Y}.", "error")
            return redirect(url_for("campus.home"))
        slug = inst["test_slug"] or _new_slug()
        code_ = inst["test_code"] or _new_code()
        # the 108 Thirukkural unless the institution chooses the whole book (the default since 1.2.132)
        syllabus = "all" if request.form.get("syllabus") == "all" else "108"
        execute("UPDATE institutions SET test_on = 1, test_from = ?, test_to = ?, test_slug = ?, test_code = ?, test_syllabus = ?, updated_at = ? "
                "WHERE id = ?", (a.isoformat(), b.isoformat(), slug, code_, syllabus, now, inst["id"]))
        audit("assessment_on", "institution", inst["id"], detail={"from": a.isoformat(), "to": b.isoformat(), "syllabus": syllabus}, ip=client_ip())
        flash("The online assessment is on" + (", on the 108 Thirukkural" if syllabus == "108" else "")
              + ". Give your students the link and the access code shown below.", "success")
    elif action == "off":
        execute("UPDATE institutions SET test_on = 0, updated_at = ? WHERE id = ?", (now, inst["id"]))
        audit("assessment_off", "institution", inst["id"], ip=client_ip())
        flash("The online assessment is off: students cannot sign up or start it.", "success")
    elif action == "newcode":
        execute("UPDATE institutions SET test_code = ?, updated_at = ? WHERE id = ?", (_new_code(), now, inst["id"]))
        audit("assessment_code", "institution", inst["id"], ip=client_ip())
        flash("A new access code is set; the old one no longer opens the assessment.", "success")
    else:
        abort(400)
    return redirect(url_for("campus.home"))


@bp.route("/institution/students.xlsx")
@institution_required
def students_xlsx():
    inst = current_institution()
    rows = students_of(inst)
    headers = ["Rank", "Name", "Roll number", "Course and year", "E-mail", "Mobile", "Language", "Signed up", "Status", "Score",
               "Correct", "Time taken (s)", "Submitted"]
    data = []
    rank = 0
    for s in rows:
        done = s["t_status"] in ("submitted", "expired")
        rank += 1 if done else 0
        data.append((rank if done else "", s["name"], s["roll_no"], s["course"], s["email"], s["mobile"],
                     (K.lang_info(s["lang"]) or {}).get("name", s["lang"]), (s["created_at"] or "")[:16].replace("T", " "),
                     {"submitted": "submitted", "expired": "submitted (time over)", "in_progress": "in progress"}.get(s["t_status"], "not started"),
                     s["score"] if done else "", s["correct_count"] if done else "", s["time_taken_sec"] if done else "",
                     (s["submitted_at"] or "")[:16].replace("T", " ")))
    return Response(xlsx_bytes(headers, data, "Assessment", text_cols=(2, 5)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=KTS5-assessment-{inst['ref']}.xlsx"})


# ---- the winner and the registration link ----------------------------------------------------------------------

def registration_mail(inst, student):
    """
    The selection of the student (1.2.158: the Institutional Coordinator submits the nomination, B-3 of the D.O. letter of 31 October
    2026): the student is informed, without a link; the coordinator is asked to submit the nomination from the institution's page.
    """
    base = current_app.config["BASE_URL"]
    if student["email"]:
        send_mail(student["email"], f"KTS 5.0: you are selected by {inst['name']}",
                  f"Dear {student['name']},\n\n{inst['name']} has selected you, on the basis of its assessment, as its student for "
                  f"Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom.\n\nYour Institutional Coordinator, {inst['coord_name']}, submits "
                  f"your nomination on the KTS 5.0 portal{_on_or_before()}. Give the coordinator a photograph, an ID "
                  f"proof and your details (date of birth, address, course and year of study, language); the nomination form is "
                  f"signed and sealed by the Head of the Institution, with your Faculty Supervisor/Guide.\n\nOnce the nomination is "
                  f"submitted, you receive your application number by e-mail, to follow your application at {base}/status and to "
                  f"sign in to the candidate portal.\n\nCentral Institute of Classical Tamil, Chennai")
    send_mail(inst["coord_email"], f"KTS 5.0: submit the nomination of {student['name']} ({inst['ref']})",
              f"Dear {inst['coord_name']},\n\n{inst['name']} has selected {student['name']} on merit. Submit the nomination on the "
              f"KTS 5.0 portal{_on_or_before()}: sign in to the institution's page, {base}/institution, and press "
              f"\u201cSubmit the nomination\u201d. The form asks for the student's details, a photograph, an ID proof, the nomination "
              f"form signed and sealed by the Head of the Institution ({base}/static/KTS5-nomination-form.pdf) and the details of the "
              f"Faculty Supervisor/Guide.\n\nThe student has been informed by e-mail"
              + (f" ({student['email']})" if student["email"] else "") +
              f".\n\nCentral Institute of Classical Tamil, Chennai")


def _on_or_before():
    """
    " on or before 27 November 2026", the last day of the nomination as a mail gives it; nothing while the last days are kept off
    the mails (1.2.209, dates.public).
    """
    return f" on or before {_reg_end_text()}" if dates_public() else ""


def _reg_end_text():
    end = _day(get_setting("reg.end"))
    if not end:
        return "the date given by CICT"
    from .heis import nominate_hour_words
    return f"{end.day} {end:%B %Y}{nominate_hour_words('en')}"      # with the hour of the nomination (1.2.209)


def _issue(inst, student_id):
    token = secrets.token_urlsafe(24)
    execute("UPDATE institutions SET winner_id = ?, winner_at = ?, reg_token = ?, updated_at = ? WHERE id = ?",
            (student_id, utcnow(), token, utcnow(), inst["id"]))
    student = query("SELECT * FROM campus_students WHERE id = ?", (student_id,), one=True)
    registration_mail(inst, student)
    audit("winner_selected", "institution", inst["id"], detail={"student": student_id, "name": student["name"]}, ip=client_ip())


@bp.route("/institution/winner", methods=["POST"])
@institution_required
def winner():
    inst = current_institution()
    if inst["status"] != "accepted":
        abort(403)
    action = request.form.get("action")
    if inst["application_id"] and action != "none":
        flash("The nomination of the selected student is submitted already; write to CICT to change the selection.", "error")
        return redirect(url_for("campus.home"))
    if action == "select":
        sid = request.form.get("student_id")
        student = query("SELECT s.*, t.status AS t_status FROM campus_students s LEFT JOIN campus_attempts t ON t.student_id = s.id "
                        "WHERE s.id = ? AND s.institution_id = ?", (sid, inst["id"]), one=True)
        if student is None:
            abort(404)
        _issue(inst, student["id"])
        flash(f"{student['name']} is selected and informed by e-mail. Now submit the nomination: \u201cSubmit the nomination\u201d below.",
              "success")
    elif action == "enter":
        d = {k: (request.form.get(k) or "").strip() for k in ("name", "email", "mobile", "roll_no", "course", "lang")}
        d["name"], english = plain_english(d["name"])
        d["email"] = d["email"].lower()
        if not d["name"] or not english or not valid_email(d["email"]) or not valid_mobile(d["mobile"]) \
                or d["lang"] not in K.ORIENTATION_LANGS:
            flash("Give the student's name (in English letters), a valid e-mail address, a 10-digit mobile number and the language.", "error")
            return redirect(url_for("campus.home"))
        existing = query("SELECT id FROM campus_students WHERE institution_id = ? AND (email = ? OR mobile = ?)",
                         (inst["id"], d["email"], d["mobile"]), one=True)
        if existing:
            sid = existing["id"]
        else:
            sid = execute("INSERT INTO campus_students(institution_id, name, email, mobile, roll_no, course, lang, source, created_at, ip) "
                          "VALUES(?,?,?,?,?,?,?,'entered',?,?)",
                          (inst["id"], d["name"], d["email"], d["mobile"], d["roll_no"], d["course"], d["lang"], utcnow(), client_ip()))
        _issue(inst, sid)
        flash(f"{d['name']} is selected and informed by e-mail. Now submit the nomination: \u201cSubmit the nomination\u201d below.",
              "success")
    elif action == "clear":
        if inst["application_id"]:
            abort(403)
        execute("UPDATE institutions SET winner_id = NULL, winner_at = NULL, reg_token = NULL, updated_at = ? WHERE id = ?",
                (utcnow(), inst["id"]))
        audit("winner_cleared", "institution", inst["id"], ip=client_ip())
        flash("The selection is withdrawn; its nomination link no longer works.", "success")
    else:
        abort(400)
    return redirect(url_for("campus.home"))


def registration_token(token):
    """The institution whose registration link this is, while its student has not registered; else None."""
    if not token or len(token) > 64:
        return None
    return query("SELECT * FROM institutions WHERE reg_token = ? AND status = 'accepted' AND application_id IS NULL", (token,), one=True)


def winner_of(inst):
    return query("SELECT * FROM campus_students WHERE id = ?", (inst["winner_id"],), one=True) if inst["winner_id"] else None


def bind_application(inst, application_id, by_coord=False):
    """
    The application registered with the institution's link: the institution keeps it, and the score
    of the winner's online assessment goes with the application as its exam session. by_coord: submitted by the Institutional
    Coordinator signed in on the institution's page (1.2.158).
    """
    execute("UPDATE institutions SET application_id = ?, updated_at = ? WHERE id = ?", (application_id, utcnow(), inst["id"]))
    attempt = query("SELECT * FROM campus_attempts WHERE student_id = ? AND status IN ('submitted', 'expired')",
                    (inst["winner_id"],), one=True) if inst["winner_id"] else None
    if attempt:
        execute("INSERT INTO exam_sessions(application_id, lang, paper_json, answers_json, started_at, deadline_at, submitted_at, status, "
                "score, correct_count, time_taken_sec, ip, user_agent) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (application_id, attempt["lang"], attempt["paper_json"], attempt["answers_json"], attempt["started_at"],
                 attempt["deadline_at"], attempt["submitted_at"], attempt["status"], attempt["score"], attempt["correct_count"],
                 attempt["time_taken_sec"], attempt["ip"], attempt["user_agent"]))
        execute("UPDATE applications SET exam_score = ?, updated_at = ? WHERE id = ?", (attempt["score"], utcnow(), application_id))
    app = query("SELECT app_no, full_name FROM applications WHERE id = ?", (application_id,), one=True)
    if by_coord:
        send_mail(inst["coord_email"], f"KTS 5.0: the nomination of {app['full_name']} is submitted ({app['app_no']})",
                  f"Dear {inst['coord_name']},\n\nThe nomination of {app['full_name']}, the student selected by {inst['name']}, is "
                  f"submitted on the KTS 5.0 portal: application {app['app_no']}. The student receives the application number by "
                  f"e-mail. The Nodal Officer of {inst['state']} now verifies the application.\n\nCentral Institute of Classical Tamil, Chennai")
    else:
        send_mail(inst["coord_email"], f"KTS 5.0: the student of {inst['name']} has registered",
                  f"Dear {inst['coord_name']},\n\nThe student selected by {inst['name']} has registered on the KTS 5.0 portal: "
                  f"application {app['app_no']}. The Nodal Officer of {inst['state']} now verifies the application.\n\n"
                  f"Central Institute of Classical Tamil, Chennai")


# ---- the video recording of the presentation (1.2.158) --------------------------------------------------------

PRESENTATION_FIELDS = ("title", "held_on", "minutes", "audience", "video_url", "material_url", "note")
URL_RE = re.compile(r"https?://[^\s<>\"']{3,490}")


def presentation_of(inst):
    return query("SELECT * FROM presentations WHERE institution_id = ?", (inst["id"],), one=True)


def presentation_window(settings=None):
    """(first day, last date): from the start of the one-month engagement (internship.start) to its last date (present.due)."""
    settings = settings or all_settings()
    return _day(settings.get("internship.start")), _day(settings.get("present.due"))


def _presentation_form(form, first, today):
    d = {k: (form.get(k) or "").strip() for k in PRESENTATION_FIELDS}
    errors = {}
    if not d["title"]:
        errors["title"] = "Give the title or topic of the presentation."
    d["title"] = d["title"][:200]
    held = _day(d["held_on"])
    if held is None:
        errors["held_on"] = "Give the date of the presentation."
    elif (first and held < first) or held > today:
        errors["held_on"] = (f"The presentation is held during the one-month engagement, from {first:%d %B %Y}, and not after today."
                             if first else "The date cannot be after today.")
    try:
        d["minutes"] = int(d["minutes"])
        if not 1 <= d["minutes"] <= 600:
            raise ValueError
    except ValueError:
        errors["minutes"] = "Give the duration in minutes (a number)."
    if d["audience"]:
        try:
            d["audience"] = int(d["audience"])
            if not 0 <= d["audience"] <= 100000:
                raise ValueError
        except ValueError:
            errors["audience"] = "Give the number of people who attended, or leave it empty."
    else:
        d["audience"] = None
    if not URL_RE.fullmatch(d["video_url"]):
        errors["video_url"] = "Give the full link to the video, beginning with https://"
    if d["material_url"] and not URL_RE.fullmatch(d["material_url"]):
        errors["material_url"] = "Give the full link, beginning with https://, or leave it empty."
    d["note"] = d["note"][:1000]
    if form.get("shared") != "1":
        errors["shared"] = "Confirm that CICT can open the video with this link."
    return d, errors


@bp.route("/institution/presentation", methods=["GET", "POST"])
@institution_required
def presentation():
    """
    The video recording of the one-hour presentation/lecture that the selected student delivers at the institution during the
    one-month research and academic engagement: the institution submits it to CICT (Annexure-III C-4 of the D.O. letter of
    31 October 2026; 1.2.158), as a link to the video with its title, date, duration and audience - a one-hour recording is far
    larger than the portal takes in one request (25 MB). Open from the start of the engagement once the nomination is submitted;
    changed until CICT accepts it.
    """
    inst = current_institution()
    if inst["status"] != "accepted":
        abort(403)
    settings = all_settings()
    application = query("SELECT * FROM applications WHERE id = ?", (inst["application_id"],), one=True) if inst["application_id"] else None
    row = presentation_of(inst)
    first, last = presentation_window(settings)
    today = now_ist().date()
    started = first is not None and today >= first
    data, errors = (dict(row) if row else {}), {}
    if request.method == "POST":
        if application is None or not started or (row is not None and row["status"] == "accepted"):
            abort(403)
        data, errors = _presentation_form(request.form, first, today)
        if not errors:
            now = utcnow()
            values = [data[k] for k in PRESENTATION_FIELDS]
            if row is None:
                execute("INSERT INTO presentations(institution_id, application_id, " + ", ".join(PRESENTATION_FIELDS) + ", status, "
                        "submitted_at, updated_at, ip) VALUES(?,?," + ",".join("?" * len(PRESENTATION_FIELDS)) + ",'submitted',?,?,?)",
                        [inst["id"], application["id"], *values, now, now, client_ip()])
            else:
                execute("UPDATE presentations SET " + ", ".join(k + " = ?" for k in PRESENTATION_FIELDS) + ", application_id = ?, "
                        "status = 'submitted', review_note = '', reviewed_by = NULL, reviewed_at = NULL, updated_at = ?, ip = ? "
                        "WHERE id = ?", [*values, application["id"], now, client_ip(), row["id"]])
            audit("presentation_submitted", "institution", inst["id"], detail={"title": data["title"], "video": data["video_url"]},
                  ip=client_ip())
            send_mail(inst["coord_email"], f"KTS 5.0: the video of the presentation is submitted ({inst['ref']})",
                      f"Dear {inst['coord_name']},\n\nThe video recording of the presentation of {application['full_name']} is "
                      f"submitted to CICT:\n\nTitle: {data['title']}\nDate: {_day(data['held_on']):%d %B %Y}\nDuration: "
                      f"{data['minutes']} minutes\nVideo: {data['video_url']}\n\nCICT reviews it; you see its status on "
                      f"{current_app.config['BASE_URL']}/institution/presentation\n\nCentral Institute of Classical Tamil, Chennai")
            flash("The video of the presentation is submitted to CICT.", "success")
            return redirect(url_for("campus.presentation"))
        flash("Please correct the marked fields.", "error")
    return render_template("campus/presentation.html", inst=inst, settings=settings, application=application, row=row,
                           data=data, errors=errors, first=first, last=last, today=today, started=started), 400 if errors else 200


# ---- the students: sign-up, the paper, the result ------------------------------------------------------------

def _institution_of_slug(slug):
    if not slug or len(slug) > 16:
        return None
    return query("SELECT * FROM institutions WHERE test_slug = ? AND status = 'accepted'", (slug,), one=True)


def _student(inst):
    sid = session.get("campus_sid")
    if not sid:
        return None
    return query("SELECT * FROM campus_students WHERE id = ? AND institution_id = ?", (sid, inst["id"]), one=True)


def _attempt(student):
    return query("SELECT * FROM campus_attempts WHERE student_id = ?", (student["id"],), one=True)


def _ctx(inst, settings):
    start, end = _day(inst["test_from"]), _day(inst["test_to"])
    return dict(inst=inst, settings=settings, state=assessment_state(inst, settings), test_from=start, test_to=end,
                langs=[K.lang_info(c) | {"code": c} for c in K.ORIENTATION_LANGS])


@bp.route("/assessment/<slug>", methods=["GET", "POST"])
def signup(slug):
    inst = _institution_of_slug(slug)
    settings = all_settings()
    if inst is None:
        return render_template("campus/closed.html", inst=None, settings=settings, state="none"), 404
    ctx = _ctx(inst, settings)
    if ctx["state"] != "open":
        return render_template("campus/closed.html", **ctx)
    student = _student(inst)
    if student:
        return redirect(url_for("campus.start", slug=slug))
    data, errors = {}, {}
    if request.method == "POST":
        ip = client_ip()
        form = request.form
        data = {k: (form.get(k) or "").strip() for k in ("code", "name", "email", "mobile", "roll_no", "course", "lang")}
        data["email"] = data["email"].lower()
        if data["code"].replace(" ", "") != inst["test_code"]:
            errors["code"] = t("camp.code_wrong")
        data["name"], english = plain_english(data["name"])
        data["roll_no"], roll_english = plain_english(data["roll_no"])
        data["course"], course_english = plain_english(data["course"])
        if not data["name"]:
            errors["name"] = t("reg.err_required")
        elif not english:
            errors["name"] = t("reg.err_english")
        if not roll_english:
            errors["roll_no"] = t("reg.err_english")
        if not course_english:
            errors["course"] = t("reg.err_english")
        if not valid_email(data["email"]):
            errors["email"] = t("reg.err_email")
        if not valid_mobile(data["mobile"]):
            errors["mobile"] = t("reg.err_mobile")
        if data["lang"] not in K.ORIENTATION_LANGS:
            errors["lang"] = t("reg.err_required")
        if form.get("declare") != "1":
            errors["declare"] = t("reg.err_declare")
        if form.get("website") or not check_captcha(form.get("captcha")):
            errors["captcha"] = t("reg.err_captcha")
        refused = not errors and limiter.blocked("campus_signup", ip, SIGNUP_PER_HOUR, 3600)
        if not errors and not refused:
            existing = query("SELECT * FROM campus_students WHERE institution_id = ? AND (email = ? OR mobile = ?)",
                             (inst["id"], data["email"], data["mobile"]), one=True)
            if existing and (existing["email"] != data["email"] or existing["mobile"] != data["mobile"]):
                errors["email"] = t("camp.err_mismatch")
            elif existing:
                session["campus_sid"] = existing["id"]
                return redirect(url_for("campus.start", slug=slug))
            else:
                sid = execute("INSERT INTO campus_students(institution_id, name, email, mobile, roll_no, course, lang, source, created_at, ip) "
                              "VALUES(?,?,?,?,?,?,?,'online',?,?)",
                              (inst["id"], data["name"], data["email"], data["mobile"], data["roll_no"], data["course"], data["lang"],
                               utcnow(), ip))
                limiter.hit("campus_signup", ip, 3600)
                session["campus_sid"] = sid
                session.permanent = True
                audit("campus_signup", "institution", inst["id"], detail={"student": sid}, ip=ip)
                return redirect(url_for("campus.start", slug=slug))
        if errors or refused:
            flash(t("reg.err_rate") if refused else t("reg.err_fix"), "error")
            return render_template("campus/signup.html", data=data, errors=errors, captcha=new_captcha(), **ctx), 400
    return render_template("campus/signup.html", data=data, errors=errors, captcha=new_captcha(), **ctx)


def _gate(slug):
    """(inst, student, attempt) of the student signed in for this assessment, or a redirect."""
    inst = _institution_of_slug(slug)
    if inst is None:
        abort(404)
    student = _student(inst)
    if student is None:
        return inst, None, None
    return inst, student, _attempt(student)


@bp.route("/assessment/<slug>/start", methods=["GET", "POST"])
def start(slug):
    inst, student, attempt = _gate(slug)
    if student is None:
        return redirect(url_for("campus.signup", slug=slug))
    settings = all_settings()
    ctx = _ctx(inst, settings)
    if attempt and attempt["status"] != "in_progress":
        return redirect(url_for("campus.result", slug=slug))
    if attempt:
        return redirect(url_for("campus.paper", slug=slug))
    if request.method == "POST":
        if ctx["state"] != "open":
            return render_template("campus/closed.html", **ctx)
        n_q = int(settings.get("exam.questions", "50"))
        duration = int(settings.get("exam.duration_min", "30"))
        paper = _build_paper(student["lang"], n_q, random.Random(f"campus-{student['id']}-{utcnow()}"),
                             kurals=K.kural108_numbers() if inst["test_syllabus"] == "108" else None)
        if not paper:
            flash(t("exam.no_questions"), "error")
            return redirect(url_for("campus.start", slug=slug))
        started = now_ist()
        try:
            execute("INSERT INTO campus_attempts(student_id, lang, paper_json, started_at, deadline_at, ip, user_agent) VALUES(?,?,?,?,?,?,?)",
                    (student["id"], student["lang"], json.dumps(paper), started.isoformat(),
                     (started + timedelta(minutes=duration)).isoformat(), client_ip(), (request.user_agent.string or "")[:200]))
        except sqlite3.IntegrityError:
            get_db().rollback()
        audit("campus_started", "institution", inst["id"], detail={"student": student["id"]}, ip=client_ip())
        return redirect(url_for("campus.paper", slug=slug))
    return render_template("campus/start.html", student=student, **ctx)


def _passed(attempt):
    return now_ist() > parse_iso(attempt["deadline_at"]) + timedelta(seconds=45)


def finalise(attempt, reason="submitted"):
    """Scores the attempt as the candidates' test is scored (exam.marks_per_q, exam.negative)."""
    paper = json.loads(attempt["paper_json"])
    answers = json.loads(attempt["answers_json"] or "{}")
    ids = [p["q"] for p in paper]
    marks = ",".join("?" * len(ids))
    correct = {r["id"]: r["correct"] for r in query(f"SELECT id, correct FROM questions WHERE id IN ({marks})", ids)} if ids else {}
    settings = all_settings()
    per_q = float(settings.get("exam.marks_per_q", "2"))
    neg = float(settings.get("exam.negative", "0"))
    right = wrong = 0
    for qid in ids:
        ans = answers.get(str(qid))
        if not ans:
            continue
        if ans == correct.get(qid):
            right += 1
        else:
            wrong += 1
    score = right * per_q - wrong * neg
    started = parse_iso(attempt["started_at"])
    ended = min(now_ist(), parse_iso(attempt["deadline_at"]) + timedelta(seconds=45))
    execute("UPDATE campus_attempts SET status = ?, submitted_at = ?, score = ?, correct_count = ?, time_taken_sec = ? WHERE id = ?",
            (reason, ended.isoformat(), score, right, int((ended - started).total_seconds()), attempt["id"]))
    return score


@bp.route("/assessment/<slug>/paper")
def paper(slug):
    inst, student, attempt = _gate(slug)
    if student is None:
        return redirect(url_for("campus.signup", slug=slug))
    if attempt is None:
        return redirect(url_for("campus.start", slug=slug))
    if attempt["status"] != "in_progress":
        return redirect(url_for("campus.result", slug=slug))
    if _passed(attempt):
        finalise(attempt, "expired")
        return redirect(url_for("campus.result", slug=slug))
    questions = _load_paper(attempt)
    answers = json.loads(attempt["answers_json"] or "{}")
    remaining = int((parse_iso(attempt["deadline_at"]) - now_ist()).total_seconds())
    info = K.lang_info(attempt["lang"]) or {}
    return render_template("candidate/exam_paper.html", exam=attempt, questions=questions, answers=answers,
                           remaining=max(0, remaining), qlang=attempt["lang"], qdir=info.get("dir", "ltr"),
                           who=f"{inst['name']} · {student['name']}", save_url=url_for("campus.save", slug=slug),
                           submit_url=url_for("campus.submit", slug=slug))


@bp.route("/assessment/<slug>/save", methods=["POST"])
def save(slug):
    inst, student, attempt = _gate(slug)
    if student is None or attempt is None or attempt["status"] != "in_progress":
        return jsonify({"ok": False, "reason": "closed"}), 409
    if _passed(attempt):
        finalise(attempt, "expired")
        return jsonify({"ok": False, "reason": "expired"}), 409
    payload = request.get_json(silent=True) or {}
    answers = json.loads(attempt["answers_json"] or "{}")
    valid_ids = {str(p["q"]) for p in json.loads(attempt["paper_json"])}
    for qid, letter in (payload.get("answers") or {}).items():
        if qid in valid_ids and letter in ("A", "B", "C", "D", ""):
            if letter:
                answers[qid] = letter
            else:
                answers.pop(qid, None)
    execute("UPDATE campus_attempts SET answers_json = ? WHERE id = ?", (json.dumps(answers), attempt["id"]))
    remaining = int((parse_iso(attempt["deadline_at"]) - now_ist()).total_seconds())
    return jsonify({"ok": True, "saved": len(answers), "remaining": max(0, remaining)})


@bp.route("/assessment/<slug>/submit", methods=["POST"])
def submit(slug):
    inst, student, attempt = _gate(slug)
    if student is None:
        return redirect(url_for("campus.signup", slug=slug))
    if attempt is None:
        return redirect(url_for("campus.start", slug=slug))
    if attempt["status"] == "in_progress":
        payload = request.form.get("answers")
        if payload:
            try:
                answers = json.loads(attempt["answers_json"] or "{}")
                valid_ids = {str(p["q"]) for p in json.loads(attempt["paper_json"])}
                for qid, letter in json.loads(payload).items():
                    if qid in valid_ids and letter in ("A", "B", "C", "D"):
                        answers[qid] = letter
                execute("UPDATE campus_attempts SET answers_json = ? WHERE id = ?", (json.dumps(answers), attempt["id"]))
                attempt = _attempt(student)
            except ValueError:
                pass
        finalise(attempt, "expired" if _passed(attempt) else "submitted")
        audit("campus_submitted", "institution", inst["id"], detail={"student": student["id"]}, ip=client_ip())
    return redirect(url_for("campus.result", slug=slug))


@bp.route("/assessment/<slug>/result")
def result(slug):
    inst, student, attempt = _gate(slug)
    if student is None:
        return redirect(url_for("campus.signup", slug=slug))
    if attempt is None:
        return redirect(url_for("campus.start", slug=slug))
    if attempt["status"] == "in_progress":
        return redirect(url_for("campus.paper", slug=slug))
    settings = all_settings()
    total = len(json.loads(attempt["paper_json"]))
    return render_template("campus/done.html", student=student, attempt=attempt, total=total,
                           show_score=settings.get("camp.show_score") == "1",
                           max_score=total * float(settings.get("exam.marks_per_q", "2")), **_ctx(inst, settings))


@bp.app_context_processor
def _names():
    """nodal_of(state): the Nodal Institution of the State/UT, for the institution's page."""
    from .heis import row_of

    def nodal_of(state):
        h = row_of(state)   # a paired Union Territory has the Nodal Institution of its State (1.2.135)
        return h["name"] if h else ""
    return {"nodal_of": nodal_of}

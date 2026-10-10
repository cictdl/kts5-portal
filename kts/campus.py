"""
The participating institutions' own area, and the online assessment they conduct (version 1.2.43).

The D.O. letter of the Ministry of Education of 9 October 2026 (Annexure-III) puts the assessment
of the students with the participating institutions: each institution conducts a test, or any other
suitable mode of assessment, on the theme of the Thirukkural, selects one student as the winner on
merit, and registers that student's details on the portal. CICT consolidates the selected students.

* The Institutional Coordinator (or the Head of the Institution) signs in at /institution/login
  with the e-mail address given when the institution registered: the portal mails a six-digit
  code, valid for CODE_MINUTES. No password is kept.
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
  The portal mails the student (and the coordinator) a personal registration link, the only way to
  /register while reg.by_institution is on; the institution of the application is fixed by it, and
  the score of the online assessment goes with the application (exam_sessions), so that the status
  page, the selection and the merit list work as before.
"""
import hashlib
import json
import random
import secrets
import sqlite3
from datetime import date, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

from . import kural as K
from .candidate import _build_paper, _load_paper
from .db import all_settings, audit, execute, get_db, get_setting, query, utcnow
from .i18n import t
from .utils import (check_captcha, client_ip, limiter, new_captcha, now_ist, parse_iso, plain_english, send_mail,
                    valid_email, valid_mobile, xlsx_bytes)

bp = Blueprint("campus", __name__)

CODE_MINUTES = 15
CODE_TRIES = 5
LOGIN_PER_HOUR = 12          # codes asked for from one address in an hour
SIGNUP_PER_HOUR = 60         # sign-ups of students from one address in an hour
RANK_SQL = "ORDER BY CASE WHEN t.status IN ('submitted', 'expired') THEN 0 ELSE 1 END, t.score DESC, t.time_taken_sec ASC, s.id ASC"


# ---- the institution and its coordinator ------------------------------------------------------------------

def _email_matches(inst, email):
    return email and email in (inst["coord_email"], inst["head_email"])


def institutions_of(email):
    """The institutions whose coordinator or head has this e-mail address, the accepted first."""
    return query("SELECT * FROM institutions WHERE (coord_email = ? OR head_email = ?) AND status != 'declined' "
                 "ORDER BY CASE status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, id", (email, email))


def current_institution():
    """The institution signed in, or None."""
    if "inst" in g:
        return g.inst
    inst = None
    iid, email = session.get("inst_id"), session.get("inst_email")
    if iid and email:
        inst = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
        if inst is None or not _email_matches(inst, email) or inst["status"] == "declined":
            inst = None
    g.inst = inst
    return inst


def _code_hash(email, code):
    return hashlib.sha256(f"{email}|{code}|{current_app.config['SECRET_KEY']}".encode("utf-8")).hexdigest()


@bp.route("/institution/login", methods=["GET", "POST"])
def login():
    if current_institution():
        return redirect(url_for("campus.home"))
    error = sent = None
    if request.method == "POST":
        ip = client_ip()
        email = (request.form.get("email") or "").strip().lower()
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
                send_mail(email, "KTS 5.0: your sign-in code",
                          f"Dear Sir/Madam,\n\nYour code to sign in to the institution's page of the KTS 5.0 portal "
                          f"({names}):\n\n    {code}\n\nIt is valid for {CODE_MINUTES} minutes. If you did not ask for it, "
                          f"ignore this mail.\n\nCentral Institute of Classical Tamil, Chennai")
                audit("institution_code_sent", "institution", rows[0]["id"], detail=email, ip=ip)
            # an address that belongs to no institution is answered in the same way: the page does not say which
            # addresses the portal knows
            sent = email
    return render_template("campus/login.html", error=error, sent=sent, settings=all_settings())


@bp.route("/institution/code", methods=["POST"])
def code():
    pending = session.get("inst_login") or {}
    typed = (request.form.get("code") or "").strip().replace(" ", "")
    error = None
    if not pending or pending.get("until", "") < now_ist().isoformat():
        error = "The code has expired: ask for a new one."
    elif pending.get("tries", 0) >= CODE_TRIES:
        error = "Too many wrong codes: ask for a new one."
    elif _code_hash(pending["email"], typed) != pending["hash"]:
        pending["tries"] = pending.get("tries", 0) + 1
        session["inst_login"] = pending
        error = "The code is wrong."
    if error:
        if "expired" in error or "Too many" in error:
            session.pop("inst_login", None)
        return render_template("campus/login.html", error=error, sent=pending.get("email") if not error.startswith(("The code has", "Too")) else None,
                               settings=all_settings()), 400
    rows = institutions_of(pending["email"])
    session.pop("inst_login", None)
    if not rows:
        return render_template("campus/login.html", error="No institution is registered with this e-mail address.", sent=None,
                               settings=all_settings()), 400
    session.pop("uid", None)
    session["inst_email"] = pending["email"]
    session["inst_id"] = rows[0]["id"]
    session.permanent = True
    audit("institution_login", "institution", rows[0]["id"], detail=pending["email"], ip=client_ip())
    return redirect(url_for("campus.home"))


@bp.route("/institution/switch/<int:iid>")
def switch(iid):
    inst = current_institution()
    if inst is None:
        return redirect(url_for("campus.login"))
    other = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
    if other is None or not _email_matches(other, session.get("inst_email")) or other["status"] == "declined":
        abort(404)
    session["inst_id"] = other["id"]
    return redirect(url_for("campus.home"))


@bp.route("/institution/logout", methods=["POST"])
def logout():
    session.pop("inst_id", None)
    session.pop("inst_email", None)
    return redirect(url_for("public.home"))


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
    others = [r for r in institutions_of(session["inst_email"]) if r["id"] != inst["id"]]
    winner = _winner(inst)
    application = query("SELECT * FROM applications WHERE id = ?", (inst["application_id"],), one=True) if inst["application_id"] else None
    start, end = assessment_period(settings)
    base = current_app.config["BASE_URL"]
    return render_template("campus/home.html", inst=inst, others=others, settings=settings, students=students_of(inst),
                           winner=winner, application=application, state=assessment_state(inst, settings),
                           period=(start, end), reg_end=_day(settings.get("reg.end")),
                           test_url=f"{base}/assessment/{inst['test_slug']}" if inst["test_slug"] else "",
                           reg_url=f"{base}/register?token={inst['reg_token']}" if inst["reg_token"] and not application else "",
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
        execute("UPDATE institutions SET test_on = 1, test_from = ?, test_to = ?, test_slug = ?, test_code = ?, updated_at = ? WHERE id = ?",
                (a.isoformat(), b.isoformat(), slug, code_, now, inst["id"]))
        audit("assessment_on", "institution", inst["id"], detail={"from": a.isoformat(), "to": b.isoformat()}, ip=client_ip())
        flash("The online assessment is on. Give your students the link and the access code shown below.", "success")
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

def registration_mail(inst, student, link):
    body = (f"Dear {student['name']},\n\n{inst['name']} has selected you, on the basis of its assessment, as its student for "
            f"Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom.\n\nRegister on the KTS 5.0 portal with this personal link, "
            f"on or before {_reg_end_text()}:\n\n{link}\n\nKeep ready: a photograph, an ID proof and the nomination form "
            f"signed by the Head of the Institution (your Institutional Coordinator has it; the form is at "
            f"{current_app.config['BASE_URL']}/static/KTS5-nomination-form.pdf), and the name, designation, e-mail and mobile "
            f"of your Faculty Supervisor/Guide.\n\nThe link is for you alone and works once.\n\n"
            f"Central Institute of Classical Tamil, Chennai")
    if student["email"]:
        send_mail(student["email"], f"KTS 5.0: register as the student selected by {inst['name']}", body)
    send_mail(inst["coord_email"], f"KTS 5.0: registration link of {student['name']} ({inst['ref']})",
              f"Dear {inst['coord_name']},\n\nThe registration link of the student selected by {inst['name']}, "
              f"{student['name']}, is:\n\n{link}\n\nIt was sent to the student as well"
              + (f" ({student['email']})" if student["email"] else "") +
              f". The registration may be filled in by the student or by you, on or before {_reg_end_text()}. "
              f"You see its state on the institution's page: {current_app.config['BASE_URL']}/institution\n\n"
              f"Central Institute of Classical Tamil, Chennai")


def _reg_end_text():
    end = _day(get_setting("reg.end"))
    return f"{end.day} {end:%B %Y}" if end else "the date given by CICT"


def _issue(inst, student_id):
    token = secrets.token_urlsafe(24)
    execute("UPDATE institutions SET winner_id = ?, winner_at = ?, reg_token = ?, updated_at = ? WHERE id = ?",
            (student_id, utcnow(), token, utcnow(), inst["id"]))
    student = query("SELECT * FROM campus_students WHERE id = ?", (student_id,), one=True)
    registration_mail(inst, student, f"{current_app.config['BASE_URL']}/register?token={token}")
    audit("winner_selected", "institution", inst["id"], detail={"student": student_id, "name": student["name"]}, ip=client_ip())


@bp.route("/institution/winner", methods=["POST"])
@institution_required
def winner():
    inst = current_institution()
    if inst["status"] != "accepted":
        abort(403)
    action = request.form.get("action")
    if inst["application_id"] and action != "none":
        flash("The selected student has registered already; write to CICT to change the selection.", "error")
        return redirect(url_for("campus.home"))
    if action == "select":
        sid = request.form.get("student_id")
        student = query("SELECT s.*, t.status AS t_status FROM campus_students s LEFT JOIN campus_attempts t ON t.student_id = s.id "
                        "WHERE s.id = ? AND s.institution_id = ?", (sid, inst["id"]), one=True)
        if student is None:
            abort(404)
        _issue(inst, student["id"])
        flash(f"{student['name']} is selected. The registration link is mailed to the student and to you, and shown below.", "success")
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
        flash(f"{d['name']} is selected. The registration link is mailed to the student and to you, and shown below.", "success")
    elif action == "clear":
        if inst["application_id"]:
            abort(403)
        execute("UPDATE institutions SET winner_id = NULL, winner_at = NULL, reg_token = NULL, updated_at = ? WHERE id = ?",
                (utcnow(), inst["id"]))
        audit("winner_cleared", "institution", inst["id"], ip=client_ip())
        flash("The selection is withdrawn; the registration link no longer works.", "success")
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


def bind_application(inst, application_id):
    """
    The application registered with the institution's link: the institution keeps it, and the score
    of the winner's online assessment goes with the application as its exam session.
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
    send_mail(inst["coord_email"], f"KTS 5.0: the student of {inst['name']} has registered",
              f"Dear {inst['coord_name']},\n\nThe student selected by {inst['name']} has registered on the KTS 5.0 portal. "
              f"The Nodal Officer of {inst['state']} now verifies the application.\n\nCentral Institute of Classical Tamil, Chennai")


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
        paper = _build_paper(student["lang"], n_q, random.Random(f"campus-{student['id']}-{utcnow()}"))
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
    from .heis import nodal_heis

    def nodal_of(state):
        return next((h["name"] for h in nodal_heis() if h["state"] == state), "")
    return {"nodal_of": nodal_of}

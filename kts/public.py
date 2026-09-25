"""
Public site: home, programme, registration, status, repository, notices.
"""
import json
from datetime import date, datetime
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)

from . import kural as K
from .db import all_settings, audit, execute, get_setting, query, utcnow
from .i18n import LANG_NAMES, get_lang, t
from .utils import (DOC_EXT, IMAGE_EXT, age_on, check_captcha, client_ip, college_key, csv_bytes,
                    exam_window, fmt_date, limiter, make_app_no, new_captcha, now_ist, qr_data_uri,
                    registration_state, save_upload, send_mail, valid_email, valid_mobile,
                    valid_pincode)

bp = Blueprint("public", __name__)


def _states():
    data = json.loads((current_app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
    data["all_states"] = data["states"] + data["union_territories"]
    return data


def _key_dates(settings):
    start, end, _ = exam_window(settings)
    return {
        "reg_start": settings.get("reg.start"),
        "reg_end": settings.get("reg.end"),
        "exam_date": settings.get("exam.date"),
        "exam_start": start,
        "exam_end": end,
        "reg_state": registration_state(settings),
    }


@bp.route("/lang/<code>")
def set_lang(code):
    if code in LANG_NAMES:
        session["lang"] = code
    target = request.referrer or url_for("public.home")
    resp = redirect(target)
    resp.set_cookie("lang", code, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.route("/")
def home():
    settings = all_settings()
    lang = get_lang()
    notices = query("SELECT * FROM notices WHERE published = 1 AND (publish_at IS NULL OR publish_at <= ?) "
                    "ORDER BY pinned DESC, created_at DESC LIMIT 5", (utcnow(),))
    events = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id "
                   "WHERE e.published = 1 AND e.starts_at >= ? ORDER BY e.starts_at LIMIT 4",
                   (now_ist().strftime("%Y-%m-%dT00:00"),))
    agencies = query("SELECT * FROM agencies WHERE active = 1 ORDER BY sort_order, name")
    stats = None
    if settings.get("stats.public") == "1":
        row = query("SELECT COUNT(*) AS n, COUNT(DISTINCT college_key) AS c, COUNT(DISTINCT state) AS s "
                    "FROM applications WHERE status != 'withdrawn'", one=True)
        stats = {"apps": row["n"], "colleges": row["c"], "states": row["s"]}
    k = K.daily()
    kotd_lang = lang if lang in ("ta", "hi") else "en"
    return render_template("public/home.html", settings=settings, dates=_key_dates(settings),
                           notices=notices, events=events, agencies=agencies, stats=stats,
                           kotd=k, kotd_lines=K.lines(k, kotd_lang), kotd_lang=kotd_lang,
                           featured=query("SELECT * FROM resources WHERE published = 1 AND featured = 1 "
                                          "ORDER BY sort_order, created_at DESC LIMIT 6"))


@bp.route("/about")
def about():
    return render_template("public/about.html")


@bp.route("/programme")
def programme():
    return render_template("public/programme.html", settings=all_settings())


# ---- registration -----------------------------------------------------------

FIELDS = [
    "full_name", "gender", "dob", "category", "mobile", "whatsapp", "email", "address", "state",
    "district", "pincode", "college_name", "aishe_code", "college_type", "college_state",
    "college_district", "university", "course_level", "discipline", "year_of_study", "roll_no",
    "mother_tongue", "pref_lang", "tamil_level", "kural_level", "mentor_name",
    "mentor_designation", "mentor_email", "mentor_phone",
]
REQUIRED = ["full_name", "gender", "dob", "mobile", "email", "state", "college_name",
            "college_type", "college_state", "course_level", "year_of_study", "pref_lang"]


def _validate(form, files):
    errors = {}
    data = {f: (form.get(f) or "").strip() for f in FIELDS}
    data["pwd"] = 1 if form.get("pwd") == "1" else 0
    for f in REQUIRED:
        if not data[f]:
            errors[f] = t("reg.err_required")
    if data["mobile"] and not valid_mobile(data["mobile"]):
        errors["mobile"] = t("reg.err_mobile")
    if data["whatsapp"] and not valid_mobile(data["whatsapp"]):
        errors["whatsapp"] = t("reg.err_mobile")
    if data["email"] and not valid_email(data["email"]):
        errors["email"] = t("reg.err_email")
    if data["mentor_email"] and not valid_email(data["mentor_email"]):
        errors["mentor_email"] = t("reg.err_email")
    if data["mentor_phone"] and not valid_mobile(data["mentor_phone"]):
        errors["mentor_phone"] = t("reg.err_mobile")
    if not valid_pincode(data["pincode"]):
        errors["pincode"] = t("reg.err_pincode")
    if data["dob"]:
        age = age_on(data["dob"])
        if age is None or age < 17 or age > 35:
            errors["dob"] = t("reg.err_dob")
    if data["pref_lang"] and data["pref_lang"] not in K.ORIENTATION_LANGS:
        errors["pref_lang"] = t("reg.err_required")
    if data["gender"] not in ("M", "F", "O"):
        errors["gender"] = t("reg.err_required")
    for f in ("declare_true", "declare_participate", "declare_consent"):
        if form.get(f) != "1":
            errors["declare"] = t("reg.err_declare")
    if form.get("website"):  # honeypot
        errors["captcha"] = t("reg.err_captcha")
    data["email"] = data["email"].lower()
    return data, errors


@bp.route("/register", methods=["GET", "POST"])
def register():
    settings = all_settings()
    state = registration_state(settings)
    ref = _states()
    langs = [K.lang_info(c) | {"code": c} for c in K.ORIENTATION_LANGS]
    mother = [K.lang_info(c) | {"code": c} for c in ["ta"] + [c for c in K.SCHEDULED if c != "ta"]]
    ctx = dict(settings=settings, state=state, ref=ref, langs=langs, mother=mother,
               dates=_key_dates(settings), data={}, errors={})
    if state != "open":
        return render_template("public/register_closed.html", **ctx)

    if request.method == "POST":
        ip = client_ip()
        data, errors = _validate(request.form, request.files)
        if not check_captcha(request.form.get("captcha")):
            errors["captcha"] = t("reg.err_captcha")
        if not errors:
            if query("SELECT 1 FROM applications WHERE email = ? AND status != 'withdrawn'", (data["email"],), one=True):
                errors["email"] = t("reg.err_dup_email")
            if query("SELECT 1 FROM applications WHERE mobile = ? AND status != 'withdrawn'", (data["mobile"],), one=True):
                errors["mobile"] = t("reg.err_dup_mobile")
        photo = idproof = None
        if not errors:
            try:
                photo = save_upload(request.files.get("photo"), "photos", IMAGE_EXT, current_app.config["PHOTO_MAX_BYTES"])
            except ValueError:
                errors["photo"] = t("reg.err_photo")
            try:
                idproof = save_upload(request.files.get("idproof"), "idproofs", DOC_EXT, current_app.config["IDPROOF_MAX_BYTES"])
            except ValueError:
                errors["idproof"] = t("reg.err_idproof")
        if not errors and not limiter.allow("register", ip, current_app.config["RATE_REGISTER_PER_HOUR"], 3600):
            errors["captcha"] = t("reg.err_rate")
        if errors:
            flash(t("reg.err_fix"), "error")
            ctx.update(data=data, errors=errors, captcha=new_captcha())
            return render_template("public/register.html", **ctx), 400

        now = utcnow()
        data["college_key"] = college_key(data["college_name"], data["college_state"], data["aishe_code"])
        cols = FIELDS + ["pwd", "college_key", "photo_path", "idproof_path", "ip", "created_at", "updated_at", "status"]
        values = [data[f] for f in FIELDS] + [data["pwd"], data["college_key"], photo[0], idproof[0], ip, now, now, "submitted"]
        row_id = execute(f"INSERT INTO applications({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", values)
        app_no = make_app_no(row_id)
        execute("UPDATE applications SET app_no = ? WHERE id = ?", (app_no, row_id))
        audit("application_submitted", "application", row_id, detail=app_no, ip=ip)
        send_mail(
            data["email"],
            f"KTS 5.0 application received: {app_no}",
            f"Dear {data['full_name']},\n\nYour application for Kashi Tamil Sangamam 5.0 (Thirukkural Payilvom) "
            f"has been received.\n\nApplication number: {app_no}\nInstitution: {data['college_name']}\n"
            f"Language chosen: {K.lang_info(data['pref_lang'])['name']}\n\n"
            f"Keep this number safe. Use it with your date of birth and mobile number to check your status "
            f"and to sign in for the online test at {current_app.config['BASE_URL']}/status\n\n"
            f"Central Institute of Classical Tamil, Chennai",
        )
        session["just_registered"] = row_id
        return redirect(url_for("public.register_done", app_no=app_no))

    ctx["captcha"] = new_captcha()
    return render_template("public/register.html", **ctx)


@bp.route("/register/done/<app_no>")
def register_done(app_no):
    row = query("SELECT * FROM applications WHERE app_no = ?", (app_no,), one=True)
    if row is None or session.get("just_registered") != row["id"]:
        return redirect(url_for("public.status"))
    return render_template("public/register_done.html", app=row,
                           qr=qr_data_uri(f"{current_app.config['BASE_URL']}/status?app={app_no}"),
                           lang_name=K.lang_info(row["pref_lang"])["name"], settings=all_settings())


# ---- status -----------------------------------------------------------------

STATUS_KEYS = {
    "submitted": "status.submitted", "verified": "status.verified", "rejected": "status.rejected",
    "selected": "status.selected", "waitlisted": "status.waitlisted", "not_selected": "status.not_selected",
    "withdrawn": "status.withdrawn",
}


@bp.route("/status", methods=["GET", "POST"])
def status():
    settings = all_settings()
    result = error = None
    if request.method == "POST":
        if not limiter.allow("status", client_ip(), 30, 15 * 60):
            error = t("reg.err_rate")
        else:
            app_no = (request.form.get("app_no") or "").strip().upper()
            dob = (request.form.get("dob") or "").strip()
            last4 = (request.form.get("last4") or "").strip()
            row = query("SELECT * FROM applications WHERE app_no = ? AND dob = ? AND substr(mobile, -4) = ?",
                        (app_no, dob, last4), one=True)
            if row is None:
                error = t("status.not_found")
            else:
                exam = query("SELECT * FROM exam_sessions WHERE application_id = ?", (row["id"],), one=True)
                result = {"app": row, "exam": exam, "status_text": t(STATUS_KEYS.get(row["status"], "common.status")),
                          "show_score": settings.get("exam.show_score") == "1"}
    return render_template("public/status.html", result=result, error=error, settings=settings,
                           prefill=request.args.get("app", ""), dates=_key_dates(settings))


# ---- examination / merit ----------------------------------------------------

@bp.route("/examination")
def examination():
    settings = all_settings()
    start, end, is_open = exam_window(settings)
    return render_template("public/examination.html", settings=settings, start=start, end=end,
                           is_open=is_open, dates=_key_dates(settings))


@bp.route("/merit-list")
def merit():
    settings = all_settings()
    published = settings.get("merit.published") == "1"
    rows = []
    q = (request.args.get("q") or "").strip()
    state = (request.args.get("state") or "").strip()
    outcome = request.args.get("outcome") or "selected"
    if published:
        sql = ("SELECT m.rank, m.score, m.outcome, a.app_no, a.full_name, a.college_name, a.college_state, a.state "
               "FROM merit_list m JOIN applications a ON a.id = m.application_id WHERE 1=1")
        args = []
        if outcome in ("selected", "waitlisted"):
            sql += " AND m.outcome = ?"
            args.append(outcome)
        if q:
            sql += " AND (a.full_name LIKE ? OR a.college_name LIKE ? OR a.app_no LIKE ?)"
            args += [f"%{q}%"] * 3
        if state:
            sql += " AND a.college_state = ?"
            args.append(state)
        sql += " ORDER BY m.rank LIMIT 2000"
        rows = query(sql, args)
    return render_template("public/merit.html", settings=settings, published=published, rows=rows,
                           q=q, state=state, outcome=outcome, ref=_states())


@bp.route("/merit-list.csv")
def merit_csv():
    if get_setting("merit.published") != "1":
        abort(404)
    rows = query("SELECT m.rank, a.app_no, a.full_name, a.college_name, a.college_state, m.outcome "
                 "FROM merit_list m JOIN applications a ON a.id = m.application_id ORDER BY m.rank")
    data = csv_bytes(["Rank", "Application No", "Name", "Institution", "State", "Outcome"],
                     [tuple(r) for r in rows])
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=KTS5-merit-list.csv"})


# ---- repository -------------------------------------------------------------

CATEGORIES = ["translation", "publication", "app", "corpus", "video", "audio", "film", "comic",
              "poster", "daily", "story", "study", "link"]


@bp.route("/resources")
def resources():
    cat = request.args.get("cat") or ""
    lang = request.args.get("l") or ""
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM resources WHERE published = 1"
    args = []
    if cat in CATEGORIES:
        sql += " AND category = ?"
        args.append(cat)
    if lang:
        sql += " AND (lang = ? OR lang = '')"
        args.append(lang)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        args += [f"%{q}%"] * 2
    sql += " ORDER BY featured DESC, sort_order, created_at DESC"
    rows = query(sql, args)
    counts = {r["category"]: r["n"] for r in query("SELECT category, COUNT(*) AS n FROM resources WHERE published = 1 GROUP BY category")}
    return render_template("public/resources.html", rows=rows, cat=cat, lang=lang, q=q,
                           categories=CATEGORIES, counts=counts, langs=K.languages())


@bp.route("/resources/<int:rid>")
def resource_open(rid):
    row = query("SELECT * FROM resources WHERE id = ? AND published = 1", (rid,), one=True)
    if row is None:
        abort(404)
    execute("UPDATE resources SET downloads = downloads + 1 WHERE id = ?", (rid,))
    if row["file_path"]:
        folder = Path(current_app.config["UPLOAD_DIR"])
        return send_from_directory(folder, row["file_path"], as_attachment=False, download_name=row["file_name"] or None)
    if row["url"]:
        return redirect(row["url"])
    abort(404)


@bp.route("/files/<path:relpath>")
def public_file(relpath):
    """Public attachments (notices, resources, shared documents marked public)."""
    if not (relpath.startswith("notices/") or relpath.startswith("resources/")):
        abort(404)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), relpath)


@bp.route("/thirukkural")
def kural_browser():
    ch = request.args.get("ch", "1")
    try:
        ch_n = max(1, min(133, int(ch)))
    except ValueError:
        ch_n = 1
    lang = request.args.get("l") or ({"ta": "ta", "hi": "hi"}.get(get_lang(), "en"))
    if not K.lang_info(lang):
        lang = "en"
    chapter = K.chapter(ch_n)
    rows = [(k, K.lines(k, lang)) for k in chapter["kurals"]]
    return render_template("public/kural.html", chapter=chapter, rows=rows, lang=lang,
                           langs=K.languages(), chapters=K.chapters(), pals=K.corpus()["meta"]["pals"],
                           variants=K.VARIANTS)


@bp.route("/thirukkural/<int:n>")
def kural_single(n):
    k = K.kural(n)
    if k is None:
        abort(404)
    streams = []
    for info in K.languages():
        ln = K.lines(k, info["code"])
        if ln:
            streams.append((info, ln))
    return render_template("public/kural_single.html", k=k, streams=streams,
                           prose=(k.get("prose") or {}) if isinstance(k.get("prose"), dict) else {})


@bp.route("/daily-kural")
def daily_kural():
    lang = request.args.get("l") or ({"ta": "ta", "hi": "hi"}.get(get_lang(), "en"))
    if not K.lang_info(lang):
        lang = "en"
    day_s = request.args.get("d")
    try:
        day = date.fromisoformat(day_s) if day_s else date.today()
    except ValueError:
        day = date.today()
    k = K.daily(day)
    return render_template("public/daily.html", k=k, day=day, lang=lang, lines=K.lines(k, lang),
                           langs=K.languages(), n=K.daily_number(day))


@bp.route("/daily-kural/calendar.csv")
def daily_calendar():
    lang = request.args.get("l") or "hi"
    if not K.lang_info(lang):
        lang = "en"
    start_s = request.args.get("start")
    try:
        start = date.fromisoformat(start_s) if start_s else date.today()
    except ValueError:
        start = date.today()
    rows = K.calendar_rows(lang, start, 200)
    data = csv_bytes(["Day", "Date", "Kural No", "Chapter (Tamil)", "Chapter (English)", "Tamil", f"Translation ({K.lang_info(lang)['name']})"],
                     [(r["day"], r["date"], r["kural"], r["chapter"], r["chapter_en"], r["tamil"], r["translation"]) for r in rows])
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=daily-kural-200-days-{lang}.csv"})


@bp.route("/orientation")
def orientation():
    settings = all_settings()
    sessions = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id "
                     "WHERE e.published = 1 AND e.kind = 'orientation' ORDER BY e.starts_at")
    videos = query("SELECT * FROM resources WHERE published = 1 AND category IN ('video', 'study') ORDER BY lang, sort_order")
    by_lang = {}
    for s in sessions:
        by_lang.setdefault(s["lang"] or "", []).append(s)
    vids = {}
    for v in videos:
        vids.setdefault(v["lang"] or "", []).append(v)
    langs = [K.lang_info(c) | {"code": c} for c in K.ORIENTATION_LANGS]
    return render_template("public/orientation.html", settings=settings, by_lang=by_lang, vids=vids, langs=langs)


# ---- notices / schedule / partners / contact --------------------------------

@bp.route("/notices")
def notices():
    cat = request.args.get("cat") or ""
    sql = "SELECT * FROM notices WHERE published = 1 AND (publish_at IS NULL OR publish_at <= ?)"
    args = [utcnow()]
    if cat:
        sql += " AND category = ?"
        args.append(cat)
    sql += " ORDER BY pinned DESC, created_at DESC"
    rows = query(sql, args)
    cats = [r["category"] for r in query("SELECT DISTINCT category FROM notices WHERE published = 1 ORDER BY category")]
    return render_template("public/notices.html", rows=rows, cat=cat, cats=cats)


@bp.route("/notices/<int:nid>")
def notice(nid):
    row = query("SELECT * FROM notices WHERE id = ? AND published = 1", (nid,), one=True)
    if row is None:
        abort(404)
    return render_template("public/notice.html", n=row)


@bp.route("/schedule")
def schedule():
    today = now_ist().strftime("%Y-%m-%dT00:00")
    upcoming = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id "
                     "WHERE e.published = 1 AND e.starts_at >= ? ORDER BY e.starts_at", (today,))
    past = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id "
                 "WHERE e.published = 1 AND e.starts_at < ? ORDER BY e.starts_at DESC LIMIT 50", (today,))
    return render_template("public/schedule.html", upcoming=upcoming, past=past, settings=all_settings(),
                           dates=_key_dates(all_settings()))


@bp.route("/partners")
def partners():
    rows = query("SELECT * FROM agencies WHERE active = 1 ORDER BY sort_order, name")
    return render_template("public/partners.html", rows=rows)


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    settings = all_settings()
    sent = False
    errors = {}
    data = {}
    if request.method == "POST":
        data = {k: (request.form.get(k) or "").strip() for k in ("name", "email", "phone", "subject", "body", "topic")}
        if not data["name"]:
            errors["name"] = t("reg.err_required")
        if not valid_email(data["email"]):
            errors["email"] = t("reg.err_email")
        if not data["subject"] or not data["body"]:
            errors["body"] = t("reg.err_required")
        if not check_captcha(request.form.get("captcha")) or request.form.get("website"):
            errors["captcha"] = t("reg.err_captcha")
        if not errors and not limiter.allow("contact", client_ip(), 5, 3600):
            errors["captcha"] = t("reg.err_rate")
        if not errors:
            execute("INSERT INTO messages(name, email, phone, subject, body, topic, ip, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (data["name"], data["email"], data["phone"], data["subject"], data["body"],
                     data["topic"] or "general", client_ip(), utcnow()))
            sent = True
            data = {}
    return render_template("public/contact.html", settings=settings, sent=sent, errors=errors, data=data,
                           captcha=new_captcha())


@bp.route("/healthz")
def healthz():
    query("SELECT 1")
    return {"ok": True, "time": utcnow()}


@bp.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /console/\nDisallow: /candidate/\nDisallow: /hub/\n", mimetype="text/plain")

"""
Public site: home, programme, registration, status, repository, notices.
"""
import json
import posixpath
import time
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

from markupsafe import escape

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)

from . import kural as K
from .db import all_settings, audit, execute, get_setting, query, utcnow
from . import i18n
from .i18n import get_lang, t
from .utils import (DOC_EXT, IMAGE_EXT, age_on, check_captcha, client_ip, college_key, csv_bytes,
                    exam_window, fmt_date, limiter, make_app_no, new_captcha, now_ist, plain_english,
                    qr_data_uri, registration_state, save_upload, send_mail, valid_email, valid_mobile,
                    valid_pincode)
from .version import RELEASED, VERSION

bp = Blueprint("public", __name__)

# Dates that may be typed into the address of the Daily Kural and its calendar.
FIRST_DAY, LAST_DAY = date(2020, 1, 1), date(2100, 12, 31)


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
        "kts_start": _iso_day(settings.get("kts.start")),
        "kts_end": _iso_day(settings.get("kts.end")),
    }


def _iso_day(value):
    """The day as YYYY-MM-DD, or None when the setting is empty or cannot be read."""
    try:
        return datetime.fromisoformat((value or "")[:10]).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _timeline(settings):
    """
    (upcoming, past) of the programme: the published events, and with them the dates that are
    kept as settings (registration opens and closes, the test, the Sangamam begins and ends), so
    that each of those stands in one place only. An event of several days is upcoming until its
    last day is over.
    """
    rows = [dict(r) for r in query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a "
                                   "ON a.id = e.agency_id WHERE e.published = 1 ORDER BY e.starts_at, e.id")]
    fixed = [(key, kind, day + "T00:00", None)
             for key, kind, day in (("timeline.reg_open", "registration", _iso_day(settings.get("reg.start"))),
                                    ("timeline.reg_close", "registration", _iso_day(settings.get("reg.end"))),
                                    ("timeline.inauguration", "general", _iso_day(settings.get("kts.start"))),
                                    ("timeline.valedictory", "general", _iso_day(settings.get("kts.end")))) if day]
    start, end, _ = exam_window(settings)
    if start and end:
        fixed.append(("timeline.exam", "examination", start.strftime("%Y-%m-%dT%H:%M"), end.strftime("%Y-%m-%dT%H:%M")))
    for key, kind, starts_at, ends_at in fixed:
        rows.append({"id": None, "title": i18n.text(key, "en"), "description": "", "kind": kind, "lang": "",
                     "starts_at": starts_at, "ends_at": ends_at, "venue": "", "link": "", "agency": None})
    rows.sort(key=lambda r: r["starts_at"])
    today = now_ist().strftime("%Y-%m-%dT00:00")
    upcoming = [r for r in rows if (r["ends_at"] or r["starts_at"]) >= today]
    past = [r for r in rows if (r["ends_at"] or r["starts_at"]) < today]
    return upcoming, past[::-1][:50]


def _stream(requested=None):
    """(stream, direction) of the corpus to show: the one asked for, else that of the interface language."""
    stream = requested or i18n.corpus_lang()
    info = K.lang_info(stream)
    if not info:
        stream, info = "en", K.lang_info("en")
    return stream, info.get("dir", "ltr")


def _day(value):
    """The date asked for; today when there is none or it cannot be read or is out of range."""
    try:
        day = date.fromisoformat(value) if value else date.today()
    except ValueError:
        return date.today()
    return day if FIRST_DAY <= day <= LAST_DAY else date.today()


def _page_before():
    """
    Path and query of the page on which the language was chosen, or None. Only a page of the
    portal itself counts, and never more than path and query is taken from the Referer header.
    'lang' is taken out of the query: left there it would win over the language just chosen.
    """
    try:
        ref = urlsplit(request.referrer or "")
    except ValueError:
        return None
    # Behind a web server that sets a Host header of its own (ARR, nginx) the visitor names the
    # portal as BASE_URL does, not as request.host.
    hosts = {request.host.lower()}
    try:
        hosts.add(urlsplit(current_app.config["BASE_URL"]).netloc.lower())
    except ValueError:
        pass
    if ref.scheme not in ("http", "https") or not ref.netloc or ref.netloc.lower() not in hosts:
        return None
    path = ref.path or "/"
    if not path.startswith("/") or path.startswith(("//", "/\\")):
        return None
    if any(ord(c) < 32 for c in path + ref.query):
        return None
    root = request.script_root  # the path prefix, when the portal is served under one
    if root and path != root and not path.startswith(root + "/"):
        return None
    own = url_for("public.set_lang")
    if path == own or path.startswith(own + "/"):
        return None
    kept = [part for part in ref.query.split("&") if part and unquote_plus(part.split("=", 1)[0]) != "lang"]
    return path + ("?" + "&".join(kept) if kept else "")


@bp.route("/lang")
@bp.route("/lang/<code>")
def set_lang(code=None):
    """Choose the interface language: /lang/bn, or /lang?code=bn from the menu."""
    code = code or request.args.get("code") or ""
    resp = redirect(_page_before() or url_for("public.home"))
    if i18n.offered(code):
        session["lang"] = code
        resp.set_cookie("lang", code, max_age=60 * 60 * 24 * 365, path="/", samesite="Lax", httponly=True,
                        secure=current_app.config["SESSION_COOKIE_SECURE"])
    return resp


@bp.route("/")
def home():
    settings = all_settings()
    lang = get_lang()
    notices = query("SELECT * FROM notices WHERE published = 1 AND (publish_at IS NULL OR publish_at <= ?) "
                    "ORDER BY pinned DESC, created_at DESC LIMIT 5", (utcnow(),))
    events = _timeline(settings)[0][:4]
    agencies = query("SELECT * FROM agencies WHERE active = 1 ORDER BY sort_order, name")
    stats = None
    if settings.get("stats.public") == "1":
        row = query("SELECT COUNT(*) AS n, COUNT(DISTINCT college_key) AS c, COUNT(DISTINCT state) AS s "
                    "FROM applications WHERE status != 'withdrawn'", one=True)
        stats = {"apps": row["n"], "colleges": row["c"], "states": row["s"]}
    k = K.daily()
    kotd_lang, kotd_dir = _stream()
    if not K.lines(k, kotd_lang):
        kotd_lang, kotd_dir = "en", "ltr"
    return render_template("public/home.html", settings=settings, dates=_key_dates(settings),
                           notices=notices, events=events, agencies=agencies, stats=stats,
                           kotd=k, kotd_lines=K.lines(k, kotd_lang), kotd_lang=kotd_lang, kotd_dir=kotd_dir,
                           featured=query("SELECT * FROM resources WHERE published = 1 AND featured = 1 "
                                          "ORDER BY sort_order, created_at DESC LIMIT 6"))


@bp.route("/about")
def about():
    return render_template("public/about.html")


@lru_cache(maxsize=1)
def reels():
    """
    The short videos of CICT on YouTube in which the Thirukkural is explained in another language
    (data/reels.json, in the order of the list of CICT), grouped by language.
    """
    rows = json.loads((current_app.config["DATA_DIR"] / "reels.json").read_text(encoding="utf-8"))
    groups = {}
    for row in rows:
        group = groups.setdefault(row["lang"], {"name": row["lang"], "native": row["native"], "videos": []})
        group["videos"].append({"id": row["id"], "presenter": row["presenter"]})
    return {"count": len(rows), "langs": tuple(groups.values())}


@bp.route("/programme")
def programme():
    return render_template("public/programme.html", settings=all_settings(), reels=reels())


@bp.route("/stipend")
def stipend_guide():
    """
    How the selected students give their bank details for the stipend (the form itself is
    /candidate/bank). The page says whether the form is open: it opens for the selected
    students once the merit list is published and the setting stipend.open is on.
    """
    settings = all_settings()
    last = _iso_day(settings.get("stipend.last_date"))
    if settings.get("merit.published") != "1" or settings.get("stipend.open") != "1":
        state = "wait"
    elif last and now_ist().strftime("%Y-%m-%d") > last:
        state = "closed"
    else:
        state = "open"
    return render_template("public/stipend.html", state=state, last_date=last,
                           aadhaar=settings.get("stipend.aadhaar") == "1")


# ---- registration -----------------------------------------------------------

FIELDS = [
    "full_name", "gender", "dob", "category", "mobile", "whatsapp", "email", "address", "state",
    "district", "pincode", "college_name", "aishe_code", "college_type", "college_state",
    "college_district", "university", "course_level", "discipline", "year_of_study", "roll_no",
    "mother_tongue", "pref_lang", "tamil_level", "kural_level", "mentor_name",
    "mentor_designation", "mentor_email", "mentor_phone",
]
# the Faculty Supervisor/Guide is named in the nomination of the institution (1.2.22)
REQUIRED = ["full_name", "gender", "dob", "mobile", "email", "state", "college_name",
            "college_type", "college_state", "course_level", "year_of_study", "pref_lang",
            "mentor_name", "mentor_designation", "mentor_email", "mentor_phone"]
# Written by the applicant; every applicant fills them in English, whatever the language of the page
ENGLISH = ["full_name", "address", "district", "college_name", "aishe_code", "college_district", "university",
           "discipline", "roll_no", "mentor_name", "mentor_designation"]


def _validate(form, files):
    errors = {}
    data = {f: (form.get(f) or "").strip() for f in FIELDS}
    data["pwd"] = 1 if form.get("pwd") == "1" else 0
    for f in ENGLISH:
        data[f], english = plain_english(data[f])
        if not english:
            errors[f] = t("reg.err_english")
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


def _discard(*saved):
    """Remove what save_upload has stored for a request that is refused after all."""
    folder = Path(current_app.config["UPLOAD_DIR"])
    for item in saved:
        if item:
            try:
                (folder / item[0]).unlink()
            except OSError:
                pass


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
        # asked before a file is stored: a refused request leaves nothing in the upload folder
        refused = not errors and limiter.blocked("register", ip, current_app.config["RATE_REGISTER_PER_HOUR"], 3600)
        photo = idproof = nomination = None
        if not errors and not refused:
            try:
                photo = save_upload(request.files.get("photo"), "photos", IMAGE_EXT, current_app.config["PHOTO_MAX_BYTES"])
            except ValueError:
                errors["photo"] = t("reg.err_photo")
            try:
                idproof = save_upload(request.files.get("idproof"), "idproofs", DOC_EXT, current_app.config["IDPROOF_MAX_BYTES"])
            except ValueError:
                errors["idproof"] = t("reg.err_idproof")
            try:
                nomination = save_upload(request.files.get("nomination"), "nominations", DOC_EXT,
                                         current_app.config["NOMINATION_MAX_BYTES"])
            except ValueError:
                errors["nomination"] = t("reg.err_nomination")
            if errors:
                _discard(photo, idproof, nomination)
        if errors or refused:
            # the limit is no mistake of the applicant: it is said at the top and no field is marked
            flash(t("reg.err_rate") if refused else t("reg.err_fix"), "error")
            ctx.update(data=data, errors=errors, captcha=new_captcha())
            return render_template("public/register.html", **ctx), 400

        now = utcnow()
        data["college_key"] = college_key(data["college_name"], data["college_state"], data["aishe_code"])
        cols = FIELDS + ["pwd", "college_key", "photo_path", "idproof_path", "nomination_path", "ip", "created_at", "updated_at", "status"]
        values = [data[f] for f in FIELDS] + [data["pwd"], data["college_key"], photo[0], idproof[0], nomination[0], ip, now, now, "submitted"]
        row_id = execute(f"INSERT INTO applications({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", values)
        app_no = make_app_no(row_id)
        execute("UPDATE applications SET app_no = ? WHERE id = ?", (app_no, row_id))
        limiter.hit("register", ip, 3600)  # only applications that were stored are counted
        audit("application_submitted", "application", row_id, detail=app_no, ip=ip)
        from .certificate import certificate_link
        cert = certificate_link(query("SELECT * FROM applications WHERE id = ?", (row_id,), one=True), external=True)
        send_mail(
            data["email"],
            f"KTS 5.0 application received: {app_no}",
            f"Dear {data['full_name']},\n\nYour application for Kashi Tamil Sangamam 5.0 (Thirukkural Payilvom) "
            f"has been received.\n\nApplication number: {app_no}\nInstitution: {data['college_name']}\n"
            f"Language chosen: {K.lang_info(data['pref_lang'])['name']}\n\n"
            f"Keep this number safe. Use it with your date of birth and mobile number to check your status "
            f"and to sign in for the online test at {current_app.config['BASE_URL']}/status\n\n"
            + (f"Your certificate of recognition, signed by the Director of CICT, can be printed or saved as PDF "
               f"from {cert}\n\n" if cert else "")
            + "Central Institute of Classical Tamil, Chennai",
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
        # Only look-ups that found nothing are counted: per address, and per application number
        # and address together as at the candidates' sign-in, whose details this page compares
        # as well. The bucket is the page's own: mistakes made here do not close the sign-in.
        ip = client_ip()
        app_no = (request.form.get("app_no") or "").strip().upper()
        number_here = f"{app_no[:32]}|{ip}"
        if (limiter.blocked("status", ip, current_app.config["RATE_STATUS_FAILS_PER_15MIN"], 15 * 60)
                or limiter.blocked("status_app", number_here, current_app.config["RATE_CAND_FAILS_APP_PER_15MIN"], 15 * 60)):
            error = t("reg.err_rate")
        else:
            dob = (request.form.get("dob") or "").strip()
            last4 = (request.form.get("last4") or "").strip()
            row = query("SELECT * FROM applications WHERE app_no = ? AND dob = ? AND substr(mobile, -4) = ?",
                        (app_no, dob, last4), one=True)
            if row is None:
                limiter.hit("status", ip, 15 * 60)
                limiter.hit("status_app", number_here, 15 * 60)
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

# the videos of CICT on the Thirukkural, on Thiruvalluvar and in Indian Sign Language have tabs of their own
CATEGORIES = ["translation", "publication", "app", "corpus", "video", "video_kural", "video_valluvar", "video_sign",
              "audio", "music", "film", "comic", "poster", "daily", "story", "study", "link"]


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
    return render_template("public/resources.html", rows=rows, cat=cat, flang=lang, q=q,
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
        # an address of the portal itself (written /static/...) keeps the path prefix of the portal
        return redirect(request.script_root + row["url"] if row["url"].startswith("/") else row["url"])
    abort(404)


@bp.route("/files/<path:relpath>")
def public_file(relpath):
    """Public attachments (notices, resources, shared documents marked public)."""
    # the folder is tested on the path as it will be opened: "notices/../photos/x" is "photos/x"
    relpath = posixpath.normpath(relpath)
    if not relpath.startswith(("notices/", "resources/", "gallery/")):
        abort(404)
    if relpath.startswith("gallery/") and not query("SELECT 1 FROM gallery_photos WHERE file_path = ? AND published = 1",
                                                     (relpath,), one=True):
        # a photograph that is not published, or one that is gone, is not served
        abort(404)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), relpath)


@bp.route("/thirukkural")
def kural_browser():
    ch = request.args.get("ch", "1")
    try:
        ch_n = max(1, min(133, int(ch)))
    except ValueError:
        ch_n = 1
    stream, stream_dir = _stream(request.args.get("l"))
    chapter = K.chapter(ch_n)
    rows = [(k, K.lines(k, stream)) for k in chapter["kurals"]]
    return render_template("public/kural.html", chapter=chapter, rows=rows, stream=stream, stream_dir=stream_dir,
                           langs=K.languages(), chapters=K.chapters(), pals=K.corpus()["meta"]["pals"],
                           variants=K.VARIANTS)


@bp.route("/thirukkural/<int:n>")
def kural_single(n):
    k = K.kural(n)
    if k is None:
        abort(404)
    streams = []
    # the script variants too: the Kashmiri and Konkani interfaces show exactly those in the browser
    for info in K.languages(variants=True):
        ln = K.lines(k, info["code"])
        if ln:
            streams.append((info, ln))
    return render_template("public/kural_single.html", k=k, streams=streams,
                           prose=(k.get("prose") or {}) if isinstance(k.get("prose"), dict) else {})


@bp.route("/daily-kural")
def daily_kural():
    stream, stream_dir = _stream(request.args.get("l"))
    day = _day(request.args.get("d"))
    k = K.daily(day)
    # `stream` stays the choice in the menu; the text falls back to English as on the home page
    shown, shown_dir = stream, stream_dir
    if not K.lines(k, shown):
        shown, shown_dir = "en", "ltr"
    return render_template("public/daily.html", k=k, day=day, stream=stream, stream_dir=stream_dir,
                           shown=shown, shown_dir=shown_dir, lines=K.lines(k, shown),
                           langs=K.languages(), variants=K.VARIANTS, n=K.daily_number(day))


@bp.route("/daily-kural/calendar.csv")
def daily_calendar():
    lang, _ = _stream(request.args.get("l"))
    start = _day(request.args.get("start"))
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
    settings = all_settings()
    upcoming, past = _timeline(settings)
    return render_template("public/schedule.html", upcoming=upcoming, past=past, settings=settings,
                           dates=_key_dates(settings))


@lru_cache(maxsize=1)
def nodal_heis():
    """The State/UT-wise Nodal Higher Educational Institutions (data/nodal_heis.json), as the Ministry listed them."""
    return tuple(json.loads((current_app.config["DATA_DIR"] / "nodal_heis.json").read_text(encoding="utf-8")))


@bp.route("/partners")
def partners():
    rows = query("SELECT * FROM agencies WHERE active = 1 ORDER BY sort_order, name")
    return render_template("public/partners.html", rows=rows, nodal=nodal_heis())


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
        refused = not errors and not limiter.allow("contact", client_ip(), current_app.config["RATE_CONTACT_PER_HOUR"], 3600)
        if refused:
            # the limit is no mistake of the visitor: it is said at the top and no field is marked
            flash(t("reg.err_rate"), "error")
        elif not errors:
            mid = execute("INSERT INTO messages(name, email, phone, subject, body, topic, ip, created_at) VALUES(?,?,?,?,?,?,?,?)",
                          (data["name"], data["email"], data["phone"], data["subject"], data["body"],
                           data["topic"] or "general", client_ip(), utcnow()))
            _notify_helpdesk(settings, mid, data)
            sent = True
            data = {}
    return render_template("public/contact.html", settings=settings, sent=sent, errors=errors, data=data,
                           captcha=new_captcha())


def _notify_helpdesk(settings, mid, data):
    """
    The message as an e-mail to the helpdesk address of the settings, so that nobody has to
    watch the console for it. The visitor's address stands in the body and not as the sender:
    the portal sends from its own account; a reply goes to the visitor from the helpdesk's own
    mail. Nothing is sent when the address is empty or not an address.
    """
    to = (settings.get("contact.notify") or "").strip()
    if not valid_email(to):
        return
    link = f"{current_app.config['BASE_URL'].rstrip('/')}/console/messages"
    body = "\n".join([
        f"A message has come through the contact form of the KTS 5.0 portal (no. {mid}).",
        "",
        f"From: {data['name']} <{data['email']}>" + (f", {data['phone']}" if data["phone"] else ""),
        f"Topic: {data['topic'] or 'general'}",
        f"Subject: {data['subject']}",
        "",
        data["body"],
        "",
        f"Reply to the visitor at {data['email']}. The message is kept in the console: {link}",
    ])
    send_mail(to, f"[KTS 5.0 contact] {data['subject'][:120]}", body)


@bp.route("/healthz")
def healthz():
    query("SELECT 1")
    return {"ok": True, "time": utcnow(), "version": VERSION}


@bp.route("/robots.txt")
def robots():
    # /lang/<code> only switches the language and leads back to the page the visitor came from
    base = current_app.config["BASE_URL"].rstrip("/")
    return Response("User-agent: *\nDisallow: /console/\nDisallow: /candidate/\nDisallow: /hub/\nDisallow: /lang\n"
                    f"Sitemap: {base}/sitemap.xml\n", mimetype="text/plain")


# ---- website policies, help and sitemap (GIGW 3.0, version 1.2.34) -------------------------------------

POLICY_PAGES = {"terms": "/terms-of-use", "privacy": "/privacy-policy", "copyright": "/copyright-policy",
                "hyperlinking": "/hyperlinking-policy", "accessibility": "/accessibility-statement", "help": "/help",
                "sitemap": "/sitemap"}
# the texts of the policies are written in these languages (templates/public/policies/<page>.<lang>.html);
# in the other interface languages the English text is shown, with a note in the language of the page
POLICY_LANGS = ("en", "hi", "ta")

# the sitemap: (heading, [(endpoint, arguments, label)]), the public pages only
SITEMAP = [
    ("pol.sm_programme", [("public.home", {}, "nav.home"), ("public.about", {}, "nav.about"),
                          ("public.programme", {}, "nav.programme"), ("public.schedule", {}, "nav.schedule"),
                          ("public.notices", {}, "nav.notices"), ("public.partners", {}, "nav.partners"),
                          ("public.gallery", {}, "nav.gallery"), ("public.contact", {}, "nav.contact")]),
    ("pol.sm_students", [("public.register", {}, "nav.register"), ("public.status", {}, "nav.status"),
                         ("public.examination", {}, "nav.exam"), ("public.merit", {}, "nav.merit"),
                         ("public.stipend_guide", {}, "stip.title"), ("candidate.login", {}, "nav.candidate")]),
    ("pol.sm_learning", [("public.orientation", {}, "nav.orientation"), ("public.resources", {}, "nav.resources"),
                         ("public.kural_browser", {}, "nav.kural"), ("public.daily_kural", {}, "nav.daily"),
                         ("quiz.join", {}, "quiz.title")]),
    ("pol.sm_help", [("public.policy", {"page": p}, "pol." + p) for p in POLICY_PAGES if p != "sitemap"]),
]


def site_updated():
    """
    The day on which the portal last changed, for the line "Last updated" (GIGW): the day of the
    release, or a later day on which a notice, an entry of the repository, an event or a photograph
    was published or changed. Worked out at most every five minutes.
    """
    cache = current_app.extensions.setdefault("kts_updated", {})
    moment = time.monotonic()
    if cache.get("at") is not None and moment - cache["at"] < 300:
        return cache["day"]
    days = [RELEASED]
    for table, column in (("notices", "updated_at"), ("resources", "updated_at"), ("events", "updated_at"),
                          ("gallery_photos", "created_at")):
        row = query(f"SELECT MAX({column}) AS d FROM {table} WHERE published = 1", one=True)
        if row and row["d"]:
            days.append(str(row["d"])[:10])
    cache.update(at=moment, day=max(days))
    return cache["day"]


def policy(page):
    if page == "sitemap":
        groups = [(heading, [(url_for(ep, **args), label) for ep, args, label in links]) for heading, links in SITEMAP]
        return render_template("public/sitemap.html", page=page, groups=groups, updated=site_updated())
    lang = get_lang()
    return render_template("public/policy.html", page=page, body_lang=lang if lang in POLICY_LANGS else "en",
                           settings=all_settings(), updated=site_updated())


for _page, _path in POLICY_PAGES.items():
    bp.add_url_rule(_path, "policy", policy, defaults={"page": _page})


@bp.route("/sitemap.xml")
def sitemap_xml():
    """The public pages for search engines; each page carries all the languages (?lang=)."""
    base = current_app.config["BASE_URL"].rstrip("/")
    day = site_updated()
    paths = [url_for(ep, **args) for _heading, links in SITEMAP for ep, args, _label in links]
    paths.append(url_for("public.policy", page="sitemap"))
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in dict.fromkeys(paths):
        body.append(f"  <url><loc>{escape(base + path)}</loc><lastmod>{day}</lastmod></url>")
    body.append("</urlset>")
    return Response("\n".join(body) + "\n", mimetype="application/xml")


@bp.route("/favicon.ico")
def favicon():
    """Browsers and crawlers ask for this address by themselves; the pages name static/img/favicon.png."""
    return send_from_directory(Path(current_app.static_folder) / "img", "favicon.png", mimetype="image/png",
                               max_age=24 * 60 * 60)

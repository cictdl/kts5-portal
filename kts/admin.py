"""
Administration console: applications, verification, question bank, exam
monitoring, selection and merit list, content, users, settings, audit.
"""
import csv
import io
import json
import secrets
from datetime import timedelta
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template,
                   request, send_from_directory, url_for)
from werkzeug.security import generate_password_hash

from . import kural as K
from .auth import PERMS, ROLES, current_user, has_perm, login_required
from .db import (DEFAULT_SETTINGS, all_settings, audit, execute, executemany, get_setting, query,
                 set_setting, utcnow)
from .public import CATEGORIES
from .utils import (RESOURCE_EXT, client_ip, csv_bytes, exam_window, now_ist, paginate, parse_iso,
                    registration_state, safe_int, save_upload, send_mail, xlsx_bytes)

bp = Blueprint("admin", __name__, url_prefix="/console")

APP_STATUSES = ["submitted", "verified", "rejected", "selected", "waitlisted", "not_selected", "withdrawn"]
NOTICE_CATS = ["general", "registration", "examination", "orientation", "merit", "conference", "circular", "press"]
EVENT_KINDS = ["general", "registration", "examination", "orientation", "conference", "internship", "cultural", "display", "meeting"]


def _user():
    return current_user()


def _states():
    data = json.loads((current_app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
    return data["states"] + data["union_territories"]


# ---- dashboard --------------------------------------------------------------

@bp.route("/")
@login_required("dashboard")
def dashboard():
    user = _user()
    if user["role"] == "agency":
        return redirect(url_for("agency.home"))
    settings = all_settings()
    by_status = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM applications GROUP BY status")}
    total = sum(by_status.values())
    colleges = query("SELECT COUNT(DISTINCT college_key) AS n FROM applications WHERE status != 'withdrawn'", one=True)["n"]
    states = query("SELECT COUNT(DISTINCT college_state) AS n FROM applications WHERE status != 'withdrawn'", one=True)["n"]
    since = (now_ist() - timedelta(days=29)).strftime("%Y-%m-%d")
    per_day_rows = query("SELECT substr(created_at, 1, 10) AS d, COUNT(*) AS n FROM applications "
                         "WHERE created_at >= ? GROUP BY d ORDER BY d", (since,))
    per_day = {r["d"]: r["n"] for r in per_day_rows}
    days = []
    for i in range(29, -1, -1):
        d = (now_ist() - timedelta(days=i)).strftime("%Y-%m-%d")
        days.append((d, per_day.get(d, 0)))
    max_day = max([n for _, n in days] + [1])
    top_states = query("SELECT college_state AS s, COUNT(*) AS n FROM applications WHERE status != 'withdrawn' "
                       "GROUP BY college_state ORDER BY n DESC LIMIT 10")
    by_lang = query("SELECT pref_lang AS l, COUNT(*) AS n FROM applications WHERE status != 'withdrawn' "
                    "GROUP BY pref_lang ORDER BY n DESC")
    exam = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM exam_sessions GROUP BY status")}
    qbank = query("SELECT lang, COUNT(*) AS n FROM questions WHERE active = 1 GROUP BY lang ORDER BY lang")
    tasks = query("SELECT t.status, COUNT(*) AS n FROM tasks t GROUP BY t.status")
    overdue = query("SELECT COUNT(*) AS n FROM tasks WHERE status NOT IN ('done') AND due_date IS NOT NULL AND due_date < ?",
                    (now_ist().strftime("%Y-%m-%d"),), one=True)["n"]
    messages = query("SELECT COUNT(*) AS n FROM messages WHERE handled = 0", one=True)["n"]
    recent = query("SELECT * FROM audit_log ORDER BY id DESC LIMIT 12")
    start, end, is_open = exam_window(settings)
    return render_template("console/dashboard.html", settings=settings, by_status=by_status, total=total,
                           colleges=colleges, states=states, days=days, max_day=max_day, top_states=top_states,
                           by_lang=by_lang, exam=exam, qbank=qbank, tasks={r["status"]: r["n"] for r in tasks},
                           overdue=overdue, messages=messages, recent=recent, reg_state=registration_state(settings),
                           exam_start=start, exam_end=end, exam_open=is_open)


# ---- applications -----------------------------------------------------------

def _app_filters():
    f = {k: (request.args.get(k) or "").strip() for k in ("status", "state", "lang", "q", "college", "exam")}
    sql = " FROM applications a WHERE 1=1"
    args = []
    if f["status"]:
        sql += " AND a.status = ?"
        args.append(f["status"])
    if f["state"]:
        sql += " AND a.college_state = ?"
        args.append(f["state"])
    if f["lang"]:
        sql += " AND a.pref_lang = ?"
        args.append(f["lang"])
    if f["college"]:
        sql += " AND a.college_name LIKE ?"
        args.append(f"%{f['college']}%")
    if f["q"]:
        sql += " AND (a.full_name LIKE ? OR a.email LIKE ? OR a.mobile LIKE ? OR a.app_no LIKE ? OR a.aishe_code LIKE ?)"
        args += [f"%{f['q']}%"] * 5
    if f["exam"] == "done":
        sql += " AND a.exam_score IS NOT NULL"
    elif f["exam"] == "pending":
        sql += " AND a.exam_score IS NULL"
    return f, sql, args


@bp.route("/applications")
@login_required("apps.view")
def applications():
    f, sql, args = _app_filters()
    total = query("SELECT COUNT(*) AS n" + sql, args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 50)
    rows = query("SELECT a.*" + sql + " ORDER BY a.id DESC LIMIT ? OFFSET ?", args + [pg["per_page"], pg["offset"]])
    return render_template("console/applications.html", rows=rows, f=f, pg=pg, statuses=APP_STATUSES,
                           states=_states(), langs=K.ORIENTATION_LANGS)


@bp.route("/applications/export.<fmt>")
@login_required("apps.export")
def applications_export(fmt):
    f, sql, args = _app_filters()
    rows = query("SELECT a.*" + sql + " ORDER BY a.id", args)
    headers = ["App No", "Status", "Name", "Gender", "DOB", "Category", "PwD", "Mobile", "WhatsApp", "Email",
               "Address", "State", "District", "PIN", "College", "AISHE", "College type", "College state",
               "College district", "University", "Level", "Discipline", "Year", "Roll no", "Mother tongue",
               "Language", "Tamil level", "Kural level", "Mentor", "Mentor designation", "Mentor email",
               "Mentor phone", "Exam score", "Rank", "Remarks", "Submitted"]
    data = [(r["app_no"], r["status"], r["full_name"], r["gender"], r["dob"], r["category"], r["pwd"], r["mobile"],
             r["whatsapp"], r["email"], r["address"], r["state"], r["district"], r["pincode"], r["college_name"],
             r["aishe_code"], r["college_type"], r["college_state"], r["college_district"], r["university"],
             r["course_level"], r["discipline"], r["year_of_study"], r["roll_no"], r["mother_tongue"],
             r["pref_lang"], r["tamil_level"], r["kural_level"], r["mentor_name"], r["mentor_designation"],
             r["mentor_email"], r["mentor_phone"], r["exam_score"], r["exam_rank"], r["remarks"], r["created_at"])
            for r in rows]
    audit("export_applications", "application", None, detail={"count": len(data), "fmt": fmt}, user=_user(), ip=client_ip())
    stamp = now_ist().strftime("%Y%m%d-%H%M")
    if fmt == "xlsx":
        return Response(xlsx_bytes(headers, data, "Applications"),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=KTS5-applications-{stamp}.xlsx"})
    return Response(csv_bytes(headers, data), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=KTS5-applications-{stamp}.csv"})


@bp.route("/applications/<int:aid>", methods=["GET", "POST"])
@login_required("apps.view")
def application(aid):
    row = query("SELECT * FROM applications WHERE id = ?", (aid,), one=True)
    if row is None:
        abort(404)
    user = _user()
    if request.method == "POST":
        if not has_perm(user, "apps.verify"):
            abort(403)
        action = request.form.get("action")
        note = (request.form.get("remarks") or "").strip()
        now = utcnow()
        if action in ("verify", "reject"):
            new_status = "verified" if action == "verify" else "rejected"
            execute("UPDATE applications SET status = ?, remarks = ?, verified_by = ?, verified_at = ?, updated_at = ? WHERE id = ?",
                    (new_status, note, user["id"], now, now, aid))
            audit(f"application_{new_status}", "application", aid, detail=note, user=user, ip=client_ip())
            if new_status == "verified":
                settings = all_settings()
                send_mail(row["email"], f"KTS 5.0: application {row['app_no']} verified",
                          f"Dear {row['full_name']},\n\nYour application {row['app_no']} has been verified. "
                          f"You are eligible for the online selection test on {settings['exam.date']} "
                          f"({settings['exam.start_time']}–{settings['exam.end_time']} IST).\n\n"
                          f"Sign in at {current_app.config['BASE_URL']}/candidate/login with your application number, "
                          f"date of birth and the last four digits of your mobile number.\n\nCICT, Chennai")
            flash(f"Application {row['app_no']} marked {new_status}.", "success")
        elif action == "note":
            execute("UPDATE applications SET remarks = ?, updated_at = ? WHERE id = ?", (note, now, aid))
            audit("application_note", "application", aid, detail=note, user=user, ip=client_ip())
            flash("Remarks saved.", "success")
        elif action == "withdraw":
            execute("UPDATE applications SET status = 'withdrawn', withdrawn_at = ?, remarks = ?, updated_at = ? WHERE id = ?",
                    (now, note, now, aid))
            audit("application_withdrawn", "application", aid, detail=note, user=user, ip=client_ip())
            flash("Application withdrawn.", "success")
        elif action == "reset_exam" and has_perm(user, "exam.manage"):
            execute("DELETE FROM exam_sessions WHERE application_id = ?", (aid,))
            execute("UPDATE applications SET exam_score = NULL, exam_rank = NULL, updated_at = ? WHERE id = ?", (now, aid))
            audit("exam_reset", "application", aid, detail=note, user=user, ip=client_ip())
            flash("Test attempt cleared; the candidate may take the test again.", "warning")
        return redirect(url_for("admin.application", aid=aid))
    exam = query("SELECT * FROM exam_sessions WHERE application_id = ?", (aid,), one=True)
    same_college = query("SELECT id, app_no, full_name, status, exam_score FROM applications WHERE college_key = ? AND id != ? ORDER BY id",
                         (row["college_key"], aid))
    history = query("SELECT * FROM audit_log WHERE entity = 'application' AND entity_id = ? ORDER BY id DESC LIMIT 30", (aid,))
    verifier = query("SELECT name FROM users WHERE id = ?", (row["verified_by"],), one=True) if row["verified_by"] else None
    merit = query("SELECT * FROM merit_list WHERE application_id = ?", (aid,), one=True)
    return render_template("console/application.html", a=row, exam=exam, same_college=same_college, history=history,
                           verifier=verifier, merit=merit, lang_name=K.lang_label(row["pref_lang"]))


@bp.route("/applications/bulk", methods=["POST"])
@login_required("apps.verify")
def applications_bulk():
    ids = [safe_int(i) for i in request.form.getlist("ids") if safe_int(i)]
    action = request.form.get("action")
    if ids and action in ("verify", "reject"):
        new_status = "verified" if action == "verify" else "rejected"
        now = utcnow()
        marks = ",".join("?" * len(ids))
        execute(f"UPDATE applications SET status = ?, verified_by = ?, verified_at = ?, updated_at = ? "
                f"WHERE id IN ({marks}) AND status IN ('submitted', 'verified', 'rejected')",
                [new_status, _user()["id"], now, now] + ids)
        audit(f"bulk_{new_status}", "application", None, detail={"ids": ids}, user=_user(), ip=client_ip())
        flash(f"{len(ids)} application(s) marked {new_status}.", "success")
    return redirect(request.referrer or url_for("admin.applications"))


@bp.route("/files/<path:relpath>")
@login_required("dashboard")
def staff_file(relpath):
    user = _user()
    if relpath.startswith(("photos/", "idproofs/")) and not has_perm(user, "apps.view"):
        abort(403)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), relpath)


# ---- question bank ----------------------------------------------------------

@bp.route("/questions")
@login_required("exam.view")
def questions():
    f = {k: (request.args.get(k) or "").strip() for k in ("lang", "qtype", "active", "q")}
    sql = " FROM questions WHERE 1=1"
    args = []
    if f["lang"]:
        sql += " AND lang = ?"
        args.append(f["lang"])
    if f["qtype"]:
        sql += " AND qtype = ?"
        args.append(f["qtype"])
    if f["active"] in ("0", "1"):
        sql += " AND active = ?"
        args.append(int(f["active"]))
    if f["q"]:
        sql += " AND text LIKE ?"
        args.append(f"%{f['q']}%")
    total = query("SELECT COUNT(*) AS n" + sql, args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 40)
    rows = query("SELECT *" + sql + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [pg["per_page"], pg["offset"]])
    counts = query("SELECT lang, SUM(active) AS active, COUNT(*) AS n FROM questions GROUP BY lang ORDER BY lang")
    return render_template("console/questions.html", rows=rows, f=f, pg=pg, counts=counts,
                           langs=["ta"] + K.ORIENTATION_LANGS, qtypes=["complete", "chapter", "section", "gk", "manual"])


@bp.route("/questions/new", methods=["GET", "POST"])
@bp.route("/questions/<int:qid>/edit", methods=["GET", "POST"])
@login_required("exam.manage")
def question_form(qid=None):
    row = query("SELECT * FROM questions WHERE id = ?", (qid,), one=True) if qid else None
    if qid and row is None:
        abort(404)
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("lang", "qtype", "text", "opt_a", "opt_b", "opt_c", "opt_d", "correct", "kural_no", "difficulty")}
        if not all(d[k] for k in ("lang", "text", "opt_a", "opt_b", "opt_c", "opt_d")) or d["correct"] not in ("A", "B", "C", "D"):
            flash("Fill the question, all four options and mark the correct one.", "error")
        else:
            vals = (d["lang"], d["qtype"] or "manual", d["text"], d["opt_a"], d["opt_b"], d["opt_c"], d["opt_d"], d["correct"],
                    safe_int(d["kural_no"]) or None, safe_int(d["difficulty"], 1), 1 if request.form.get("active") else 0)
            if row:
                execute("UPDATE questions SET lang=?, qtype=?, text=?, opt_a=?, opt_b=?, opt_c=?, opt_d=?, correct=?, kural_no=?, difficulty=?, active=? WHERE id=?",
                        vals + (qid,))
                audit("question_updated", "question", qid, user=_user(), ip=client_ip())
            else:
                qid = execute("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,'manual',?)", vals + (utcnow(),))
                audit("question_created", "question", qid, user=_user(), ip=client_ip())
            flash("Question saved.", "success")
            return redirect(url_for("admin.questions", lang=d["lang"]))
    return render_template("console/question_form.html", q=row, langs=["ta"] + K.ORIENTATION_LANGS,
                           qtypes=["manual", "complete", "chapter", "section", "gk"])


@bp.route("/questions/<int:qid>/toggle", methods=["POST"])
@login_required("exam.manage")
def question_toggle(qid):
    execute("UPDATE questions SET active = 1 - active WHERE id = ?", (qid,))
    return redirect(request.referrer or url_for("admin.questions"))


@bp.route("/questions/generate", methods=["POST"])
@login_required("exam.manage")
def questions_generate():
    langs = request.form.getlist("langs") or []
    count = min(max(safe_int(request.form.get("count"), 40), 5), 300)
    if "all" in langs:
        langs = ["ta"] + K.ORIENTATION_LANGS
    made = 0
    for lang in langs:
        if not K.lang_info(lang):
            continue
        seed = f"{lang}-{secrets.token_hex(4)}"
        rows = K.generate_questions(lang, count, seed)
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
        made += len(rows)
    audit("questions_generated", "question", None, detail={"langs": langs, "count": count, "made": made}, user=_user(), ip=client_ip())
    flash(f"Generated {made} questions from the Thirukkural corpus.", "success")
    return redirect(url_for("admin.questions"))


@bp.route("/questions/import", methods=["POST"])
@login_required("exam.manage")
def questions_import():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Upload a CSV file with columns: lang, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty.", "error")
        return redirect(url_for("admin.questions"))
    text = f.read().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows, bad = [], 0
    for r in reader:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("lang") or not r.get("text") or r.get("correct", "").upper() not in ("A", "B", "C", "D"):
            bad += 1
            continue
        rows.append((r["lang"], r.get("qtype") or "manual", r["text"], r.get("opt_a", ""), r.get("opt_b", ""),
                     r.get("opt_c", ""), r.get("opt_d", ""), r["correct"].upper(), safe_int(r.get("kural_no")) or None,
                     safe_int(r.get("difficulty"), 1), utcnow()))
    if rows:
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'import',?)", rows)
    audit("questions_imported", "question", None, detail={"rows": len(rows), "skipped": bad}, user=_user(), ip=client_ip())
    flash(f"Imported {len(rows)} question(s); skipped {bad}.", "success" if rows else "error")
    return redirect(url_for("admin.questions"))


@bp.route("/questions/export.csv")
@login_required("exam.manage")
def questions_export():
    rows = query("SELECT lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active FROM questions ORDER BY lang, id")
    data = csv_bytes(["lang", "qtype", "text", "opt_a", "opt_b", "opt_c", "opt_d", "correct", "kural_no", "difficulty", "active"],
                     [tuple(r) for r in rows])
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=KTS5-question-bank.csv"})


# ---- exam monitor -----------------------------------------------------------

@bp.route("/exam", methods=["GET", "POST"])
@login_required("exam.view")
def exam_monitor():
    settings = all_settings()
    if request.method == "POST" and has_perm(_user(), "exam.manage"):
        action = request.form.get("action")
        if action == "expire_stale":
            from .candidate import _finalise
            stale = query("SELECT * FROM exam_sessions WHERE status = 'in_progress' AND deadline_at < ?",
                          ((now_ist() - timedelta(seconds=45)).isoformat(),))
            for s in stale:
                _finalise(s, "expired")
            flash(f"Closed {len(stale)} overdue session(s).", "success")
        elif action in ("open", "close", "auto"):
            set_setting("exam.open", {"open": "1", "close": "0", "auto": "auto"}[action])
            audit("exam_window_" + action, "settings", None, user=_user(), ip=client_ip())
            flash("Test window updated.", "success")
        return redirect(url_for("admin.exam_monitor"))
    start, end, is_open = exam_window(settings)
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM exam_sessions GROUP BY status")}
    eligible = query("SELECT COUNT(*) AS n FROM applications WHERE status IN ('verified','selected','waitlisted','not_selected')", one=True)["n"]
    by_lang = query("SELECT lang, COUNT(*) AS n, AVG(score) AS avg, MAX(score) AS best FROM exam_sessions WHERE status != 'in_progress' GROUP BY lang ORDER BY n DESC")
    live = query("SELECT s.*, a.app_no, a.full_name FROM exam_sessions s JOIN applications a ON a.id = s.application_id "
                 "WHERE s.status = 'in_progress' ORDER BY s.started_at DESC LIMIT 100")
    recent = query("SELECT s.*, a.app_no, a.full_name, a.college_name FROM exam_sessions s JOIN applications a ON a.id = s.application_id "
                   "WHERE s.status != 'in_progress' ORDER BY s.submitted_at DESC LIMIT 50")
    dist = query("SELECT CAST(score AS INTEGER) AS s, COUNT(*) AS n FROM exam_sessions WHERE status != 'in_progress' GROUP BY s ORDER BY s")
    return render_template("console/exam.html", settings=settings, start=start, end=end, is_open=is_open, counts=counts,
                           eligible=eligible, by_lang=by_lang, live=live, recent=recent, dist=dist, now=now_ist())


@bp.route("/exam/sessions/<int:sid>")
@login_required("exam.view")
def exam_session(sid):
    s = query("SELECT s.*, a.app_no, a.full_name, a.college_name FROM exam_sessions s JOIN applications a ON a.id = s.application_id WHERE s.id = ?",
              (sid,), one=True)
    if s is None:
        abort(404)
    from .candidate import _load_paper
    questions = _load_paper(s)
    answers = json.loads(s["answers_json"] or "{}")
    correct = {r["id"]: r["correct"] for r in query("SELECT id, correct FROM questions WHERE id IN (%s)" % ",".join(str(q["id"]) for q in questions) or "0")} if questions else {}
    return render_template("console/exam_session.html", s=s, questions=questions, answers=answers, correct=correct)


# ---- selection / merit list -------------------------------------------------

def run_selection(select_count, wait_count, user):
    """
    Rank every candidate who submitted the test, keep the best candidate of
    each institution, and mark the top `select_count` as selected, the next
    `wait_count` as waitlisted, the rest as not selected.
    Tie-breaks: higher score, shorter time taken, earlier application.
    """
    rows = query("SELECT a.id, a.college_key, s.score, s.time_taken_sec, a.created_at "
                 "FROM applications a JOIN exam_sessions s ON s.application_id = a.id "
                 "WHERE a.status IN ('verified','selected','waitlisted','not_selected') AND s.status != 'in_progress' "
                 "ORDER BY s.score DESC, s.time_taken_sec ASC, a.created_at ASC")
    seen = set()
    ranked, runners_up = [], []
    for r in rows:
        if r["college_key"] in seen:
            runners_up.append(r)
            continue
        seen.add(r["college_key"])
        ranked.append(r)
    run_id = now_ist().strftime("%Y%m%d-%H%M%S")
    now = utcnow()
    execute("DELETE FROM merit_list")
    execute("UPDATE applications SET exam_rank = NULL, updated_at = ? WHERE status IN ('selected','waitlisted','not_selected')", (now,))
    execute("UPDATE applications SET status = 'verified' WHERE status IN ('selected','waitlisted','not_selected')")
    entries, updates = [], []
    for i, r in enumerate(ranked, start=1):
        outcome = "selected" if i <= select_count else ("waitlisted" if i <= select_count + wait_count else "not_selected")
        entries.append((i, r["id"], r["score"], r["college_key"], outcome, run_id, now))
        updates.append((outcome, i, now, r["id"]))
    for r in runners_up:
        updates.append(("not_selected", None, now, r["id"]))
    if entries:
        executemany("INSERT INTO merit_list(rank, application_id, score, college_key, outcome, run_id, created_at) VALUES(?,?,?,?,?,?,?)", entries)
    if updates:
        executemany("UPDATE applications SET status = ?, exam_rank = ?, updated_at = ? WHERE id = ?", updates)
    audit("selection_run", "merit_list", None,
          detail={"run": run_id, "ranked": len(ranked), "selected": min(select_count, len(ranked)), "runners_up": len(runners_up)},
          user=user, ip=client_ip())
    return run_id, len(ranked), len(runners_up)


@bp.route("/selection", methods=["GET", "POST"])
@login_required("selection")
def selection():
    settings = all_settings()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "run":
            sc = safe_int(request.form.get("select_count"), 1000)
            wc = safe_int(request.form.get("wait_count"), 300)
            set_setting("merit.select_count", str(sc))
            set_setting("merit.wait_count", str(wc))
            run_id, ranked, runners = run_selection(sc, wc, _user())
            flash(f"Selection run {run_id}: {ranked} institutions ranked, {runners} runner-up candidates within the same institutions.", "success")
        elif action == "publish":
            set_setting("merit.published", "1")
            set_setting("merit.note", (request.form.get("note") or "").strip())
            audit("merit_published", "merit_list", None, user=_user(), ip=client_ip())
            flash("Merit list published on the public site.", "success")
        elif action == "unpublish":
            set_setting("merit.published", "0")
            audit("merit_unpublished", "merit_list", None, user=_user(), ip=client_ip())
            flash("Merit list hidden from the public site.", "warning")
        return redirect(url_for("admin.selection"))
    summary = {r["outcome"]: r["n"] for r in query("SELECT outcome, COUNT(*) AS n FROM merit_list GROUP BY outcome")}
    last = query("SELECT run_id, created_at FROM merit_list ORDER BY id DESC LIMIT 1", one=True)
    top = query("SELECT m.rank, m.score, m.outcome, a.app_no, a.full_name, a.college_name, a.college_state, a.pref_lang "
                "FROM merit_list m JOIN applications a ON a.id = m.application_id ORDER BY m.rank LIMIT 100")
    tested = query("SELECT COUNT(*) AS n FROM exam_sessions WHERE status != 'in_progress'", one=True)["n"]
    by_state = query("SELECT a.college_state AS s, SUM(m.outcome = 'selected') AS sel, COUNT(*) AS n "
                     "FROM merit_list m JOIN applications a ON a.id = m.application_id GROUP BY s ORDER BY sel DESC")
    return render_template("console/selection.html", settings=settings, summary=summary, last=last, top=top,
                           tested=tested, by_state=by_state)


@bp.route("/selection/export.xlsx")
@login_required("selection")
def selection_export():
    rows = query("SELECT m.rank, m.outcome, m.score, a.app_no, a.full_name, a.gender, a.email, a.mobile, a.college_name, a.aishe_code, "
                 "a.college_state, a.college_district, a.university, a.course_level, a.year_of_study, a.pref_lang, a.mentor_name, a.mentor_email "
                 "FROM merit_list m JOIN applications a ON a.id = m.application_id ORDER BY m.rank")
    headers = ["Rank", "Outcome", "Score", "App No", "Name", "Gender", "Email", "Mobile", "Institution", "AISHE", "State",
               "District", "University", "Level", "Year", "Language", "Mentor", "Mentor email"]
    audit("export_merit", "merit_list", None, user=_user(), ip=client_ip())
    return Response(xlsx_bytes(headers, [tuple(r) for r in rows], "Merit list"),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-merit-list.xlsx"})


# ---- content: notices / resources / events ----------------------------------

@bp.route("/notices")
@login_required("content")
def notices():
    rows = query("SELECT n.*, u.name AS author FROM notices n LEFT JOIN users u ON u.id = n.created_by ORDER BY n.pinned DESC, n.created_at DESC")
    return render_template("console/notices.html", rows=rows)


@bp.route("/notices/new", methods=["GET", "POST"])
@bp.route("/notices/<int:nid>/edit", methods=["GET", "POST"])
@login_required("content")
def notice_form(nid=None):
    row = query("SELECT * FROM notices WHERE id = ?", (nid,), one=True) if nid else None
    if nid and row is None:
        abort(404)
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("title", "body", "category", "lang", "publish_at", "link")}
        if not d["title"]:
            flash("A title is required.", "error")
        else:
            attachment = row["attachment"] if row else ""
            f = request.files.get("attachment")
            if f and f.filename:
                try:
                    attachment = save_upload(f, "notices", RESOURCE_EXT, current_app.config["RESOURCE_MAX_BYTES"])[0]
                except ValueError:
                    flash("Attachment rejected: allowed types are PDF, images and office files up to 20 MB.", "error")
                    return redirect(request.url)
            vals = (d["title"], d["body"], d["category"] or "general", d["lang"] or "en",
                    1 if request.form.get("pinned") else 0, 1 if request.form.get("published") else 0,
                    d["publish_at"] or None, attachment, d["link"], utcnow())
            if row:
                execute("UPDATE notices SET title=?, body=?, category=?, lang=?, pinned=?, published=?, publish_at=?, attachment=?, link=?, updated_at=? WHERE id=?",
                        vals + (nid,))
                audit("notice_updated", "notice", nid, detail=d["title"], user=_user(), ip=client_ip())
            else:
                nid = execute("INSERT INTO notices(title, body, category, lang, pinned, published, publish_at, attachment, link, updated_at, created_by, created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", vals + (_user()["id"], utcnow()))
                audit("notice_created", "notice", nid, detail=d["title"], user=_user(), ip=client_ip())
            flash("Notice saved.", "success")
            return redirect(url_for("admin.notices"))
    return render_template("console/notice_form.html", n=row, cats=NOTICE_CATS)


@bp.route("/notices/<int:nid>/delete", methods=["POST"])
@login_required("content")
def notice_delete(nid):
    execute("DELETE FROM notices WHERE id = ?", (nid,))
    audit("notice_deleted", "notice", nid, user=_user(), ip=client_ip())
    flash("Notice deleted.", "warning")
    return redirect(url_for("admin.notices"))


@bp.route("/resources")
@login_required("content")
def resources():
    cat = request.args.get("cat") or ""
    sql = "SELECT * FROM resources"
    args = []
    if cat:
        sql += " WHERE category = ?"
        args.append(cat)
    rows = query(sql + " ORDER BY category, sort_order, created_at DESC", args)
    return render_template("console/resources.html", rows=rows, cat=cat, categories=CATEGORIES)


@bp.route("/resources/new", methods=["GET", "POST"])
@bp.route("/resources/<int:rid>/edit", methods=["GET", "POST"])
@login_required("content")
def resource_form(rid=None):
    row = query("SELECT * FROM resources WHERE id = ?", (rid,), one=True) if rid else None
    if rid and row is None:
        abort(404)
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("title", "description", "category", "lang", "url", "sort_order")}
        if not d["title"] or d["category"] not in CATEGORIES:
            flash("Title and a valid category are required.", "error")
        else:
            file_path, file_name, file_size = (row["file_path"], row["file_name"], row["file_size"]) if row else ("", "", 0)
            f = request.files.get("file")
            if f and f.filename:
                try:
                    file_path, file_name, file_size = save_upload(f, "resources", RESOURCE_EXT, current_app.config["RESOURCE_MAX_BYTES"])
                except ValueError:
                    flash("File rejected: allowed types are PDF, images, audio, video, zip and office files up to 20 MB.", "error")
                    return redirect(request.url)
            if not file_path and not d["url"]:
                flash("Provide either a file or a link.", "error")
                return redirect(request.url)
            vals = (d["title"], d["description"], d["category"], d["lang"], d["url"], file_path, file_name, file_size,
                    1 if request.form.get("published") else 0, 1 if request.form.get("featured") else 0,
                    safe_int(d["sort_order"], 100), utcnow())
            if row:
                execute("UPDATE resources SET title=?, description=?, category=?, lang=?, url=?, file_path=?, file_name=?, file_size=?, published=?, featured=?, sort_order=?, updated_at=? WHERE id=?",
                        vals + (rid,))
                audit("resource_updated", "resource", rid, detail=d["title"], user=_user(), ip=client_ip())
            else:
                rid = execute("INSERT INTO resources(title, description, category, lang, url, file_path, file_name, file_size, published, featured, sort_order, updated_at, created_by, created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (_user()["id"], utcnow()))
                audit("resource_created", "resource", rid, detail=d["title"], user=_user(), ip=client_ip())
            flash("Resource saved.", "success")
            return redirect(url_for("admin.resources", cat=d["category"]))
    return render_template("console/resource_form.html", r=row, categories=CATEGORIES, langs=K.languages())


@bp.route("/resources/<int:rid>/delete", methods=["POST"])
@login_required("content")
def resource_delete(rid):
    execute("DELETE FROM resources WHERE id = ?", (rid,))
    audit("resource_deleted", "resource", rid, user=_user(), ip=client_ip())
    flash("Resource deleted.", "warning")
    return redirect(url_for("admin.resources"))


@bp.route("/events")
@login_required("content")
def events():
    rows = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id ORDER BY e.starts_at DESC")
    return render_template("console/events.html", rows=rows)


@bp.route("/events/new", methods=["GET", "POST"])
@bp.route("/events/<int:eid>/edit", methods=["GET", "POST"])
@login_required("content")
def event_form(eid=None):
    row = query("SELECT * FROM events WHERE id = ?", (eid,), one=True) if eid else None
    if eid and row is None:
        abort(404)
    agencies = query("SELECT id, short_name FROM agencies WHERE active = 1 ORDER BY sort_order")
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("title", "description", "kind", "lang", "starts_at", "ends_at", "venue", "link", "agency_id")}
        if not d["title"] or not parse_iso(d["starts_at"]):
            flash("A title and a valid start date-time are required.", "error")
        else:
            vals = (d["title"], d["description"], d["kind"] or "general", d["lang"], d["starts_at"], d["ends_at"] or None,
                    d["venue"], d["link"], safe_int(d["agency_id"]) or None, 1 if request.form.get("published") else 0, utcnow())
            if row:
                execute("UPDATE events SET title=?, description=?, kind=?, lang=?, starts_at=?, ends_at=?, venue=?, link=?, agency_id=?, published=?, updated_at=? WHERE id=?",
                        vals + (eid,))
                audit("event_updated", "event", eid, detail=d["title"], user=_user(), ip=client_ip())
            else:
                eid = execute("INSERT INTO events(title, description, kind, lang, starts_at, ends_at, venue, link, agency_id, published, updated_at, created_by, created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (_user()["id"], utcnow()))
                audit("event_created", "event", eid, detail=d["title"], user=_user(), ip=client_ip())
            flash("Event saved.", "success")
            return redirect(url_for("admin.events"))
    return render_template("console/event_form.html", e=row, kinds=EVENT_KINDS, agencies=agencies,
                           langs=["", "ta"] + K.ORIENTATION_LANGS)


@bp.route("/events/<int:eid>/delete", methods=["POST"])
@login_required("content")
def event_delete(eid):
    execute("DELETE FROM events WHERE id = ?", (eid,))
    audit("event_deleted", "event", eid, user=_user(), ip=client_ip())
    flash("Event deleted.", "warning")
    return redirect(url_for("admin.events"))


# ---- agencies ---------------------------------------------------------------

@bp.route("/agencies")
@login_required("coord.manage")
def agencies():
    rows = query("SELECT a.*, (SELECT COUNT(*) FROM users u WHERE u.agency_id = a.id AND u.active = 1) AS users, "
                 "(SELECT COUNT(*) FROM tasks t WHERE t.agency_id = a.id AND t.status != 'done') AS open_tasks "
                 "FROM agencies a ORDER BY a.sort_order, a.name")
    return render_template("console/agencies.html", rows=rows)


@bp.route("/agencies/new", methods=["GET", "POST"])
@bp.route("/agencies/<int:aid>/edit", methods=["GET", "POST"])
@login_required("coord.manage")
def agency_form(aid=None):
    row = query("SELECT * FROM agencies WHERE id = ?", (aid,), one=True) if aid else None
    if aid and row is None:
        abort(404)
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("code", "name", "short_name", "kind", "role_desc", "contact_name", "email", "phone", "website", "sort_order")}
        if not d["code"] or not d["name"] or not d["short_name"]:
            flash("Code, name and short name are required.", "error")
        else:
            vals = (d["code"].upper(), d["name"], d["short_name"], d["kind"] or "institute", d["role_desc"], d["contact_name"],
                    d["email"], d["phone"], d["website"], safe_int(d["sort_order"], 100), 1 if request.form.get("active") else 0)
            try:
                if row:
                    execute("UPDATE agencies SET code=?, name=?, short_name=?, kind=?, role_desc=?, contact_name=?, email=?, phone=?, website=?, sort_order=?, active=? WHERE id=?", vals + (aid,))
                else:
                    aid = execute("INSERT INTO agencies(code, name, short_name, kind, role_desc, contact_name, email, phone, website, sort_order, active) VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals)
                audit("agency_saved", "agency", aid, detail=d["name"], user=_user(), ip=client_ip())
                flash("Agency saved.", "success")
                return redirect(url_for("admin.agencies"))
            except Exception:  # noqa: BLE001 - unique code clash
                flash("That agency code is already in use.", "error")
    return render_template("console/agency_form.html", a=row,
                           kinds=["ministry", "institute", "university", "authority", "board", "committee", "government", "other"])


# ---- messages ---------------------------------------------------------------

@bp.route("/messages", methods=["GET", "POST"])
@login_required("messages")
def messages():
    if request.method == "POST":
        mid = safe_int(request.form.get("id"))
        execute("UPDATE messages SET handled = 1 - handled, reply_note = ? WHERE id = ?", ((request.form.get("note") or "").strip(), mid))
        return redirect(url_for("admin.messages", show=request.form.get("show", "")))
    show = request.args.get("show") or "open"
    sql = "SELECT * FROM messages"
    if show == "open":
        sql += " WHERE handled = 0"
    rows = query(sql + " ORDER BY id DESC LIMIT 300")
    return render_template("console/messages.html", rows=rows, show=show)


# ---- users ------------------------------------------------------------------

@bp.route("/users")
@login_required("users")
def users():
    rows = query("SELECT u.*, a.short_name AS agency FROM users u LEFT JOIN agencies a ON a.id = u.agency_id ORDER BY u.role, u.name")
    return render_template("console/users.html", rows=rows, roles=ROLES)


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@login_required("users")
def user_form(uid=None):
    row = query("SELECT * FROM users WHERE id = ?", (uid,), one=True) if uid else None
    if uid and row is None:
        abort(404)
    agencies = query("SELECT id, short_name, name FROM agencies ORDER BY sort_order")
    temp_password = None
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("email", "name", "role", "agency_id", "phone")}
        d["email"] = d["email"].lower()
        if not d["email"] or not d["name"] or d["role"] not in ROLES:
            flash("Email, name and a valid role are required.", "error")
        elif d["role"] == "agency" and not safe_int(d["agency_id"]):
            flash("Agency users must be linked to an agency.", "error")
        else:
            agency_id = safe_int(d["agency_id"]) or None
            active = 1 if request.form.get("active") else 0
            try:
                if row:
                    execute("UPDATE users SET email=?, name=?, role=?, agency_id=?, phone=?, active=? WHERE id=?",
                            (d["email"], d["name"], d["role"], agency_id, d["phone"], active, uid))
                    if request.form.get("reset"):
                        temp_password = "Kts5-" + secrets.token_urlsafe(6)
                        execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                                (generate_password_hash(temp_password), uid))
                    audit("user_updated", "user", uid, detail=d["email"], user=_user(), ip=client_ip())
                else:
                    temp_password = "Kts5-" + secrets.token_urlsafe(6)
                    uid = execute("INSERT INTO users(email, name, password_hash, role, agency_id, phone, active, must_change_password, created_at) "
                                  "VALUES(?,?,?,?,?,?,?,1,?)",
                                  (d["email"], d["name"], generate_password_hash(temp_password), d["role"], agency_id, d["phone"], active, utcnow()))
                    audit("user_created", "user", uid, detail=d["email"], user=_user(), ip=client_ip())
                    send_mail(d["email"], "Your KTS 5.0 portal account",
                              f"Dear {d['name']},\n\nAn account has been created for you on the Kashi Tamil Sangamam 5.0 portal.\n\n"
                              f"Sign in: {current_app.config['BASE_URL']}/console/login\nEmail: {d['email']}\n"
                              f"Temporary password: {temp_password}\n\nYou will be asked to set a new password at first sign-in.\n\nCICT, Chennai")
                flash("User saved." + (f" Temporary password: {temp_password}" if temp_password else ""), "success")
                return redirect(url_for("admin.users"))
            except Exception:  # noqa: BLE001 - unique email clash
                flash("That email address is already registered.", "error")
    return render_template("console/user_form.html", u=row, roles=ROLES, agencies=agencies, perms=PERMS)


# ---- settings / audit / outbox ----------------------------------------------

SETTING_GROUPS = [
    ("Site", [("site.banner", "Banner text", "text"), ("site.banner_on", "Show banner", "bool"), ("stats.public", "Show live counts on the home page", "bool")]),
    ("Registration", [("reg.open", "Registration enabled", "bool"), ("reg.start", "Opens on (YYYY-MM-DD)", "date"), ("reg.end", "Closes on (YYYY-MM-DD)", "date")]),
    ("Online test", [("exam.date", "Test date (YYYY-MM-DD)", "date"), ("exam.start_time", "Login window opens (HH:MM IST)", "text"),
                     ("exam.end_time", "Login window closes (HH:MM IST)", "text"), ("exam.duration_min", "Duration in minutes", "number"),
                     ("exam.questions", "Questions per paper", "number"), ("exam.marks_per_q", "Marks per question", "number"),
                     ("exam.negative", "Negative marks per wrong answer", "number"), ("exam.show_score", "Show score to candidates", "bool"),
                     ("exam.open", "Window mode: auto | 1 (force open) | 0 (force closed)", "text"), ("exam.instructions_url", "Link to the official instructions PDF", "text")]),
    ("Merit list", [("merit.published", "Merit list published", "bool"), ("merit.select_count", "Number to select", "number"),
                    ("merit.wait_count", "Waitlist size", "number"), ("merit.note", "Note shown above the merit list", "text")]),
    ("Orientation", [("orientation.note", "Note shown on the orientation page", "text")]),
    ("Contact", [("contact.email", "Helpdesk email", "text"), ("contact.phone", "Helpdesk phone", "text"), ("contact.address", "Postal address", "text")]),
]


@bp.route("/settings", methods=["GET", "POST"])
@login_required("settings")
def settings_page():
    if request.method == "POST":
        changed = []
        for _, items in SETTING_GROUPS:
            for key, _label, kind in items:
                if kind == "bool":
                    value = "1" if request.form.get(key) else "0"
                else:
                    value = (request.form.get(key) or "").strip()
                if value != get_setting(key):
                    set_setting(key, value)
                    changed.append(key)
        audit("settings_changed", "settings", None, detail=changed, user=_user(), ip=client_ip())
        flash(f"Saved {len(changed)} setting(s).", "success")
        return redirect(url_for("admin.settings_page"))
    return render_template("console/settings.html", groups=SETTING_GROUPS, values=all_settings())


@bp.route("/audit")
@login_required("audit")
def audit_log():
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM audit_log"
    args = []
    if q:
        sql += " WHERE action LIKE ? OR actor LIKE ? OR detail LIKE ? OR entity LIKE ?"
        args = [f"%{q}%"] * 4
    total = query("SELECT COUNT(*) AS n FROM (" + sql + ")", args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 100)
    rows = query(sql + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [pg["per_page"], pg["offset"]])
    return render_template("console/audit.html", rows=rows, q=q, pg=pg)


@bp.route("/outbox")
@login_required("settings")
def outbox():
    rows = query("SELECT * FROM outbox ORDER BY id DESC LIMIT 200")
    smtp = bool(current_app.config.get("SMTP_HOST"))
    return render_template("console/outbox.html", rows=rows, smtp=smtp)

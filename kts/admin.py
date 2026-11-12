"""
Administration console: applications, verification, question bank, exam
monitoring, selection and merit list, content, users, settings, audit.
"""
import csv
import io
import json
import posixpath
import re
import secrets
from datetime import timedelta
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, send_file,
                   request, send_from_directory, url_for)
from werkzeug.security import generate_password_hash

from . import kural as K
from . import backup as BACKUP
from . import heis as HEI
from . import nodal as NODAL
from . import progress as PROGRESS
from . import qbank as QBANK
from .auth import PERMS, ROLES, current_user, has_perm, login_required, state_scope
from .db import (DEFAULT_SETTINGS, INSTITUTE_HEAD, NODAL_FIELDS, NODAL_OFFICERS, SOCIAL_LINKS, all_settings, audit, execute, executemany, get_setting, query,
                 set_setting, utcnow)
from .public import CATEGORIES
from .utils import (RESOURCE_EXT, client_ip, csv_bytes, exam_window, file_folder, now_ist, paginate, parse_iso,
                    fmt_date, registration_state, safe_int, save_upload, send_again, send_mail, valid_email, xlsx_bytes,
                    mail_check, SHEET_MAX_BYTES, sheet_rows)

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
    qcheck = QBANK.summary(settings.get("exam.questions", "50"))
    prog = PROGRESS.board()["total"]
    tasks = query("SELECT t.status, COUNT(*) AS n FROM tasks t GROUP BY t.status")
    overdue = query("SELECT COUNT(*) AS n FROM tasks WHERE status NOT IN ('done') AND due_date IS NOT NULL AND due_date < ?",
                    (now_ist().strftime("%Y-%m-%d"),), one=True)["n"]
    messages = query("SELECT COUNT(*) AS n FROM messages WHERE handled = 0", one=True)["n"]
    # the rows of the bank details are for those who may open them
    hide = "" if has_perm(user, "stipend") else " WHERE action NOT LIKE 'bank_%'"
    recent = query("SELECT * FROM audit_log" + hide + " ORDER BY id DESC LIMIT 12")
    start, end, is_open = exam_window(settings)
    from .visits import days as visit_days
    visit_rows = visit_days(30)
    return render_template("console/dashboard.html", visit_rows=visit_rows, settings=settings, by_status=by_status, total=total,
                           colleges=colleges, states=states, days=days, max_day=max_day, top_states=top_states,
                           by_lang=by_lang, exam=exam, qbank=qbank, qcheck=qcheck, prog=prog, tasks={r["status"]: r["n"] for r in tasks},
                           overdue=overdue, messages=messages, recent=recent, reg_state=registration_state(settings),
                           backup_warn=BACKUP.state()["warn"] if has_perm(user, "backup") else "",
                           exam_start=start, exam_end=end, exam_open=is_open)


# ---- applications -----------------------------------------------------------

def _app_filters():
    f = {k: (request.args.get(k) or "").strip() for k in ("status", "state", "lang", "q", "college", "exam", "inst")}
    sql = " FROM applications a WHERE 1=1"
    args = []
    if f["status"]:
        sql += " AND a.status = ?"
        args.append(f["status"])
    if f["state"]:   # a State with the Union Territory Annexure-I pairs with it (1.2.135)
        group = HEI.with_covered([f["state"]])
        sql += f" AND a.college_state IN ({','.join('?' * len(group))})"
        args += group
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
    # chosen from the list of participating institutions, or "not listed" (1.2.41)
    if f["inst"] == "listed":
        sql += " AND a.institution_id IS NOT NULL"
    elif f["inst"] == "unlisted":
        sql += " AND a.institution_id IS NULL"
    # a Nodal Officer: the applications of the institutions of their States/UTs, whatever is asked for
    scope = state_scope(_user())
    if scope is not None:
        sql += f" AND a.college_state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        args += scope
    return f, sql, args


@bp.route("/applications")
@login_required("apps.view")
def applications():
    f, sql, args = _app_filters()
    total = query("SELECT COUNT(*) AS n" + sql, args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 50)
    rows = query("SELECT a.*" + sql + " ORDER BY a.id DESC LIMIT ? OFFSET ?", args + [pg["per_page"], pg["offset"]])
    scope = state_scope(_user())
    return render_template("console/applications.html", rows=rows, f=f, pg=pg, statuses=APP_STATUSES,
                           states=scope if scope is not None else _states(), langs=K.ORIENTATION_LANGS, scope=scope,
                           closes=NODAL.closes_line() if scope is not None else "")


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
    user = _user()
    scope = state_scope(user)
    # an application of another State/UT does not exist for a Nodal Officer
    if row is None or (scope is not None and row["college_state"] not in scope):
        abort(404)
    if request.method == "POST":
        if not has_perm(user, "apps.verify"):
            abort(403)
        action = request.form.get("action")
        # a Nodal Officer verifies, rejects and writes remarks; withdrawing and deleting stay with CICT
        if scope is not None and action not in ("verify", "reject", "note"):
            abort(403)
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
                          f"CICT will confirm the selection of the students on {fmt_date(settings.get('letter.date'))}, "
                          f"by e-mail and on the portal.\n\n"
                          f"Follow your application at {current_app.config['BASE_URL']}/status, and sign in to the "
                          f"candidate portal at {current_app.config['BASE_URL']}/candidate/login, with your application "
                          f"number, date of birth and the last four digits of your mobile number.\n\nCICT, Chennai")
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
        elif action == "delete":
            if not has_perm(user, "apps.delete"):
                abort(403)
            reason = (request.form.get("reason") or "").strip()[:200]
            if (request.form.get("confirm_no") or "").strip().upper() != row["app_no"]:
                flash("Nothing was deleted: type the application number exactly as shown to confirm.", "error")
            elif query("SELECT 1 FROM merit_list WHERE application_id = ?", (aid,), one=True):
                flash("This application stands in the selection list and cannot be deleted. Withdraw it instead.", "error")
            elif query("SELECT 1 FROM bank_details WHERE application_id = ?", (aid,), one=True):
                # the bank details and the record of a payment stay with the application
                flash("This application has bank details for the stipend and cannot be deleted. Withdraw it instead.", "error")
            else:
                _delete_application(row)
                # the number and the reason only: nothing of the person stays behind
                audit("application_deleted", "application", aid, detail=f"{row['app_no']} {reason}".strip(), user=user, ip=client_ip())
                flash(f"Application {row['app_no']} was deleted with its uploaded files.", "success")
                return redirect(url_for("admin.applications"))
        elif action == "reset_exam" and has_perm(user, "exam.manage"):
            execute("DELETE FROM exam_sessions WHERE application_id = ?", (aid,))
            execute("UPDATE applications SET exam_score = NULL, exam_rank = NULL, updated_at = ? WHERE id = ?", (now, aid))
            audit("exam_reset", "application", aid, detail=note, user=user, ip=client_ip())
            flash("Test attempt cleared; the candidate may take the test again.", "warning")
        return redirect(url_for("admin.application", aid=aid))
    exam = query("SELECT * FROM exam_sessions WHERE application_id = ?", (aid,), one=True)
    same_college = query("SELECT id, app_no, full_name, status, exam_score FROM applications WHERE college_key = ? AND id != ? ORDER BY id",
                         (row["college_key"], aid))
    # the rows of the bank details are for those who may open them; the looks at the full numbers
    # stand on the stipend page, here they would push the history off
    hide = ("" if has_perm(user, "stipend") else " AND action NOT LIKE 'bank_%'") \
        + " AND action NOT IN ('bank_viewed', 'bank_proof_opened')"
    history = query("SELECT * FROM audit_log WHERE entity = 'application' AND entity_id = ?" + hide +
                    " ORDER BY id DESC LIMIT 30", (aid,))
    verifier = query("SELECT name FROM users WHERE id = ?", (row["verified_by"],), one=True) if row["verified_by"] else None
    merit = query("SELECT * FROM merit_list WHERE application_id = ?", (aid,), one=True)
    # the state of the bank details of a selected student, for those who may open them
    bank = None
    if row["status"] == "selected" and has_perm(user, "stipend"):
        entry = query("SELECT status FROM bank_details WHERE application_id = ?", (aid,), one=True)
        bank = entry["status"] if entry else "none"
    return render_template("console/application.html", a=row, exam=exam, same_college=same_college, history=history,
                           verifier=verifier, merit=merit, bank=bank, lang_name=K.lang_label(row["pref_lang"]))


def _delete_application(row):
    """
    Remove an application for good: its test attempt, its row and the photograph and ID uploaded
    with it. For a trial entry or one made by mistake; its number is not given again.
    """
    execute("DELETE FROM exam_sessions WHERE application_id = ?", (row["id"],))
    execute("DELETE FROM inaug_attendance WHERE application_id = ?", (row["id"],))
    # a paper is sent by a selected student only, whose application the delete refuses; its lines go with it all the same
    execute("DELETE FROM paper_files WHERE paper_id IN (SELECT id FROM papers WHERE application_id = ?)", (row["id"],))
    execute("DELETE FROM papers WHERE application_id = ?", (row["id"],))
    execute("DELETE FROM applications WHERE id = ?", (row["id"],))
    folder = Path(current_app.config["UPLOAD_DIR"]).resolve()
    for rel in (row["photo_path"], row["idproof_path"], row["nomination_path"]):
        path = (folder / rel).resolve() if rel else None
        if path is None or folder not in path.parents:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            current_app.logger.warning("An uploaded file of the deleted application %s stays on the disk (%s).", row["app_no"], exc)


@bp.route("/applications/bulk", methods=["POST"])
@login_required("apps.verify")
def applications_bulk():
    ids = [safe_int(i) for i in request.form.getlist("ids") if safe_int(i)]
    action = request.form.get("action")
    scope = state_scope(_user())
    if ids and scope is not None:
        # a Nodal Officer: the applications of their States/UTs among those ticked
        marks = ",".join("?" * len(ids))
        ids = [r["id"] for r in query(f"SELECT id FROM applications WHERE id IN ({marks}) AND college_state IN "
                                      f"({','.join('?' * len(scope)) or 'NULL'})", ids + scope)]
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
@login_required()
def staff_file(relpath):
    user = _user()
    # the folder is tested on the path as it will be opened
    relpath = posixpath.normpath(relpath)
    # the folders that exist, by their names as the portal writes them: Windows would open
    # "Photos" or "photos." as the folder photos
    folder = relpath.partition("/")[0]
    if folder not in ("photos", "idproofs", "nominations", "bankproofs", "notices", "resources", "tasks", "documents", "gallery"):
        abort(404)
    if folder in ("photos", "idproofs", "nominations"):
        if not has_perm(user, "apps.view"):
            abort(403)
        # a Nodal Officer: the files of the applications of their States/UTs only
        scope = state_scope(user)
        if scope is not None:
            owner = query("SELECT college_state FROM applications WHERE photo_path = ? OR idproof_path = ? OR nomination_path = ?",
                          (relpath, relpath, relpath), one=True)
            if owner is None or owner["college_state"] not in scope:
                abort(404)
    elif not has_perm(user, "dashboard"):
        abort(403)
    if folder == "bankproofs":
        if not has_perm(user, "stipend"):
            abort(403)
        # the proof shows the account number in full: only the name an entry keeps is served
        # (Windows opens "x.pdf." or "X.PDF" as x.pdf), and every opening is written down. The
        # whole file goes each time, without parts on request, so no part is read unrecorded
        entry = query("SELECT application_id FROM bank_details WHERE proof_path = ?", (relpath,), one=True)
        if entry is None:
            abort(404)
        audit("bank_proof_opened", "application", entry["application_id"], detail=relpath, user=user, ip=client_ip())
        return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), relpath, conditional=False)
    return send_from_directory(file_folder(relpath), relpath)


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
                           langs=K.ORIENTATION_LANGS, qtypes=["complete", "chapter", "section", "gk", "manual"])


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
        elif len({QBANK.norm(d[k]) for k in ("opt_a", "opt_b", "opt_c", "opt_d")}) < 4:
            flash("Two of the options are the same. Give four different options.", "error")
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
    return render_template("console/question_form.html", q=row, langs=K.ORIENTATION_LANGS,
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
        langs = list(K.ORIENTATION_LANGS)
    only108 = request.form.get("set") == "108"           # the 108 Thirukkural alone (1.2.64)
    made = 0
    for lang in langs:
        if not K.lang_info(lang):
            continue
        seed = f"{lang}-{secrets.token_hex(4)}"
        rows = QBANK.generate_k108(lang, count, seed) if only108 else K.generate_questions(lang, count, seed)
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
        made += len(rows)
    audit("questions_generated", "question", None, detail={"langs": langs, "count": count, "made": made, "set": "108" if only108 else "all"},
          user=_user(), ip=client_ip())
    flash(f"Generated {made} questions from the Thirukkural corpus"
          + (", on the 108 Thirukkural (none that the bank asked already)" if only108 else "") + ".", "success")
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
        r["lang"] = (r.get("lang") or "").lower()
        if (r["lang"] not in K.ORIENTATION_LANGS or not r.get("text") or r.get("correct", "").upper() not in ("A", "B", "C", "D")
                or not all(r.get(k) for k in ("opt_a", "opt_b", "opt_c", "opt_d"))):
            bad += 1
            continue
        rows.append((r["lang"], r.get("qtype") or "manual", r["text"], r.get("opt_a", ""), r.get("opt_b", ""),
                     r.get("opt_c", ""), r.get("opt_d", ""), r["correct"].upper(), safe_int(r.get("kural_no")) or None,
                     safe_int(r.get("difficulty"), 1), utcnow()))
    if rows:
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'import',?)", rows)
    audit("questions_imported", "question", None, detail={"rows": len(rows), "skipped": bad}, user=_user(), ip=client_ip())
    flash(f"Imported {len(rows)} question(s); skipped {bad}"
          + (" (a language code that is not one of the 23, a blank option or an answer other than A–D)" if bad else "") + ".",
          "success" if rows else "error")
    return redirect(url_for("admin.questions"))


@bp.route("/questions/export.csv")
@login_required("exam.manage")
def questions_export():
    rows = query("SELECT lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active FROM questions ORDER BY lang, id")
    data = csv_bytes(["lang", "qtype", "text", "opt_a", "opt_b", "opt_c", "opt_d", "correct", "kural_no", "difficulty", "active"],
                     [tuple(r) for r in rows])
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=KTS5-question-bank.csv"})


@bp.route("/questions/check", methods=["GET", "POST"])
@login_required("exam.view")
def questions_check():
    """Whether a full paper can be drawn in each language, and the questions that should not be in one."""
    n = all_settings().get("exam.questions", "50")
    if request.method == "POST":
        if not has_perm(_user(), "exam.manage"):
            abort(403)
        ids = QBANK.report(n)["faulty_ids"]
        if ids:
            executemany("UPDATE questions SET active = 0 WHERE id = ? AND active = 1", [(i,) for i in ids])
            audit("questions_set_aside", "question", None, detail={"count": len(ids), "ids": ids[:200]}, user=_user(), ip=client_ip())
            flash(f"Set aside {len(ids)} question(s). They stay in the bank as inactive; correct one and enable it to use it again.", "success")
        else:
            flash("No faulty question to set aside.", "info")
        return redirect(url_for("admin.questions_check"))
    lang = (request.args.get("lang") or "").strip()
    rep = QBANK.report(n)
    shown = [p for p in rep["problems"] if not lang or p["row"]["lang"] == lang]
    return render_template("console/questions_check.html", rep=rep, shown=shown[:300], hidden=max(len(shown) - 300, 0))


@bp.route("/questions/check.csv")
@login_required("exam.manage")
def questions_check_export():
    rep = QBANK.report(all_settings().get("exam.questions", "50"))
    rows = [(p["row"]["id"], p["row"]["lang"], p["kind"], "set aside" if p["kind"] in QBANK.FAULTS else "check", p["why"],
             p["row"]["text"], p["row"]["opt_a"], p["row"]["opt_b"], p["row"]["opt_c"], p["row"]["opt_d"], p["row"]["correct"], p["row"]["source"])
            for p in rep["problems"]]
    data = csv_bytes(["id", "lang", "problem", "action", "explanation", "text", "opt_a", "opt_b", "opt_c", "opt_d", "correct", "source"], rows)
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=KTS5-question-bank-check.csv"})


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
    from .candidate import test_statuses
    statuses = test_statuses(settings)
    eligible = query("SELECT COUNT(*) AS n FROM applications WHERE status IN (%s)" % ",".join("?" * len(statuses)), statuses, one=True)["n"]
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

def run_selection(user):
    """
    The list of the selected students (1.2.155, the D.O. letter of 31 October 2026): each selected Participating Institution nominates
    one student on merit, and that nominee, once verified by the Nodal Institution and CICT, is the selected student - no rank among the
    students and no waiting list (the reserve list of Annexure-V is one of institutions). Where several verified applications name the
    same institution, the one registered with the institution's personal link is selected (else the earliest); the others are not.
    The list runs State/UT by State/UT and institution by institution; its "rank" is only the serial number.
    """
    # an attempt whose time ran out while the browser was closed is still "in progress": it is closed and scored here
    from .candidate import _finalise
    for stale in query("SELECT * FROM exam_sessions WHERE status = 'in_progress' AND deadline_at < ?",
                       ((now_ist() - timedelta(seconds=45)).isoformat(),)):
        _finalise(stale, "expired")
    rows = query("SELECT a.id, a.college_key, a.institution_id, a.created_at, "
                 "COALESCE((SELECT score FROM exam_sessions s WHERE s.application_id = a.id AND s.status != 'in_progress' "
                 "ORDER BY s.id DESC LIMIT 1), 0) AS score, "
                 "CASE WHEN i.application_id = a.id THEN 0 ELSE 1 END AS unbound "
                 "FROM applications a LEFT JOIN institutions i ON i.id = a.institution_id "
                 "WHERE a.status IN ('verified','selected','waitlisted','not_selected') "
                 "ORDER BY a.college_state, a.college_name COLLATE NOCASE, unbound, a.created_at ASC")
    seen, chosen, others = set(), [], []
    for r in rows:
        unit = ("institution", r["institution_id"]) if r["institution_id"] else ("college", r["college_key"])
        (others if unit in seen else chosen).append(r)
        seen.add(unit)
    run_id = now_ist().strftime("%Y%m%d-%H%M%S")
    now = utcnow()
    execute("DELETE FROM merit_list")
    execute("UPDATE applications SET exam_rank = NULL, status = 'verified', updated_at = ? WHERE status IN ('selected','waitlisted','not_selected')",
            (now,))
    entries = [(n, r["id"], r["score"], r["college_key"], "selected", run_id, now) for n, r in enumerate(chosen, start=1)]
    entries += [(len(chosen) + n, r["id"], r["score"], r["college_key"], "not_selected", run_id, now) for n, r in enumerate(others, start=1)]
    if entries:
        executemany("INSERT INTO merit_list(rank, application_id, score, college_key, outcome, run_id, created_at) VALUES(?,?,?,?,?,?,?)", entries)
    executemany("UPDATE applications SET status = ?, exam_rank = NULL, updated_at = ? WHERE id = ?",
                [("selected", now, r["id"]) for r in chosen] + [("not_selected", now, r["id"]) for r in others])
    audit("selection_run", "merit_list", None, detail={"run": run_id, "selected": len(chosen), "not_selected": len(others)},
          user=user, ip=client_ip())
    return run_id, len(chosen), len(others)


@bp.route("/selection", methods=["GET", "POST"])
@login_required("selection")
def selection():
    settings = all_settings()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "run":
            run_id, chosen, others = run_selection(_user())
            flash(f"List {run_id}: {chosen} selected student{'' if chosen == 1 else 's'}, the verified nominee of each Participating Institution"
                  + (f"; {others} other application(s) of the same institutions not selected." if others else "."), "success")
        elif action == "publish":
            set_setting("merit.published", "1")
            set_setting("merit.note", (request.form.get("note") or "").strip())
            audit("merit_published", "merit_list", None, user=_user(), ip=client_ip())
            flash("The list of the selected students is published on the public site.", "success")
        elif action == "unpublish":
            set_setting("merit.published", "0")
            audit("merit_unpublished", "merit_list", None, user=_user(), ip=client_ip())
            flash("The list of the selected students is hidden from the public site.", "warning")
        return redirect(url_for("admin.selection"))
    summary = {r["outcome"]: r["n"] for r in query("SELECT outcome, COUNT(*) AS n FROM merit_list GROUP BY outcome")}
    last = query("SELECT run_id, created_at FROM merit_list ORDER BY id DESC LIMIT 1", one=True)
    top = query("SELECT m.rank, m.score, m.outcome, a.app_no, a.full_name, a.college_name, a.college_state, a.pref_lang "
                "FROM merit_list m JOIN applications a ON a.id = m.application_id ORDER BY m.rank LIMIT 100")
    verified = query("SELECT COUNT(*) AS n FROM applications WHERE status IN ('verified','selected','waitlisted','not_selected')", one=True)["n"]
    by_state = query("SELECT a.college_state AS s, SUM(m.outcome = 'selected') AS sel, COUNT(*) AS n "
                     "FROM merit_list m JOIN applications a ON a.id = m.application_id GROUP BY s ORDER BY sel DESC")
    return render_template("console/selection.html", settings=settings, summary=summary, last=last, top=top,
                           verified=verified, by_state=by_state)


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
                           langs=[""] + K.ORIENTATION_LANGS)


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
        d = {k: (request.form.get(k) or "").strip() for k in ("email", "name", "role", "agency_id", "phone", "designation")}
        d["email"] = d["email"].lower()
        known = _states()
        chosen = [s for s in request.form.getlist("states") if s in known]
        states = "|".join(chosen) if d["role"] == "nodal" else ""
        if not d["email"] or not d["name"] or d["role"] not in ROLES:
            flash("Email, name and a valid role are required.", "error")
        elif d["role"] == "agency" and not safe_int(d["agency_id"]):
            flash("Agency users must be linked to an agency.", "error")
        elif d["role"] == "nodal" and not chosen:
            flash("A Nodal Officer needs the State/UT (or States/UTs) whose applications they verify.", "error")
        else:
            agency_id = safe_int(d["agency_id"]) or None
            active = 1 if request.form.get("active") else 0
            try:
                if row:
                    execute("UPDATE users SET email=?, name=?, role=?, agency_id=?, phone=?, active=?, states=?, designation=? WHERE id=?",
                            (d["email"], d["name"], d["role"], agency_id, d["phone"], active, states, d["designation"], uid))
                    if request.form.get("reset"):
                        temp_password = "Kts5-" + secrets.token_urlsafe(6)
                        execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                                (generate_password_hash(temp_password), uid))
                    audit("user_updated", "user", uid, detail=d["email"], user=_user(), ip=client_ip())
                else:
                    uid, temp_password = _create_account(d["email"], d["name"], d["role"], d["phone"],
                                                         chosen if d["role"] == "nodal" else (), agency_id, active, d["designation"])
                flash("User saved." + (f" Temporary password: {temp_password}" if temp_password else ""), "success")
                return redirect(url_for("admin.users"))
            except Exception:  # noqa: BLE001 - unique email clash
                flash("That email address is already registered.", "error")
    # a new Nodal Officer from the page of the Nodal Officers comes with role and State/UT filled in
    preset = {"role": request.args.get("role") or "", "states": request.args.getlist("states")}
    return render_template("console/user_form.html", acct=row, roles=ROLES, agencies=agencies, perms=PERMS,
                           all_states=_states(), preset=preset)


def _create_account(email, name, role, phone="", states=(), agency_id=None, active=1, designation=""):
    """
    A new account of the console with a temporary password, which is mailed to its owner (and shown
    once to the administrator who made it). Gives (id, temporary password).
    """
    temp_password = "Kts5-" + secrets.token_urlsafe(6)
    uid = execute("INSERT INTO users(email, name, password_hash, role, agency_id, phone, active, must_change_password, created_at, states, designation) "
                  "VALUES(?,?,?,?,?,?,?,1,?,?,?)",
                  (email, name, generate_password_hash(temp_password), role, agency_id, phone, active, utcnow(), "|".join(states), designation))
    audit("user_created", "user", uid, detail=email, user=_user(), ip=client_ip())
    send_mail(email, "Your KTS 5.0 portal account",
              f"Dear {name},\n\nAn account has been created for you on the Kashi Tamil Sangamam 5.0 portal.\n\n"
              + (NODAL.account_paragraph(list(states)) if role == "nodal" else "") +
              f"Sign in: {current_app.config['BASE_URL']}/console/login\nEmail: {email}\n"
              f"Temporary password: {temp_password}\n\nYou will be asked to set a new password at first sign-in.\n\nCICT, Chennai")
    return uid, temp_password


def _nodal_heis():
    return json.loads((current_app.config["DATA_DIR"] / "nodal_heis.json").read_text(encoding="utf-8"))


def _officers_by_state(active_only=False):
    officers = {}
    for u in query("SELECT * FROM users WHERE role = 'nodal'" + (" AND active = 1" if active_only else "") + " ORDER BY name"):
        for s in NODAL.states_of(u):
            officers.setdefault(s, []).append(u)
    return officers



@bp.route("/nodal", methods=["GET", "POST"])
@login_required("nodal.manage")
def nodal_access():
    """
    The 31 Nodal Higher Educational Institutions with the accounts of their Nodal Officers and the
    applications of their States/UTs: awaiting verification, how long, verified, rejected (1.2.38);
    reminders to the officers, the accounts from a spreadsheet (1.2.39).
    """
    if request.method == "POST":
        action = request.form.get("action")
        if action == "remind_signin":   # the officers who have never signed in: all of them, or one (1.2.136)
            uid = safe_int(request.form.get("uid"))
            targets = query("SELECT * FROM users WHERE role = 'nodal' AND active = 1" + (" AND id = ?" if uid else "") + " ORDER BY id",
                            (uid,) if uid else ())
            sent = NODAL.remind_signin(targets)
            audit("nodal_signin_reminder", "user", uid or None, detail={"mails": sent}, user=_user(), ip=client_ip())
            if sent:
                flash(f"A sign-in reminder is queued to {sent} Nodal Officer(s) who have not signed in yet; it goes out with the next "
                      f"round of the mail queue.", "success")
            else:
                flash("No reminder sent: the officer has signed in already, or the account is disabled.", "error")
            return redirect(url_for("admin.nodal_access"))
        if action == "remind":
            state = request.form.get("state") or ""
            targets = _officers_by_state(active_only=True).get(state, [])
        elif action == "remind_all":
            state = "all"
            targets = query("SELECT * FROM users WHERE role = 'nodal' AND active = 1 ORDER BY id")
        else:
            abort(400)
        sent = NODAL.remind(targets)
        audit("nodal_reminder", "user", None, detail={"state": state, "mails": sent}, user=_user(), ip=client_ip())
        if sent:
            flash(f"Reminder queued to {sent} Nodal Officer(s); it goes out with the next round of the mail queue.", "success")
        else:
            flash("No reminder sent: no applications await these officers, or the State/UT has no active account.", "error")
        return redirect(url_for("admin.nodal_access"))
    heis = _nodal_heis()
    # by the row of Annexure-I: a paired Union Territory counts with its State (1.2.135)
    counts = {}
    for r in query("SELECT college_state AS s, status, COUNT(*) AS n FROM applications GROUP BY college_state, status"):
        c = counts.setdefault(HEI.nodal_state_of(r["s"]), {})
        c[r["status"]] = c.get(r["status"], 0) + r["n"]
    officers = _officers_by_state()
    figures, total = NODAL.figures(_states())
    covered = {s for h in heis for s in HEI.group_of(h["state"])}
    inst = {}
    for r in query("SELECT state, status, COUNT(*) AS n FROM institutions GROUP BY state, status"):
        c = inst.setdefault(HEI.nodal_state_of(r["state"]), {})
        c[r["status"]] = c.get(r["status"], 0) + r["n"]

    def row(state, hei):
        return {"state": state, "label": HEI.label_of(state, "en"), "hei": hei, "officers": officers.get(state, []),
                "total": sum(counts.get(state, {}).values()), "f": NODAL.fold(figures, HEI.group_of(state)), "inst": inst.get(state, {})}
    rows = [row(h["state"], h["name"]) for h in heis]
    # the States/UTs without a Nodal Institution: their applications are verified by CICT, or by an officer given them
    others = [row(s, "") for s in _states() if s not in covered]
    settings = all_settings()
    return render_template("console/nodal.html", rows=rows, others=others, total=total, can_create=has_perm(_user(), "users"),
                           allocation={h["state"]: h.get("allocation", 0) for h in heis},
                           not_signed_in=len(NODAL.not_signed_in()),
                           closes=NODAL.closes_line(), digest_on=settings.get("nodal.digest") == "1",
                           digest_time=settings.get("nodal.digest_time") or "08:00",
                           can_settings=has_perm(_user(), "settings"))


@bp.route("/backups", methods=["GET", "POST"])
@login_required("backup")
def backups():
    """
    The copies of the database (1.2.40): the last one and its check, the copies kept on the server,
    a copy now, a download, a restore (kts/backup.py).
    """
    app = current_app._get_current_object()
    if request.method == "POST":
        action = request.form.get("action")
        if action in ("now", "now_download"):
            try:
                info = BACKUP.make(app, "manual")
            except Exception as exc:  # noqa: BLE001
                audit("backup_failed", "backup", None, detail={"error": str(exc)[:300]}, user=_user(), ip=client_ip())
                flash(f"The copy failed: {exc}", "error")
                return redirect(url_for("admin.backups"))
            audit("backup_made", "backup", None, detail=info, user=_user(), ip=client_ip())
            if action == "now_download":
                audit("backup_downloaded", "backup", None, detail=info["file"], user=_user(), ip=client_ip())
                return send_file(BACKUP.path_of(app, info["file"]), mimetype="application/zip", as_attachment=True,
                                 download_name=info["file"])
            flash(f"Copy made: {info['file']} ({info['applications']} applications, check {'ok' if info['ok'] else 'NOT OK'}).",
                  "success" if info["ok"] else "error")
            return redirect(url_for("admin.backups"))
        if action == "download":
            path = BACKUP.path_of(app, request.form.get("name"))
            if path is None:
                abort(404)
            audit("backup_downloaded", "backup", None, detail=path.name, user=_user(), ip=client_ip())
            return send_file(path, mimetype="application/zip", as_attachment=True, download_name=path.name)
        if action == "restore":
            if (request.form.get("confirm") or "").strip() != "RESTORE":
                flash("Nothing was restored: type RESTORE in capital letters to confirm.", "error")
                return redirect(url_for("admin.backups"))
            upload = request.files.get("file")
            if upload and upload.filename:
                source, named = upload.read(), upload.filename
            else:
                source = BACKUP.path_of(app, request.form.get("name"))
                if source is None:
                    flash("Nothing was restored: choose a copy, or upload one.", "error")
                    return redirect(url_for("admin.backups"))
                named = source.name
            try:
                done = BACKUP.restore(app, source)
            except ValueError as exc:
                flash(f"Nothing was restored: {exc}.", "error")
                return redirect(url_for("admin.backups"))
            audit("backup_restored", "backup", None, detail=dict(done, source=named), user=_user(), ip=client_ip())
            flash(f"Restored {named}: {done['applications']} applications, {done['accounts']} accounts, {done['tests']} tests. "
                  f"The state of before is kept as {done['before']}. {done['key']}", "success")
            return redirect(url_for("admin.backups"))
        abort(400)
    import shutil
    folder = BACKUP.folder(app)
    folder.mkdir(parents=True, exist_ok=True)
    files, size = BACKUP.uploads_size(app)
    settings = all_settings()
    return render_template("console/backups.html", st=BACKUP.state(), rows=BACKUP.listing(app), folder=folder,
                           free=shutil.disk_usage(folder).free, uploads_files=files, uploads_bytes=size,
                           times=settings.get("backup.times") or "", keep=settings.get("backup.keep") or "",
                           db_bytes=Path(app.config["DATABASE"]).stat().st_size)


# ---- the participating institutions of the States/UTs (1.2.41, kts/heis.py) ----------------------------------

def _inst_filters(scope):
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "status", "q", "unregistered", "unmarked")}
    sql, args = " FROM institutions i WHERE 1=1", []
    if scope is not None:
        sql += f" AND i.state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        args += scope
    if f["state"]:   # a State with the Union Territory Annexure-I pairs with it (1.2.135)
        group = HEI.with_covered([f["state"]])
        sql += f" AND i.state IN ({','.join('?' * len(group))})"
        args += group
    if f["status"]:
        sql += " AND i.status = ?"
        args.append(f["status"])
    if f["unregistered"]:   # selected, on the reserve list or declined before they registered (1.2.173)
        sql += " AND i." + HEI.UNREGISTERED_SQL.replace(" AND ", " AND i.")
    if f["unmarked"]:       # selected or on the reserve list without the marks of Annexure-V (1.2.174)
        sql += " AND i." + HEI.UNMARKED_SQL.replace(" AND ", " AND i.")
    if f["q"]:
        sql += " AND (i.name LIKE ? OR i.ref LIKE ? OR i.aishe_code LIKE ? OR i.head_email LIKE ? OR i.coord_email LIKE ? OR i.district LIKE ?)"
        args += [f"%{f['q']}%"] * 6
    return f, sql, args


INST_ROWS_SHOWN = 500


@bp.route("/institutions", methods=["GET", "POST"])
@login_required("hei.view")
def institutions():
    """
    The participating institutions of the States/UTs: identified by the Nodal Institution (Annexure-II of the
    D.O. letter of 9 October 2026, uploaded here, each invited by mail), applied on the website (accepted or
    declined by the Nodal Officer of the State/UT, or CICT), followed through their assessment and the
    registration of their selected student (1.2.41, 1.2.43).
    """
    user = _user()
    scope = state_scope(user)
    back = url_for("admin.institutions", **request.args.to_dict())
    if request.method == "POST":
        if not has_perm(user, "hei.decide"):
            abort(403)
        row = query("SELECT * FROM institutions WHERE id = ?", (safe_int(request.form.get("id")),), one=True)
        if row is None or (scope is not None and row["state"] not in scope):
            abort(404)
        action = request.form.get("action")
        note = (request.form.get("note") or "").strip()[:500]
        # an institution identified by the Nodal Institution is selected once it has registered with its invitation (1.2.173)
        if action in ("accept", "reserve") and (row["status"] == "identified"
                                                or (HEI.never_registered(row) and not HEI.busy_reason(row))):
            again = "Invite again" if row["status"] == "identified" else "↩ Back to invited"
            flash(f"{row['name']} has not completed its registration yet: it is selected, or put on the reserve list, once it has "
                  f"registered with its invitation, on its marks of Annexure-V ({again} mails the link once more).", "error")
            return redirect(back)
        # selected, or put on the reserve list, on the marks of the Evaluation Committee (Annexure-V), recorded first (1.2.174)
        if action in ("accept", "reserve") and row["sop_total"] is None and get_setting("hei.marks_first") == "1":
            flash(f"{row['name']}: record the marks of the Evaluation Committee first (Marks, Annexure-V). An institution is selected, "
                  f"or put on the reserve list, on its marks.", "error")
            return redirect(back)
        # selected, put on the reserve list or declined before it registered: back to identified, invited again (1.2.173)
        if action == "reinvite":
            if row["status"] == "identified" or not HEI.never_registered(row):
                abort(400)
            busy = HEI.busy_reason(row)
            if busy:
                flash(f"{row['name']} stays as it is: {busy}.", "error")
                return redirect(back)
            HEI.back_to_invited(row)
            audit("institution_reinvited", "institution", row["id"], detail={"ref": row["ref"], "was": row["status"]}, user=user,
                  ip=client_ip())
            flash(f"{row['name']}: back to identified · invited; the invitation to complete its registration is mailed again to "
                  f"{row['coord_email']}.", "success")
            return redirect(back)
        if action == "accept":
            cap = HEI.cap_of(row["state"])
            group = HEI.group_of(row["state"])   # a paired Union Territory and its State share the number (1.2.135)
            taken = query(f"SELECT COUNT(*) AS n FROM institutions WHERE state IN ({','.join('?' * len(group))}) "
                          f"AND status = 'accepted' AND id != ?", (*group, row["id"]), one=True)["n"]
            if cap and taken >= cap:
                flash(f"{HEI.label_of(row['state'], 'en')} has {taken} accepted institutions: that is the number Annexure-I prescribes for it "
                      f"(Settings › Participating institutions). The others may be placed on the reserve list, which has no upper limit.",
                      "error")
                return redirect(back)
            status = "accepted"
        elif action == "reserve":
            status = "reserve"
        elif action == "decline":
            status = "declined"
        elif action == "pending":
            status = "pending"
        elif action == "invite" and row["status"] == "identified":
            HEI.mail_invited(row)
            audit("institution_invited", "institution", row["id"], detail=row["ref"], user=user, ip=client_ip())
            flash(f"{row['name']}: the invitation is mailed again to {row['coord_email']}.", "success")
            return redirect(back)
        else:
            abort(400)
        now = utcnow()
        execute("UPDATE institutions SET status = ?, decision_note = ?, decided_by = ?, decided_at = ?, invite_token = NULL, updated_at = ? WHERE id = ?",
                (status, note if status == "declined" else "", user["id"], now if status != "pending" else None, now, row["id"]))
        audit("institution_" + status, "institution", row["id"], detail={"ref": row["ref"], "note": note}, user=user, ip=client_ip())
        if status != "pending":
            HEI.mail_decision(query("SELECT * FROM institutions WHERE id = ?", (row["id"],), one=True))
        flash(f"{row['name']}: {status}" + (" – the Head of the Institution and the coordinator are informed by mail." if status != "pending" else "."),
              "success")
        return redirect(back)
    f, sql, args = _inst_filters(scope)
    rows = query("SELECT i.*, a.app_no AS app_no, a.status AS app_status, a.full_name AS app_name, "
                 "(SELECT COUNT(*) FROM campus_students s WHERE s.institution_id = i.id) AS students, "
                 "(SELECT COUNT(*) FROM campus_students s JOIN campus_attempts t ON t.student_id = s.id "
                 " WHERE s.institution_id = i.id AND t.status != 'in_progress') AS assessed, "
                 "w.name AS winner_name"
                 + sql.replace(" FROM institutions i WHERE", " FROM institutions i LEFT JOIN applications a ON a.id = i.application_id "
                                                             "LEFT JOIN campus_students w ON w.id = i.winner_id WHERE")
                 + " ORDER BY i.state, CASE i.status WHEN 'pending' THEN 0 WHEN 'identified' THEN 1 WHEN 'accepted' THEN 2 WHEN 'reserve' THEN 3 ELSE 4 END, i.name COLLATE NOCASE"
                 + " LIMIT ?", args + [INST_ROWS_SHOWN + 1])
    # in the order of the marks of Annexure-V (1.2.111), best first, when asked
    if request.args.get("order") == "marks":
        rows = sorted(rows, key=lambda r: (HEI.nodal_state_of(r["state"]), HEI.sop_order(r)))
    # the States/UTs: identified, pending, accepted, declined, assessing, winners selected and registered
    summary = {}
    s_sql, s_args = " FROM institutions WHERE 1=1", []
    if scope is not None:
        s_sql += f" AND state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        s_args += scope
    for r in query("SELECT state, status, COUNT(*) AS n, SUM(test_on) AS testing, SUM(winner_id IS NOT NULL) AS winners, "
                   "SUM(application_id IS NOT NULL) AS registered" + s_sql + " GROUP BY state, status", s_args):
        # by the row of Annexure-I: a paired Union Territory counts with its State (1.2.135)
        c = summary.setdefault(HEI.nodal_state_of(r["state"]), {"testing": 0, "winners": 0, "registered": 0})
        c[r["status"]] = c.get(r["status"], 0) + r["n"]
        if r["status"] == "accepted":
            c["testing"] += r["testing"] or 0
            c["winners"] += r["winners"] or 0
            c["registered"] += r["registered"] or 0
    # selected, on the reserve list or declined before they registered (1.2.173), by the row of Annexure-I
    stray = {}
    for r in query("SELECT state, COUNT(*) AS n" + s_sql + " AND " + HEI.UNREGISTERED_SQL + " GROUP BY state", s_args):
        unit = HEI.nodal_state_of(r["state"])
        stray[unit] = stray.get(unit, 0) + r["n"]
    # selected or on the reserve list without the marks of Annexure-V (before 1.2.174), by the row of Annexure-I
    unmarked = {}
    for r in query("SELECT state, COUNT(*) AS n" + s_sql + " AND " + HEI.UNMARKED_SQL + " GROUP BY state", s_args):
        unit = HEI.nodal_state_of(r["state"])
        unmarked[unit] = unmarked.get(unit, 0) + r["n"]
    states = scope if scope is not None else _states()
    units = list(dict.fromkeys(HEI.nodal_state_of(s) for s in states))
    allocation = {h["state"]: h.get("allocation", 0) for h in _nodal_heis()}
    settings = all_settings()
    return render_template("console/institutions.html", rows=rows[:INST_ROWS_SHOWN], more=len(rows) > INST_ROWS_SHOWN, f=f,
                           states=states, units=units, labels={u: HEI.label_of(u, "en") for u in units},
                           summary=summary, allocation=allocation, scope=scope, stray=[(u, stray[u]) for u in units if stray.get(u)],
                           can_decide=has_perm(user, "hei.decide"), window=HEI.window(settings),
                           reg_end=settings.get("reg.end"), assess_to=settings.get("camp.to"), hei_end=settings.get("hei.end"),
                           select_end=settings.get("hei.select_end"), unmarked=[(u, unmarked[u]) for u in units if unmarked.get(u)],
                           reserve_public=settings.get("hei.public") == "1" and settings.get("hei.reserve_public") == "1",
                           marks_first=settings.get("hei.marks_first") == "1",
                           sop_max=sum(m for _k, _c, m, *_ in HEI.SOP), benchmark=HEI.SOP_BENCHMARK,
                           marks={r["id"]: HEI.sop_marks(r) for r in rows[:INST_ROWS_SHOWN]}, order=request.args.get("order", ""))


@bp.route("/institutions/<int:iid>/marks", methods=["GET", "POST"])
@login_required("hei.decide")
def institution_marks(iid):
    """
    The marks of the evaluation committee of the Nodal Institution on the criteria of Annexure-V of the D.O. letter of 31 October
    2026 (1.2.155; of 26 October in 1.2.111), each one of the marks its scoring parameters give; their total out of 100 orders the
    institutions of the State/UT.
    """
    user = _user()
    scope = state_scope(user)
    row = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
    if row is None or (scope is not None and row["state"] not in scope):
        abort(404)
    marks, errors = HEI.sop_marks(row), {}
    note = row["sop_note"] or ""
    if request.method == "POST":
        note = (request.form.get("note") or "").strip()[:1000]
        marks = {}
        for key, _criterion, _most, _parameters, _evidence, allowed in HEI.SOP:
            value = (request.form.get(key) or "").strip()
            if not value.isdigit() or int(value) not in allowed:
                errors[key] = "one of " + ", ".join(str(m) for m in allowed)
            else:
                marks[key] = int(value)
        if not errors:
            now = utcnow()
            execute("UPDATE institutions SET sop_scores = ?, sop_total = ?, sop_note = ?, sop_by = ?, sop_at = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(marks), sum(marks.values()), note, user["id"], now, now, iid))
            audit("institution_marked", "institution", iid, detail={"ref": row["ref"], "total": sum(marks.values())}, user=user, ip=client_ip())
            flash(f"{row['name']}: {sum(marks.values())} of 100 recorded.", "success")
            return redirect(url_for("admin.institutions", state=row["state"], order="marks"))
    return render_template("console/institution_marks.html", row=row, marks=marks, errors=errors, note=note, sop=HEI.SOP,
                           legacy=HEI.sop_legacy(row),
                           benchmark=HEI.SOP_BENCHMARK, allocation=HEI.allocation_of(row["state"]),
                           marks_first=get_setting("hei.marks_first") == "1")


@bp.route("/institutions/evaluation.xlsx")
@login_required("hei.view")
def institutions_evaluation():
    """
    The evaluation sheet of Annexure-V, State/UT by State/UT: every registered institution with the marks of the committee, ranked
    by the total and the tie-breaks, with the number Annexure-I prescribes, for the committee to sign and the competent authority
    to approve (1.2.111). An institution of the reserve list has its place in that list, which has no upper limit (1.2.174).
    """
    scope = state_scope(_user())
    sql, args = "SELECT * FROM institutions WHERE status != 'identified'", []
    if scope is not None:
        sql += f" AND state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        args += scope
    if request.args.get("state"):
        # the row of Annexure-I: a State with the Union Territory paired with it, ranked together (1.2.155); asked for the
        # Union Territory, the sheet is that of the row too, so that the ranks are those of the row (1.2.174)
        covered = HEI.with_covered([HEI.nodal_state_of(request.args["state"])])
        sql += f" AND state IN ({','.join('?' * len(covered))})"
        args += covered
    rows = query(sql, args)
    nodal = {s: h["name"] for h in _nodal_heis() for s in HEI.group_of(h["state"])}   # a paired Union Territory: its State's (1.2.135)
    headers = (["State/UT", "Nodal HEI", "Number to be selected (Annexure-I)", "Rank", "Name of Institution",
                "Reference", "District/City", "Type", "AISHE/Institution Code", "Registered on"]
               + [f"{criterion} (max {most})" for _k, criterion, most, *_ in HEI.SOP]
               + ["Total (100)", f"Benchmark {HEI.SOP_BENCHMARK}", "Status", "Remarks of the committee"])
    data, ranks = [], {}
    # the place of an institution in the reserve list of its row of Annexure-I, as the website gives it: whatever the sheet holds
    place = {x["id"]: n for _unit, items in HEI.reserve_by_unit(_states()) for n, x in enumerate(items, start=1)
             if x["sop_total"] is not None}
    for r in sorted(rows, key=lambda r: (HEI.nodal_state_of(r["state"]), HEI.sop_order(r))):
        marks = HEI.sop_marks(r)
        unit = HEI.nodal_state_of(r["state"])   # a paired Union Territory is ranked with its State (1.2.135)
        ranks[unit] = ranks.get(unit, 0) + 1
        scored = r["sop_total"] is not None
        status = {"accepted": "selected", "reserve": "reserve list"}.get(r["status"], r["status"])
        if r["id"] in place:   # one without marks (before 1.2.174) has no place yet
            status = f"reserve list {place[r['id']]}"
        data.append((r["state"], nodal.get(r["state"], ""), HEI.allocation_of(r["state"]) or "",
                     ranks[unit] if scored else "", r["name"], r["ref"], r["district"], r["itype"], r["aishe_code"],
                     (r["created_at"] or "")[:10])
                    + tuple(marks.get(k, "") for k, *_ in HEI.SOP)
                    + (r["sop_total"] if scored else "", ("yes" if r["sop_total"] >= HEI.SOP_BENCHMARK else "no") if scored else "",
                       status, r["sop_note"] or ""))
    audit("institutions_evaluation_exported", "institution", None, detail={"rows": len(data)}, user=_user(), ip=client_ip())
    return Response(xlsx_bytes(headers, data, "Evaluation (Annexure-V)", text_cols=(8,)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-evaluation-sheet-Annexure-V.xlsx"})


# ---- the progress of the institutions in the week of the assessments (1.2.52) ------------------------------------

PROGRESS_STAGES = ("behind", "none", "testing", "selected", "registered", "verified", "all")


@bp.route("/progress", methods=["GET", "POST"])
@login_required("hei.view")
def progress():
    """
    The stage of each participating institution, State/UT by State/UT; the institutions that are behind,
    with their coordinators; the reminders mailed to them, and a reminder by hand (kts/progress.py).
    """
    user = _user()
    scope = state_scope(user)
    if request.method == "POST":
        if not has_perm(user, "hei.decide"):
            abort(403)
        state = (request.form.get("state") or "").strip()
        if state and scope is not None and state not in scope:
            abort(404)
        reg_end = PROGRESS.schedule()[1]
        if reg_end and now_ist().date() > reg_end:
            flash("The last date of registration has passed: no reminder is sent.", "error")
        else:
            n = PROGRESS.remind_now(PROGRESS.institutions(scope, state or None), user)
            audit("institutions_reminded", "institution", None, detail={"count": n, "state": state or "all"}, user=user, ip=client_ip())
            flash(f"A reminder is mailed to {n} institution(s) that are behind." if n
                  else "No institution is behind, or each has had a reminder today.", "success" if n else "info")
        return redirect(url_for("admin.progress", state=state or None))
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "stage")}
    if f["state"] and scope is not None and f["state"] not in scope:
        f["state"] = ""
    stage = f["stage"] if f["stage"] in PROGRESS_STAGES else "behind"
    rows = PROGRESS.institutions(scope, f["state"] or None)
    behind = PROGRESS.behind(rows)
    shown = behind if stage == "behind" else rows if stage == "all" else [r for r in rows if r["stage"] == stage]
    settings = all_settings()
    plan, reg_end = PROGRESS.schedule(settings)
    return render_template("console/progress.html", board=PROGRESS.board(scope), rows=shown[:INST_ROWS_SHOWN],
                           more=max(len(shown) - INST_ROWS_SHOWN, 0), shown_count=len(shown), behind_count=len(behind),
                           f=f, stage=stage, stages=PROGRESS_STAGES, stage_names=PROGRESS.STAGE_NAMES, scope=scope,
                           settings=settings, plan=plan, reg_end=reg_end, sent=PROGRESS.sent_counts(scope),
                           can_remind=has_perm(user, "hei.decide"), today=now_ist().date())


@bp.route("/progress.xlsx")
@login_required("hei.view")
def progress_export():
    """Every participating institution (of the Nodal Officer's States/UTs) with its stage, for calls and follow-up."""
    rows = PROGRESS.institutions(state_scope(_user()))
    headers = ["State/UT", "Reference", "Institution", "District/City", "Stage", "Coordinator", "Coordinator e-mail", "Coordinator mobile",
               "Head of the Institution", "Head e-mail", "Online assessment", "Students signed up", "Students tested", "Selected student",
               "Application no.", "Application status", "Reminders sent", "Last reminder"]
    data = [(r["state"], r["ref"], r["name"], r["district"], PROGRESS.STAGE_NAMES[r["stage"]], r["coord_name"], r["coord_email"],
             r["coord_mobile"], r["head_name"], r["head_email"],
             f"{r['test_from']} to {r['test_to']}" if r["test_on"] else "", r["signed_up"], r["tested"], r["winner_name"] or "",
             r["app_no"] or "", (r["app_status"] or "").replace("_", " "), r["reminders"], (r["reminded_at"] or "")[:16].replace("T", " "))
            for r in rows]
    return Response(xlsx_bytes(headers, data, "Progress", text_cols=(7, 14)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-institutions-progress.xlsx"})


NOMINEE_STAGES = (("all", "all"), ("link", "nomination not submitted yet"), ("registered", "submitted, awaiting verification"),
                  ("verified", "verified"))


def _nominees(scope, state="", stage="all", q=""):
    """
    The students selected on merit by the Participating Institutions (institutions.winner_id, from the institution's page, 1.2.43 and
    1.2.154), State/UT by State/UT: the student, the institution, the day of the selection, the online test if the student took it,
    and the application once the student has registered with the institution's personal link (1.2.157).
    """
    sql = ("SELECT i.id AS inst_id, i.name AS inst_name, i.ref, i.state, i.district, i.coord_name, i.coord_email, i.coord_mobile, "
           "i.guide_name, i.winner_at, i.application_id, w.name, w.email, w.mobile, w.roll_no, w.course, w.lang, w.source, "
           "t.status AS t_status, t.score, t.correct_count, a.app_no, a.status AS app_status "
           "FROM institutions i JOIN campus_students w ON w.id = i.winner_id "
           "LEFT JOIN campus_attempts t ON t.student_id = w.id AND t.status IN ('submitted', 'expired') "
           "LEFT JOIN applications a ON a.id = i.application_id WHERE i.status = 'accepted'")
    args = []
    if scope is not None:
        sql += f" AND i.state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        args += scope
    if state:   # a State with the Union Territory Annexure-I pairs with it
        group = HEI.with_covered([state])
        sql += f" AND i.state IN ({','.join('?' * len(group))})"
        args += group
    verified = ",".join("?" * len(PROGRESS.VERIFIED))
    if stage == "link":
        sql += " AND i.application_id IS NULL"
    elif stage == "registered":
        sql += f" AND i.application_id IS NOT NULL AND a.status NOT IN ({verified})"
        args += PROGRESS.VERIFIED
    elif stage == "verified":
        sql += f" AND a.status IN ({verified})"
        args += PROGRESS.VERIFIED
    if q:
        sql += (" AND (w.name LIKE ? OR w.email LIKE ? OR w.mobile LIKE ? OR w.roll_no LIKE ? OR i.name LIKE ? OR i.ref LIKE ? "
                "OR a.app_no LIKE ?)")
        args += [f"%{q}%"] * 7
    return query(sql + " ORDER BY i.state, i.name COLLATE NOCASE", args)


@bp.route("/nominees")
@login_required("hei.view")
def nominees():
    """The students selected on merit by the Participating Institutions, before and after they register (1.2.157)."""
    scope = state_scope(_user())
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "stage", "q")}
    if f["state"] and scope is not None and f["state"] not in scope:
        f["state"] = ""
    if f["stage"] not in dict(NOMINEE_STAGES):
        f["stage"] = "all"
    every = _nominees(scope)
    board = PROGRESS.board(scope)
    k = {"all": len(every), "link": sum(1 for r in every if not r["application_id"]),
         "verified": sum(1 for r in every if r["app_status"] in PROGRESS.VERIFIED)}
    k["registered"] = k["all"] - k["link"] - k["verified"]
    k["yet"] = max(board["total"]["participating"] - k["all"], 0)
    rows = every if (f["stage"] == "all" and not f["state"] and not f["q"]) else _nominees(scope, f["state"], f["stage"], f["q"])
    return render_template("console/nominees.html", rows=rows, k=k, f=f, states=board["states"], stages=NOMINEE_STAGES, scope=scope,
                           verified=PROGRESS.VERIFIED, settings=all_settings())


@bp.route("/nominees.xlsx")
@login_required("hei.view")
def nominees_export():
    """Every student selected on merit (of the Nodal Officer's States/UTs), with the contacts (1.2.157)."""
    rows = _nominees(state_scope(_user()))
    headers = ["S. No.", "State/UT", "Participating Institution", "Reference", "District/City", "Student", "Course", "Roll no.", "E-mail",
               "Mobile", "Language", "Selected on", "Online test (marks)", "Correct answers", "Application no.", "Application status",
               "Institutional Coordinator", "Coordinator e-mail", "Coordinator mobile", "Faculty Supervisor/Guide"]
    data = [(n, r["state"], r["inst_name"], r["ref"], r["district"], r["name"], r["course"], r["roll_no"], r["email"], r["mobile"],
             r["lang"], (r["winner_at"] or "")[:16].replace("T", " "), r["score"] if r["t_status"] else "",
             r["correct_count"] if r["t_status"] else "", r["app_no"] or "",
             (r["app_status"] or "").replace("_", " ") if r["app_no"] else "nomination not submitted yet",
             r["coord_name"], r["coord_email"], r["coord_mobile"], r["guide_name"] or "")
            for n, r in enumerate(rows, start=1)]
    return Response(xlsx_bytes(headers, data, "Selected on merit", text_cols=(7, 9, 14, 18)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-students-selected-on-merit.xlsx"})


def _presentations(scope, state="", status=""):
    """The presentation videos submitted by the Participating Institutions (1.2.158), State/UT by State/UT."""
    sql = ("SELECT p.*, i.name AS inst_name, i.ref, i.state, i.coord_name, i.coord_email, i.coord_mobile, a.app_no, a.full_name "
           "FROM presentations p JOIN institutions i ON i.id = p.institution_id LEFT JOIN applications a ON a.id = p.application_id "
           "WHERE 1=1")
    args = []
    if scope is not None:
        sql += f" AND i.state IN ({','.join('?' * len(scope))})" if scope else " AND 0"
        args += scope
    if state:
        group = HEI.with_covered([state])
        sql += f" AND i.state IN ({','.join('?' * len(group))})"
        args += group
    if status in ("submitted", "accepted", "returned"):
        sql += " AND p.status = ?"
        args.append(status)
    due = (get_setting("present.due") or "")[:10]
    rows = query(sql + " ORDER BY i.state, i.name COLLATE NOCASE", args)
    return [dict(r, late=bool(due) and (r["updated_at"] or "")[:10] > due) for r in rows]


@bp.route("/presentations", methods=["GET", "POST"])
@login_required("hei.view")
def presentations():
    """The videos of the one-hour presentations of the selected students (Annexure-III C-4, 1.2.158): CICT accepts or returns each."""
    user = _user()
    scope = state_scope(user)
    if request.method == "POST":
        if not has_perm(user, "papers.review"):
            abort(403)
        row = query("SELECT p.*, i.name AS inst_name, i.ref, i.state, i.coord_name, i.coord_email FROM presentations p "
                    "JOIN institutions i ON i.id = p.institution_id WHERE p.id = ?", (safe_int(request.form.get("id")),), one=True)
        if row is None or (scope is not None and row["state"] not in scope):
            abort(404)
        action = request.form.get("action")
        note = (request.form.get("note") or "").strip()[:500]
        if action not in ("accept", "return"):
            abort(400)
        if action == "return" and not note:
            flash("Write the remark that goes to the institution with the return.", "error")
            return redirect(url_for("admin.presentations", **request.args.to_dict()))
        status = "accepted" if action == "accept" else "returned"
        execute("UPDATE presentations SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                (status, note if status == "returned" else "", user["id"], utcnow(), row["id"]))
        audit("presentation_" + status, "institution", row["institution_id"], detail={"ref": row["ref"], "note": note}, user=user,
              ip=client_ip())
        base = current_app.config["BASE_URL"]
        if status == "accepted":
            send_mail(row["coord_email"], f"KTS 5.0: the video of the presentation is accepted ({row['ref']})",
                      f"Dear {row['coord_name']},\n\nCICT has accepted the video recording of the presentation of the student of "
                      f"{row['inst_name']} (\u201c{row['title']}\u201d).\n\nCentral Institute of Classical Tamil, Chennai")
        else:
            send_mail(row["coord_email"], f"KTS 5.0: the video of the presentation is returned ({row['ref']})",
                      f"Dear {row['coord_name']},\n\nCICT has returned the video recording of the presentation of the student of "
                      f"{row['inst_name']} (\u201c{row['title']}\u201d), with this remark:\n\n{note}\n\nPlease correct it and submit "
                      f"it again at {base}/institution/presentation\n\nCentral Institute of Classical Tamil, Chennai")
        flash(f"{row['inst_name']}: the video is {status}; the coordinator is informed by mail.", "success")
        return redirect(url_for("admin.presentations", **request.args.to_dict()))
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "status")}
    if f["state"] and scope is not None and f["state"] not in scope:
        f["state"] = ""
    every = _presentations(scope)
    nominated = PROGRESS.board(scope)["total"]["registered"]
    k = {"all": len(every), "nominated": nominated, "late": sum(1 for r in every if r["late"] and r["status"] == "submitted")}
    for s in ("submitted", "accepted", "returned"):
        k[s] = sum(1 for r in every if r["status"] == s)
    rows = every if not (f["state"] or f["status"]) else _presentations(scope, f["state"], f["status"])
    return render_template("console/presentations.html", rows=rows, k=k, f=f, states=PROGRESS.board(scope)["states"], scope=scope,
                           can_review=has_perm(user, "papers.review"), settings=all_settings())


@bp.route("/presentations.xlsx")
@login_required("hei.view")
def presentations_export():
    """Every presentation video (of the Nodal Officer's States/UTs), with the links (1.2.158)."""
    rows = _presentations(state_scope(_user()))
    headers = ["S. No.", "State/UT", "Participating Institution", "Reference", "Student", "Application no.", "Title of the presentation",
               "Date", "Minutes", "Attended", "Video", "Presentation material", "Remarks", "Submitted", "After the last date", "Status",
               "Remark of CICT", "Institutional Coordinator", "Coordinator e-mail", "Coordinator mobile"]
    data = [(n, r["state"], r["inst_name"], r["ref"], r["full_name"] or "", r["app_no"] or "", r["title"], r["held_on"], r["minutes"],
             r["audience"] if r["audience"] is not None else "", r["video_url"], r["material_url"], r["note"],
             (r["updated_at"] or "")[:16].replace("T", " "), "yes" if r["late"] else "", r["status"], r["review_note"],
             r["coord_name"], r["coord_email"], r["coord_mobile"])
            for n, r in enumerate(rows, start=1)]
    return Response(xlsx_bytes(headers, data, "Presentation videos", text_cols=(5, 10, 11, 19)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-presentation-videos.xlsx"})


ANNEXURE_II = ["S. No.", "Name of Institution", "District/City", "Type", "AISHE/Institution Code", "Institutional Coordinator Name",
               "Mobile No.", "Official Email ID"]


@bp.route("/institutions/annexure-ii.xlsx")
@login_required("hei.decide")
def institutions_format():
    """The format of the list of institutions to invite (the State/UT column takes the list of a Nodal Officer of several States/UTs;
    called Annexure-II before 1.2.155 - Annexure-II is the final list of the selected institutions, institutions_annexure_ii)."""
    return Response(xlsx_bytes(ANNEXURE_II + ["State/UT"], [], "Annexure-II", text_cols=(4, 6)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-institutions-to-invite.xlsx"})


def _annexure_columns(rows):
    for i, row in enumerate(rows[:10]):
        heads = [(c or "").strip().lower() for c in row]
        name = next((j for j, h in enumerate(heads) if "institution" in h and "name" in h and "coordinator" not in h), None)
        if name is None:
            name = next((j for j, h in enumerate(heads) if h in ("institution", "name")), None)
        mail = next((j for j, h in enumerate(heads) if "mail" in h), None)
        if name is None or mail is None:
            continue
        return i, {"name": name, "email": mail,
                   "district": next((j for j, h in enumerate(heads) if "district" in h or "city" in h), None),
                   "itype": next((j for j, h in enumerate(heads) if h.startswith("type")), None),
                   "aishe": next((j for j, h in enumerate(heads) if "aishe" in h or "code" in h), None),
                   "coord": next((j for j, h in enumerate(heads) if "coordinator" in h), None),
                   "mobile": next((j for j, h in enumerate(heads) if "mobile" in h or "phone" in h), None),
                   "state": next((j for j, h in enumerate(heads) if "state" in h), None)}
    return None


@bp.route("/institutions/back-to-invited", methods=["POST"])
@login_required("hei.decide")
def institutions_back_to_invited():
    """
    Every institution of a row of Annexure-I that its Nodal Institution identified and that was selected, put on the reserve list
    or declined before it completed its registration goes back to 'identified', each invited again by mail with a new link (1.2.173;
    the Nodal Institution of Maharashtra, 11 November 2026). One with a selected student, students or its online assessment on stays.
    """
    user = _user()
    scope = state_scope(user)
    state = (request.form.get("state") or "").strip()
    members = [s for s in (HEI.group_of(state) if state in _states() else []) if scope is None or s in scope]
    if not members:
        abort(404)
    rows = query(f"SELECT * FROM institutions WHERE state IN ({','.join('?' * len(members))}) AND {HEI.UNREGISTERED_SQL} "
                 "ORDER BY name COLLATE NOCASE", members)
    back, kept = [], []
    for row in rows:
        busy = HEI.busy_reason(row)
        if busy:
            kept.append(f"{row['name']} ({busy})")
            continue
        HEI.back_to_invited(row)
        back.append(row["ref"])
    label = HEI.label_of(state, "en")
    audit("institutions_reinvited", "institution", None, detail={"state": label, "back": back, "kept": kept}, user=user, ip=client_ip())
    flash(f"{label}: {len(back)} institution(s) back to identified · invited, each invited again by mail"
          + (f"; {len(kept)} stay as they are: " + "; ".join(kept) if kept else "") + ".", "success" if back else "error")
    return redirect(url_for("admin.institutions", state=HEI.nodal_state_of(state), status="identified"))


@bp.route("/institutions/identified", methods=["POST"])
@login_required("hei.decide")
def institutions_identified():
    """
    A list of institutions that the Nodal Institution invites to register, uploaded as .xlsx or .csv: each becomes an institution
    'identified', invited by mail to complete its registration; then it awaits the selection like any other (1.2.155; accepted at once
    before, which the D.O. letter of 31 October 2026 does not allow: the selection is under Annexure-V, within Annexure-I).
    """
    user = _user()
    scope = state_scope(user)
    known = _states()
    chosen_state = (request.form.get("state") or "").strip()
    f = request.files.get("file")
    filename = (f.filename or "") if f else ""
    if not filename.lower().endswith((".xlsx", ".csv")):
        flash("Upload the list as an Excel file (.xlsx) or as .csv, in the format of the list of institutions to invite.", "error")
        return redirect(url_for("admin.institutions"))
    data = f.read(SHEET_MAX_BYTES + 1)
    if len(data) > SHEET_MAX_BYTES:
        flash("The list is larger than 1 MB.", "error")
        return redirect(url_for("admin.institutions"))
    try:
        rows = sheet_rows(filename, data)
    except Exception:  # noqa: BLE001
        flash("The file could not be read as a spreadsheet: save it from Excel as .xlsx and upload it again.", "error")
        return redirect(url_for("admin.institutions"))
    found = _annexure_columns(rows)
    if not found:
        flash("The list needs at least the columns Name of Institution and Official Email ID (the format of the list of institutions to invite).", "error")
        return redirect(url_for("admin.institutions"))
    head, cols = found
    ref = json.loads((current_app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
    types = {t.lower(): t for t in ref["college_types"]}
    created, skipped = [], []
    now = utcnow()
    for n, cells in enumerate(rows[head + 1:], start=head + 2):
        def cell(key):
            j = cols[key]
            return (cells[j] if j is not None and j < len(cells) else "").strip()
        name = " ".join(cell("name").split())
        if not name:
            continue
        state = _canon_state(cell("state"), known) if cols["state"] is not None and cell("state") else chosen_state
        if not state or state not in known:
            skipped.append((n, name, "no State/UT"))
            continue
        if scope is not None and state not in scope:
            skipped.append((n, name, f"{state} is not yours"))
            continue
        email = cell("email").lower()
        if not valid_email(email):
            skipped.append((n, name, "no valid e-mail address"))
            continue
        itype = cell("itype")
        itype = types.get(itype.lower()) or next((t for low, t in types.items() if itype and (itype.lower() in low or low in itype.lower())), "Other")
        aishe = cell("aishe").upper().replace(" ", "")[:20]
        d = {"name": name, "state": state, "aishe_code": aishe}
        if HEI.duplicate(d):
            skipped.append((n, name, "is in the list already"))
            continue
        mobile = re.sub(r"\D", "", cell("mobile"))[-10:]
        token = secrets.token_urlsafe(18)
        rid = execute("INSERT INTO institutions(name, itype, state, district, aishe_code, inst_key, coord_name, coord_email, coord_mobile, "
                      "status, invite_token, invited_by, ip, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,'identified',?,?,?,?,?)",
                      (name, itype, state, cell("district"), aishe, HEI.key_of(d), cell("coord"), email, mobile, token, user["id"],
                       client_ip(), now, now))
        execute("UPDATE institutions SET ref = ? WHERE id = ?", (HEI.ref_of(rid), rid))
        HEI.mail_invited(query("SELECT * FROM institutions WHERE id = ?", (rid,), one=True))
        created.append((n, name, state))
    audit("institutions_identified", "institution", None, detail={"created": len(created), "skipped": len(skipped), "file": filename},
          user=user, ip=client_ip())
    return render_template("console/institutions_identified.html", created=created, skipped=skipped, filename=filename)


@bp.route("/institutions/annexure-ii-selected.xlsx")
@login_required("hei.view")
def institutions_annexure_ii():
    """
    The final list of the institutions selected by the Nodal HEI, in the format of Annexure-II of the D.O. letter of 31 October 2026
    (1.2.155): for each row of Annexure-I that the account sees (or the State/UT asked for), its five head lines - State/UT, Name of
    Nodal HEI, Number of institutions prescribed in Annexure-I, Total registrations received, Number of institutions selected - and
    the selected institutions: # | Name of Institution | District/City | Type | AISHE/Institution Code | Coordinator Name | Mobile No. |
    Email ID.
    """
    import xlsxwriter
    scope = state_scope(_user())
    want = (request.args.get("state") or "").strip()
    blocks = []
    for h in _nodal_heis():
        members = HEI.group_of(h["state"])
        if (scope is not None and not any(m in scope for m in members)) or (want and want not in members):
            continue
        marks = ",".join("?" * len(members))
        registered = query(f"SELECT COUNT(*) AS n FROM institutions WHERE status != 'identified' AND state IN ({marks})", members, one=True)["n"]
        selected = query(f"SELECT * FROM institutions WHERE status = 'accepted' AND state IN ({marks}) ORDER BY name COLLATE NOCASE", members)
        blocks.append((HEI.label_of(h["state"]), h["name"], int(h.get("allocation") or 0), registered, selected))
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet("Annexure-II")
    bold = wb.add_format({"bold": True})
    head = wb.add_format({"bold": True, "bg_color": "#EDE7DB", "border": 1, "text_wrap": True})
    cell = wb.add_format({"border": 1})
    text = wb.add_format({"border": 1, "num_format": "@"})
    ws.write(0, 0, "ANNEXURE-II", bold)
    ws.write(1, 0, "FORMAT FOR LIST OF INSTITUTIONS SELECTED BY THE NODAL HEI", bold)
    r = 3
    for label, hei, prescribed, registered, selected in blocks:
        for line in (f"State/UT: {label}", f"Name of Nodal HEI: {hei}", f"Number of institutions prescribed in Annexure-I: {prescribed}",
                     f"Total registrations received: {registered}", f"Number of institutions selected: {len(selected)}"):
            ws.write(r, 0, line, bold)
            r += 1
        for c, title in enumerate(("#", "Name of Institution", "District/City", "Type", "AISHE/Institution Code", "Coordinator Name",
                                   "Mobile No.", "Email ID")):
            ws.write(r, c, title, head)
        r += 1
        for n, i in enumerate(selected, start=1):
            for c, (value, fmt) in enumerate(((n, cell), (i["name"], cell), (i["district"], cell), (i["itype"], cell),
                                              (i["aishe_code"] or "", text), (i["coord_name"] or "", cell), (i["coord_mobile"] or "", text),
                                              (i["coord_email"] or "", cell))):
                ws.write(r, c, value, fmt) if fmt is cell else ws.write_string(r, c, str(value), fmt)
            r += 1
        r += 2
    for c, width in enumerate((5, 48, 22, 26, 22, 28, 14, 32)):
        ws.set_column(c, c, width)
    wb.close()
    audit("institutions_annexure_ii_exported", "institution", None, detail={"rows": len(blocks)}, user=_user(), ip=client_ip())
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-Annexure-II-selected-institutions.xlsx"})


@bp.route("/institutions/export.xlsx")
@login_required("hei.view")
def institutions_export():
    """Every institution of the filter with its details and the state of its assessment and nomination (the final list in the format
    of Annexure-II is institutions_annexure_ii, 1.2.155)."""
    _f, sql, args = _inst_filters(state_scope(_user()))
    rows = query("SELECT i.*, a.app_no AS app_no, a.status AS app_status, w.name AS winner_name, "
                 "(SELECT COUNT(*) FROM campus_students s JOIN campus_attempts t ON t.student_id = s.id "
                 " WHERE s.institution_id = i.id AND t.status != 'in_progress') AS assessed"
                 + sql.replace(" FROM institutions i WHERE", " FROM institutions i LEFT JOIN applications a ON a.id = i.application_id "
                                                             "LEFT JOIN campus_students w ON w.id = i.winner_id WHERE")
                 + " ORDER BY i.state, i.name COLLATE NOCASE", args)
    nodal = {s: h["name"] for h in _nodal_heis() for s in HEI.group_of(h["state"])}   # a paired Union Territory: its State's (1.2.135)
    headers = ["State/UT", "Name of Nodal HEI"] + ANNEXURE_II + ["Status", "Reference", "Head of the Institution", "Designation",
               "Head: e-mail", "Head: phone", "Coordinator: designation", "Faculty Supervisor/Guide", "Guide: designation",
               "Guide: e-mail", "Guide: mobile", "Online assessment", "Students assessed", "Selected student", "Registered (application)",
               "Application status", "Remark", "Applied on", "Decided on", "Source"]
    data = []
    for n, r in enumerate(rows, start=1):
        test = "off" if not r["test_on"] else f"{r['test_from']} to {r['test_to']}"
        data.append((r["state"], nodal.get(r["state"], ""), n, r["name"], r["district"], r["itype"], r["aishe_code"], r["coord_name"],
                     r["coord_mobile"], r["coord_email"], r["status"], r["ref"], r["head_name"], r["head_designation"], r["head_email"],
                     r["head_phone"], r["coord_designation"], r["guide_name"], r["guide_designation"], r["guide_email"], r["guide_mobile"],
                     test, r["assessed"], r["winner_name"] or "", r["app_no"] or "", r["app_status"] or "",
                     r["decision_note"], (r["created_at"] or "")[:10], (r["decided_at"] or "")[:10],
                     "State/UT page" if r["source"] == "join" else ""))
    audit("institutions_exported", "institution", None, detail={"rows": len(data)}, user=_user(), ip=client_ip())
    return Response(xlsx_bytes(headers, data, "Institutions", text_cols=(6, 8, 15, 20)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-participating-institutions.xlsx"})


@bp.route("/institutions/<int:iid>/edit", methods=["GET", "POST"])
@login_required("hei.decide")
def institution_edit(iid):
    """Corrects what an institution wrote; the applications of its students follow (1.2.41)."""
    scope = state_scope(_user())
    row = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
    if row is None or (scope is not None and row["state"] not in scope):
        abort(404)
    known = _states()
    ref = json.loads((current_app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
    data, errors = dict(row), {}
    if request.method == "POST":
        data.update({f: (request.form.get(f) or "").strip() for f in HEI.FIELDS})
        # an institution registered before 1.2.46 has no Faculty Supervisor/Guide yet: CICT may save it without one
        for f in HEI.REQUIRED:
            if not data[f] and not f.startswith(("guide_", "coord_designation")):
                errors[f] = "required"
        for f in HEI.EMAILS:
            data[f] = data[f].lower()
            if data[f] and not valid_email(data[f]):
                errors[f] = "not a valid e-mail address"
        if data["state"] not in known or (scope is not None and data["state"] not in scope):
            errors["state"] = "choose a State/UT" + (" of your own" if scope is not None else "")
        if data["itype"] not in ref["college_types"]:
            errors["itype"] = "choose a type"
        data["aishe_code"] = data["aishe_code"].upper().replace(" ", "")[:20]
        if not errors and HEI.duplicate(data, exclude_id=iid):
            errors["name"] = "another application of this institution exists"
        if not errors:
            execute(f"UPDATE institutions SET {', '.join(f + ' = ?' for f in HEI.FIELDS)}, inst_key = ?, updated_at = ? WHERE id = ?",
                    [data[f] for f in HEI.FIELDS] + [HEI.key_of(data), utcnow(), iid])
            from .utils import college_key
            execute("UPDATE applications SET college_name = ?, aishe_code = ?, college_type = ?, college_state = ?, college_district = ?, "
                    "college_key = ? WHERE institution_id = ?",
                    (data["name"], data["aishe_code"], data["itype"], data["state"], data["district"],
                     college_key(data["name"], data["state"], data["aishe_code"]), iid))
            audit("institution_updated", "institution", iid, detail=row["ref"], user=_user(), ip=client_ip())
            flash(f"Saved {data['name']}.", "success")
            return redirect(url_for("admin.institutions", state=data["state"]))
        flash("Please correct the fields marked.", "error")
    return render_template("console/institution_edit.html", d=data, errors=errors, row=row,
                           states=scope if scope is not None else known, types=ref["college_types"])


NODAL_SHEET = ["State/UT", "Nodal HEI", "Name of the Nodal Officer", "Designation", "E-mail", "Phone"]


@bp.route("/nodal/sheet.xlsx")
@login_required("users")
def nodal_sheet():
    """The sheet to fill in: every State/UT with its Nodal Institution and the accounts that exist."""
    heis = _nodal_heis()
    officers = _officers_by_state()
    covered = {s for h in heis for s in HEI.group_of(h["state"])}   # a paired Union Territory has its State's row (1.2.135)
    rows = []
    for state, hei in [(h["state"], h["name"]) for h in heis] + [(s, "") for s in _states() if s not in covered]:
        people = officers.get(state) or [None]
        for u in people:
            rows.append((state, hei, u["name"] if u else "", (u["designation"] or "") if u else "", u["email"] if u else "",
                         (u["phone"] or "") if u else ""))
    return Response(xlsx_bytes(NODAL_SHEET, rows, "Nodal officers", text_cols=(4, 5)),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=KTS5-nodal-officers.xlsx"})


def _canon_state(value, known):
    key = " ".join((value or "").replace("&", "and").split()).lower()
    for s in known:
        if " ".join(s.replace("&", "and").split()).lower() == key:
            return s
    return None


def _sheet_columns(rows):
    """The row of the headings and the columns of State/UT, name, e-mail and phone; None when the sheet has none."""
    for i, row in enumerate(rows[:10]):
        heads = [(c or "").strip().lower() for c in row]
        mail = next((j for j, h in enumerate(heads) if "mail" in h), None)
        state = next((j for j, h in enumerate(heads) if "state" in h), None)
        name = next((j for j, h in enumerate(heads) if "name" in h and "officer" in h), None)
        if name is None:
            name = next((j for j, h in enumerate(heads) if "name" in h and "hei" not in h and "institution" not in h), None)
        phone = next((j for j, h in enumerate(heads) if "phone" in h or "mobile" in h), None)
        designation = next((j for j, h in enumerate(heads) if "designation" in h), None)
        if mail is not None and state is not None and name is not None:
            return i, {"state": state, "name": name, "email": mail, "phone": phone, "designation": designation}
    return None


def _nodal_plan(entries):
    """
    What the rows of the sheet will do: a new account, a State/UT added to an existing account of a
    Nodal Officer, nothing (the account has it, a repeated row), or an error. One officer may take
    several States/UTs: the same e-mail on several rows makes one account.
    """
    known = _states()
    users = {u["email"].lower(): u for u in query("SELECT email, role, states FROM users")}
    seen, plan = set(), []
    for e in entries:
        p = dict(e, error="", action="")
        p["email"] = (e.get("email") or "").strip().lower()
        p["name"] = " ".join((e.get("name") or "").split())
        p["phone"] = (e.get("phone") or "").strip()
        p["designation"] = " ".join((e.get("designation") or "").split())
        state = _canon_state(e.get("state"), known)
        if not state:
            p["error"] = f"unknown State/UT “{e.get('state')}”" if e.get("state") else "no State/UT"
        elif not p["name"]:
            p["error"] = "no name"
        elif not valid_email(p["email"]):
            p["error"] = "the e-mail address is not valid"
        else:
            p["state"] = state
            u = users.get(p["email"])
            if (p["email"], state) in seen:
                p["action"] = "repeated"
            elif u is None:
                p["action"] = "new"
            elif u["role"] != "nodal":
                p["error"] = f"the e-mail belongs to an account with the role {u['role']}; change that account under Users & roles"
            elif state in (u["states"] or "").split("|"):
                p["action"] = "has"
            else:
                p["action"] = "add"
            seen.add((p["email"], state))
        plan.append(p)
    return plan


@bp.route("/nodal/import", methods=["POST"])
@login_required("users")
def nodal_import():
    """The accounts of the Nodal Officers from the sheet: first what will happen, then, when confirmed, the accounts."""
    if request.form.get("step") == "confirm":
        try:
            entries = json.loads(request.form.get("entries") or "[]")
        except ValueError:
            entries = []
        entries = [{k: str(e.get(k) or "") for k in ("line", "state", "name", "email", "phone", "designation")}
                   for e in entries if isinstance(e, dict)][:500]
        new, more = {}, {}
        for p in _nodal_plan(entries):
            if p["action"] == "new":
                new.setdefault(p["email"], {"name": p["name"], "phone": p["phone"], "designation": p["designation"], "states": []})["states"].append(p["state"])
            elif p["action"] == "add":
                more.setdefault(p["email"], []).append(p["state"])
        for email, a in new.items():
            _create_account(email, a["name"], "nodal", a["phone"], a["states"], designation=a["designation"])
        for email, states in more.items():
            u = query("SELECT id, states FROM users WHERE lower(email) = ? AND role = 'nodal'", (email,), one=True)
            merged = NODAL.own_states(u) + [s for s in states if s not in NODAL.own_states(u)]
            execute("UPDATE users SET states = ? WHERE id = ?", ("|".join(merged), u["id"]))
            audit("user_updated", "user", u["id"], detail={"states": merged}, user=_user(), ip=client_ip())
        audit("nodal_accounts_imported", "user", None, detail={"created": len(new), "states_added": len(more)}, user=_user(), ip=client_ip())
        flash(f"Created {len(new)} account(s) of Nodal Officers, each mailed a temporary password; "
              f"added States/UTs to {len(more)} existing account(s).", "success")
        return redirect(url_for("admin.nodal_access"))
    f = request.files.get("file")
    filename = (f.filename or "") if f else ""
    if not filename.lower().endswith((".xlsx", ".csv")):
        flash("Upload the sheet as an Excel file (.xlsx) or as .csv.", "error")
        return redirect(url_for("admin.nodal_access"))
    data = f.read(SHEET_MAX_BYTES + 1)
    if len(data) > SHEET_MAX_BYTES:
        flash("The sheet is larger than 1 MB.", "error")
        return redirect(url_for("admin.nodal_access"))
    try:
        rows = sheet_rows(filename, data)
    except Exception:  # noqa: BLE001 - not a spreadsheet, or a damaged one
        flash("The file could not be read as a spreadsheet: save it from Excel as .xlsx and upload it again.", "error")
        return redirect(url_for("admin.nodal_access"))
    found = _sheet_columns(rows)
    if not found:
        flash("The sheet needs the columns State/UT, Name of the Nodal Officer and E-mail: download the sheet from this page and fill it in.", "error")
        return redirect(url_for("admin.nodal_access"))
    head, cols = found
    entries = []
    for n, cells in enumerate(rows[head + 1:], start=head + 2):
        def cell(key):
            j = cols[key]
            return (cells[j] if j is not None and j < len(cells) else "").strip()
        e = {"line": str(n), "state": cell("state"), "name": cell("name"), "email": cell("email"), "phone": cell("phone"),
             "designation": cell("designation")}
        if e["name"] or e["email"]:  # a State/UT not filled in is left alone
            entries.append(e)
    plan = _nodal_plan(entries)
    keep = [{k: p[k] for k in ("line", "state", "name", "email", "phone", "designation")} for p in plan if p["action"] in ("new", "add")]
    accounts = len({p["email"] for p in plan if p["action"] == "new"})
    added = len({p["email"] for p in plan if p["action"] == "add"})
    return render_template("console/nodal_import.html", plan=plan, entries=json.dumps(keep, ensure_ascii=False),
                           accounts=accounts, added=added, filename=filename)


# ---- settings / audit / outbox ----------------------------------------------

SETTING_GROUPS = [
    ("Site", [("site.banner", "Banner text", "text"), ("site.banner_on", "Show banner", "bool"), ("stats.public", "Show live counts on the home page", "bool"),
              ("home.hub", "Show “Find your next step” on the home page (a tab for each audience: what to do now, the days left, ‘Is your college taking part?’)", "bool"),
              ("home.launch_video", "Show the video of the launch of the web portal and registration (22 October 2026) on the home page", "bool"),
              ("reg.public", "Show the students' registration on the public pages: the menu, buttons and dates of the registration and of the application status, and the counts of student delegates registered (the pages /register and /status work either way)", "bool"),
              ("nominate.open", "The nomination by the Participating Institutions: the personal registration link of the student a Participating Institution has selected opens the registration form up to its last day (reg.end), even while the students' own registration is switched off (reg.open) or hidden (reg.public)", "bool"),
              ("schedule.central_test", "Show CICT's central online test (its days: exam.date to exam.date_to) in the schedule and among the upcoming events of the home page", "bool"),
              ("circular.new_days", "The newest circular of the Ministry (a circular notice with the letter attached) carries a blinking ‘NEW’ on the home page for so many days after it is put in (0: never)", "text"),
              ("home.circular", "Show the newest circular of the Ministry, with its PDF, first in the circular band of the home page (the notice stays under Notices either way)", "bool"),
              ("institutions.registered", "Show the number of institutions registered on the public pages: At a glance (home page, Participating Institutions), the Progress page, the dashboard by State/UT, the State/UT pages of the registration drive and “Find your next step” (the Console always shows it)", "bool"),
              ("nodal.covered", "Show the ring “Participating Institutions under a Nodal Officer” on the page of the Nodal Institutions", "bool"),
              ("events.public", "Show the seminars and workshops of CICT on the public pages: the menu, the cards on the home page and in the Digital repository, the figure in “KTS 5.0 in numbers”, the search and the sitemap (the page /seminars-workshops works either way)", "bool"),
              ("menu.assessment", "Show “Institution-level assessment” in the menu and in the quick links of the footer (the page /examination works either way, with the links to it from the pages of the institutions, the guide and the study material)", "bool"),
              ("dashboard.public", "Public dashboard KTS 5.0 by State/UT (/dashboard): the live counts of each State/UT, its Nodal Officers and its Participating Institutions", "bool"),
              ("dashboard.names", "The dashboard names the student delegate of each Participating Institution once the Nodal Officer has verified the student (name and institution only, as the students agreed on registering)", "bool"),
              ("dashboard.marks", "The dashboard says, for each State/UT, for how many of the institutions selected or placed on the reserve list the marks of Annexure-V are recorded (“Marks recorded: N of M”; counts only)", "bool"),
              ("site.visitors", "Show the count of visitors in the footer of every page", "bool"),
              ("site.draft_note_on", "Show the note “this translation is a draft” in interface languages that are not yet reviewed", "bool")]),
    ("Home page", [("home.pm_on", "Show the Prime Minister's photograph and quotation", "bool"),
                   ("home.pm_quote", "Quotation (without quotation marks)", "text"),
                   ("home.pm_quote_by", "Attribution", "text"), ("home.pm_caption", "Photograph caption", "text")]),
    ("Registration", [("reg.open", "Registration enabled", "bool"), ("reg.start", "Opens on (YYYY-MM-DD)", "date"), ("reg.end", "Closes on (YYYY-MM-DD)", "date")]),
    ("Launch of the KTS 5.0 web portal and registration (by the Hon'ble Minister of Education; the stage screen: /launch)", [
        ("launch.on", "Announce the launch: the banner and the home page before it; registration opens at the launch", "bool"),
        ("launch.at", "Moment of the launch (YYYY-MM-DDTHH:MM, IST)", "text"),
        ("launch.until", "The home page says 'launched' until (YYYY-MM-DD)", "date")]),
    ("Backups of the database (Console › Backups)", [
        ("backup.on", "Copy the database by itself at the hours below, into instance\\backups", "bool"),
        ("backup.times", "Hours of the copies (HH:MM IST, separated by commas)", "text"),
        ("backup.keep", "Copies made at those hours that are kept (28: two weeks, at two a day)", "number")]),
    ("Participating institutions (Console › Institutions; the website: /institutions)", [
        ("hei.open", "Institutions may apply on the website (/institutions/register); those identified by a Nodal Institution register with their invitation at any time", "bool"),
        ("hei.end", "Last date for institutions to apply (YYYY-MM-DD; empty: none)", "date"),
        ("hei.cap_annexure", "Each State/UT accepts at most the number of Participating Institutions that Annexure-I of the revised D.O. letter prescribes for it (off since 1.2.178: no ceiling)", "bool"),
        ("hei.select_end", "Last date for the Nodal Institutions to select the Participating Institutions (YYYY-MM-DD)", "date"),
        ("hei.max_per_state", "Otherwise: institutions accepted in one State/UT at most, the same for all (0: no limit)", "number"),
        ("hei.public", "Show the participating institutions on the website, State/UT by State/UT", "bool"),
        ("hei.reserve_public", "The public pages list the institutions of the reserve list with the Participating Institutions of their State/UT and count them with them, not told apart (off: only the institutions selected)", "bool"),
        ("hei.marks_first", "An institution is selected, or put on the reserve list, only once the marks of Annexure-V are recorded for it (off: the marks may be recorded at a later stage)", "bool"),
        ("join.on", "Show the State/UT pages for the registration of institutions (/join), with their links and A4 posters", "bool"),
        ("nodal.officers_public", "Show the Nodal Officer of each State/UT (name, designation, e-mail and phone of the active Nodal Officer accounts) on the Nodal HEIs and Partners pages", "bool"),
        ("hei.orientation", "Pre-assessment orientation session by CICT for the institutions: date, time and link, shown on the institutions' page (empty: nothing)", "text")]),
    ("The assessment by the institutions and the nomination of their students (D.O. letter of 31 October 2026)", [
        ("reg.by_institution", "Students register only with the link that the portal sends when their institution selects them (off: anybody may register, as before 1.2.43)", "bool"),
        ("camp.on", "The portal offers the participating institutions its online assessment (the question bank, in the language of each student)", "bool"),
        ("camp.from", "Institution-level assessments from (YYYY-MM-DD)", "date"),
        ("camp.to", "Institution-level assessments complete by (YYYY-MM-DD)", "date"),
        ("camp.show_score", "Show each student the score at the end of the online assessment", "bool"),
        ("practice.on", "Practice test for students on the public site (/practice): questions made afresh from the Thirukkural, never those of the question bank; nothing is recorded", "bool"),
        ("practice.questions", "Practice test: number of questions (3–30)", "number"),
        ("practice.minutes", "Practice test: minutes (1–60)", "number"),
        ("companion.on", "Thirukkural study companion on the public site (/companion): a question in any language answered with the couplets that speak of it, from the portal's own translations and commentaries; free, nothing is sent outside", "bool"),
        ("remind.on", "Reminders by mail to the participating institutions that are behind: each once, in the morning at the time of the Nodal Officers' mail, up to the last day of registration (Console › Progress)", "bool"),
        ("remind.test_by", "Reminder to assess the students and select one, to the institutions that have done nothing yet, from (YYYY-MM-DD)", "date"),
        ("remind.select_by", "Reminder to select the student, to those that have not, with the Head of the Institution in copy, from (YYYY-MM-DD)", "date"),
        ("remind.register_by", "Reminder to submit the nomination of the selected student, to the coordinator, from (YYYY-MM-DD)", "date")]),
    ("Verification by the Nodal Officers of the States/UTs", [
        ("verify.end", "Verification by the Nodal Officers closes on (YYYY-MM-DD; shown to them and in their mails; CICT can still verify after it)", "date"),
        ("nodal.digest", "Morning mail to every Nodal Officer with applications awaiting them, from the opening of registration to the close of verification", "bool"),
        ("nodal.digest_time", "Time of the morning mail (HH:MM IST)", "text")]),
    ("The central online test of CICT (open again from 1.2.120: 10 to 20 November 2026) and the pattern of the online assessment",
     [("exam.date", "Test date: its first day (YYYY-MM-DD)", "date"),
      ("exam.date_to", "Last day of the test (YYYY-MM-DD; empty: the test date only). The test is open from the first day at the opening time to the last day at the closing time", "date"),
      ("exam.start_time", "Login window opens (HH:MM IST, on the first day)", "text"),
                     ("exam.end_time", "The test closes for everyone (HH:MM IST, on the last day): nobody starts after it, and every attempt ends at it", "text"), ("exam.duration_min", "Duration in minutes", "number"),
                     ("exam.questions", "Questions per paper", "number"), ("exam.marks_per_q", "Marks per question", "number"),
                     ("exam.negative", "Negative marks per wrong answer", "number"), ("exam.show_score", "Show score to candidates", "bool"),
                     ("exam.open", "Window mode: auto | 1 (force open) | 0 (force closed)", "text"), ("exam.instructions_url", "Link to the official instructions PDF", "text"),
                     ("exam.unverified", "Registered students may take the central test before the Nodal Officer verifies their application (off: verified students only; the selection counts verified students only either way)", "bool")]),
    ("The one-month research and academic engagement (dates named in the confirmation letter of the selected students)",
     [("letter.date", "Date of the confirmation letter (YYYY-MM-DD)", "date"),
      ("internship.start", "One-month research and academic engagement begins (YYYY-MM-DD)", "date"),
      ("papers.due", "Last date for the article/research note (YYYY-MM-DD)", "date"),
      ("present.due", "Last date for the presentation (YYYY-MM-DD)", "date"),
      ("papers.open", "Research papers: auto (from the start of the internship to the last date) | 1 (open) | 0 (closed, also for returned papers)", "text"),
      ("papers.note", "Research papers: note shown above the form (empty: none)", "text"),
      ("papers.guide_url", "Research papers: link to the guidelines (https://… or /static/…; empty: none)", "text"),
      ("orientation.by", "Academic orientation by CICT, by (YYYY-MM-DD; the schedule and the home page)", "date")]),
    ("Classroom quiz", [("quiz.on", "Classroom quiz open (hosting and joining)", "bool"),
                        ("quiz.candidates", "Selected students may host a quiz once the merit list is published", "bool"),
                        ("quiz.public", "Anybody may host a quiz, without an account (10 quizzes an hour from one address, 300 a day in all)", "bool"),
                        ("quiz.max_players", "Players in one quiz at most", "number")]),
    ("Kashi Tamil Sangamam 5.0", [("kts.start", "Inauguration (YYYY-MM-DD)", "date"),
                                  ("kts.start_time", "Hour of the inauguration (HH:MM IST; the countdown on the home page counts to it; empty: 00:00)", "text"),
                                  ("kts.end", "Valedictory programme (YYYY-MM-DD)", "date"),
                                  ("inaug.link", "Live stream of the inauguration (address, shown to the selected students)", "text"),
                                  ("inaug.code", "Attendance code announced during the live stream (from the day of the inauguration; empty: the students cannot record their attendance)", "text"),
                                  ("schedule.tentative", "Show the note “tentative timeline” on the schedule page", "bool")]),
    ("The selected students", [("merit.published", "The list of the selected students published", "bool"),
                               ("merit.note", "Note shown above the list of the selected students", "text")]),
    ("Stipend", [("stipend.open", "Form for the bank details of the selected students is open", "bool"),
                 ("stipend.last_date", "Last date for first entries (YYYY-MM-DD; empty: none)", "date"),
                 ("stipend.amount", "Stipend in rupees", "number"),
                 ("stipend.aadhaar", "Ask for the Aadhaar number", "bool")]),
    ("Orientation", [("orientation.note", "Note shown on the orientation page", "text")]),
    ("Mail", [("mail.daily_limit", "Mails sent in 24 hours at most (a Google Workspace account sends about 2,000 a day)", "number"),
              ("mail.per_minute", "Mails sent in one minute at most", "number"),
              ("mail.paused", "Sending paused (new mails wait in the queue)", "bool")]),
    ("Contact", [("contact.email", "Helpdesk email", "text"), ("contact.phone", "Helpdesk phone", "text"), ("contact.address", "Postal address", "text"),
                 ("contact.notify", "Every message of the contact form is also e-mailed to this address (empty: none)", "text")]),
    ("Social media (an empty address hides the link)", [(key, name, "text") for key, name, _address in SOCIAL_LINKS]),
    ("Head of the institute (shown on the contact page above the nodal officers; an empty name hides it)",
     [(f"{prefix}.{field}", label, "text") for prefix, _person in INSTITUTE_HEAD for field, label in NODAL_FIELDS]),
    ("Nodal officers of KTS 5.0 (shown on the contact page; an empty name hides the officer)",
     [(f"{prefix}.{field}", f"Officer {n}: {label}", "text") for n, (prefix, _officer) in enumerate(NODAL_OFFICERS, start=1)
      for field, label in NODAL_FIELDS]),
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


# messages sent again in one go, the oldest first
SEND_AGAIN_MOST = 500


@bp.route("/outbox", methods=["GET", "POST"])
@login_required("settings")
def outbox():
    user = current_user()
    cfg = current_app.config
    check = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "check":
            # the answer is shown on this page itself
            check = mail_check(cfg)
            audit("mail_check", "outbox", None, detail=[f"{name}: {'ok' if ok else 'failed'}" for name, ok, _d in check],
                  user=user, ip=client_ip())
        elif action == "test":
            to = (request.form.get("to") or "").strip()
            if not valid_email(to):
                flash("Enter the e-mail address to send the test message to.", "error")
            else:
                row_id = send_mail(to, "KTS 5.0 portal: test message",
                                   "This is a test message of the portal of Kashi Tamil Sangamam 5.0 "
                                   f"({cfg['BASE_URL']}), sent from Console → Mail outbox on "
                                   f"{now_ist().strftime('%d %b %Y, %H:%M')} IST by {user['name']}.\n\n"
                                   "If it has arrived, the portal can send its mails.", now=True)
                row = query("SELECT status, error FROM outbox WHERE id = ?", (row_id,), one=True)
                audit("mail_test", "outbox", row_id, detail={"to": to, "status": row["status"]}, user=user, ip=client_ip())
                if row["status"] == "sent":
                    flash(f"The test message was sent to {to}. Look for it in that mailbox (and in its spam folder).", "success")
                elif row["status"] == "failed":
                    flash(f"The test message could not be sent: {row['error']}", "error")
                else:
                    flash("Mail is not configured: the test message waits in the list below.", "warning")
        elif action == "again":
            if not cfg.get("SMTP_HOST"):
                flash("Mail is not configured: nothing can be sent.", "error")
            else:
                rows = query("SELECT id FROM outbox WHERE status = 'failed' ORDER BY id LIMIT ?", (SEND_AGAIN_MOST,))
                count = send_again(rows)
                audit("mail_again", "outbox", None, detail=f"{count} message(s)", user=user, ip=client_ip())
                flash(f"{count} failed message(s) are back in the queue and will be sent with the others.", "success")
        elif action in ("pause", "resume"):
            set_setting("mail.paused", "1" if action == "pause" else "0")
            if action == "resume":
                from .mailq import wake
                wake()
            audit("mail_" + action, "outbox", None, user=user, ip=client_ip())
            flash("Sending is paused: new mails wait in the queue." if action == "pause" else "Sending goes on.", "success")
        if check is None:
            return redirect(url_for("admin.outbox"))
    rows = query("SELECT * FROM outbox ORDER BY id DESC LIMIT 200")
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM outbox GROUP BY status")}
    from .mailq import figures
    queue = figures()
    smtp = {"host": cfg.get("SMTP_HOST") or "", "port": cfg.get("SMTP_PORT"), "user": cfg.get("SMTP_USER") or "",
            "sender": cfg.get("SMTP_FROM") or "", "tls": bool(cfg.get("SMTP_TLS")), "password": bool(cfg.get("SMTP_PASSWORD"))}
    return render_template("console/outbox.html", rows=rows, smtp=smtp, counts=counts, me=user["email"],
                           most=SEND_AGAIN_MOST, check=check, queue=queue)

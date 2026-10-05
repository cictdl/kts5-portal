"""
Research papers of the student delegates (from 1.2.11).

Every selected student writes a research paper on the Thirukkural under the faculty mentor named in
the application, between the start of the internship (setting internship.start) and the last date
(papers.due), and sends it here: title, language, abstract, keywords, the couplets studied, the
mentor, and the paper itself as PDF or Word (DOCX) of up to 10 MB. Until the paper is reviewed the
student may replace it within the period; the reviewers of CICT accept it or return it with
remarks, and a returned paper may be sent again, also after the last date, until an administrator
closes the submission (papers.open = 0). Every file sent is kept, with its version.

The files lie in uploads/papers/, which the web server never serves: they are sent to the student
who sent them and to staff only.
"""
from pathlib import Path

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, send_from_directory, url_for

from . import kural as K
from .admin import bp as console
from .auth import candidate_required, current_user, has_perm, login_required
from .candidate import bp as candidates
from .db import all_settings, audit, execute, get_db, query, utcnow
from .i18n import t
from .utils import (client_ip, csv_bytes, now_ist, paginate, safe_int, save_upload, send_mail, to_ist, valid_email,
                    xlsx_bytes)

PAPER_EXT = {"pdf", "docx"}
MAX_BYTES = 10 * 1024 * 1024
LIMITS = {"title": 200, "abstract": 3000, "keywords": 200, "couplets": 200, "mentor_name": 120,
          "mentor_designation": 120, "mentor_email": 254}
STATES = ("submitted", "returned", "accepted")


def may_use(cand, settings):
    """The papers are for the delegates: the students selected in the published merit list."""
    return settings.get("merit.published") == "1" and cand["status"] == "selected"


def window(settings):
    """'open', 'not_yet' or 'closed'. papers.open: auto (the dates of the internship), 1 open, 0 closed."""
    mode = (settings.get("papers.open") or "auto").strip()
    if mode == "1":
        return "open"
    if mode == "0":
        return "closed"
    today = now_ist().date().isoformat()
    start = (settings.get("internship.start") or "")[:10]
    due = (settings.get("papers.due") or "")[:10]
    if start and today < start:
        return "not_yet"
    if due and today > due:
        return "closed"
    return "open"


def paper_of(application_id):
    return query("SELECT * FROM papers WHERE application_id = ?", (application_id,), one=True)


def may_send(paper, settings):
    """A first paper or a replacement within the period; a returned paper until the submission is closed."""
    if paper is not None and paper["status"] == "accepted":
        return False
    if paper is not None and paper["status"] == "returned":
        return window(settings) != "not_yet" and (settings.get("papers.open") or "auto").strip() != "0"
    return window(settings) == "open"


def number_of(app_no):
    """KTS5-2026-000123 -> KTS5/RP/2026/000123."""
    parts = app_no.split("-")
    return "/".join([parts[0], "RP"] + parts[1:]) if len(parts) == 3 else app_no


def card_state(cand, settings):
    """What the card of the candidate portal shows; None for a student who is not a delegate."""
    if not may_use(cand, settings):
        return None
    paper = paper_of(cand["id"])
    return {"status": paper["status"] if paper else "none", "due": settings.get("papers.due") or "",
            "window": window(settings)}


def _langs():
    return [(L["code"], K.lang_label(L["code"])) for L in K.languages() if L["code"] in K.ORIENTATION_LANGS]


def _validate(form, has_file):
    data = {key: " ".join((form.get(key) or "").split()) for key in LIMITS if key != "abstract"}
    # the abstract keeps its paragraphs
    data["abstract"] = "\n".join(line.strip() for line in (form.get("abstract") or "").strip().splitlines()).strip()
    data["lang"] = form.get("lang") or ""
    errors = {}
    for key in ("title", "abstract", "mentor_name"):
        if not data[key]:
            errors[key] = t("reg.err_required")
    for key, most in LIMITS.items():
        if len(data[key]) > most:
            errors[key] = t("paper.err_long")
    if data["mentor_email"] and not valid_email(data["mentor_email"]):
        errors["mentor_email"] = t("reg.err_email")
    if data["lang"] not in K.ORIENTATION_LANGS:
        errors["lang"] = t("reg.err_required")
    if not has_file:
        errors["file"] = t("paper.err_file")
    if not form.get("declare"):
        errors["declare"] = t("paper.err_declare")
    return data, errors


def _store_file(upload):
    """(path, name, size) of the paper sent, or None when it is no PDF or DOCX of up to 10 MB."""
    head = upload.stream.read(4)
    upload.stream.seek(0)
    name = (upload.filename or "").lower()
    # a Word file is a ZIP archive; a PDF is checked by save_upload
    if name.endswith(".docx") and head != b"PK\x03\x04":
        return None
    try:
        return save_upload(upload, "papers", PAPER_EXT, MAX_BYTES)
    except ValueError:
        return None


def _mail(cand, subject, lines):
    body = "\n\n".join([f"Dear {cand['full_name']},"] + lines + [
        f"Your research paper on the portal: {current_app.config['BASE_URL'].rstrip('/')}/candidate/paper",
        "Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom\nCentral Institute of Classical Tamil, Chennai"])
    send_mail(cand["email"], subject, body)


@candidates.route("/paper", methods=["GET", "POST"])
@candidate_required
def research_paper():
    cand = g.candidate
    settings = all_settings()
    if not may_use(cand, settings):
        return render_template("candidate/paper.html", cand=cand, state="not_for_you", paper=None, settings=settings), \
            403 if request.method == "POST" else 200
    current = paper_of(cand["id"])
    can_send = may_send(current, settings)
    errors = {}
    data = dict(current) if current else {"mentor_name": cand["mentor_name"] or "", "lang": cand["pref_lang"] or "en",
                                          "mentor_designation": cand["mentor_designation"] or "",
                                          "mentor_email": cand["mentor_email"] or ""}
    if request.method == "POST":
        if not can_send:
            abort(403)
        upload = request.files.get("file")
        sent = upload is not None and bool(upload.filename)
        data, errors = _validate(request.form, sent or current is not None)
        stored = None
        if sent and not errors:
            stored = _store_file(upload)
            if stored is None:
                errors["file"] = t("paper.err_file")
        if errors:
            flash(t("reg.err_fix"), "error")
        else:
            now = utcnow()
            fields = (data["title"], data["lang"], data["abstract"], data["keywords"], data["couplets"], data["mentor_name"],
                      data["mentor_designation"], data["mentor_email"])
            conn = get_db()
            if current is None:
                path, name, size = stored
                cur = conn.execute(
                    "INSERT INTO papers(application_id, title, lang, abstract, keywords, couplets, mentor_name, mentor_designation, "
                    "mentor_email, file_path, file_name, file_size, version, status, submitted_at, first_submitted_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,'submitted',?,?,?)", (cand["id"],) + fields + (path, name, size, now, now, now))
                conn.execute("INSERT INTO paper_files(paper_id, version, file_path, file_name, file_size, uploaded_at) VALUES(?,1,?,?,?,?)",
                             (cur.lastrowid, path, name, size, now))
                version = 1
            else:
                version = current["version"] + (1 if stored else 0)
                conn.execute("UPDATE papers SET title = ?, lang = ?, abstract = ?, keywords = ?, couplets = ?, mentor_name = ?, "
                             "mentor_designation = ?, mentor_email = ?, status = 'submitted', submitted_at = ?, updated_at = ? WHERE id = ?",
                             fields + (now, now, current["id"]))
                if stored:
                    path, name, size = stored
                    conn.execute("UPDATE papers SET file_path = ?, file_name = ?, file_size = ?, version = ? WHERE id = ?",
                                 (path, name, size, version, current["id"]))
                    conn.execute("INSERT INTO paper_files(paper_id, version, file_path, file_name, file_size, uploaded_at) VALUES(?,?,?,?,?,?)",
                                 (current["id"], version, path, name, size, now))
            conn.commit()
            audit("paper_submitted", "application", cand["id"], detail={"version": version, "new_file": bool(stored)}, ip=client_ip())
            if current is None or stored or current["status"] == "returned":
                _mail(cand, f"KTS 5.0: research paper received ({number_of(cand['app_no'])})", [
                    f"Your research paper \"{data['title']}\" has been received (version {version}).",
                    "The reviewers of CICT will read it. Until then you may replace it on the portal within the last date."])
            flash(t("paper.sent_ok"), "success")
            return redirect(url_for("candidate.research_paper"))
    guide = (settings.get("papers.guide_url") or "").strip()
    return render_template("candidate/paper.html", cand=cand, state=window(settings), paper=current, can_send=can_send,
                           data=data, errors=errors, langs=_langs(), settings=settings, number=number_of(cand["app_no"]),
                           max_bytes=MAX_BYTES, guide_url=guide if guide.startswith(("https://", "http://", "/")) else "")


@candidates.route("/paper/file")
@candidate_required
def research_paper_file():
    current = paper_of(g.candidate["id"])
    if current is None:
        abort(404)
    return _send(current["file_path"], current["file_name"])


def _send(relpath, name):
    folder, _, fname = relpath.rpartition("/")
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]) / folder, fname, as_attachment=True, download_name=name)


# ---- the console ----------------------------------------------------------------------------------

@console.route("/papers")
@login_required("papers.view")
def papers():
    settings = all_settings()
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "lang", "q")}
    sql = " FROM applications a LEFT JOIN papers p ON p.application_id = a.id WHERE a.status = 'selected'"
    args = []
    if f["state"] == "none":
        sql += " AND p.id IS NULL"
    elif f["state"] in STATES:
        sql += " AND p.status = ?"
        args.append(f["state"])
    if f["lang"]:
        sql += " AND p.lang = ?"
        args.append(f["lang"])
    if f["q"]:
        sql += " AND (a.full_name LIKE ? OR a.app_no LIKE ? OR a.college_name LIKE ? OR p.title LIKE ?)"
        args += [f"%{f['q']}%"] * 4
    if request.args.get("export") in ("xlsx", "csv"):
        return _export(request.args["export"], sql, args)
    total = query("SELECT COUNT(*) AS n" + sql, args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 100)
    rows = query("SELECT a.id, a.app_no, a.full_name, a.college_name, a.college_state, a.state, p.title, p.lang, p.status, "
                 "p.version, p.submitted_at, p.score" + sql + " ORDER BY p.submitted_at IS NULL, p.submitted_at DESC, a.id LIMIT ? OFFSET ?",
                 args + [pg["per_page"], pg["offset"]])
    counts = {r["s"]: r["n"] for r in query(
        "SELECT COALESCE(p.status, 'none') AS s, COUNT(*) AS n FROM applications a LEFT JOIN papers p ON p.application_id = a.id "
        "WHERE a.status = 'selected' GROUP BY s")}
    return render_template("console/papers.html", rows=rows, f=f, pg=pg, counts=counts, delegates=sum(counts.values()),
                           langs=_langs(), settings=settings, window=window(settings))


def _export(fmt, sql, args):
    rows = query("SELECT a.app_no, a.full_name, a.college_name, a.college_state, a.state, a.email, p.*" + sql +
                 " ORDER BY a.exam_rank IS NULL, a.exam_rank, a.id", args)
    headers = ["Application number", "Submission number", "Name", "College", "State", "E-mail", "Status", "Title", "Language",
               "Keywords", "Couplets studied", "Mentor", "Mentor designation", "Mentor e-mail", "Version", "First sent (IST)",
               "Last sent (IST)", "Score", "Remarks"]

    def when(value):
        return to_ist(value).strftime("%d-%m-%Y %H:%M") if value else ""

    def cell(value):
        value = "" if value is None else str(value)
        return "'" + value if value[:1] in ("=", "+", "-", "@") else value

    data = [(r["app_no"], number_of(r["app_no"]), cell(r["full_name"]), cell(r["college_name"]), r["college_state"] or r["state"],
             r["email"], r["status"] or "not sent", cell(r["title"]), K.lang_label(r["lang"]) if r["lang"] else "",
             cell(r["keywords"]), cell(r["couplets"]), cell(r["mentor_name"]), cell(r["mentor_designation"]), r["mentor_email"] or "",
             r["version"] or "", when(r["first_submitted_at"]), when(r["submitted_at"]),
             "" if r["score"] is None else r["score"], cell(r["remarks"])) for r in rows]
    audit("papers_export", "papers", None, detail=f"{len(data)} rows, {fmt}", user=current_user(), ip=client_ip())
    name = f"kts5-research-papers-{now_ist().strftime('%Y%m%d-%H%M')}.{fmt}"
    if fmt == "xlsx":
        return Response(xlsx_bytes(headers, data, "Research papers", text_cols=(0, 1)),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={name}"})
    return Response(csv_bytes(headers, data), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


@console.route("/papers/<int:aid>", methods=["GET", "POST"])
@login_required("papers.view")
def paper_entry(aid):
    a = query("SELECT * FROM applications WHERE id = ?", (aid,), one=True)
    current = paper_of(aid)
    if a is None or current is None:
        abort(404)
    user = current_user()
    if request.method == "POST":
        if not has_perm(user, "papers.review"):
            abort(403)
        action = request.form.get("action")
        remarks = (request.form.get("remarks") or "").strip()[:3000]
        score_text = (request.form.get("score") or "").strip()
        score = safe_int(score_text, -1) if score_text else None
        if action not in ("accept", "return"):
            abort(400)
        if score is not None and not 0 <= score <= 100:
            flash("The score is a whole number from 0 to 100, or empty.", "error")
        elif action == "return" and not remarks:
            flash("Write the remarks that tell the student what to change.", "error")
        elif request.form.get("version") != str(current["version"]) or current["status"] == "accepted" and action == "accept":
            flash("The paper changed since this page was opened, or it is accepted already. Look at it again.", "warning")
        else:
            status = "accepted" if action == "accept" else "returned"
            execute("UPDATE papers SET status = ?, remarks = ?, score = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ? WHERE id = ?",
                    (status, remarks, score, user["id"], utcnow(), utcnow(), current["id"]))
            audit("paper_" + status, "application", aid, detail={"version": current["version"], "score": score},
                  user=user, ip=client_ip())
            if status == "accepted":
                _mail(a, f"KTS 5.0: research paper accepted ({number_of(a['app_no'])})", [
                    f"Your research paper \"{current['title']}\" has been accepted. Congratulations!"]
                    + ([f"Remarks of the reviewers: {remarks}"] if remarks else []))
            else:
                _mail(a, f"KTS 5.0: research paper returned for changes ({number_of(a['app_no'])})", [
                    f"The reviewers have returned your research paper \"{current['title']}\" for changes.",
                    f"Remarks of the reviewers: {remarks}",
                    "Revise the paper and send it again on the portal."])
            flash(f"The paper is {status}; the student is told by e-mail.", "success")
        return redirect(url_for("admin.paper_entry", aid=aid))
    files = query("SELECT * FROM paper_files WHERE paper_id = ? ORDER BY version DESC", (current["id"],))
    reviewer = query("SELECT name FROM users WHERE id = ?", (current["reviewed_by"],), one=True) if current["reviewed_by"] else None
    return render_template("console/paper_entry.html", a=a, p=current, files=files, reviewer=reviewer,
                           number=number_of(a["app_no"]), lang_name=K.lang_label(current["lang"]),
                           may_review=has_perm(user, "papers.review"))


@console.route("/papers/<int:aid>/file/<int:version>")
@login_required("papers.view")
def paper_version(aid, version):
    row = query("SELECT f.* FROM paper_files f JOIN papers p ON p.id = f.paper_id WHERE p.application_id = ? AND f.version = ?",
                (aid, version), one=True)
    if row is None:
        abort(404)
    a = query("SELECT app_no FROM applications WHERE id = ?", (aid,), one=True)
    ext = row["file_name"].rsplit(".", 1)[-1] if "." in row["file_name"] else "pdf"
    return _send(row["file_path"], f"{number_of(a['app_no']).replace('/', '-')}-v{version}.{ext}")

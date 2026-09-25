"""
Coordination hub shared by CICT and the partner agencies: workstream tasks,
status updates, shared documents and the programme calendar.

Agency users see their own agency's tasks and the documents shared with
them; CICT administrators see everything and can assign work.
"""
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)

from .auth import current_user, has_perm, login_required
from .db import audit, execute, query, utcnow
from .utils import RESOURCE_EXT, client_ip, now_ist, safe_int, save_upload, send_mail

bp = Blueprint("agency", __name__, url_prefix="/hub")

TASK_STATUSES = ["open", "in_progress", "blocked", "done"]
PRIORITIES = ["low", "normal", "high", "urgent"]
WORKSTREAMS = [
    ("portal", "Portal and registration"),
    ("publicity", "Pan-India publicity"),
    ("exam", "Examination and selection"),
    ("orientation", "Online orientation (21 languages)"),
    ("internship", "Internship and campus presentations"),
    ("repository", "Digital repository and apps"),
    ("video", "Educational videos, audiobooks, films, reels"),
    ("conference", "National conferences"),
    ("displays", "Public displays (rail, air, highways)"),
    ("schools", "Daily Kural, comics, posters, storytelling"),
    ("logistics", "Travel, venues and hospitality"),
    ("finance", "Finance and approvals"),
    ("general", "General"),
]


def _user():
    return current_user()


def _scope(user):
    """Return (agency_id restriction or None, can_manage)."""
    if user["role"] == "agency":
        return user["agency_id"], False
    return None, has_perm(user, "coord.manage")


@bp.route("/")
@login_required("coord.view")
def home():
    user = _user()
    agency_id, manage = _scope(user)
    args, where = [], "1=1"
    if agency_id:
        where = "t.agency_id = ?"
        args = [agency_id]
    counts = {r["status"]: r["n"] for r in query(f"SELECT t.status, COUNT(*) AS n FROM tasks t WHERE {where} GROUP BY t.status", args)}
    today = now_ist().strftime("%Y-%m-%d")
    due_soon = query(f"SELECT t.*, a.short_name AS agency FROM tasks t LEFT JOIN agencies a ON a.id = t.agency_id "
                     f"WHERE {where} AND t.status != 'done' AND t.due_date IS NOT NULL ORDER BY t.due_date LIMIT 8", args)
    updates = query(f"SELECT u.*, t.title, us.name AS who FROM task_updates u JOIN tasks t ON t.id = u.task_id "
                    f"LEFT JOIN users us ON us.id = u.user_id WHERE {where.replace('t.agency_id', 't.agency_id')} ORDER BY u.id DESC LIMIT 10", args)
    docs_where = "d.visibility = 'all'" if not agency_id else "(d.visibility = 'all' OR d.agency_id = ?)"
    docs = query(f"SELECT d.*, a.short_name AS agency FROM documents d LEFT JOIN agencies a ON a.id = d.agency_id "
                 f"WHERE {docs_where} ORDER BY d.id DESC LIMIT 8", [agency_id] if agency_id else [])
    events = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id "
                   "WHERE e.starts_at >= ? ORDER BY e.starts_at LIMIT 8", (today,))
    notices = query("SELECT * FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC LIMIT 5")
    agency = query("SELECT * FROM agencies WHERE id = ?", (agency_id,), one=True) if agency_id else None
    by_agency = [] if agency_id else query(
        "SELECT a.short_name, SUM(t.status != 'done') AS open, SUM(t.status = 'done') AS done, "
        "SUM(t.status != 'done' AND t.due_date < ?) AS overdue FROM agencies a LEFT JOIN tasks t ON t.agency_id = a.id "
        "WHERE a.active = 1 GROUP BY a.id ORDER BY a.sort_order", (today,))
    return render_template("hub/home.html", counts=counts, due_soon=due_soon, updates=updates, docs=docs, events=events,
                           notices=notices, agency=agency, manage=manage, by_agency=by_agency, today=today)


@bp.route("/tasks")
@login_required("coord.view")
def tasks():
    user = _user()
    agency_id, manage = _scope(user)
    f = {k: (request.args.get(k) or "").strip() for k in ("status", "agency", "workstream", "q")}
    sql = "SELECT t.*, a.short_name AS agency, u.name AS assignee FROM tasks t LEFT JOIN agencies a ON a.id = t.agency_id LEFT JOIN users u ON u.id = t.assignee_id WHERE 1=1"
    args = []
    if agency_id:
        sql += " AND t.agency_id = ?"
        args.append(agency_id)
    elif f["agency"]:
        sql += " AND t.agency_id = ?"
        args.append(safe_int(f["agency"]))
    if f["status"]:
        sql += " AND t.status = ?"
        args.append(f["status"])
    if f["workstream"]:
        sql += " AND t.workstream = ?"
        args.append(f["workstream"])
    if f["q"]:
        sql += " AND (t.title LIKE ? OR t.description LIKE ?)"
        args += [f"%{f['q']}%"] * 2
    sql += " ORDER BY CASE t.status WHEN 'blocked' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'open' THEN 2 ELSE 3 END, " \
           "CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.due_date"
    rows = query(sql, args)
    board = {s: [r for r in rows if r["status"] == s] for s in TASK_STATUSES}
    agencies = query("SELECT id, short_name FROM agencies WHERE active = 1 ORDER BY sort_order")
    return render_template("hub/tasks.html", rows=rows, board=board, f=f, statuses=TASK_STATUSES, agencies=agencies,
                           workstreams=WORKSTREAMS, manage=manage, view=request.args.get("view", "board"),
                           today=now_ist().strftime("%Y-%m-%d"))


@bp.route("/tasks/new", methods=["GET", "POST"])
@bp.route("/tasks/<int:tid>/edit", methods=["GET", "POST"])
@login_required("coord.edit")
def task_form(tid=None):
    user = _user()
    agency_id, manage = _scope(user)
    row = query("SELECT * FROM tasks WHERE id = ?", (tid,), one=True) if tid else None
    if tid and row is None:
        abort(404)
    if row and agency_id and row["agency_id"] != agency_id:
        abort(403)
    agencies = query("SELECT id, short_name, name FROM agencies WHERE active = 1 ORDER BY sort_order")
    users = query("SELECT id, name, agency_id, role FROM users WHERE active = 1 ORDER BY name")
    if request.method == "POST":
        d = {k: (request.form.get(k) or "").strip() for k in ("title", "description", "workstream", "agency_id", "assignee_id", "status", "priority", "due_date")}
        target_agency = agency_id or (safe_int(d["agency_id"]) or None)
        if not d["title"]:
            flash("A title is required.", "error")
        elif d["status"] not in TASK_STATUSES or d["priority"] not in PRIORITIES:
            flash("Choose a valid status and priority.", "error")
        else:
            vals = (d["title"], d["description"], d["workstream"] or "general", target_agency, safe_int(d["assignee_id"]) or None,
                    d["status"], d["priority"], d["due_date"] or None, utcnow())
            if row:
                if row["status"] != d["status"]:
                    execute("INSERT INTO task_updates(task_id, user_id, note, old_status, new_status, created_at) VALUES(?,?,?,?,?,?)",
                            (tid, user["id"], "Status changed while editing", row["status"], d["status"], utcnow()))
                execute("UPDATE tasks SET title=?, description=?, workstream=?, agency_id=?, assignee_id=?, status=?, priority=?, due_date=?, updated_at=? WHERE id=?",
                        vals + (tid,))
                audit("task_updated", "task", tid, detail=d["title"], user=user, ip=client_ip())
            else:
                tid = execute("INSERT INTO tasks(title, description, workstream, agency_id, assignee_id, status, priority, due_date, updated_at, created_by, created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals + (user["id"], utcnow()))
                audit("task_created", "task", tid, detail=d["title"], user=user, ip=client_ip())
                if target_agency:
                    ag = query("SELECT * FROM agencies WHERE id = ?", (target_agency,), one=True)
                    if ag and ag["email"]:
                        send_mail(ag["email"], f"KTS 5.0 task assigned: {d['title']}",
                                  f"A new task has been assigned to {ag['short_name']} on the KTS 5.0 coordination hub.\n\n"
                                  f"{d['title']}\nPriority: {d['priority']}\nDue: {d['due_date'] or 'not set'}\n\n"
                                  f"{current_app.config['BASE_URL']}/hub/tasks/{tid}")
            flash("Task saved.", "success")
            return redirect(url_for("agency.task", tid=tid))
    return render_template("hub/task_form.html", tk=row, agencies=agencies, users=users, statuses=TASK_STATUSES,
                           priorities=PRIORITIES, workstreams=WORKSTREAMS, locked_agency=agency_id)


@bp.route("/tasks/<int:tid>", methods=["GET", "POST"])
@login_required("coord.view")
def task(tid):
    user = _user()
    agency_id, manage = _scope(user)
    row = query("SELECT t.*, a.short_name AS agency, a.name AS agency_name, u.name AS assignee, c.name AS creator "
                "FROM tasks t LEFT JOIN agencies a ON a.id = t.agency_id LEFT JOIN users u ON u.id = t.assignee_id "
                "LEFT JOIN users c ON c.id = t.created_by WHERE t.id = ?", (tid,), one=True)
    if row is None:
        abort(404)
    if agency_id and row["agency_id"] != agency_id:
        abort(403)
    if request.method == "POST":
        if not has_perm(user, "coord.edit"):
            abort(403)
        note = (request.form.get("note") or "").strip()
        new_status = request.form.get("status") or row["status"]
        if new_status not in TASK_STATUSES:
            new_status = row["status"]
        attachment = ""
        f = request.files.get("attachment")
        if f and f.filename:
            try:
                attachment = save_upload(f, "tasks", RESOURCE_EXT, current_app.config["RESOURCE_MAX_BYTES"])[0]
            except ValueError:
                flash("Attachment rejected (type or size).", "error")
                return redirect(url_for("agency.task", tid=tid))
        if not note and new_status == row["status"] and not attachment:
            flash("Write an update or change the status.", "error")
            return redirect(url_for("agency.task", tid=tid))
        execute("INSERT INTO task_updates(task_id, user_id, note, old_status, new_status, attachment, created_at) VALUES(?,?,?,?,?,?,?)",
                (tid, user["id"], note, row["status"] if new_status != row["status"] else "", new_status if new_status != row["status"] else "", attachment, utcnow()))
        if new_status != row["status"]:
            execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, utcnow(), tid))
        else:
            execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (utcnow(), tid))
        audit("task_progress", "task", tid, detail={"status": new_status, "note": note[:120]}, user=user, ip=client_ip())
        flash("Update posted.", "success")
        return redirect(url_for("agency.task", tid=tid))
    updates = query("SELECT u.*, us.name AS who FROM task_updates u LEFT JOIN users us ON us.id = u.user_id WHERE u.task_id = ? ORDER BY u.id",
                    (tid,))
    return render_template("hub/task.html", tk=row, updates=updates, statuses=TASK_STATUSES, manage=manage,
                           workstreams=dict(WORKSTREAMS), can_edit=has_perm(user, "coord.edit"))


@bp.route("/documents", methods=["GET", "POST"])
@login_required("coord.view")
def documents():
    user = _user()
    agency_id, manage = _scope(user)
    if request.method == "POST":
        if not has_perm(user, "coord.edit"):
            abort(403)
        title = (request.form.get("title") or "").strip()
        f = request.files.get("file")
        if not title or not f or not f.filename:
            flash("A title and a file are required.", "error")
        else:
            try:
                path, name, size = save_upload(f, "documents", RESOURCE_EXT, current_app.config["RESOURCE_MAX_BYTES"])
            except ValueError:
                flash("File rejected (type or size).", "error")
                return redirect(url_for("agency.documents"))
            vis = request.form.get("visibility") or "all"
            target = agency_id or (safe_int(request.form.get("agency_id")) or None)
            did = execute("INSERT INTO documents(title, description, agency_id, visibility, file_path, file_name, file_size, uploaded_by, created_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?)",
                          (title, (request.form.get("description") or "").strip(), target, "agency" if vis == "agency" else "all",
                           path, name, size, user["id"], utcnow()))
            audit("document_uploaded", "document", did, detail=title, user=user, ip=client_ip())
            flash("Document shared.", "success")
        return redirect(url_for("agency.documents"))
    if agency_id:
        rows = query("SELECT d.*, a.short_name AS agency, u.name AS who FROM documents d LEFT JOIN agencies a ON a.id = d.agency_id "
                     "LEFT JOIN users u ON u.id = d.uploaded_by WHERE d.visibility = 'all' OR d.agency_id = ? ORDER BY d.id DESC", (agency_id,))
    else:
        rows = query("SELECT d.*, a.short_name AS agency, u.name AS who FROM documents d LEFT JOIN agencies a ON a.id = d.agency_id "
                     "LEFT JOIN users u ON u.id = d.uploaded_by ORDER BY d.id DESC")
    agencies = query("SELECT id, short_name FROM agencies WHERE active = 1 ORDER BY sort_order")
    return render_template("hub/documents.html", rows=rows, agencies=agencies, manage=manage, locked_agency=agency_id,
                           can_edit=has_perm(user, "coord.edit"))


@bp.route("/documents/<int:did>/download")
@login_required("coord.view")
def document_download(did):
    user = _user()
    agency_id, _ = _scope(user)
    row = query("SELECT * FROM documents WHERE id = ?", (did,), one=True)
    if row is None:
        abort(404)
    if agency_id and row["visibility"] != "all" and row["agency_id"] != agency_id:
        abort(403)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), row["file_path"], as_attachment=True, download_name=row["file_name"])


@bp.route("/documents/<int:did>/delete", methods=["POST"])
@login_required("coord.edit")
def document_delete(did):
    user = _user()
    agency_id, manage = _scope(user)
    row = query("SELECT * FROM documents WHERE id = ?", (did,), one=True)
    if row is None:
        abort(404)
    if not manage and row["uploaded_by"] != user["id"]:
        abort(403)
    execute("DELETE FROM documents WHERE id = ?", (did,))
    audit("document_deleted", "document", did, user=user, ip=client_ip())
    flash("Document removed.", "warning")
    return redirect(url_for("agency.documents"))


@bp.route("/calendar")
@login_required("coord.view")
def calendar():
    rows = query("SELECT e.*, a.short_name AS agency FROM events e LEFT JOIN agencies a ON a.id = e.agency_id ORDER BY e.starts_at")
    return render_template("hub/calendar.html", rows=rows, today=now_ist().strftime("%Y-%m-%d"))


@bp.route("/files/<path:relpath>")
@login_required("coord.view")
def hub_file(relpath):
    if not relpath.startswith(("tasks/", "documents/")):
        abort(404)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), relpath)

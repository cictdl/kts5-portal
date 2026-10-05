"""
Staff authentication and role-based access.

Roles
  superadmin  everything, including users and settings
  admin       everything except user management
  verifier    application verification and exports
  content     notices, resources, events
  agency      coordination hub for their own agency (tasks, documents, calendar)
  viewer      read-only dashboard and lists
"""
import hashlib
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import RETIRED_FIRST_PASSWORD, audit, execute, forget_first_admin, query, utcnow
from .utils import client_ip, limiter

bp = Blueprint("auth", __name__, url_prefix="/console")

ROLES = ["superadmin", "admin", "verifier", "content", "agency", "viewer"]

PERMS = {
    "dashboard":     {"superadmin", "admin", "verifier", "content", "viewer", "agency"},
    "apps.view":     {"superadmin", "admin", "verifier", "viewer"},
    "apps.verify":   {"superadmin", "admin", "verifier"},
    "apps.export":   {"superadmin", "admin", "verifier"},
    "apps.delete":   {"superadmin", "admin"},
    "exam.manage":   {"superadmin", "admin"},
    "exam.view":     {"superadmin", "admin", "verifier", "viewer"},
    "selection":     {"superadmin", "admin"},
    # bank details of the selected students: full numbers are shown to these two roles only
    "stipend":       {"superadmin", "admin"},
    "content":       {"superadmin", "admin", "content"},
    "coord.view":    {"superadmin", "admin", "content", "verifier", "viewer", "agency"},
    "coord.edit":    {"superadmin", "admin", "agency"},
    "coord.manage":  {"superadmin", "admin"},
    "messages":      {"superadmin", "admin", "content"},
    "users":         {"superadmin"},
    "settings":      {"superadmin", "admin"},
    "audit":         {"superadmin", "admin"},
    # the classroom quiz: every member of staff may host one
    "quiz.host":     {"superadmin", "admin", "verifier", "content", "agency", "viewer"},
}


def has_perm(user, perm):
    return bool(user) and user["active"] and user["role"] in PERMS.get(perm, set())


def _password_mark(password_hash):
    """What a session keeps of the password it was opened with; it says nothing about the password."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def current_user():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    user = query("SELECT * FROM users WHERE id = ? AND active = 1", (uid,), one=True) if uid else None
    # A session ends when the password of its account is no longer the one it was opened with:
    # changed by its owner elsewhere, reset by an administrator or replaced when the portal started.
    if user is not None and session.get("pw") != _password_mark(user["password_hash"]):
        user = None
    g.user = user
    return g.user


def login_required(perm=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                # the page to go to after the sign-in, with the path prefix of the portal if any
                asked = request.full_path if request.query_string else request.path
                session["next"] = request.script_root + asked if request.method == "GET" else None
                return redirect(url_for("auth.login"))
            if user["must_change_password"] and request.endpoint != "auth.password":
                flash("Please set a new password before continuing.", "warning")
                return redirect(url_for("auth.password"))
            if perm and not has_perm(user, perm):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def candidate_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cid = session.get("cand_id")
        cand = query("SELECT * FROM applications WHERE id = ?", (cid,), one=True) if cid else None
        if cand is None:
            return redirect(url_for("candidate.login"))
        g.candidate = cand
        return fn(*args, **kwargs)
    return wrapper


def register(app):
    @app.context_processor
    def _inject():
        return {"current_user": current_user(), "has_perm": has_perm}


def _local_path(value):
    """True for an address inside the portal such as /console/audit; never //host or /\\host."""
    return (isinstance(value, str) and value.startswith("/") and not value.startswith(("//", "/\\"))
            and not any(ord(c) < 32 for c in value))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("admin.dashboard"))
    error = None
    if request.method == "POST":
        ip = client_ip()
        # only failed attempts are counted: a correct sign-in costs nothing
        if limiter.blocked("login", ip, current_app.config["RATE_LOGIN_FAILS_PER_15MIN"], 15 * 60):
            error = "Too many sign-in attempts. Try again in 15 minutes."
        else:
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            user = query("SELECT * FROM users WHERE email = ?", (email,), one=True)
            if user and user["active"] and check_password_hash(user["password_hash"], password):
                csrf = session.get("_csrf")
                lang = session.get("lang")
                nxt = session.get("next")
                session.clear()
                session.permanent = True
                session["_csrf"] = csrf
                if lang:
                    session["lang"] = lang
                session["uid"] = user["id"]
                session["pw"] = _password_mark(user["password_hash"])
                execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utcnow(), user["id"]))
                audit("login", "user", user["id"], user=user, ip=ip)
                if user["must_change_password"]:
                    return redirect(url_for("auth.password"))
                if user["role"] == "agency":
                    return redirect(url_for("agency.home"))
                return redirect(nxt if _local_path(nxt) else url_for("admin.dashboard"))
            limiter.hit("login", ip, 15 * 60)
            error = "Incorrect email or password."
            # what was typed may be of any length; an e-mail address has 254 characters at most
            audit("login_failed", "user", None, detail=email[:254], ip=ip)
    return render_template("console/login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    user = current_user()
    if user:
        audit("logout", "user", user["id"], user=user, ip=client_ip())
    session.clear()
    return redirect(url_for("public.home"))


@bp.route("/password", methods=["GET", "POST"])
def password():
    user = current_user()
    if user is None:
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        current = request.form.get("current") or ""
        new = request.form.get("new") or ""
        confirm = request.form.get("confirm") or ""
        if not check_password_hash(user["password_hash"], current):
            error = "The current password is incorrect."
        elif len(new) < 10 or new.lower() == new or not any(c.isdigit() for c in new):
            error = "Use at least 10 characters with a capital letter and a digit."
        elif new != confirm:
            error = "The two new passwords do not match."
        elif new == current or new == RETIRED_FIRST_PASSWORD:
            # a first password that stays is no change, and the retired one was published
            error = "Choose a password that you have not used here before."
        else:
            changed = generate_password_hash(new)
            execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                    (changed, user["id"]))
            # whoever changes his password stays signed in, here and nowhere else
            session["pw"] = _password_mark(changed)
            audit("password_changed", "user", user["id"], user=user, ip=client_ip())
            try:
                # the first password of this account need not be kept in instance/first-admin.txt
                forget_first_admin(current_app, user["email"])
            except OSError as exc:
                current_app.logger.warning("%s could not be removed: %s", "instance/first-admin.txt", exc)
            flash("Password updated.", "success")
            return redirect(url_for("agency.home") if user["role"] == "agency" else url_for("admin.dashboard"))
    return render_template("console/password.html", error=error, forced=bool(user["must_change_password"]))

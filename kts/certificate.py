"""
Certificate of recognition for every student who registers, signed by the Director of CICT.

The certificate is a page of the portal, laid out as an A4 sheet (landscape) that the student
prints or saves as PDF: /certificate/<application number>/<seal>. The seal is a keyed digest of
the number, so nobody reaches the certificate of another student by changing the number in the
address. The QR code on the sheet opens that same page on the portal: the page itself is the
proof that the certificate is genuine.

Who signs: the head of the institute in the settings (director.name, director.designation). The
image of the signature is uploaded by an administrator in the console and kept in the instance
folder, which the web server never serves; it is written into the page itself.
"""
import base64
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, current_app, flash, redirect, render_template, request, url_for

from .admin import bp as console
from .auth import current_user, login_required
from .db import all_settings, audit, query, set_setting
from .public import bp as public
from .utils import client_ip, fmt_date, now_ist, qr_data_uri, to_ist

# applications that receive no certificate
NOT_ISSUED = ("rejected", "withdrawn")
SIGNATURE_NAME = "certificate-signature"
SIGNATURE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
SIGNATURE_MAX_BYTES = 1024 * 1024
ORGANISER = "Central Institute of Classical Tamil, Chennai"


def _seal(app_no):
    key = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(key, f"kts5-certificate|{app_no}".encode("utf-8"), hashlib.sha256).hexdigest()[:20]


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


def number_of(app_no):
    """KTS5-2026-000123 -> KTS5/CR/2026/000123."""
    parts = app_no.split("-")
    return "/".join([parts[0], "CR"] + parts[1:]) if len(parts) == 3 else app_no


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


def _sheet(name, college, place, number, issued_on, link):
    """The certificate page for these details."""
    settings = all_settings()
    return render_template(
        "public/certificate.html", name=name, college=college, place=place, number=number, issued_on=issued_on,
        kts_start=_long_date(settings.get("kts.start")), kts_end=_long_date(settings.get("kts.end")),
        qr=qr_data_uri(link), link=link, host=urlsplit(link).netloc, signature=signature_data(),
        signatory=(settings.get("director.name") or "").strip(),
        designation=(settings.get("director.designation") or "").strip(), organiser=ORGANISER)


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
            flash("Certificates are issued." if action == "on" else "Certificates are no longer issued.", "success")
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
    return render_template("console/certificate.html", on=settings.get("cert.on") == "1", signature=signature_data(),
                           signatory=settings.get("director.name") or "", designation=settings.get("director.designation") or "",
                           count=counts["n"])


@console.route("/certificate/sample")
@login_required("settings")
def certificate_sample():
    """The certificate as a student receives it, with the details of an invented student."""
    response = current_app.make_response(_sheet(
        "Sample Student Name", "Government Arts College, Sample Town", "Tamil Nadu", "KTS5/CR/2026/000000",
        fmt_date(now_ist()), current_app.config["BASE_URL"].rstrip("/") + "/"))
    response.headers["Cache-Control"] = "private, no-store"
    return response

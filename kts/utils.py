"""
Shared helpers: CSRF, rate limiting, uploads, exports, mail, dates.
"""
import base64
import csv
import io
import re
import secrets
import smtplib
import threading
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from flask import abort, current_app, request, session
from werkzeug.utils import secure_filename

from .db import execute, utcnow

IST = timezone(timedelta(hours=5, minutes=30))


# ---- time -------------------------------------------------------------------

def now_ist():
    return datetime.now(IST)


def parse_iso(value):
    """Parse ISO date or datetime strings (naive values are taken as IST)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt


def to_ist(value):
    dt = parse_iso(value) if isinstance(value, str) else value
    return dt.astimezone(IST) if dt else None


def fmt_date(value):
    dt = to_ist(value) if isinstance(value, str) and len(value) > 10 else None
    if dt is None:
        try:
            d = datetime.fromisoformat(value[:10])
        except (TypeError, ValueError):
            return value or ""
        return d.strftime("%d %b %Y")
    return dt.strftime("%d %b %Y")


def fmt_dt(value):
    dt = to_ist(value)
    return dt.strftime("%d %b %Y, %I:%M %p") if dt else (value or "")


def fmt_time(value):
    dt = to_ist(value)
    return dt.strftime("%I:%M %p") if dt else (value or "")


def registration_state(settings):
    """'open' | 'not_yet' | 'closed' based on the reg.* settings."""
    if settings.get("reg.open") == "0":
        return "closed"
    today = now_ist().date()
    start = settings.get("reg.start")
    end = settings.get("reg.end")
    try:
        if start and today < datetime.fromisoformat(start).date():
            return "not_yet"
        if end and today > datetime.fromisoformat(end).date():
            return "closed"
    except ValueError:
        pass
    return "open"


def exam_window(settings):
    """(start, end, is_open) for the test login window, in IST."""
    try:
        start = datetime.fromisoformat(f"{settings['exam.date']}T{settings['exam.start_time']}").replace(tzinfo=IST)
        end = datetime.fromisoformat(f"{settings['exam.date']}T{settings['exam.end_time']}").replace(tzinfo=IST)
    except (KeyError, ValueError):
        return None, None, False
    mode = settings.get("exam.open", "auto")
    if mode == "1":
        return start, end, True
    if mode == "0":
        return start, end, False
    now = now_ist()
    return start, end, start <= now <= end


# ---- CSRF -------------------------------------------------------------------

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def check_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
        abort(400, "Invalid or missing CSRF token. Reload the page and try again.")


# ---- rate limiting ----------------------------------------------------------

class RateLimiter:
    """Tiny in-process sliding-window limiter keyed by (bucket, ip)."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, bucket, key, limit, window_sec):
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and now - q[0] > window_sec:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


# ---- uploads ----------------------------------------------------------------

IMAGE_EXT = {"jpg", "jpeg", "png"}
DOC_EXT = {"pdf", "jpg", "jpeg", "png"}
RESOURCE_EXT = {"pdf", "jpg", "jpeg", "png", "webp", "mp3", "mp4", "m4a", "zip", "docx", "pptx", "xlsx", "csv", "epub", "svg", "txt"}


def _sniff(head, ext):
    if ext in ("jpg", "jpeg"):
        return head[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "pdf":
        return head[:5] == b"%PDF-"
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return True


def save_upload(file, subdir, allowed_ext, max_bytes):
    """
    Store an uploaded file under UPLOAD_DIR/subdir with a random name.
    Returns the relative path, or raises ValueError with a reason.
    """
    if file is None or not file.filename:
        raise ValueError("missing")
    name = secure_filename(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed_ext:
        raise ValueError("type")
    head = file.stream.read(16)
    file.stream.seek(0, io.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size == 0 or size > max_bytes:
        raise ValueError("size")
    if not _sniff(head, ext):
        raise ValueError("type")
    folder = Path(current_app.config["UPLOAD_DIR"]) / subdir
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(8)}.{ext}"
    file.save(str(folder / fname))
    return f"{subdir}/{fname}", name, size


# ---- identifiers ------------------------------------------------------------

def make_app_no(row_id):
    return f"KTS5-2026-{row_id:06d}"


def normalise_text(value):
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"[^a-z0-9ऀ-෿ ]+", " ", value)
    value = re.sub(r"\b(the|of|and|college|university|institute|dept|department|govt|government)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def college_key(name, state, aishe=""):
    aishe = (aishe or "").strip().upper().replace(" ", "")
    if aishe:
        return f"aishe:{aishe}"
    return f"name:{normalise_text(name)}|{normalise_text(state)}"


def valid_mobile(value):
    return bool(re.fullmatch(r"[6-9]\d{9}", (value or "").strip()))


def valid_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", (value or "").strip()))


def valid_pincode(value):
    value = (value or "").strip()
    return value == "" or bool(re.fullmatch(r"[1-9]\d{5}", value))


def age_on(dob, on=None):
    on = on or now_ist().date()
    try:
        d = datetime.fromisoformat(dob).date()
    except (TypeError, ValueError):
        return None
    return on.year - d.year - ((on.month, on.day) < (d.month, d.day))


# ---- captcha (arithmetic, no third party) -----------------------------------

def new_captcha():
    a, b = secrets.randbelow(9) + 1, secrets.randbelow(9) + 1
    session["_captcha"] = str(a + b)
    return f"{a} + {b} = ?"


def check_captcha(answer):
    expected = session.pop("_captcha", None)
    return expected is not None and (answer or "").strip() == expected


# ---- exports ----------------------------------------------------------------

def csv_bytes(headers, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def xlsx_bytes(headers, rows, sheet="Sheet1"):
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(sheet[:31])
    bold = wb.add_format({"bold": True, "bg_color": "#EDE7DB", "border": 1})
    for c, h in enumerate(headers):
        ws.write(0, c, h, bold)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            ws.write(r, c, "" if v is None else v)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(rows), 1), max(len(headers) - 1, 0))
    for c, h in enumerate(headers):
        ws.set_column(c, c, min(max(12, len(str(h)) + 2), 48))
    wb.close()
    return buf.getvalue()


# ---- QR ---------------------------------------------------------------------

def qr_data_uri(text):
    """PNG data URI for a QR code; uses Pillow when present, pure-Python PNG otherwise."""
    try:
        import qrcode
    except ImportError:
        return ""
    buf = io.BytesIO()
    try:
        img = qrcode.make(text, box_size=4, border=1)
        img.save(buf, format="PNG")
    except Exception:  # noqa: BLE001 - Pillow missing (vendored deployment)
        try:
            from qrcode.image.pure import PyPNGImage
            buf = io.BytesIO()
            qrcode.make(text, box_size=4, border=1, image_factory=PyPNGImage).save(buf)
        except Exception:  # noqa: BLE001
            return ""
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---- mail -------------------------------------------------------------------

def send_mail(to_addr, subject, body):
    """Queue a message in the outbox and try SMTP if it is configured."""
    row_id = execute(
        "INSERT INTO outbox(to_addr, subject, body, status, created_at) VALUES(?,?,?,?,?)",
        (to_addr, subject, body, "queued", utcnow()),
    )
    cfg = current_app.config
    if not cfg.get("SMTP_HOST"):
        return row_id
    try:
        msg = EmailMessage()
        msg["From"] = cfg["SMTP_FROM"]
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
            if cfg["SMTP_TLS"]:
                smtp.starttls()
            if cfg.get("SMTP_USER"):
                smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"] or "")
            smtp.send_message(msg)
        execute("UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (utcnow(), row_id))
    except Exception as exc:  # noqa: BLE001 - record and move on
        execute("UPDATE outbox SET status='failed', error=? WHERE id=?", (str(exc)[:500], row_id))
    return row_id


# ---- misc -------------------------------------------------------------------

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate(total, page, per_page):
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    return {"page": page, "pages": pages, "per_page": per_page, "total": total,
            "offset": (page - 1) * per_page, "has_prev": page > 1, "has_next": page < pages}


def human_size(n):
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

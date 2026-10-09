"""
Shared helpers: CSRF, rate limiting, uploads, exports, mail, dates.
"""
import base64
import csv
import io
import ipaddress
import os
import re
import secrets
import smtplib
import socket
import ssl
import tempfile
import threading
import time
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from flask import abort, current_app, request, session
from werkzeug.utils import secure_filename

from .db import execute, get_db, utcnow

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


def _as_datetime(value):
    """datetime for an ISO string, a date or a datetime; None when it cannot be read."""
    if isinstance(value, datetime):
        return value.astimezone(IST) if value.tzinfo else value
    if hasattr(value, "year") and hasattr(value, "month"):  # datetime.date
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        if len(value) > 10:
            return to_ist(value)
        try:
            return datetime.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def fmt_date(value, numeric=False):
    """25 Sep 2026; with numeric=True 25-09-2026, which reads the same in every language."""
    dt = _as_datetime(value)
    if dt is None:
        return value or ""
    return dt.strftime("%d-%m-%Y" if numeric else "%d %b %Y")


def fmt_dt(value, numeric=False):
    dt = _as_datetime(value)
    if dt is None:
        return value or ""
    return dt.strftime("%d-%m-%Y, %H:%M" if numeric else "%d %b %Y, %I:%M %p")


def fmt_when(value, numeric=False):
    """Day and time of an event; the day alone when it has no time of day (00:00)."""
    dt = _as_datetime(value)
    if dt is not None and (dt.hour, dt.minute) == (0, 0):
        return fmt_date(value, numeric)
    return fmt_dt(value, numeric)


def fmt_time(value, numeric=False):
    dt = _as_datetime(value)
    if dt is None:
        return value or ""
    return dt.strftime("%H:%M" if numeric else "%I:%M %p")


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
        abort(400, "err.csrf")


# ---- rate limiting ----------------------------------------------------------

class RateLimiter:
    """
    Tiny in-process sliding-window limiter keyed by (bucket, key); the key is an address or,
    where the details of a candidate are asked, an application number with the address.

    allow() checks and counts in one step. Where only failures count (sign-in, status look-up)
    blocked() is asked first and hit() is called after a failure.
    """
    SWEEP_EVERY = 60  # seconds between two clearances of the whole table

    def __init__(self, clock=time.monotonic):
        self._hits = {}  # (bucket, key) -> [window_sec, deque of times]
        self._lock = threading.Lock()
        self._clock = clock
        self._swept = clock()

    def _count(self, bucket, key, window_sec, now):
        """Hits inside the window. A key without any is removed, so the table does not grow for ever."""
        entry = self._hits.get((bucket, key))
        if entry is None:
            return 0
        q = entry[1]
        while q and now - q[0] > window_sec:
            q.popleft()
        if not q:
            del self._hits[(bucket, key)]
        return len(q)

    def _add(self, bucket, key, window_sec, now):
        entry = self._hits.setdefault((bucket, key), [window_sec, deque()])
        entry[0] = window_sec
        entry[1].append(now)
        if now - self._swept > self.SWEEP_EVERY:
            # addresses that did not come back: their last hit is older than their window
            self._swept = now
            for name in [n for n, (window, q) in self._hits.items() if now - q[-1] > window]:
                del self._hits[name]

    def blocked(self, bucket, key, limit, window_sec):
        """True when the limit is reached. Nothing is counted."""
        with self._lock:
            return self._count(bucket, key, window_sec, self._clock()) >= limit

    def hit(self, bucket, key, window_sec):
        """Count one event."""
        with self._lock:
            self._add(bucket, key, window_sec, self._clock())

    def allow(self, bucket, key, limit, window_sec):
        """False when the limit is reached; otherwise the event is counted."""
        with self._lock:
            now = self._clock()
            if self._count(bucket, key, window_sec, now) >= limit:
                return False
            self._add(bucket, key, window_sec, now)
            return True


limiter = RateLimiter()


def plain_address(value):
    """
    An address without port and brackets, in one spelling: '198.51.100.7:51234' -> '198.51.100.7',
    '[2001:db8::7]:40112' -> '2001:db8::7', '::ffff:198.51.100.7' -> '198.51.100.7'.
    Anything that is not an address comes back as it is, cut to 64 characters.
    """
    text = (value or "").strip()
    host = text
    if text.startswith("["):
        inner, _, rest = text[1:].partition("]")
        if rest == "" or (rest[0] == ":" and rest[1:].isdigit()):
            host = inner
    elif text.count(":") == 1 and text.rsplit(":", 1)[1].isdigit():
        host = text.rsplit(":", 1)[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return text[:64]
    return str(getattr(ip, "ipv4_mapped", None) or ip)


def client_ip():
    """
    The visitor's address, for the rate limits and the audit log. Behind a proxy Waitress has
    put it into REMOTE_ADDR (server_options() in serve.py); a header is never read here, because
    a visitor can write one himself.
    """
    return plain_address(request.remote_addr)


# ---- uploads ----------------------------------------------------------------

IMAGE_EXT = {"jpg", "jpeg", "png"}
DOC_EXT = {"pdf", "jpg", "jpeg", "png"}
# the other extensions of a JPEG, taken wherever a jpg is allowed
JPEG_NAMES = ("jfif", "pjpeg", "pjp")
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
    if "jpg" in allowed_ext:
        # other names of a JPEG: browsers on Windows save photos as .jfif; kept as .jpg. Before the
        # next step, so that a name wholly in another script with such an extension is taken as
        # well: 'புகைப்படம்.jfif' is 'jfif' once the script is dropped
        if ext in JPEG_NAMES:
            ext = "jpg"
        elif not ext and name.lower() in JPEG_NAMES:
            ext, name = "jpg", f"file.{name.lower()}"
    if not ext and name.lower() in allowed_ext:
        # a name wholly in another script keeps only its extension: 'காசோலை.pdf' becomes 'pdf'
        ext, name = name.lower(), f"file.{name.lower()}"
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


def valid_ifsc(value):
    """The IFSC of a bank branch, in capitals: four letters, a zero, six letters or digits."""
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", value or ""))


def valid_account(value):
    """A bank account number: 9 to 18 digits 0-9 (no digits of other scripts), not all of them zero."""
    value = value or ""
    return bool(re.fullmatch(r"[0-9]{9,18}", value)) and value.strip("0") != ""


# The Verhoeff scheme, which gives the Aadhaar number its last digit: it finds every single
# wrong digit and every two neighbours that changed places.
_VERHOEFF_D = ((0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5), (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
               (3, 4, 0, 1, 2, 8, 9, 5, 6, 7), (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
               (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3), (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
               (9, 8, 7, 6, 5, 4, 3, 2, 1, 0))
_VERHOEFF_P = ((0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4), (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
               (8, 9, 1, 6, 0, 4, 3, 5, 2, 7), (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
               (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8))
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def _verhoeff(digits, start):
    c = 0
    for i, ch in enumerate(reversed(digits), start=start):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c


def verhoeff_digit(digits):
    """The check digit that the Verhoeff scheme puts behind a row of digits 0-9."""
    return str(_VERHOEFF_INV[_verhoeff(digits, 1)])


def valid_aadhaar(value):
    """An Aadhaar number: 12 digits 0-9, the first of them 2 to 9, the last the Verhoeff check digit."""
    value = value or ""
    return bool(re.fullmatch(r"[2-9][0-9]{11}", value)) and _verhoeff(value, 0) == 0


def rupees(value):
    """'10,000' and '1,25,000': an amount in whole rupees with the commas as they are set in India."""
    digits = str(safe_int(value))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail])


def age_on(dob, on=None):
    on = on or now_ist().date()
    try:
        d = datetime.fromisoformat(dob).date()
    except (TypeError, ValueError):
        return None
    return on.year - d.year - ((on.month, on.day) < (d.month, d.day))


# ---- English entries ----------------------------------------------------------

# Marks that phone keyboards put in by themselves, and their plain forms
_PLAIN = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                        "\u2014": "-", "\u2026": "...", "\u00a0": " "})


def plain_english(value):
    """
    (text, is_english): the text with the curly quotes and dashes of phone keyboards made plain,
    and whether it is written in English, that is in letters A-Z, digits, spaces and the usual
    punctuation, nothing else.
    """
    text = (value or "").translate(_PLAIN)
    return text, all(" " <= c <= "~" or c in "\r\n\t" for c in text)


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


def xlsx_bytes(headers, rows, sheet="Sheet1", text_cols=()):
    """
    text_cols: the columns (numbers from 0) that are text whatever they look like. Their cells
    are written as strings in the format Text: an account number keeps its zeros in front and
    all its digits, and what a student typed is never taken for a formula or a link.
    """
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(sheet[:31])
    bold = wb.add_format({"bold": True, "bg_color": "#EDE7DB", "border": 1})
    as_text = wb.add_format({"num_format": "@"})
    text_cols = set(text_cols)
    for c, h in enumerate(headers):
        ws.write(0, c, h, bold)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            if c in text_cols:
                ws.write_string(r, c, "" if v is None else str(v), as_text)
            else:
                ws.write(r, c, "" if v is None else v)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(rows), 1), max(len(headers) - 1, 0))
    for c, h in enumerate(headers):
        ws.set_column(c, c, min(max(12, len(str(h)) + 2), 48))
    wb.close()
    return buf.getvalue()


SHEET_MAX_BYTES = 1024 * 1024


def xlsx_rows(data):
    """
    The rows of the first sheet of an .xlsx file, each a list of texts (a small reader: shared and
    inline strings, numbers; a whole number keeps all its digits, as a mobile number must).
    """
    import zipfile
    from decimal import Decimal, InvalidOperation
    from xml.etree import ElementTree as ET
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > 40 * SHEET_MAX_BYTES:
            raise ValueError("the spreadsheet is too large")
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(main + "si"):
                shared.append("".join(t.text or "" for t in si.iter(main + "t")))
        # the first sheet of the workbook, wherever it is kept
        sheet = "xl/worksheets/sheet1.xml"
        try:
            first = ET.fromstring(z.read("xl/workbook.xml")).find(f"{main}sheets/{main}sheet")
            target = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}[first.get(rel + "id")]
            sheet = target.lstrip("/") if target.startswith("/") else "xl/" + target
        except (KeyError, AttributeError, ET.ParseError):
            pass
        rows = []
        for row in ET.fromstring(z.read(sheet)).iter(main + "row"):
            cells = {}
            for n, c in enumerate(row.findall(main + "c")):
                letters = "".join(ch for ch in (c.get("r") or "") if ch.isalpha())
                col = n
                if letters:
                    col = 0
                    for ch in letters.upper():
                        col = col * 26 + ord(ch) - 64
                    col -= 1
                kind, value = c.get("t"), c.find(main + "v")
                if kind == "s":
                    text = shared[int(value.text)] if value is not None and value.text else ""
                elif kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(main + "t"))
                else:
                    text = value.text if value is not None and value.text else ""
                    if kind in (None, "n") and text:
                        try:
                            number = Decimal(text)
                            text = str(int(number)) if number == number.to_integral_value() else format(number.normalize(), "f")
                        except InvalidOperation:
                            pass
                cells[col] = text
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return rows


def sheet_rows(filename, data):
    """The rows of an uploaded spreadsheet, .xlsx or .csv (UTF-8, or the code page of Excel; comma or semicolon)."""
    if filename.lower().endswith(".xlsx"):
        return xlsx_rows(data)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


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

def send_mail(to_addr, subject, body, now=False):
    """
    Queue a message to one person in the outbox (kts/mailq.py sends it in the background, before the
    mails of lists). now=True sends it at once and waits for the answer of the mail server: for the
    test message of the console only.
    """
    row_id = execute(
        "INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
        (to_addr, subject, body, "queued", utcnow()),
    )
    if now and current_app.config.get("SMTP_HOST"):
        _deliver(row_id, to_addr, subject, body)
    else:
        from . import mailq
        mailq.wake()
    return row_id


def send_later(messages):
    """
    The mails of a list, each (address, subject, body): queued together in the outbox as mails of a
    list (priority 1), which kts/mailq.py sends after the mails to one person and within the limits
    of the mail account. Gives the number queued.
    """
    conn = get_db()
    now = utcnow()
    count = 0
    for to_addr, subject, body in messages:
        conn.execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,1)",
                     (to_addr, subject, body, "queued", now))
        count += 1
    conn.commit()
    if count:
        from . import mailq
        mailq.wake()
    return count


def send_again(rows):
    """
    Failed messages of the outbox put back in the queue, as if new: the sender tries them again.
    Gives the number put back.
    """
    ids = [r["id"] for r in rows]
    if not ids:
        return 0
    conn = get_db()
    conn.executemany("UPDATE outbox SET status = 'queued', attempts = 0, next_try = NULL, error = '' "
                     "WHERE id = ? AND status IN ('queued', 'failed')", [(i,) for i in ids])
    conn.commit()
    from . import mailq
    mailq.wake()
    return len(ids)


def _smtp(cfg, timeout=15):
    """
    A connection to the mail server: on port 465 encrypted from the first byte (implicit TLS),
    on any other port plain and then, with KTS_SMTP_TLS=1, encrypted by STARTTLS.
    """
    if int(cfg["SMTP_PORT"]) == 465:
        return smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=timeout)
    smtp = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=timeout)
    if cfg["SMTP_TLS"]:
        smtp.starttls()
    return smtp


def peer_certificate(host, port=465, timeout=10):
    """
    (subject, issuer) of the certificate that the server on an implicit-TLS port shows, read
    without checking it: a certificate that the issuer of the real server did not make shows
    that something on the way opens the encrypted line.
    """
    pem = ssl.get_server_certificate((host, port), timeout=timeout)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pem)
    try:
        cert = ssl._ssl._test_decode_cert(fh.name)
    finally:
        os.unlink(fh.name)

    def names(part):
        return ", ".join(value for rdn in cert.get(part, ()) for key, value in rdn
                         if key in ("commonName", "organizationName"))

    return names("subject"), names("issuer")


def password_form(password):
    """What the password looks like, never what it is: (has the form of an app password, words)."""
    password = password or ""
    if re.fullmatch(r"[a-z]{16}", password):
        return True, "16 letters a–z, the form of a Google app password"
    if not password:
        return False, "empty"
    kinds = []
    if " " in password:
        kinds.append("spaces")
    if re.search(r"[A-Z]", password):
        kinds.append("capital letters")
    if re.search(r"[0-9]", password):
        kinds.append("digits")
    if re.search(r"[^A-Za-z0-9 ]", password):
        kinds.append("other characters")
    return False, f"{len(password)} characters" + (" with " + ", ".join(kinds) if kinds else "") + \
        "; a Google app password is 16 letters a–z, written without the spaces Google shows"


def mail_check(cfg, timeout=10):
    """
    The way to the mail server, step by step: [(step, ok, detail)]. It stops at the first step
    that fails, after trying which of the ports 587 and 465 can be reached at all; a hosting
    company that blocks mail lets none of them through. The certificate that the server shows
    says whether the line reaches the mail server itself; the sign-in is made in its three steps
    (AUTH LOGIN, the name, the password), each with the answer of the server, so that a line that
    is cut before the password is sent is told from a password that is refused. The password is
    used, never shown; only its form is described.
    """
    host = cfg.get("SMTP_HOST") or ""
    port = int(cfg.get("SMTP_PORT") or 587)
    steps = []

    def step(name, work):
        try:
            detail = work()
        except Exception as exc:  # noqa: BLE001 - every failure is the answer of the check
            steps.append((name, False, f"{type(exc).__name__}: {exc}"[:300]))
            return False
        if isinstance(detail, tuple):
            ok, detail = detail
            steps.append((name, ok, detail))
            return ok
        steps.append((name, True, detail or ""))
        return True

    if not host:
        return [("Mail server", False, "KTS_SMTP_HOST is not set")]
    if not step(f"Find {host}", lambda: ", ".join(sorted({a[4][0] for a in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})[:4])):
        return steps
    for p in sorted({port, 587, 465}):
        step(f"Reach port {p}", lambda p=p: socket.create_connection((host, p), timeout).close() or "open")

    def certificate():
        subject, issuer = peer_certificate(host, 465, timeout)
        genuine = "google" in issuer.lower() if "gmail" in host or "google" in host else True
        text = f"{subject}, issued by {issuer}"
        return (True, text) if genuine else (False, text + " (not a certificate of Google: something on the "
                                                           "way opens the encrypted line)")

    step("Certificate on port 465", certificate)
    if cfg.get("SMTP_USER"):
        step("Password as read from portal.env", lambda: password_form(cfg.get("SMTP_PASSWORD")))
    conn = {}

    def greet():
        conn["smtp"] = (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)(host, port, timeout=timeout)
        code, text = conn["smtp"].ehlo()
        return f"{code} {text.decode('utf-8', 'replace').splitlines()[0]}"

    if not step(f"Greeting on port {port}", greet):
        return steps
    smtp = conn["smtp"]

    def answer(code, text):
        return f"{code} {text.decode('utf-8', 'replace') if isinstance(text, bytes) else text}"[:200]

    def expect(command, wanted):
        code, text = smtp.docmd(*command)
        return (code == wanted, answer(code, text))

    try:
        if port != 465 and cfg.get("SMTP_TLS"):
            if not step("Encryption (STARTTLS)", lambda: str(smtp.starttls()[0])):
                return steps
            smtp.ehlo()
        if cfg.get("SMTP_USER"):
            step("Sign-in methods offered", lambda: smtp.esmtp_features.get("auth", "none").strip() or "none")
            user, password = cfg["SMTP_USER"], cfg.get("SMTP_PASSWORD") or ""
            if step("Sign-in, 1: AUTH LOGIN", lambda: expect(("AUTH", "LOGIN"), 334)) and \
                    step(f"Sign-in, 2: the name {user}", lambda: expect((base64.b64encode(user.encode()).decode(),), 334)):
                step("Sign-in, 3: the password", lambda: expect((base64.b64encode(password.encode()).decode(),), 235))
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001 - the line may be gone already
            pass
    return steps


def _deliver(row_id, to_addr, subject, body):
    """One message of the outbox over SMTP; its row says afterwards whether it went."""
    cfg = current_app.config
    try:
        msg = EmailMessage()
        msg["From"] = cfg["SMTP_FROM"]
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        with _smtp(cfg) as smtp:
            if cfg.get("SMTP_USER"):
                smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"] or "")
            smtp.send_message(msg)
        execute("UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (utcnow(), row_id))
    except Exception as exc:  # noqa: BLE001 - record and move on
        execute("UPDATE outbox SET status='failed', error=? WHERE id=?", (str(exc)[:500], row_id))


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

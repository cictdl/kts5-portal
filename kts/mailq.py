"""
The outbox as a queue (version 1.2.35).

Every mail of the portal is written to the table outbox and sent by one sender in the background,
never inside the request that caused it: a student who registers does not wait for the mail server.

The sender works in rounds: when a mail is queued, and at the latest every ROUND_SECONDS. In a round
it sends, over one connection, as many waiting mails as the limits allow:

* mail.daily_limit (default 1,800): mails sent in the last 24 hours. Google Workspace lets an account
  send about 2,000 a day; past that it refuses every mail for a day. The default keeps a margin for
  the mails that people send from the same account by hand.
* mail.per_minute (default 30): mails sent in the last minute, so that a list of a thousand goes out
  over the hours and not in one burst.

Mails to one person (the acknowledgement of an application, a password, a verification) have
priority 0 and go before the mails of a list (priority 1, send_later), so a list never holds them up.

A mail that fails for a passing reason (no connection, the server busy, 4xx) is tried again after
2, 4, 8, 16 minutes, MAX_ATTEMPTS times in all; one that the server refuses for good (5xx, an address
that does not exist) is marked failed at once. When Google says that the daily quota is used up, the
sender waits QUOTA_PAUSE_MINUTES and sends nothing in between. mail.paused stops the sender.

A mail is claimed (status 'sending') before it is sent, so that two senders never send it twice; a
claim older than CLAIM_MINUTES (the portal stopped in the middle) is given back to the queue.
"""
import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import current_app

from .db import get_db, get_setting, query

ROUND_SECONDS = 60
MAX_ATTEMPTS = 5
QUOTA_PAUSE_MINUTES = 60
LOGIN_PAUSE_MINUTES = 15
CLAIM_MINUTES = 10
DEFAULTS = {"mail.daily_limit": 1800, "mail.per_minute": 30}


def _iso(moment):
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _now():
    return datetime.now(timezone.utc)


def _number(key):
    try:
        return max(0, int(get_setting(key) or DEFAULTS[key]))
    except (TypeError, ValueError):
        return DEFAULTS[key]


def figures(now=None):
    """What the outbox page shows: waiting mails, sent in the last 24 hours and minute, the limits."""
    now = now or _now()
    day = query("SELECT COUNT(*) AS n FROM outbox WHERE status = 'sent' AND sent_at > ?",
                (_iso(now - timedelta(hours=24)),), one=True)["n"]
    minute = query("SELECT COUNT(*) AS n FROM outbox WHERE status = 'sent' AND sent_at > ?",
                   (_iso(now - timedelta(minutes=1)),), one=True)["n"]
    waiting = {r["priority"]: r["n"] for r in query(
        "SELECT priority, COUNT(*) AS n FROM outbox WHERE status IN ('queued', 'sending') GROUP BY priority")}
    paused_until = get_setting("mail.quota_pause_until") or ""
    return {"sent_day": day, "sent_minute": minute, "daily_limit": _number("mail.daily_limit"),
            "per_minute": _number("mail.per_minute"), "paused": get_setting("mail.paused") == "1",
            "quota_pause": paused_until if paused_until > _iso(now) else "",
            "waiting_one": waiting.get(0, 0), "waiting_list": sum(n for p, n in waiting.items() if p != 0)}


def _permanent(exc):
    """True when the server refuses the mail for good (5xx), not for a passing reason."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return all(code >= 500 for code, _msg in exc.recipients.values())
    code = getattr(exc, "smtp_code", None)
    return isinstance(code, int) and code >= 500 and not _quota(exc)


def _quota(exc):
    text = str(exc).lower()
    return "5.4.5" in text or "sending quota" in text or "sending limit" in text or "daily user" in text


def run_once(app, now=None):
    """
    One round of the sender. Gives what happened: {"sent": n, "failed": n, "retry": n, "waiting": reason}.
    Safe to call at any time and from tests; the background sender calls it in a loop.
    """
    now = now or _now()
    result = {"sent": 0, "failed": 0, "retry": 0, "waiting": ""}
    with app.app_context():
        conn = get_db()
        # claims of a sender that stopped in the middle go back to the queue
        conn.execute("UPDATE outbox SET status = 'queued' WHERE status = 'sending' AND (next_try IS NULL OR next_try < ?)",
                     (_iso(now - timedelta(minutes=CLAIM_MINUTES)),))
        conn.commit()
        cfg = app.config
        if not cfg.get("SMTP_HOST"):
            result["waiting"] = "mail is not configured"
            return result
        if get_setting("mail.paused") == "1":
            result["waiting"] = "paused"
            return result
        pause = get_setting("mail.quota_pause_until") or ""
        if pause > _iso(now):
            result["waiting"] = "daily quota of the mail account used up"
            return result
        f = figures(now)
        room = min(f["daily_limit"] - f["sent_day"], f["per_minute"] - f["sent_minute"])
        if room <= 0:
            result["waiting"] = "daily limit" if f["sent_day"] >= f["daily_limit"] else "limit per minute"
            return result
        rows = query("SELECT id, to_addr, subject, body, attempts FROM outbox WHERE status = 'queued' "
                     "AND (next_try IS NULL OR next_try <= ?) ORDER BY priority, id LIMIT ?", (_iso(now), room))
        claimed = []
        for r in rows:
            cur = conn.execute("UPDATE outbox SET status = 'sending', next_try = ? WHERE id = ? AND status = 'queued'",
                               (_iso(now), r["id"]))
            if cur.rowcount == 1:
                claimed.append(r)
        conn.commit()
        if not claimed:
            return result

        def later(row, exc, minutes=None):
            attempts = (row["attempts"] or 0) + 1
            if minutes is None and (attempts >= MAX_ATTEMPTS or _permanent(exc)):
                conn.execute("UPDATE outbox SET status = 'failed', attempts = ?, error = ?, next_try = NULL WHERE id = ?",
                             (attempts, str(exc)[:500], row["id"]))
                result["failed"] += 1
                return
            wait = minutes if minutes is not None else 2 ** attempts
            conn.execute("UPDATE outbox SET status = 'queued', attempts = ?, error = ?, next_try = ? WHERE id = ?",
                         (attempts, str(exc)[:500], _iso(now + timedelta(minutes=wait)), row["id"]))
            result["retry"] += 1

        from .utils import _smtp
        try:
            smtp = _smtp(cfg)
            if cfg.get("SMTP_USER"):
                smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"] or "")
        except Exception as exc:  # noqa: BLE001 - no connection or no sign-in: not the fault of any mail
            # every claimed mail waits LOGIN_PAUSE_MINUTES, without counting an attempt; a wrong password
            # must not make the waiting mails fail for good
            for r in claimed:
                conn.execute("UPDATE outbox SET status = 'queued', error = ?, next_try = ? WHERE id = ?",
                             (str(exc)[:500], _iso(now + timedelta(minutes=LOGIN_PAUSE_MINUTES)), r["id"]))
                result["retry"] += 1
            conn.commit()
            result["waiting"] = "no connection to the mail server"
            return result
        try:
            for i, r in enumerate(claimed):
                msg = EmailMessage()
                msg["From"] = cfg["SMTP_FROM"]
                msg["To"] = r["to_addr"]
                msg["Subject"] = r["subject"]
                msg.set_content(r["body"])
                try:
                    smtp.send_message(msg)
                except Exception as exc:  # noqa: BLE001
                    if _quota(exc):
                        # Google refuses for a day: this one and the rest wait, nothing is tried before the pause ends
                        until = _iso(now + timedelta(minutes=QUOTA_PAUSE_MINUTES))
                        conn.execute("INSERT INTO settings(key, value, updated_at) VALUES('mail.quota_pause_until', ?, ?) "
                                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                                     (until, _iso(now)))
                        for rest in claimed[i:]:
                            conn.execute("UPDATE outbox SET status = 'queued', error = ?, next_try = ? WHERE id = ?",
                                         (str(exc)[:500], until, rest["id"]))
                            result["retry"] += 1
                        result["waiting"] = "daily quota of the mail account used up"
                        break
                    later(r, exc)
                    if isinstance(exc, (smtplib.SMTPServerDisconnected, OSError)):
                        for rest in claimed[i + 1:]:
                            later(rest, exc)
                        break
                    continue
                conn.execute("UPDATE outbox SET status = 'sent', sent_at = ?, error = '', next_try = NULL WHERE id = ?",
                             (_iso(_now()), r["id"]))
                result["sent"] += 1
                conn.commit()
        finally:
            conn.commit()
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
    return result


def start(app):
    """
    The sender in the background: one thread, started by serve.py (and run.py) when the portal is
    served, never by create_app, so that tests and scripts have none. Not without a mail server.
    """
    if app.config.get("TESTING") or not app.config.get("SMTP_HOST") or not app.config.get("MAIL_QUEUE", True):
        return None
    state = app.extensions.get("kts_mailq")
    if state:
        return state["thread"]
    event = threading.Event()

    def loop():
        while True:
            try:
                # the morning mail to the Nodal Officers of the States/UTs, once a day (kts/nodal.py)
                from . import nodal
                nodal.daily(app)
            except Exception:  # noqa: BLE001
                app.logger.exception("mail sender: the morning mail of the Nodal Officers failed")
            try:
                # the reminders to the participating institutions that are behind (kts/progress.py)
                from . import progress
                progress.daily(app)
            except Exception:  # noqa: BLE001
                app.logger.exception("mail sender: the reminders to the institutions failed")
            try:
                run_once(app)
            except Exception:  # noqa: BLE001 - the sender never stops for one bad round
                app.logger.exception("mail sender: round failed")
            event.wait(ROUND_SECONDS)
            event.clear()

    thread = threading.Thread(target=loop, name="kts-mailq", daemon=True)
    app.extensions["kts_mailq"] = {"thread": thread, "event": event}
    thread.start()
    return thread


def wake(app=None):
    """A mail was queued: the sender starts a round at once instead of at the end of its minute."""
    app = app or current_app._get_current_object()
    state = app.extensions.get("kts_mailq")
    if state:
        state["event"].set()

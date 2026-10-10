"""
The Nodal Officers of the States/UTs (versions 1.2.38 and 1.2.39): what the portal tells them by mail.

* The mail of a new account says what a Nodal Officer does and when verification closes.
* The morning mail (nodal.digest, at nodal.digest_time IST): every active Nodal Officer with
  applications awaiting them hears how many, from the opening of registration (reg.start) to the
  close of verification (verify.end). It goes once a day, whatever the number of senders
  (nodal.digest_sent); on the last two days it is a reminder. The sender of the mail queue calls
  daily() at each round (kts/mailq.py).
* The reminder that CICT sends from Console > Nodal officers (remind()).

Only verified students are consolidated by CICT: verify.end is the last day of the consolidation.
"""
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from .db import get_db, get_setting, query, utcnow
from .utils import now_ist, send_later

# the applications that a Nodal Officer has verified, whatever happened to them afterwards
DONE = ("verified", "selected", "waitlisted", "not_selected")


def states_of(user):
    return [s for s in (user["states"] or "").split("|") if s]


def _day(value):
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def long_date(day):
    return f"{day.day} {day.strftime('%B %Y')}" if day else ""


def verify_end():
    return _day(get_setting("verify.end"))


def closes_line():
    """Verification closes on 21 October 2026 (end of the day, IST); only verified students take the test."""
    end = verify_end()
    if not end:
        return ""
    return (f"Verification closes on {long_date(end)} (end of the day, IST). Only verified students are consolidated by CICT "
            f"into the list of the selected students.")


def figures(states, now=None):
    """
    The applications of the institutions of these States/UTs, each State/UT and all together:
    awaiting verification, new in the last 24 hours, verified, rejected, days the oldest has waited.
    """
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).astimezone(timezone.utc).replace(microsecond=0).isoformat()
    per = {s: {"awaiting": 0, "new": 0, "verified": 0, "rejected": 0, "oldest": None} for s in states}
    if states:
        marks = ",".join("?" * len(states))
        for r in query(f"SELECT college_state AS s, status, COUNT(*) AS n, MIN(created_at) AS first, "
                       f"SUM(CASE WHEN created_at > ? THEN 1 ELSE 0 END) AS fresh FROM applications "
                       f"WHERE college_state IN ({marks}) GROUP BY college_state, status", [since] + list(states)):
            f = per[r["s"]]
            if r["status"] == "submitted":
                f["awaiting"] += r["n"]
                f["new"] += r["fresh"] or 0
                f["oldest"] = r["first"]
            elif r["status"] in DONE:
                f["verified"] += r["n"]
            elif r["status"] == "rejected":
                f["rejected"] += r["n"]
    for f in per.values():
        first = f.pop("oldest")
        try:
            f["waiting_days"] = max(0, (now - datetime.fromisoformat(first)).days) if first else None
        except ValueError:
            f["waiting_days"] = None
    total = {k: sum(f[k] for f in per.values()) for k in ("awaiting", "new", "verified", "rejected")}
    waited = [f["waiting_days"] for f in per.values() if f["waiting_days"] is not None]
    total["waiting_days"] = max(waited) if waited else None
    return per, total


def account_paragraph(states):
    """The part of the mail of a new account that a Nodal Officer reads."""
    text = (f"As Nodal Officer for {', '.join(states)}, you see the applications of the students of the institutions "
            f"of your State/UT, with their photograph, ID proof and signed nomination form, and you verify them: "
            f"Console > Verification queue. Only verified students are consolidated by CICT into the list of the selected students.")
    end = verify_end()
    if end:
        text += f" Verification closes on {long_date(end)}."
    return text + "\n\n"


def institutions_pending(states):
    """The institutions of these States/UTs that await the decision of the Nodal Officer (1.2.41)."""
    if not states:
        return 0
    return query(f"SELECT COUNT(*) AS n FROM institutions WHERE status = 'pending' AND state IN ({','.join('?' * len(states))})",
                 list(states), one=True)["n"]


def officer_mail(user, reminder=False, now=None):
    """(subject, body) of the morning mail or of a reminder to one Nodal Officer; None when nothing awaits them."""
    states = states_of(user)
    per, total = figures(states, now)
    pending = institutions_pending(states)
    if not total["awaiting"] and not pending:
        return None
    base = current_app.config["BASE_URL"]
    stamp = (now or now_ist()).astimezone(now_ist().tzinfo)
    n = total["awaiting"]
    parts = []
    if n:
        parts.append(f"{n} application{'s' if n != 1 else ''} await{'s' if n == 1 else ''} your verification")
    if pending:
        parts.append(f"{pending} institution{'s' if pending != 1 else ''} await{'s' if pending == 1 else ''} your decision")
    what = "; ".join(parts)
    subject = f"KTS 5.0: {what} ({', '.join(states)})"
    end = verify_end()
    if reminder:
        subject = "Reminder – " + subject + (f"; verification closes on {long_date(end)}" if end else "")
    lines = [f"Dear {user['name']},", "",
             (f"This is a reminder from CICT. " if reminder else "")
             + f"The applications of the students of the institutions of {', '.join(states)}, "
             f"on {long_date(stamp.date())} at {stamp.strftime('%I:%M %p').lstrip('0')} IST:", ""]

    def block(f):
        out = [f"  Awaiting your verification: {f['awaiting']}" + (f" ({f['new']} new in the last 24 hours)" if f["new"] else "")]
        if f["waiting_days"]:
            out.append(f"  Waiting longest: {f['waiting_days']} day{'s' if f['waiting_days'] != 1 else ''}")
        out += [f"  Verified: {f['verified']}", f"  Rejected: {f['rejected']}"]
        return out

    if len(states) == 1:
        lines += block(total)
    else:
        for s in states:
            lines += [s] + block(per[s]) + [""]
        lines += [f"All together: {total['awaiting']} awaiting, {total['verified']} verified, {total['rejected']} rejected."]
    if pending:
        lines += ["", f"Institutions awaiting your decision: {pending}. Accept or decline them: {base}/console/institutions?status=pending"]
    close = closes_line()
    lines += ["", close] if close else []
    lines += ["", f"Open the verification queue: {base}/console/applications?status=submitted",
              f"(Sign in at {base}/console/login with your e-mail address.)", "",
              "Open each application, look at the photograph, the ID proof and the nomination form signed by the head of "
              "the institution, and verify it, or reject it with a remark that the student will read.", "",
              "CICT, Chennai", "",
              "This mail comes every morning while applications or institutions await you, until verification closes."]
    return subject, "\n".join(lines)


def remind(users, now=None):
    """A reminder from CICT to these Nodal Officers, to each one with applications awaiting them. Gives the number queued."""
    messages = []
    for u in users:
        mail = officer_mail(u, reminder=True, now=now)
        if mail and u["active"]:
            messages.append((u["email"],) + mail)
    return send_later(messages)


def daily(app, now=None):
    """
    The morning mail: once a day after nodal.digest_time, between reg.start and verify.end, to every
    active Nodal Officer with applications awaiting them. Gives the number of mails queued.
    """
    now = now or now_ist()
    with app.app_context():
        if get_setting("nodal.digest") != "1":
            return 0
        today = now.date()
        start, end = _day(get_setting("reg.start")), verify_end()
        if end and today > end:
            return 0
        # before registration opens, only for the institutions that await a decision (1.2.41)
        if start and today < start and not query("SELECT 1 FROM institutions WHERE status = 'pending' LIMIT 1", one=True):
            return 0
        at = (get_setting("nodal.digest_time") or "08:00").strip()
        try:
            hour, minute = (int(x) for x in at.split(":")[:2])
        except ValueError:
            hour, minute = 8, 0
        if (now.hour, now.minute) < (hour, minute):
            return 0
        # once a day: only the sender that writes today's date here sends
        conn = get_db()
        cur = conn.execute("INSERT INTO settings(key, value, updated_at) VALUES('nodal.digest_sent', ?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at "
                           "WHERE settings.value != excluded.value", (today.isoformat(), utcnow()))
        conn.commit()
        if cur.rowcount != 1:
            return 0
        last_days = bool(end) and (end - today).days <= 1
        messages = []
        for u in query("SELECT * FROM users WHERE role = 'nodal' AND active = 1 ORDER BY id"):
            mail = officer_mail(u, reminder=last_days, now=now)
            if mail:
                messages.append((u["email"],) + mail)
        count = send_later(messages)
        from .db import audit
        audit("nodal_morning_mail", "user", None, detail={"mails": count, "day": today.isoformat()})
        return count

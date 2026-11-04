"""
The Nodal Officers of the States/UTs (versions 1.2.38 and 1.2.39): what the portal tells them by mail.

* The mail of a new account says what a Nodal Officer does and when verification closes.
* The morning mail (nodal.digest, at nodal.digest_time IST): every active Nodal Officer with
  applications awaiting them hears how many, from the opening of registration (reg.start) to the
  close of verification (verify.end). It goes once a day, whatever the number of senders
  (nodal.digest_sent); on the last two days it is a reminder. The sender of the mail queue calls
  daily() at each round (kts/mailq.py).
* The reminder that CICT sends from Console > Nodal officers (remind()).
* The sign-in reminder to an officer whose account has never been signed in to (1.2.136): from
  Console > Nodal officers (remind_signin()), and every third morning with the morning mail.

Only verified students are consolidated by CICT: verify.end is the last day of the consolidation.
"""
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from .db import execute, get_db, get_setting, query, utcnow
from .utils import now_ist, send_later

# the applications that a Nodal Officer has verified, whatever happened to them afterwards
DONE = ("verified", "selected", "waitlisted", "not_selected")


def own_states(user):
    """The States/UTs given to the account (users.states), as they are."""
    return [s for s in (user["states"] or "").split("|") if s]


def states_of(user):
    """The States/UTs a Nodal Officer works on: those of the account, with the Union Territories Annexure-I pairs with them (1.2.135)."""
    from .heis import with_covered
    return with_covered(own_states(user))


def rows_of(states):
    """The rows of Annexure-I these States/UTs belong to, each with its members: {'Kerala and Lakshadweep': ['Kerala', 'Lakshadweep']}."""
    from .heis import label_of
    rows = {}
    for s in states:
        rows.setdefault(label_of(s, "en"), []).append(s)
    return rows


def fold(per, states):
    """The figures of these States/UTs together: the counts added, the longest wait (1.2.135)."""
    f = {"awaiting": 0, "new": 0, "verified": 0, "rejected": 0, "waiting_days": None}
    for s in states:
        g = per.get(s)
        if not g:
            continue
        for k in ("awaiting", "new", "verified", "rejected"):
            f[k] += g[k]
        if g["waiting_days"] is not None and (f["waiting_days"] is None or g["waiting_days"] > f["waiting_days"]):
            f["waiting_days"] = g["waiting_days"]
    return f


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
    from .heis import with_covered
    names = ", ".join(rows_of(with_covered(list(states))))   # the row of Annexure-I: Kerala and Lakshadweep (1.2.135)
    text = (f"As Nodal Officer for {names}, you scrutinise the institutions of your State/UT that register on the portal, record "
            f"the marks of the Evaluation Committee on the criteria of Annexure-V of the D.O. letter of 31 October 2026 and select "
            f"the number of Participating Institutions that Annexure-I prescribes, with a reserve list: Console > Institutions. "
            f"Then you see the applications of the students the Participating Institutions nominate, with their photograph, ID "
            f"proof and signed nomination form, and you verify them: Console > Verification queue. Only verified students are "
            f"consolidated by CICT into the list of the selected students.")
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
    rows = rows_of(states)   # by the row of Annexure-I (1.2.135): a State and the Union Territory paired with it as one
    names = ", ".join(rows)
    base = current_app.config["BASE_URL"]
    stamp = (now or now_ist()).astimezone(now_ist().tzinfo)
    n = total["awaiting"]
    parts = []
    if n:
        parts.append(f"{n} application{'s' if n != 1 else ''} await{'s' if n == 1 else ''} your verification")
    if pending:
        parts.append(f"{pending} institution{'s' if pending != 1 else ''} await{'s' if pending == 1 else ''} your decision")
    what = "; ".join(parts)
    subject = f"KTS 5.0: {what} ({names})"
    end = verify_end()
    if reminder:
        subject = "Reminder – " + subject + (f"; verification closes on {long_date(end)}" if end else "")
    lines = [f"Dear {user['name']},", "",
             (f"This is a reminder from CICT. " if reminder else "")
             + f"The applications of the students of the institutions of {names}, "
             f"on {long_date(stamp.date())} at {stamp.strftime('%I:%M %p').lstrip('0')} IST:", ""]

    def block(f):
        out = [f"  Awaiting your verification: {f['awaiting']}" + (f" ({f['new']} new in the last 24 hours)" if f["new"] else "")]
        if f["waiting_days"]:
            out.append(f"  Waiting longest: {f['waiting_days']} day{'s' if f['waiting_days'] != 1 else ''}")
        out += [f"  Verified: {f['verified']}", f"  Rejected: {f['rejected']}"]
        return out

    if len(rows) == 1:
        lines += block(total)
    else:
        for name, members in rows.items():
            lines += [name] + block(fold(per, members)) + [""]
        lines += [f"All together: {total['awaiting']} awaiting, {total['verified']} verified, {total['rejected']} rejected."]
    if pending:
        lines += ["", f"Institutions registered and awaiting your selection: {pending}. Record their marks of Annexure-V and select the "
                      f"Participating Institutions within the number of Annexure-I: {base}/console/institutions?status=pending"]
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


# the reminder to a Nodal Officer whose account has never been signed in to (1.2.136)
SIGNIN_SUBJECT = "KTS 5.0: your Console account awaits your first sign-in"
SIGNIN_EVERY = 3   # days from the account, or from the last reminder, to the next automatic reminder


def not_signed_in(users=None):
    """The active accounts of Nodal Officers that have never been signed in to (users.last_login_at empty)."""
    rows = users if users is not None else query("SELECT * FROM users WHERE role = 'nodal' AND active = 1 ORDER BY id")
    return [u for u in rows if u["role"] == "nodal" and u["active"] and not u["last_login_at"]]


def signin_mail(user, now=None):
    """(subject, body) of the reminder to a Nodal Officer who has not signed in to the Console yet."""
    from .heis import allocation_of
    from .public import guide_videos
    base = current_app.config["BASE_URL"]
    states = states_of(user)
    rows = rows_of(states)
    names = ", ".join(rows)
    created = _day(user["created_at"])
    registered = (query(f"SELECT COUNT(*) AS n FROM institutions WHERE status != 'identified' AND state IN ({','.join('?' * len(states))})",
                        states, one=True)["n"] if states else 0)
    pending = institutions_pending(states)
    _per, total = figures(states, now)
    number = sum(allocation_of(members[0]) for members in rows.values())
    hei_end, select_end, reg_end, end = (_day(get_setting(k)) for k in ("hei.end", "hei.select_end", "reg.end", "verify.end"))
    contact = (get_setting("contact.email") or "").strip() or "office@cict.in"
    guide = next((v["url"] for v in guide_videos() if v["n"] == 1), f"{base}/nodal-institutions")
    on = f" on {long_date(created)}" if created else ""
    lines = [f"Dear {user['name']},", "",
             f"Your account as Nodal Officer for {names} on the KTS 5.0 portal ({base}) was created{on} and the temporary password "
             f"was mailed to this address; the account has not been signed in to yet. The Students' Engagement Programme of Kashi "
             f"Tamil Sangamam 5.0 – Thirukkural Payilvom needs the Nodal Institution on the portal now:", "",
             f"• The institutions of {names} register on the portal" + (f" up to {long_date(hei_end)}" if hei_end else "")
             + f": {registered} registered so far" + (f", {pending} awaiting your decision" if pending else "") + ".",
             f"• The Nodal Institution selects the {number} Participating Institutions that Annexure-I prescribes"
             + (f" by {long_date(select_end)}" if select_end else "") + ", with a reserve list, in the Console (Institutions).",
             "• Each selected institution nominates one student" + (f" by {long_date(reg_end)}" if reg_end else "")
             + "; the Nodal Officers verify the nominations" + (f" by {long_date(end)}" if end else "") + "."
             + (f" {total['awaiting']} application(s) await your verification already." if total["awaiting"] else ""),
             "",
             f"Sign in: {base}/console/login",
             f"E-mail: {user['email']}",
             f"Password: the temporary password in the mail \"Your KTS 5.0 portal account\"{' of ' + long_date(created) if created else ''}. "
             f"The portal asks you to set a password of your own at the first sign-in.",
             f"If that mail cannot be found, write to {contact} and CICT will send a new temporary password.",
             "",
             f"The video guide for Nodal Officers (13 minutes): {guide}",
             f"The Nodal Institutions and the numbers of Annexure-I: {base}/nodal-institutions",
             "",
             "Central Institute of Classical Tamil, Chennai"]
    return f"{SIGNIN_SUBJECT} ({names})", "\n".join(lines)


def remind_signin(users, now=None):
    """The sign-in reminder to those of these Nodal Officers who have not signed in yet, noted on the account; gives the number queued."""
    due = not_signed_in(users)
    count = send_later([(u["email"],) + signin_mail(u, now) for u in due])
    stamp = now.isoformat() if now else utcnow()
    for u in due:
        execute("UPDATE users SET signin_reminded_at = ? WHERE id = ?", (stamp, u["id"]))
    return count


def daily(app, now=None):
    """
    The morning mail: once a day after nodal.digest_time, between reg.start and verify.end, to every
    active Nodal Officer with applications awaiting them, and every third day the sign-in reminder
    to an officer who has never signed in (1.2.136). Gives the number of mails queued.
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
        # the officers who have never signed in: a sign-in reminder every third day (1.2.136)
        due = []
        for u in not_signed_in():
            since = _day(u["signin_reminded_at"] or u["created_at"])
            if since and (today - since).days >= SIGNIN_EVERY:
                due.append(u)
        messages += [(u["email"],) + signin_mail(u, now) for u in due]
        count = send_later(messages)
        for u in due:
            execute("UPDATE users SET signin_reminded_at = ? WHERE id = ?", (now.isoformat(), u["id"]))
        from .db import audit
        audit("nodal_morning_mail", "user", None, detail={"mails": count, "day": today.isoformat()})
        return count

"""
The progress of the participating institutions in the week of the assessments, and the reminders
mailed to those that are behind (version 1.2.52).

* Each accepted institution stands at one stage: nothing done yet ("none"), its online assessment
  opened ("testing"), a student selected ("selected"), that student registered ("registered"),
  the application verified by the Nodal Officer ("verified"). Console > Progress shows the
  stages State/UT by State/UT, and the institutions that are behind with their coordinators.
* The reminders go once to each institution that is behind, in the morning (at nodal.digest_time
  IST, as the Nodal Officers' mail), while remind.on is on and up to the last day of registration:
  on and after remind.test_by to those that have done nothing; on and after remind.select_by to
  those that have not selected a student (the Head of the Institution in copy); on and after
  remind.register_by to those whose selected student has not registered (the student receives the
  personal link again). Where two are due on one morning, only the later one goes.
* CICT, or the Nodal Officer of the State/UT, can send a reminder by hand to the institutions that
  are behind (Console > Progress): once a day to each.
"""
import json
from datetime import date

from flask import current_app

from .db import get_db, get_setting, query, utcnow
from .utils import now_ist, send_later

STAGES = ("none", "testing", "selected", "registered", "verified")
STAGE_NAMES = {"none": "nothing done yet", "testing": "assessing, no student selected", "selected": "selected, not registered",
               "registered": "registered, awaiting verification", "verified": "verified"}
# the applications that a Nodal Officer has verified, whatever happened to them afterwards (as kts/nodal.py)
VERIFIED = ("verified", "selected", "waitlisted", "not_selected")
# the automatic reminders, in their order, with the setting of the first day and the stages they go to
KINDS = (("start", "remind.test_by", ("none",)),
         ("select", "remind.select_by", ("none", "testing")),
         ("register", "remind.register_by", ("selected",)))


def _day(value):
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def long_date(day):
    return f"{day.day} {day.strftime('%B %Y')}" if day else ""


def stage_of(row):
    if row["application_id"]:
        return "verified" if row["app_status"] in VERIFIED else "registered"
    if row["winner_id"]:
        return "selected"
    if row["test_on"]:
        return "testing"
    return "none"


def _scope_sql(scope, column="i.state"):
    if scope is None:
        return "", []
    if not scope:
        return " AND 0", []
    return f" AND {column} IN ({','.join('?' * len(scope))})", list(scope)


def institutions(scope=None, state=None, ids=None):
    """The accepted institutions (of these States/UTs), each with its figures, its stage and its reminders."""
    sql, args = _scope_sql(scope)
    if state:
        sql += " AND i.state = ?"
        args.append(state)
    if ids is not None:
        sql += f" AND i.id IN ({','.join('?' * len(ids))})" if ids else " AND 0"
        args += list(ids)
    rows = query(
        "SELECT i.*, a.app_no, a.status AS app_status, a.full_name AS app_name, w.name AS winner_name, w.email AS winner_email, "
        "(SELECT COUNT(*) FROM campus_students s WHERE s.institution_id = i.id) AS signed_up, "
        "(SELECT COUNT(*) FROM campus_students s JOIN campus_attempts t ON t.student_id = s.id "
        " WHERE s.institution_id = i.id AND t.status IN ('submitted', 'expired')) AS tested, "
        "(SELECT MAX(r.sent_at) FROM institution_reminders r WHERE r.institution_id = i.id) AS reminded_at, "
        "(SELECT COUNT(*) FROM institution_reminders r WHERE r.institution_id = i.id) AS reminders "
        "FROM institutions i LEFT JOIN applications a ON a.id = i.application_id "
        "LEFT JOIN campus_students w ON w.id = i.winner_id "
        "WHERE i.status = 'accepted'" + sql + " ORDER BY i.state, i.name COLLATE NOCASE", args)
    out = []
    for r in rows:
        d = dict(r)
        d["stage"] = stage_of(r)
        out.append(d)
    return out


def nodal_heis():
    return json.loads((current_app.config["DATA_DIR"] / "nodal_heis.json").read_text(encoding="utf-8"))


def _empty():
    return {"participating": 0, "testing": 0, "signed_up": 0, "tested": 0, "selected": 0, "registered": 0, "verified": 0,
            "not_selected": 0, "not_registered": 0}


def board(scope=None):
    """
    The States/UTs (those of Annexure-I first, in its order, then any other with participating
    institutions), each with its allocation and its figures, and the total.
    """
    per = {}
    for r in institutions(scope):
        c = per.setdefault(r["state"], _empty())
        c["participating"] += 1
        c["testing"] += 1 if r["test_on"] else 0
        c["signed_up"] += r["signed_up"]
        c["tested"] += r["tested"]
        stage = r["stage"]
        c["selected"] += 1 if stage in ("selected", "registered", "verified") else 0
        c["registered"] += 1 if stage in ("registered", "verified") else 0
        c["verified"] += 1 if stage == "verified" else 0
        c["not_selected"] += 1 if stage in ("none", "testing") else 0
        c["not_registered"] += 1 if stage == "selected" else 0
    allocation = {h["state"]: h["allocation"] for h in nodal_heis()}
    order = [h["state"] for h in nodal_heis()] + sorted(s for s in per if s not in allocation)
    if scope is not None:
        order = [s for s in order if s in scope] + [s for s in scope if s not in order]
    states = []
    for s in order:
        if s not in per and scope is None and s not in allocation:
            continue
        states.append({"state": s, "allocation": allocation.get(s), **per.get(s, _empty())})
    total = _empty()
    for row in states:
        for k in total:
            total[k] += row[k]
    total["allocation"] = sum(row["allocation"] or 0 for row in states)
    return {"states": states, "total": total}


# ---- the reminders --------------------------------------------------------------------------------------

def schedule(settings=None):
    """The automatic reminders: [(kind, first day)], and the last day of registration."""
    get = (settings or {}).get if settings else get_setting
    return [(kind, _day(get(key))) for kind, key, _stages in KINDS], _day(get("reg.end"))


def due_kind(stage, today, settings=None):
    """The automatic reminder due today to an institution at this stage, with the earlier kinds it stands for; else (None, [])."""
    plan, reg_end = schedule(settings)
    if reg_end and today > reg_end:
        return None, []
    due = [kind for (kind, first), (_k, _key, stages) in zip(plan, KINDS) if first and today >= first and stage in stages]
    return (due[-1], due) if due else (None, [])


def _contact():
    return f"{current_app.config['BASE_URL']}/contact"


def _nodal_line(inst):
    hei = next((h for h in nodal_heis() if h["state"] == inst["state"]), None)
    return f"The Nodal Institution of {inst['state']}, {hei['name']}, coordinates the programme in your State/UT.\n\n" if hei else ""


def mails_for(inst, kind, reminder=True):
    """[(address, subject, body)] of one reminder to one institution."""
    base = current_app.config["BASE_URL"]
    camp_to, reg_end = _day(get_setting("camp.to")), _day(get_setting("reg.end"))
    head = "Reminder – " if reminder else ""
    sign_in = (f"Sign in to the institution's page with this e-mail address (a code is mailed to you, no password): "
               f"{base}/institution/login\n\n")
    footer = f"Questions: {_contact()}\n\nCentral Institute of Classical Tamil, Chennai"
    dear = f"Dear {inst['coord_name'] or 'Coordinator'},\n\n"
    if kind in ("start", "select"):
        if inst["test_on"]:
            state = (f"Your online assessment is open from {long_date(_day(inst['test_from']))} to {long_date(_day(inst['test_to']))}: {inst['signed_up']} "
                     f"student{'s' if inst['signed_up'] != 1 else ''} signed up, {inst['tested']} tested. No student is selected yet.")
        else:
            state = "The portal does not show an assessment or a selected student for your institution yet."
        subject = (f"{head}KTS 5.0: select your student by {long_date(camp_to)} – {inst['name']}" if kind == "select"
                   else f"{head}KTS 5.0: assess your students and select one by {long_date(camp_to)} – {inst['name']}")
        body = (dear + f"{inst['name']} ({inst['ref']}) is a participating institution of Kashi Tamil Sangamam 5.0 – Thirukkural "
                f"Payilvom. {state}\n\n"
                f"What remains to be done:\n"
                f"  1. Assess your interested students on the Thirukkural, on or before {long_date(camp_to)}: with the online "
                f"assessment of the portal (switch it on at the institution's page and give the students its link and access code), "
                f"or in any other suitable mode.\n"
                f"  2. Select one student on merit on the institution's page; the portal mails that student a personal registration link.\n"
                f"  3. The student registers on or before {long_date(reg_end)}, with the nomination form signed by the Head of the "
                f"Institution and the details of the Faculty Supervisor/Guide.\n\n"
                + sign_in + _nodal_line(inst) + footer)
        out = [(inst["coord_email"], subject, body)]
        if kind == "select" and inst["head_email"] and inst["head_email"] != inst["coord_email"]:
            out.append((inst["head_email"], subject, f"Dear {inst['head_name'] or 'Head of the Institution'},\n\n"
                        f"For your information: the reminder below has gone to the Institutional Coordinator of {inst['name']}, "
                        f"{inst['coord_name']}.\n\n" + "-" * 60 + "\n\n" + body))
        return out
    # the selected student has not registered
    link = f"{base}/register?token={inst['reg_token']}" if inst["reg_token"] else f"{base}/register"
    subject = f"{head}KTS 5.0: {inst['winner_name']} has not registered yet – register by {long_date(reg_end)}"
    out = [(inst["coord_email"], subject,
            dear + f"{inst['name']} selected {inst['winner_name']} for Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom, but the "
            f"registration of the student is not complete. The last date is {long_date(reg_end)}.\n\n"
            f"The student's personal registration link (the registration may be filled in by the student or by you):\n\n{link}\n\n"
            f"Keep ready: a photograph, an ID proof, the nomination form signed by the Head of the Institution, and the name, "
            f"designation, e-mail and mobile of the Faculty Supervisor/Guide.\n\n" + sign_in + _nodal_line(inst) + footer)]
    if inst["winner_email"]:
        out.append((inst["winner_email"], subject,
                    f"Dear {inst['winner_name']},\n\n{inst['name']} has selected you for Kashi Tamil Sangamam 5.0 – Thirukkural "
                    f"Payilvom, but your registration on the KTS 5.0 portal is not complete. Register on or before "
                    f"{long_date(reg_end)} with your personal link:\n\n{link}\n\nKeep ready: a photograph, an ID proof and the "
                    f"nomination form signed by the Head of the Institution (your Institutional Coordinator has it), and the name, "
                    f"designation, e-mail and mobile of your Faculty Supervisor/Guide.\n\n" + footer))
    return out


def _mark(conn, inst_id, kind, user_id=None):
    """True when this reminder was not recorded yet (and is now): so it goes once, whichever sender asks first."""
    cur = conn.execute("INSERT OR IGNORE INTO institution_reminders(institution_id, kind, sent_at, sent_by) VALUES(?,?,?,?)",
                       (inst_id, kind, utcnow(), user_id))
    return cur.rowcount == 1


def send_due(today, scope=None):
    """The automatic reminders due today; gives the number of institutions reminded."""
    conn = get_db()
    messages, count = [], 0
    for inst in institutions(scope):
        kind, kinds = due_kind(inst["stage"], today)
        if not kind:
            continue
        fresh = _mark(conn, inst["id"], kind)
        for earlier in kinds[:-1]:
            _mark(conn, inst["id"], earlier)
        if fresh:
            messages += mails_for(inst, kind)
            count += 1
    conn.commit()
    send_later(messages)
    return count


def behind(rows):
    """The institutions that have not registered their student yet, with the reminder that fits each."""
    return [r for r in rows if r["stage"] in ("none", "testing", "selected")]


def remind_now(rows, user, today=None):
    """A reminder by hand to the institutions that are behind, once a day to each; gives the number reminded."""
    today = today or now_ist().date()
    conn = get_db()
    messages, count = [], 0
    for inst in behind(rows):
        kind = "register" if inst["stage"] == "selected" else "select"
        if _mark(conn, inst["id"], f"manual:{today.isoformat()}", user["id"] if user else None):
            messages += mails_for(inst, kind)
            count += 1
    conn.commit()
    send_later(messages)
    return count


def daily(app, now=None):
    """
    The automatic reminders: in the morning, after nodal.digest_time IST, while remind.on is on and
    up to the last day of registration. The sender of the mail queue calls it at each round; the
    reminders themselves are recorded, so that each goes once. Gives the number of institutions reminded.
    """
    now = now or now_ist()
    with app.app_context():
        if get_setting("remind.on") != "1":
            return 0
        today = now.date()
        plan, reg_end = schedule()
        firsts = [first for _kind, first in plan if first]
        if not firsts or today < min(firsts) or (reg_end and today > reg_end):
            return 0
        at = (get_setting("nodal.digest_time") or "08:00").strip()
        try:
            hour, minute = (int(x) for x in at.split(":")[:2])
        except ValueError:
            hour, minute = 8, 0
        if (now.hour, now.minute) < (hour, minute):
            return 0
        # one look a day: only the sender that writes today's date here looks
        conn = get_db()
        cur = conn.execute("INSERT INTO settings(key, value, updated_at) VALUES('remind.sent_day', ?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at "
                           "WHERE settings.value != excluded.value", (today.isoformat(), utcnow()))
        conn.commit()
        if cur.rowcount != 1:
            return 0
        count = send_due(today)
        from .db import audit
        audit("institution_reminders", "institution", None, detail={"institutions": count, "day": today.isoformat()})
        return count


def sent_counts(scope=None):
    """How many institutions (of these States/UTs) each kind of reminder has gone to."""
    sql, args = _scope_sql(scope)
    out = {"start": 0, "select": 0, "register": 0, "manual": 0}
    for r in query("SELECT CASE WHEN r.kind LIKE 'manual:%' THEN 'manual' ELSE r.kind END AS k, COUNT(DISTINCT r.institution_id) AS n "
                   "FROM institution_reminders r JOIN institutions i ON i.id = r.institution_id WHERE 1=1" + sql + " GROUP BY k", args):
        out[r["k"]] = r["n"]
    return out

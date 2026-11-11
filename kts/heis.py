"""
The participating Higher Educational Institutions of the States/UTs (version 1.2.41).

As the revised D.O. letter of the Ministry sets out (26 October 2026): every interested institution registers; the Nodal
Institution of each State/UT scrutinises them and selects the number of Participating Institutions that Annexure-I prescribes
(cap_of), by the Standard Operating Procedure of Annexure-V (SOP: the marks of its evaluation committee, 1.2.111), and keeps a
reserve list (status 'reserve'); each selected institution nominates one student and one Faculty Supervisor/Guide, endorsed by
the Head of the Institution.

Annexure-I of the D.O. letter of 31 October 2026 (1.2.135) pairs five Union Territories with a State under one Nodal
Institution and one number: Gujarat and Dadra and Nagar Haveli and Daman and Diu; Kerala and Lakshadweep; Punjab and
Chandigarh; Tamil Nadu and Andaman and Nicobar Islands; Jammu and Kashmir and Ladakh ("covers" in data/nodal_heis.json). An
institution and a student keep their own State/UT; the Nodal Institution, the number and the reserve list, the scope of the
Nodal Officers and the figures State/UT by State/UT are those of the row of Annexure-I (row_of, nodal_state_of, group_of,
with_covered, label_of, unit_name).

* An institution applies on the website (/institutions/register) while hei.open is on and up to
  hei.end: its name, type, State/UT, district, AISHE code, its Head and a coordinator/Faculty
  Supervisor. The Head and the coordinator get a mail with the reference; so do the Nodal Officers
  of the State/UT.
* The Nodal Officer of the State/UT (or CICT) accepts or declines it in Console > Institutions;
  the Head and the coordinator hear the decision by mail.
* The accepted institutions are listed on the website, State/UT by State/UT (/institutions,
  hei.public), and a student who registers chooses one of them, or says that the institution is
  not listed (applications.institution_id stays empty: the Nodal Officer sees it). One student per
  institution: a second registration for the same institution is refused while the first is
  neither withdrawn nor rejected.
"""
import json
import re
import secrets
from datetime import date, timedelta

from flask import current_app

from .db import execute, get_setting, query, utcnow
from .utils import college_key, now_ist, send_later, send_mail

# identified: in the list of the Nodal Institution (Annexure-II), invited, not yet registered (1.2.43); accepted: a selected
# Participating Institution; reserve: in the reserve list of the Nodal Institution, to replace one that drops out (1.2.111)
STATUSES = ["identified", "pending", "accepted", "reserve", "declined"]

# Annexure-V of the D.O. letter of 31 October 2026 (1.2.155; six criteria of 25/20/20/15/10/10 in the letter of 26 October before),
# 3. Selection criteria: (key, criterion, maximum marks, scoring parameters, evidence, the marks the parameters give). Total 100;
# recommended qualifying benchmark 60. Criterion 5, institutional and disciplinary diversity (20), is marked as its two parts: A, the
# institution type (up to 10), and B, the disciplines (up to 10). In a tie (paragraph 4): higher marks in institutional readiness, then
# in academic engagement with the Thirukkural, then in geographical representation, then the earlier complete registration.
SOP = [("readiness", "1. Institutional readiness", 20,
        "All four requirements: (i) Nodal/Institutional Coordinator identified; (ii) adequate faculty support available; (iii) arrangements "
        "made for student assessment; (iv) readiness to undertake the one-month academic engagement. 20 marks: all four fulfilled; "
        "15: any three; 10: any two; 5: any one; 0: none.",
        "Institutional undertaking and implementation plan", (0, 5, 10, 15, 20)),
       ("outreach", "2. Proposed student outreach", 20,
        "20 marks: 200 or more students proposed for mobilisation; 15: 150–199 students; 10: 100–149; 5: 50–99; 0: fewer than 50.",
        "Number of students proposed and outreach plan", (0, 5, 10, 15, 20)),
       ("academic", "3. Academic engagement with the Thirukkural", 20,
        "All four components: (i) use of prescribed resources; (ii) faculty-guided study; (iii) preparation of an article/research note; "
        "(iv) presentation. 20 marks: all four covered; 15: any three; 10: any two; 5: any one; 0: none.",
        "Academic activity plan (preference for the study of the Thirukkural in any of the 22 scheduled Indian languages)", (0, 5, 10, 15, 20)),
       ("geography", "4. Geographical representation", 20,
        "20 marks: located in or substantially serves an Aspirational District or an otherwise under-represented district/region of "
        "the State/UT; 15: strengthens the representation of a district/region with limited representation among the institutions under "
        "consideration; 10: provides additional district/regional representation; 5: the district/region is already adequately represented.",
        "Institution location, district coverage and distribution of eligible applications", (5, 10, 15, 20)),
       ("diversity_type", "5A. Institutional diversity: institution type", 10,
        "10 marks: the selection adds an institution type not represented, or not adequately represented, in the proposed State/UT "
        "list; 5: the type is already adequately represented. Types: University; College; Standalone Institution; Institution of "
        "National Importance/other specialised HEI.",
        "Institution profile, AISHE details", (5, 10)),
       ("diversity_disc", "5B. Disciplinary diversity", 10,
        "10 marks: programmes offered in four broad disciplinary groups; 7: three; 5: two; 2: one. Groups: (i) Arts, Humanities, "
        "Languages and Social Sciences; (ii) Science and Mathematics; (iii) Engineering, Technology and Technical Education; "
        "(iv) Commerce, Management, Law, Education, Medical/Allied and other professional disciplines.",
        "Programme/course information", (2, 5, 7, 10))]
SOP_BENCHMARK = 60
# the reserve list: ordinarily up to 20 per cent of the prescribed allocation
RESERVE_SHARE = 20


def _recorded(row):
    try:
        marks = json.loads(row["sop_scores"] or "{}")
    except (ValueError, TypeError):
        return {}
    return marks if isinstance(marks, dict) else {}


def sop_legacy(row):
    """
    The marks recorded on the six criteria of the letter of 26 October 2026 (before 1.2.155), which no longer count: {criterion: marks},
    or {} for marks of the present criteria or none.
    """
    marks = _recorded(row)
    return marks if "record" in marks or ("diversity" in marks and "diversity_type" not in marks) else {}


def sop_marks(row):
    """{criterion: marks} of the institution, as the committee recorded them on the present criteria; {} when not yet."""
    marks = _recorded(row)
    if sop_legacy(row):
        return {}
    return {key: int(marks[key]) for key, *_ in SOP if isinstance(marks.get(key), int)}


def sop_order(row):
    """The order of Annexure-V, best first: the total, then the tie-breaks of its paragraph 4, then the earlier registration."""
    marks = sop_marks(row)
    return (-(row["sop_total"] if row["sop_total"] is not None else -1), -marks.get("readiness", 0), -marks.get("academic", 0),
            -marks.get("geography", 0), row["created_at"] or "")


def reserve_of(state):
    """The reserve list that Annexure-V suggests for the State/UT: ordinarily up to 20 per cent of its allocation (at least one); 0 without one."""
    n = allocation_of(state)
    return max(1, n * RESERVE_SHARE // 100) if n else 0
# what an institution writes, in English, as the student does
# Annexure-IV of the D.O. letter of 9 October 2026: the Institutional Coordinator and the Faculty Supervisor/Guide, each with
# name, designation, mobile and e-mail (1.2.46)
ENGLISH = ["name", "district", "head_name", "head_designation", "coord_name", "coord_designation", "guide_name", "guide_designation"]
REQUIRED = ["name", "itype", "state", "district", "head_name", "head_designation", "head_email", "head_phone",
            "coord_name", "coord_designation", "coord_email", "coord_mobile",
            "guide_name", "guide_designation", "guide_email", "guide_mobile"]
FIELDS = ["name", "itype", "state", "district", "aishe_code", "head_name", "head_designation", "head_email", "head_phone",
          "coord_name", "coord_designation", "coord_email", "coord_mobile",
          "guide_name", "guide_designation", "guide_email", "guide_mobile"]
EMAILS = ["head_email", "coord_email", "guide_email"]
MOBILES = ["coord_mobile", "guide_mobile"]


def ref_of(row_id):
    return f"KTS5-HEI-{row_id:05d}"


def phone_digits(value):
    """A phone number of India as 10 digits (a landline with its STD code), or '' when it is none."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] != "0" else ""


def selection_start(settings):
    """
    The first day of the selection by the Nodal Institutions (YYYY-MM-DD): the day after the last date of registration
    (hei.end) while that is not after hei.select_end; else the first day of the step of the schedule "hei_select"
    (data/timeline.json, as the Console keeps it), if it is before hei.select_end. Since 1.2.171 the registration (18
    November) runs past the selection (16-17 November). None without the two settings or such a day.
    """
    end, select_end = (settings.get("hei.end") or "")[:10], (settings.get("hei.select_end") or "")[:10]
    if not (end and select_end):
        return None
    after = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    if after <= select_end:
        return after
    seeds = json.loads((current_app.config["DATA_DIR"] / "timeline.json").read_text(encoding="utf-8"))
    title = next((e["title"] for e in seeds if e["key"] == "hei_select"), None)
    row = query("SELECT starts_at FROM events WHERE title = ? AND published = 1", (title,), one=True) if title else None
    first = (row["starts_at"] or "")[:10] if row else ""
    return first if first and first < select_end else None


def never_registered(row):
    """
    An institution that its Nodal Institution identified (the uploaded list, 1.2.43) and that has not completed its registration:
    it has no Head of the Institution, which the registration form asks for (1.2.173).
    """
    return bool(row["invited_by"]) and not (row["head_name"] or "").strip()


# the institutions selected, put on the reserve list or declined before they registered, in SQL (1.2.173)
UNREGISTERED_SQL = "status != 'identified' AND invited_by IS NOT NULL AND head_name = ''"


def busy_reason(row):
    """Why an institution cannot go back to invited: its selected student, its students, its online assessment (1.2.173); '' if none."""
    if row["application_id"] or row["winner_id"]:
        return "it has a selected student"
    if query("SELECT 1 FROM campus_students WHERE institution_id = ? LIMIT 1", (row["id"],), one=True):
        return "students have joined its assessment"
    if row["test_on"]:
        return "its online assessment is switched on"
    return ""


def back_to_invited(row):
    """
    The institution goes back to 'identified', invited again by mail with a new link, as when its Nodal Institution first invited
    it; the decision on it is cleared (1.2.173). Gives the row as it is now.
    """
    execute("UPDATE institutions SET status = 'identified', invite_token = ?, decision_note = '', decided_by = NULL, decided_at = NULL, "
            "updated_at = ? WHERE id = ?", (secrets.token_urlsafe(18), utcnow(), row["id"]))
    fresh = query("SELECT * FROM institutions WHERE id = ?", (row["id"],), one=True)
    mail_invited(fresh)
    return fresh


def window(settings):
    """'open', 'off' (hei.open is off) or 'ended' (after hei.end)."""
    if settings.get("hei.open") != "1":
        return "off"
    end = (settings.get("hei.end") or "").strip()
    if end and now_ist().date().isoformat() > end[:10]:
        return "ended"
    return "open"


def max_per_state():
    """The institutions accepted in one State/UT at most (hei.max_per_state), the same for every State/UT; 0: no limit."""
    try:
        return max(0, int(get_setting("hei.max_per_state") or 0))
    except ValueError:
        return 0


def cap_of(state):
    """
    The institutions that may be accepted in the State/UT at most: the number Annexure-I prescribes for it (the revised D.O.
    letter of 26 October 2026) while hei.cap_annexure is on, else hei.max_per_state; 0: no limit.
    """
    if get_setting("hei.cap_annexure") == "1" and allocation_of(state):
        return allocation_of(state)
    return max_per_state()


def nodal_heis():
    return json.loads((current_app.config["DATA_DIR"] / "nodal_heis.json").read_text(encoding="utf-8"))


def row_of(state):
    """The row of Annexure-I that covers the State/UT: its own, or the State it is paired with (1.2.135); None without one."""
    for h in nodal_heis():
        if state == h["state"] or state in h.get("covers", ()):
            return h
    return None


def nodal_state_of(state):
    """The State/UT of Annexure-I that this one belongs to: Lakshadweep gives Kerala; a State/UT of no row gives itself."""
    h = row_of(state)
    return h["state"] if h else state


def group_of(state):
    """The States/UTs of the row of Annexure-I that covers this one, the State first: Kerala or Lakshadweep gives both."""
    h = row_of(state)
    return [h["state"], *h.get("covers", [])] if h else [state]


def with_covered(states):
    """
    These States/UTs with the Union Territories that Annexure-I pairs with them, each after its State: ['Kerala'] gives
    ['Kerala', 'Lakshadweep'], ['Lakshadweep'] stays as it is (the scope of a Nodal Officer, a filter of the Console).
    """
    out = []
    for s in states:
        h = row_of(s)
        for x in [s] + (list(h.get("covers", [])) if h and h["state"] == s else []):
            if x not in out:
                out.append(x)
    return out


def label_of(state, lang=None):
    """The row of Annexure-I that covers the State/UT, as the letter names it, in the language of the reader: Kerala and Lakshadweep."""
    from .i18n import place, t
    names = [place(s, lang) for s in group_of(state)]
    label = names[0]
    for name in names[1:]:
        label = t("nodal.pair", lang).replace("{a}", label).replace("{b}", name)
    return label


def scope_label(states):
    """A Nodal Officer's States/UTs by the rows of Annexure-I: Kerala and Lakshadweep, Tamil Nadu and Andaman and Nicobar Islands."""
    return ", ".join(dict.fromkeys(label_of(s, "en") for s in states))


def unit_name(state):
    """The State/UT as a mail names it: itself, or, for a Union Territory paired in Annexure-I, the row (Kerala and Lakshadweep)."""
    return state if nodal_state_of(state) == state else label_of(state, "en")


def allocation_of(state):
    """The number of Participating Institutions to be selected in the State/UT (Annexure-I), or 0; a paired Union Territory shares its State's."""
    h = row_of(state)
    return int(h.get("allocation") or 0) if h else 0


def mail_invited(row):
    """The invitation to an institution identified by the Nodal Institution: it completes its registration with the link."""
    base = current_app.config["BASE_URL"]
    link = f"{base}/institutions/register?invite={row['invite_token']}"
    try:  # the last day of registration, from the settings (22 October 2026 until the launch moved it, 1.2.95)
        ends = date.fromisoformat(get_setting("reg.end"))
        by = f"{ends.day} {ends.strftime('%B %Y')}"
    except ValueError:
        by = "the date shown on the portal"
    for address in [a for a in dict.fromkeys([row["coord_email"], row["head_email"]]) if a]:
        send_mail(address, f"KTS 5.0: {row['name']} is invited to register",
                  f"Dear Sir/Madam,\n\nThe Nodal Institution of {unit_name(row['state'])} invites {row['name']} to register for "
                  f"Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom, the nationwide Students' Engagement "
                  f"Programme of the Ministry of Education (the Sangamam at Varanasi: {_by(get_setting('kts.start'))} – "
                  f"{_by(get_setting('kts.end'))}).\n\n"
                  f"Please complete the registration of the institution on the KTS 5.0 portal with this link:\n\n{link}\n\n"
                  f"It asks for the Head of the Institution and confirms the Institutional Coordinator. The Nodal Institution then "
                  f"selects the Participating Institutions from those registered, under the Standard Operating Procedure "
                  f"(Annexure-V of the D.O. letter of 31 October 2026) and within the number that Annexure-I prescribes; "
                  f"registration does not by itself confer selection. A selected institution assesses its students on the "
                  f"Thirukkural (the portal offers a ready online test) and nominates one student on merit on the portal by {by}. "
                  f"The steps and the dates are on the institution's page of the portal.\n\nReference: {row['ref']}\n\n"
                  f"Central Institute of Classical Tamil, Chennai")


def accepted_by_state(states):
    """The accepted institutions, State/UT by State/UT in the order of `states`: [(state, [rows])]."""
    rows = query("SELECT * FROM institutions WHERE status = 'accepted' ORDER BY name COLLATE NOCASE")
    by = {}
    for r in rows:
        by.setdefault(r["state"], []).append(r)
    return [(s, by[s]) for s in states if s in by]


def key_of(data):
    return college_key(data["name"], data["state"], data.get("aishe_code") or "")


def duplicate(data, exclude_id=None):
    """An application of the same institution that is pending or accepted."""
    return query("SELECT * FROM institutions WHERE inst_key = ? AND status IN ('identified', 'pending', 'accepted') AND id != ?",
                 (key_of(data), exclude_id or 0), one=True)


def _details(row):
    return (f"Institution: {row['name']}\nType: {row['itype']}\nState/UT: {row['state']}\nDistrict: {row['district']}\n"
            + (f"AISHE code: {row['aishe_code']}\n" if row["aishe_code"] else "")
            + f"Head of the Institution: {row['head_name']}, {row['head_designation']}\n"
            f"Institutional Coordinator: {row['coord_name']}" + (f", {row['coord_designation']}" if row["coord_designation"] else "")
            + f" ({row['coord_email']}, {row['coord_mobile']})\n"
            + (f"Faculty Supervisor/Guide: {row['guide_name']}, {row['guide_designation']} ({row['guide_email']}, {row['guide_mobile']})\n"
               if row["guide_name"] else ""))


def _by(day):
    """25 November 2026, as a mail says a last day; the day as it is when it cannot be read."""
    try:
        d = date.fromisoformat((day or "")[:10])
        return f"{d.day} {d.strftime('%B %Y')}"
    except ValueError:
        return day or "the date shown on the portal"


def _to_institution(row):
    return [a for a in dict.fromkeys([row["head_email"], row["coord_email"]]) if a]


def mail_received(row):
    base = current_app.config["BASE_URL"]
    for address in _to_institution(row):
        send_mail(address, f"KTS 5.0: application of {row['name']} received ({row['ref']})",
                  f"Dear Sir/Madam,\n\nThe application of your institution to take part in Kashi Tamil Sangamam 5.0 – "
                  f"Thirukkural Payilvom has been received.\n\nReference: {row['ref']}\n{_details(row)}\n"
                  f"The Nodal Institution of {unit_name(row['state'])} scrutinises the registered institutions and selects, by "
                  f"{_by(get_setting('hei.select_end'))}, the number of Participating Institutions that Annexure-I of the D.O. letter of "
                  f"31 October 2026 prescribes, under the Standard Operating Procedure (Annexure-V); registration does not by itself "
                  f"confer selection. You will receive another mail with the decision. A selected institution is listed at "
                  f"{base}/institutions; it assesses its interested students and nominates one student on merit from its own page "
                  f"on the portal ({base}/institution/login).\n\nCentral Institute of Classical Tamil, Chennai")
    officers = [u for u in query("SELECT * FROM users WHERE role = 'nodal' AND active = 1")
                if row["state"] in with_covered([s for s in (u["states"] or "").split("|") if s])]
    send_later([(u["email"], f"KTS 5.0: {row['name']} applies to participate ({row['state']})",
                 f"Dear {u['name']},\n\nAn institution of {row['state']} has applied to take part in KTS 5.0.\n\n"
                 f"Reference: {row['ref']}\n{_details(row)}\n"
                 f"Scrutinise it and record the marks of the Evaluation Committee on the criteria of Annexure-V in the console; the "
                 f"Participating Institutions are selected in the order of the marks, within the number of Annexure-I, by "
                 f"{_by(get_setting('hei.select_end'))}: {base}/console/institutions?status=pending\n\nCICT, Chennai")
                for u in officers])


def mail_decision(row):
    base = current_app.config["BASE_URL"]
    if row["status"] == "reserve":
        subject = f"KTS 5.0: {row['name']} is in the reserve list"
        body = (f"Dear Sir/Madam,\n\nThe Nodal Institution of {unit_name(row['state'])} has placed your institution in the reserve list of the "
                f"Participating Institutions of Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom, in accordance with the Standard "
                f"Operating Procedure. If a selected institution withdraws, does not respond or does not nominate its student, the "
                f"next institution of the reserve list may be included; you will then receive another mail.\n\nReference: {row['ref']}\n"
                f"\nFor any question, please write to the Nodal Officer of your State/UT or to CICT.\n\nCentral Institute of Classical Tamil, Chennai")
    elif row["status"] == "accepted":
        subject = f"KTS 5.0: {row['name']} is a Participating Institution"
        body = (f"Dear Sir/Madam,\n\nThe Nodal Institution of {unit_name(row['state'])} has selected your institution as a Participating "
                f"Institution of Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom.\n\nReference: {row['ref']}\n{_details(row)}\n"
                f"Please assess your interested students on the Thirukkural by {_by(get_setting('camp.to'))} (a short written test, "
                f"an oral interaction, a presentation, an essay, a quiz or a combination of these; fair, documented and approved by "
                f"the Head of the Institution or an authorised committee) and nominate one student on merit, with one Faculty "
                f"Supervisor/Guide, by {_by(get_setting('reg.end'))}.\n\n"
                f"How to nominate: sign in to the institution's page at {base}/institution/login with the e-mail address of the "
                f"Institutional Coordinator or of the Head of the Institution (a six-digit code is mailed; there is no password). "
                f"There you may switch on the portal's ready online test for your students; then select the student on merit and "
                f"submit the nomination there: the Institutional Coordinator fills in the student's form with a photograph, an ID "
                f"proof and the nomination form signed and sealed by the Head of the Institution "
                f"({base}/static/KTS5-nomination-form.pdf). The steps: "
                f"{base}/how-to-submit-the-student\n\n"
                f"The participating institutions are listed at {base}/institutions\n\nCentral Institute of Classical Tamil, Chennai")
    else:
        subject = f"KTS 5.0: application of {row['name']} ({row['ref']})"
        body = (f"Dear Sir/Madam,\n\nThe Nodal Institution of {unit_name(row['state'])} could not select your institution as a Participating "
                f"Institution of KTS 5.0. Registration does not by itself confer selection.\n\nReference: {row['ref']}\n"
                + (f"Remark: {row['decision_note']}\n" if row["decision_note"] else "")
                + "\nFor any question, please write to the Nodal Officer of your State/UT or to CICT.\n\n"
                "Central Institute of Classical Tamil, Chennai")
    for address in _to_institution(row):
        send_mail(address, subject, body)

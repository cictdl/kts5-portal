"""
The participating Higher Educational Institutions of the States/UTs (version 1.2.41).

As the D.O. letter of CICT sets out: the Nodal Institution of each State/UT identifies up to 50
institutions of its State/UT (hei.max_per_state) and coordinates their participation; each of them
nominates one student and one Faculty Supervisor/Guide, endorsed by the Head of the Institution.

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
import re

from flask import current_app

from .db import get_setting, query
from .utils import college_key, now_ist, send_later, send_mail

STATUSES = ["pending", "accepted", "declined"]
# what an institution writes, in English, as the student does
ENGLISH = ["name", "district", "head_name", "head_designation", "coord_name"]
REQUIRED = ["name", "itype", "state", "district", "head_name", "head_designation", "head_email", "head_phone",
            "coord_name", "coord_email", "coord_mobile"]
FIELDS = ["name", "itype", "state", "district", "aishe_code", "head_name", "head_designation", "head_email", "head_phone",
          "coord_name", "coord_email", "coord_mobile"]


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


def window(settings):
    """'open', 'off' (hei.open is off) or 'ended' (after hei.end)."""
    if settings.get("hei.open") != "1":
        return "off"
    end = (settings.get("hei.end") or "").strip()
    if end and now_ist().date().isoformat() > end[:10]:
        return "ended"
    return "open"


def max_per_state():
    try:
        return max(1, int(get_setting("hei.max_per_state") or 50))
    except ValueError:
        return 50


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
    return query("SELECT * FROM institutions WHERE inst_key = ? AND status IN ('pending', 'accepted') AND id != ?",
                 (key_of(data), exclude_id or 0), one=True)


def _details(row):
    return (f"Institution: {row['name']}\nType: {row['itype']}\nState/UT: {row['state']}\nDistrict: {row['district']}\n"
            + (f"AISHE code: {row['aishe_code']}\n" if row["aishe_code"] else "")
            + f"Head of the Institution: {row['head_name']}, {row['head_designation']}\n"
            f"Coordinator / Faculty Supervisor: {row['coord_name']} ({row['coord_email']}, {row['coord_mobile']})\n")


def _to_institution(row):
    return [a for a in dict.fromkeys([row["head_email"], row["coord_email"]]) if a]


def mail_received(row):
    base = current_app.config["BASE_URL"]
    for address in _to_institution(row):
        send_mail(address, f"KTS 5.0: application of {row['name']} received ({row['ref']})",
                  f"Dear Sir/Madam,\n\nThe application of your institution to take part in Kashi Tamil Sangamam 5.0 – "
                  f"Thirukkural Payilvom has been received.\n\nReference: {row['ref']}\n{_details(row)}\n"
                  f"The Nodal Officer of {row['state']} reviews it; you will receive another mail with the decision. "
                  f"Once accepted, the institution is listed at {base}/institutions and its nominated student can choose it "
                  f"when registering at {base}/register.\n\nCentral Institute of Classical Tamil, Chennai")
    officers = [u for u in query("SELECT * FROM users WHERE role = 'nodal' AND active = 1")
                if row["state"] in (u["states"] or "").split("|")]
    send_later([(u["email"], f"KTS 5.0: {row['name']} applies to participate ({row['state']})",
                 f"Dear {u['name']},\n\nAn institution of {row['state']} has applied to take part in KTS 5.0.\n\n"
                 f"Reference: {row['ref']}\n{_details(row)}\n"
                 f"Accept or decline it in the console: {base}/console/institutions?status=pending\n\nCICT, Chennai")
                for u in officers])


def mail_decision(row):
    base = current_app.config["BASE_URL"]
    if row["status"] == "accepted":
        subject = f"KTS 5.0: {row['name']} is a participating institution"
        body = (f"Dear Sir/Madam,\n\nThe Nodal Officer of {row['state']} has accepted your institution as a participating "
                f"institution of Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom.\n\nReference: {row['ref']}\n{_details(row)}\n"
                f"Please nominate one eligible student and one Faculty Supervisor/Guide. The nomination form, signed by the Head of "
                f"the Institution, is at {base}/static/KTS5-nomination-form.pdf. The student registers at {base}/register, "
                f"chooses \"{row['name']}\" as the institution and uploads the signed form.\n\n"
                f"The participating institutions are listed at {base}/institutions\n\nCentral Institute of Classical Tamil, Chennai")
    else:
        subject = f"KTS 5.0: application of {row['name']} ({row['ref']})"
        body = (f"Dear Sir/Madam,\n\nThe Nodal Officer of {row['state']} could not accept your institution as a participating "
                f"institution of KTS 5.0.\n\nReference: {row['ref']}\n"
                + (f"Remark: {row['decision_note']}\n" if row["decision_note"] else "")
                + "\nFor any question, please write to the Nodal Officer of your State/UT or to CICT.\n\n"
                "Central Institute of Classical Tamil, Chennai")
    for address in _to_institution(row):
        send_mail(address, subject, body)

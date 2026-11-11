"""
"Find your next step" (version 1.2.140): the hub of the home page that sorts the visitor by who they are - a student, a college
or university, a Nodal Officer - and shows each what to do now and by when, with the days left; and, for the students, "Is your
college taking part?", a search of the Participating Institutions that ends, when the college is not among them, in a message to
the Principal (WhatsApp, e-mail, copy) with the link to register the institution while registration is open.

Only the accepted institutions are searched, as /institutions lists them (hei.public); the search sees the name, the district,
the State/UT and the AISHE code, and shows the name, the district and the State/UT.
"""
import re
import unicodedata
from datetime import date
from urllib.parse import quote

from flask import current_app, url_for

from . import heis as HEI
from .db import query
from .i18n import place, text
from .utils import now_ist

# a word of a query that says nothing about which college (the query keeps its other words)
GENERIC = {"the", "of", "and", "for", "in", "at", "a", "college", "colleges", "university", "universities", "institute", "institution",
           "institutions", "mahavidyalaya", "vidyalaya"}
# short forms a student types, and the word of the names
SHORT = {"govt": "government", "gov": "government", "gvt": "government", "univ": "university", "coll": "college", "clg": "college",
         "inst": "institute", "engg": "engineering", "engg.": "engineering", "sci": "science", "tech": "technology", "mgmt": "management",
         "hr": "higher", "sec": "secondary", "autonomous": "autonomous", "arts": "arts"}
AISHE = re.compile(r"^[CUS]-?\d{3,6}$", re.I)
LIMIT = 8


def words(value):
    """The words of a name or a query: NFKC, small letters, letters and digits of any script, short forms written out."""
    value = unicodedata.normalize("NFKC", value or "").lower().replace("&", " and ")
    out = []
    for w in re.findall(r"\w+", value):
        out.append(SHORT.get(w, w))
    return out


def _accepted():
    return query("SELECT id, name, district, state, aishe_code FROM institutions WHERE status = 'accepted' ORDER BY name COLLATE NOCASE")


def search(q, lang):
    """
    {"total": matches, "results": [{"name", "district", "state", "url"}] (the best LIMIT), "searched": accepted institutions}:
    every word of the query that says something must begin a word of the name, the district or the State/UT; an AISHE code
    finds its institution.
    """
    rows = _accepted()
    q = (q or "").strip()[:120]
    found = []
    if AISHE.match(q):
        code = q.upper().replace(" ", "")
        code = code if "-" in code else code[0] + "-" + code[1:]
        found = [(10, r) for r in rows if (r["aishe_code"] or "").upper().replace(" ", "") == code]
    else:
        terms = [w for w in words(q) if w not in GENERIC and len(w) >= 2]
        if terms:
            for r in rows:
                hay = words(r["name"]) + words(r["district"]) + words(r["state"]) + words(HEI.label_of(r["state"], "en"))
                name = words(r["name"])
                score = 0
                for term in terms:
                    if term in hay:
                        score += 3
                    elif any(h.startswith(term) for h in hay):
                        score += 1
                    else:
                        score = -1
                        break
                if score > 0:
                    if name and name[0].startswith(terms[0]):
                        score += 1
                    found.append((score, r))
    found.sort(key=lambda sr: (-sr[0], sr[1]["name"].lower()))
    anchor = lambda s: "st-" + re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")  # noqa: E731  (as public.state_anchor)
    results = [{"name": r["name"], "district": r["district"] or "", "state": place(r["state"], lang),
                "url": url_for("public.institutions", _anchor=anchor(r["state"]))} for _s, r in found[:LIMIT]]
    return {"total": len(found), "results": results, "searched": len(rows)}


# ---- the days and the deadlines -------------------------------------------------------------------------------------------------

def _day(settings, key):
    try:
        return date.fromisoformat((settings.get(key) or "")[:10])
    except ValueError:
        return None


def long_day(d, lang):
    return f"{d.day} {text(f'month.{d.month}', lang)} {d.year}" if d else "…"


def days_chip(d, today, lang):
    """(css class, words) of the days left to a last day: 'n days left', '1 day left', 'Last day today', 'Closed'."""
    if not d:
        return None
    n = (d - today).days
    if n < 0:
        return ("shut", text("hub.closed", lang))
    if n == 0:
        return ("now", text("hub.today", lang))
    if n == 1:
        return ("soon", text("hub.day", lang))
    return ("soon" if n <= 3 else "ok", text("hub.days", lang).replace("{n}", str(n)))


def span(a, b, lang):
    """16–17 November 2026, or 28 November – 12 December 2026; one day alone (19 November 2026, 1.2.172) when they are the same."""
    if not a or not b or a == b:
        return long_day(a or b, lang)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{long_day(b, lang)}"
    return f"{a.day} {text(f'month.{a.month}', lang)} – {long_day(b, lang)}"


def hub(settings, lang):
    """What the hub of the home page shows today, in the language of the visitor."""
    today = now_ist().date()
    hei_end, select_end, camp_to = _day(settings, "hei.end"), _day(settings, "hei.select_end"), _day(settings, "camp.to")
    reg_end, verify_end = _day(settings, "reg.end"), _day(settings, "verify.end")
    select_start = None
    if hei_end and select_end:
        first = HEI.selection_start(settings)   # the day after the registration, or the schedule's (1.2.171)
        select_start = date.fromisoformat(first) if first else select_end
    window = HEI.window(settings)
    words_ = {"hei_end": long_day(hei_end, lang), "select": span(select_start, select_end, lang), "camp_to": long_day(camp_to, lang),
              "reg_end": long_day(reg_end, lang), "verify_end": long_day(verify_end, lang), "select_end": long_day(select_end, lang)}
    link = current_app.config["BASE_URL"].rstrip("/") + url_for("public.hei_register")
    message = text("hub.invite", lang).replace("{date}", words_["hei_end"]).replace("{link}", link)
    subject = text("hub.invite_subject", lang).replace("{date}", words_["hei_end"])
    nodal_selecting = bool(select_end) and today <= select_end
    return {
        "today": today, "words": words_, "open": window == "open", "public": settings.get("hei.public") == "1",
        "chips": {"student": days_chip(camp_to, today, lang),
                  "inst": days_chip(hei_end if window == "open" else reg_end, today, lang),
                  "nodal": days_chip(select_end if nodal_selecting else verify_end, today, lang)},
        "nodal_selecting": nodal_selecting,
        "invite": {"text": message, "wa": "https://wa.me/?text=" + quote(message, safe=""),
                   "mail": "mailto:?subject=" + quote(subject, safe="") + "&body=" + quote(message, safe="")},
        "searched": query("SELECT COUNT(*) AS n FROM institutions WHERE status = 'accepted'", one=True)["n"],
        # the institutions registered so far, as the dashboard counts them (not those only identified by a Nodal Institution)
        "registered": query("SELECT COUNT(*) AS n FROM institutions WHERE status != 'identified'", one=True)["n"],
    }

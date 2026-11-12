"""
The State/UT pages for the registration of institutions (version 1.2.142): one public page for each of the 31 rows of
Annexure-I, /join/<code> (the code of the row on the dashboard's grid: /join/od, /join/up, /join/kl), with the live number of
institutions registered against the number to be selected, the days left, the button to register (the State/UT filled in,
the registration marked as coming from the page), what to have ready, the Nodal Institution and its officers, and a message to
forward; an A4 poster with a QR code (/join/<code>/poster); and a board of the 31 rows, the emptiest first (/join). After the
registration of institutions closes, the same link pushes the assessment (by camp.to) and the nomination (by reg.end); after
reg.end it points to the dashboard. Counts only: never the name of an institution or anything of a student. Setting join.on.
"""
import time
from datetime import date, timedelta
from urllib.parse import quote

from flask import current_app, url_for

from . import heis as HEI
from .db import query
from .i18n import text
from .utils import now_ist

TTL = 60   # seconds the figures are kept
_CACHE = {"at": 0.0, "data": None}


def clear():
    _CACHE.update(at=0.0, data=None)


def _rows():
    from .progress import nodal_heis
    return nodal_heis()


def code_of(state):
    """The code of the row of Annexure-I that the State/UT belongs to: 'od' for Odisha, 'kl' for Lakshadweep; None for none."""
    from .dashboard import GRID
    row = HEI.nodal_state_of(state)
    return GRID[row][2].lower() if row in GRID else None


def resolve(code):
    """(the State/UT of the row, the code to redirect to or None); (None, None) for a code of no row."""
    from .dashboard import GRID
    code = (code or "").lower()
    for state, (_r, _c, short) in GRID.items():
        if short.lower() == code:
            row = HEI.row_of(state)
            if row is None:
                return None, None
            if row["state"] == state:
                return state, None
            return row["state"], code_of(state)
    return None, None


def _day(settings, key):
    try:
        return date.fromisoformat((settings.get(key) or "")[:10])
    except ValueError:
        return None


def phase(settings, today):
    """'recruit' while the institutions register, 'assess' until the last day of the nomination, 'over' after it."""
    if HEI.window(settings) == "open":
        return "recruit"
    reg_end = _day(settings, "reg.end")
    if reg_end and today <= reg_end:
        return "assess"
    return "over"


def table():
    """{the State/UT of each row: {state, code, n, reg, week, participating, testing, selected, covers}}, kept for TTL seconds."""
    now = time.monotonic()
    if _CACHE["data"] is not None and now - _CACHE["at"] <= TTL:
        return _CACHE["data"]
    from .dashboard import _ist_day
    from .progress import board
    today = now_ist().date()
    out = {}
    for h in _rows():
        out[h["state"]] = {"state": h["state"], "code": code_of(h["state"]), "n": int(h.get("allocation") or 0), "reg": 0, "week": 0,
                           "participating": 0, "testing": 0, "selected": 0, "covers": list(h.get("covers", []))}
    # registered as the dashboard counts them: every institution but those only identified by a Nodal Institution
    for r in query("SELECT state, created_at FROM institutions WHERE status != 'identified'"):
        row = out.get(HEI.nodal_state_of(r["state"]))
        if row is None:
            continue
        row["reg"] += 1
        d = _ist_day(r["created_at"])
        if d and d >= today - timedelta(days=6):
            row["week"] += 1
    for s in board()["states"]:
        if s["state"] in out:
            out[s["state"]].update(participating=s["participating"], testing=s["testing"], selected=s["selected"])
    # the institutions of the reserve list count with the Participating Institutions while it is public (1.2.178)
    for unit, n in HEI.reserve_by_row().items():
        if unit in out:
            out[unit]["participating"] += n
    _CACHE.update(at=now, data=out)
    return out


def share(row, lang, settings, ph):
    """The message to forward: {text, subject, wa, mail, link}."""
    from .finder import long_day
    link = current_app.config["BASE_URL"].rstrip("/") + "/join/" + row["code"] + (f"?lang={lang}" if lang != "en" else "")
    label = HEI.label_of(row["state"], lang)
    when = long_day(_day(settings, "hei.end"), lang)
    if ph == "assess":
        message = title(row, lang, settings, ph) + " " + link
        subject = title(row, lang, settings, ph)
    else:
        # without the number registered while it is hidden on the public pages (institutions.registered, 1.2.168)
        shown = settings.get("institutions.registered") == "1"
        message = (text("join.share_msg" if shown else "join.share_msg_plain", lang).replace("{n}", f"{row['n']:,}")
                   .replace("{state}", label).replace("{reg}", f"{row['reg']:,}").replace("{date}", when).replace("{link}", link))
        subject = text("join.share_subject", lang).replace("{state}", label).replace("{date}", when)
    return {"text": message, "subject": subject, "link": link, "wa": "https://wa.me/?text=" + quote(message, safe=""),
            "mail": "mailto:?subject=" + quote(subject, safe="") + "&body=" + quote(message, safe="")}


def title(row, lang, settings, ph):
    """The heading of the page: the number to be selected, or, while the institutions assess, the two last days."""
    from .finder import long_day
    if ph == "assess":
        return (text("hub.i_shut_t", lang).replace("{camp_to}", long_day(_day(settings, "camp.to"), lang))
                .replace("{reg_end}", long_day(_day(settings, "reg.end"), lang)))
    return text("join.title", lang).replace("{state}", HEI.label_of(row["state"], lang)).replace("{n}", f"{row['n']:,}")


def register_url(row):
    """The registration form with the State/UT filled in, marked as coming from the page; a row with a paired Union Territory
    gets no State/UT, so that a college of Lakshadweep or Chandigarh is not filed under Kerala or Punjab."""
    if row["covers"]:
        return url_for("public.hei_register", via="join")
    return url_for("public.hei_register", state=row["state"], via="join")

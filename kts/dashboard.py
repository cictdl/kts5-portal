"""
KTS 5.0 by State/UT (version 1.2.122): the live public dashboard. For each State/UT, the number of students it is to select
(Annexure-I of the D.O. letter), the institutions registered and selected as Participating Institutions, the students who
took an institution's online test, and the student delegates registered and verified. Counts only, never a name; the
students counted as At a glance on the home page counts them (every application not withdrawn), by the State/UT of the
institution. Console > Settings dashboard.public switches the page off.

Below the figures (1.2.124, the user's "the nodal officers details, participating institutions and students registered
details should come"), each State/UT in a block of its own: its Nodal HEI and Nodal Officers as /nodal-institutions shows
them (Console > Settings nodal.officers_public), its Participating Institutions as /institutions shows them (hei.public),
and under each its student delegate: the name, with the institution, once the Nodal Officer has verified the student, as
the students agreed on registering ("publication of my name and institution in the list of selected students"; the user
chose verified students only, 30 October 2026; dashboard.names); never another detail of a student.

The grid is no map: each State/UT is a square, placed roughly as on the map of India (a map would have to follow the
boundaries of the Survey of India exactly), shaded by its student delegates registered against its number.
"""
import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import current_app

from .db import get_setting, query
from .progress import VERIFIED, institutions, nodal_heis
from .utils import IST, now_ist

# (row, column, short name) of each State/UT in the grid
GRID = {
    "Jammu and Kashmir": (0, 2, "JK"), "Ladakh": (0, 3, "LA"),
    "Punjab": (1, 2, "PB"), "Himachal Pradesh": (1, 3, "HP"), "Uttarakhand": (1, 4, "UK"),
    "Chandigarh": (2, 1, "CH"), "Haryana": (2, 2, "HR"), "Delhi": (2, 3, "DL"), "Uttar Pradesh": (2, 4, "UP"),
    "Bihar": (2, 5, "BR"), "Sikkim": (2, 6, "SK"), "Arunachal Pradesh": (2, 8, "AR"),
    "Rajasthan": (3, 1, "RJ"), "Madhya Pradesh": (3, 2, "MP"), "Chhattisgarh": (3, 3, "CG"), "Jharkhand": (3, 4, "JH"),
    "West Bengal": (3, 5, "WB"), "Assam": (3, 7, "AS"), "Nagaland": (3, 8, "NL"),
    "Dadra and Nagar Haveli and Daman and Diu": (4, 0, "DH"), "Gujarat": (4, 1, "GJ"), "Maharashtra": (4, 2, "MH"),
    "Telangana": (4, 3, "TG"), "Odisha": (4, 4, "OD"), "Meghalaya": (4, 7, "ML"), "Manipur": (4, 8, "MN"),
    "Goa": (5, 1, "GA"), "Karnataka": (5, 2, "KA"), "Andhra Pradesh": (5, 3, "AP"), "Tripura": (5, 7, "TR"), "Mizoram": (5, 8, "MZ"),
    "Lakshadweep": (6, 0, "LD"), "Kerala": (6, 1, "KL"), "Tamil Nadu": (6, 2, "TN"), "Puducherry": (6, 3, "PY"),
    "Andaman and Nicobar Islands": (6, 5, "AN"),
}
# inst_res (1.2.175): the institutions on the reserve list of the Nodal Institution; inst_dec, inst_marked: the institutions
# selected or placed on the reserve list, and those of them whose marks of Annexure-V are recorded; their difference is the
# number of the Console's card "Selected without marks" (heis.UNMARKED_SQL)
FIELDS = ("inst_reg", "inst_sel", "assessed", "registered", "verified", "inst_res", "inst_dec", "inst_marked")


def shade(registered, to_select):
    """The class of a square: none (no number in Annexure-I), then 0 and up to 25, 50, 75 and over 75 per cent."""
    if not to_select:
        return "nb"
    share = registered / to_select
    if share <= 0:
        return "b0"
    return "b1" if share <= .25 else "b2" if share <= .5 else "b3" if share <= .75 else "b4"


def _by_state(sql, args=()):
    return {r["st"]: r["n"] for r in query(sql, args) if r["st"]}


def _fold(by, paired):
    """The counts by State/UT with those of a paired Union Territory added to its State's (1.2.135)."""
    out = {}
    for s, n in by.items():
        out[paired.get(s, s)] = out.get(paired.get(s, s), 0) + n
    return out


def figures():
    """{"states": [one dict per State/UT, those of Annexure-I first in its order], "total": dict}."""
    states_file = json.loads((current_app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
    allocation = {h["state"]: h["allocation"] for h in nodal_heis()}
    counts = {
        "inst_reg": _by_state("SELECT state AS st, COUNT(*) AS n FROM institutions WHERE status != 'identified' GROUP BY state"),
        "inst_sel": _by_state("SELECT state AS st, COUNT(*) AS n FROM institutions WHERE status = 'accepted' GROUP BY state"),
        "inst_res": _by_state("SELECT state AS st, COUNT(*) AS n FROM institutions WHERE status = 'reserve' GROUP BY state"),
        "inst_dec": _by_state("SELECT state AS st, COUNT(*) AS n FROM institutions WHERE status IN ('accepted', 'reserve') GROUP BY state"),
        "inst_marked": _by_state("SELECT state AS st, COUNT(*) AS n FROM institutions WHERE status IN ('accepted', 'reserve') "
                                 "AND sop_total IS NOT NULL GROUP BY state"),
        "assessed": _by_state("SELECT i.state AS st, COUNT(*) AS n FROM campus_attempts t JOIN campus_students s ON s.id = t.student_id "
                              "JOIN institutions i ON i.id = s.institution_id WHERE t.status IN ('submitted', 'expired') GROUP BY i.state"),
        "registered": _by_state("SELECT COALESCE(NULLIF(college_state, ''), state) AS st, COUNT(*) AS n FROM applications "
                                "WHERE status != 'withdrawn' GROUP BY st"),
        "verified": _by_state("SELECT COALESCE(NULLIF(college_state, ''), state) AS st, COUNT(*) AS n FROM applications "
                              "WHERE status IN (%s) GROUP BY st" % ",".join("?" * len(VERIFIED)), VERIFIED),
    }
    # by the row of Annexure-I (1.2.135): a Union Territory paired with a State counts with it; its square points to the State's
    paired = {c: h["state"] for h in nodal_heis() for c in h.get("covers", [])}
    for name, by in counts.items():
        counts[name] = _fold(by, paired)
    order = [h["state"] for h in nodal_heis()]
    order += [s for s in states_file["states"] + states_file["union_territories"] if s not in order and s not in paired]
    # a name the lists do not have (written by hand in an earlier version): a row of its own, no square
    order += sorted({s for c in counts.values() for s in c} - set(order))
    states = []
    for s in order:
        row = {"state": s, "to_select": allocation.get(s), **{f: counts[f].get(s, 0) for f in FIELDS}}
        row["grid"] = GRID.get(s)
        row["shade"] = shade(row["registered"], row["to_select"])
        # the institutions registered against the number, for the squares while the students' registration is hidden (1.2.147)
        row["inst_shade"] = shade(row["inst_reg"], row["to_select"])
        # the Participating Institutions selected against the number, while the institutions registered are hidden too (1.2.168)
        row["sel_shade"] = shade(row["inst_sel"], row["to_select"])
        row["share"] = min(100, round(100 * row["registered"] / row["to_select"])) if row["to_select"] else None
        states.append(row)
    total = {f: sum(r[f] for r in states) for f in FIELDS}
    total["to_select"] = sum(r["to_select"] or 0 for r in states)
    covered = [{"state": c, "with": s, "grid": GRID[c], "code": GRID[s][2]} for c, s in paired.items() if c in GRID and s in GRID]
    return {"states": states, "covered": covered, "total": total}


def details(officers):
    """
    {State/UT: {"nodal": name of the Nodal HEI, "officers": [...], "institutions": [...]}} for the blocks of the page; each
    institution {"name", "district", "status", "delegate", "place"}, status one of delegate (verified, the name shown), verified
    (verified, names switched off), awaiting (registered, not yet verified), none; place: its Union Territory when Annexure-I
    pairs that with the State of the block (1.2.135). `officers` as the public pages have them.
    """
    names = get_setting("dashboard.names") == "1"
    found = defaultdict(lambda: {"nodal": "", "officers": [], "institutions": []})
    paired = {c: h["state"] for h in nodal_heis() for c in h.get("covers", [])}
    for h in nodal_heis():
        found[h["state"]]["nodal"] = h["name"]
    for state, people in officers.items():
        block = found[paired.get(state, state)]
        block["officers"] += [p for p in people if p not in block["officers"]]
    if get_setting("hei.public") == "1":
        for i in institutions():
            if i["stage"] == "verified":
                status = "delegate" if names else "verified"
            else:
                status = "awaiting" if i["stage"] == "registered" else "none"
            found[paired.get(i["state"], i["state"])]["institutions"].append({
                "name": i["name"], "district": i["district"], "status": status,
                "delegate": i["app_name"] if status == "delegate" else None, "place": i["state"] if i["state"] in paired else None})
    return dict(found)


# ---- the progress of the institutions (1.2.138) -----------------------------------------------------------------------------------

_PIPE = {"at": 0.0, "data": None}
PIPE_TTL = 30   # seconds: the page asks every minute, many visitors may


def _ist_day(value):
    """The day in IST of a UTC time of the database; None when it cannot be read."""
    try:
        return datetime.fromisoformat(value).astimezone(IST).date()
    except (TypeError, ValueError):
        return None


def _spark(values, width=300, height=64):
    """The points of a sparkline and of the area under it, for an SVG of width x height, the last day at the right."""
    top = max(values) or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = round(i * width / (n - 1), 1) if n > 1 else width
        y = round(height - 4 - (height - 10) * v / top, 1)
        pts.append(f"{x},{y}")
    line = " ".join(pts)
    area = f"0,{height} " + line + f" {width},{height}"
    return {"points": line, "area": area, "max": top}


def pipeline(lang=None):
    """
    The progress of the institutions for the public page /progress and its JSON (1.2.138), counts only: the stages from
    registration to verification, four rings against the 1,000 of Annexure-I, the last three weeks day by day, the rows of
    Annexure-I by their share, the milestones of the programme with today's place among them. Kept for PIPE_TTL seconds.
    """
    now = time.monotonic()
    if _PIPE["data"] is None or now - _PIPE["at"] > PIPE_TTL:
        _PIPE.update(at=now, data=_pipeline())
    return _PIPE["data"]


def _one(sql, args=()):
    return query(sql, args, one=True)["n"]


def _pipeline():
    from .i18n import CATALOG
    from .progress import board
    today = now_ist().date()
    tot = board()["total"]
    counts = {
        "annexure": tot["allocation"],
        "registered": _one("SELECT COUNT(*) AS n FROM institutions WHERE status != 'identified'"),
        "pending": _one("SELECT COUNT(*) AS n FROM institutions WHERE status = 'pending'"),
        "reserve": _one("SELECT COUNT(*) AS n FROM institutions WHERE status = 'reserve'"),
        "participating": tot["participating"], "testing": tot["testing"], "signed_up": tot["signed_up"], "tested": tot["tested"],
        "selected": tot["selected"], "app_registered": tot["registered"], "verified": tot["verified"],
        "not_selected": tot["not_selected"], "not_registered": tot["not_registered"],
        "delegates": _one("SELECT COUNT(*) AS n FROM applications WHERE status != 'withdrawn'"),
        "delegates_verified": _one("SELECT COUNT(*) AS n FROM applications WHERE status IN (%s)" % ",".join("?" * len(VERIFIED)), VERIFIED),
    }

    def pct(n, total):
        return min(100, round(100 * n / total)) if total else 0

    # the rings: (key, number, total)
    rings = [("participating", counts["participating"], counts["annexure"]), ("delegates", counts["delegates"], counts["annexure"]),
             ("verified", counts["delegates_verified"], counts["delegates"]), ("testing", counts["testing"], counts["participating"])]
    rings = [{"key": k, "n": n, "total": t, "pct": pct(n, t), "share": round(min(1, n / t), 4) if t else 0} for k, n, t in rings]
    # the stages, each against the first (the width of its bar) and the one before (the percentage)
    order = [("registered", counts["registered"]), ("participating", counts["participating"]), ("testing", counts["testing"]),
             ("selected", counts["selected"]), ("app_registered", counts["app_registered"]), ("verified", counts["verified"])]
    first = order[0][1] or 1
    stages = []
    for i, (k, n) in enumerate(order):
        prev = order[i - 1][1] if i else n
        stages.append({"key": k, "n": n, "width": round(100 * n / first, 1) if first else 0, "pct": pct(n, prev) if i else 100})
    # the last three weeks, day by day, in IST
    days = [today - timedelta(days=20 - i) for i in range(21)]
    by_day = {"inst": {d: 0 for d in days}, "app": {d: 0 for d in days}}
    for r in query("SELECT created_at FROM institutions WHERE status != 'identified'"):
        d = _ist_day(r["created_at"])
        if d in by_day["inst"]:
            by_day["inst"][d] += 1
    for r in query("SELECT created_at FROM applications WHERE status != 'withdrawn'"):
        d = _ist_day(r["created_at"])
        if d in by_day["app"]:
            by_day["app"][d] += 1
    series = {}
    for key, per in by_day.items():
        values = [per[d] for d in days]
        series[key] = dict(_spark(values), values=values, today=values[-1], week=sum(values[-7:]))
    # the rows of Annexure-I by the share of their Participating Institutions, the ten furthest ahead
    rows = [r for r in figures()["states"] if r["to_select"]]
    rows.sort(key=lambda r: (-r["inst_sel"] / r["to_select"], -r["registered"], r["state"]))
    states = [{"state": r["state"], "to_select": r["to_select"], "inst_sel": r["inst_sel"], "registered": r["registered"], "verified": r["verified"],
               "share": pct(r["inst_sel"], r["to_select"])} for r in rows[:10]]
    counts["states_active"] = sum(1 for r in figures()["states"] if r["inst_reg"])
    # the milestones: the days of the programme (data/timeline.json) and of the Sangamam (the settings), with today among them
    marks = []
    for row in json.loads((current_app.config["DATA_DIR"] / "timeline.json").read_text(encoding="utf-8")):
        if row["key"] in ("hei_reg", "hei_select", "assess", "selection", "live", "internship", "papers"):
            marks.append((row["key"], row["starts"], row.get("ends"), row["title"]))
    for key, setting, i18n_key in (("reg_close", "reg.end", "timeline.reg_close"),   # the nomination, 20 November (1.2.155)
                                   ("inauguration", "kts.start", "timeline.inauguration"), ("valedictory", "kts.end", "timeline.valedictory")):
        day = (get_setting(setting) or "")[:10]
        if day:
            marks.append((key, day, None, i18n_key))
    milestones = []
    for key, starts, ends, title in sorted(marks, key=lambda m: m[1]):
        a, b = date.fromisoformat(starts), date.fromisoformat(ends) if ends else None
        last = b or a
        status = "done" if last < today else "current" if a <= today <= last else "upcoming"
        title_key = f"timeline.{key}" if f"timeline.{key}" in CATALOG["en"] else (title if title.startswith("timeline.") and title in CATALOG["en"] else None)
        milestones.append({"key": key, "starts": starts, "ends": ends, "status": status, "days": (a - today).days,
                           "title_key": title_key, "title": title if not title.startswith("timeline.") else CATALOG["en"][title]})
    nxt = next((m for m in milestones if m["status"] == "upcoming"), None)
    if nxt:
        nxt["status"] = "next"
    return {"counts": counts, "rings": rings, "stages": stages, "series": series, "days": [d.isoformat() for d in days], "states": states,
            "milestones": milestones, "today": today.isoformat(), "as_of": now_ist().strftime("%H:%M")}


def pipeline_view(show_registered=True):
    """
    The pipeline as the public page shows it. While the number of institutions registered is hidden (institutions.registered,
    1.2.168) it is without the stage of the registrations, their day-by-day line and the counts that would give the number away;
    the bar of each remaining stage is then measured against the first of them, the Participating Institutions selected.
    """
    p = pipeline()
    if show_registered:
        return p
    stages = [dict(s) for s in p["stages"] if s["key"] != "registered"]
    first = stages[0]["n"] or 1
    for i, s in enumerate(stages):
        s["width"] = min(100.0, round(100 * s["n"] / first, 1))
        if i == 0:
            s["pct"] = 100
    counts = {k: v for k, v in p["counts"].items() if k not in ("registered", "pending", "reserve")}
    return dict(p, stages=stages, counts=counts, series={k: v for k, v in p["series"].items() if k != "inst"})


def pipeline_json(t, show_registered=True):
    """The figures of the page as its script expects them (portal.js): the texts in the language of the visitor, `t` being i18n.t."""
    p = pipeline_view(show_registered)
    c = p["counts"]
    flat = {k: v for k, v in c.items()}
    flat.update({f"st_{s['key']}": s["n"] for s in p["stages"]})
    flat.update({f"st_{s['key']}_pct": f"{s['pct']}%" for s in p["stages"][1:]})
    for r in p["rings"]:
        flat[r["key"]] = r["n"]
        flat[f"{r['key']}_pct"] = f"{r['pct']}%"
        flat[f"{r['key']}_of"] = t("dash.of").replace("{n}", f"{r['n']:,}").replace("{total}", f"{r['total']:,}")
    flat["behind"] = t("pg.behind").replace("{n}", str(c["not_selected"]))
    flat["unregistered"] = t("pg.unregistered").replace("{n}", str(c["not_registered"]))
    for key, s in p["series"].items():
        flat[f"{key}_today"] = t("pg.today").replace("{n}", str(s["today"]))
        flat[f"{key}_week"] = t("pg.week").replace("{n}", str(s["week"]))
    flat["as_of_text"] = t("dash.updated").replace("{time}", p["as_of"])
    return {"flat": flat, "shares": {r["key"]: r["share"] for r in p["rings"]}, "widths": {f"st_{s['key']}": s["width"] for s in p["stages"]},
            "series": {k: {"points": s["points"], "area": s["area"]} for k, s in p["series"].items()}, "as_of": p["as_of"]}

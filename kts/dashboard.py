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
from collections import defaultdict

from flask import current_app

from .db import get_setting, query
from .progress import VERIFIED, institutions, nodal_heis

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
FIELDS = ("inst_reg", "inst_sel", "assessed", "registered", "verified")


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

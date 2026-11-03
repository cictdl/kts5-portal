"""
The progress of the institutions (version 1.2.138): the public page /progress - four rings against the 1,000 of Annexure-I,
the stages from registration to verification, the last three weeks day by day, the rows of Annexure-I furthest ahead, the
milestones with today among them - and /progress.json, from which the page refreshes its figures every minute; counts only,
never a name; Console > Settings dashboard.public switches both off with the dashboard.

    python -m pytest tests -q
"""
import json
import re

from markupsafe import escape

from conftest import ROOT, add_candidates, make_app
from test_progress import _inst, _student


def _portal():
    """Tamil Nadu: Presidency College (assessing online, its student selected, registered and verified), Loyola College (its
    student registered, not yet verified), Madras Christian College (nothing yet); Kerala: one awaiting the decision; a
    third application withdrawn."""
    from kts.db import execute, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():   # the students' registration shown (hidden by default since 1.2.147)
        from kts.db import set_setting as _set
        _set("reg.public", "1")
    tn = _inst(app, "Presidency College", state="Tamil Nadu", test_on=1)
    sid = _student(app, tn, "Student One", tested=True)
    _student(app, tn, "Student Two", tested=True)
    loyola = _inst(app, "Loyola College", state="Tamil Nadu")
    _inst(app, "Madras Christian College", state="Tamil Nadu")
    _inst(app, "Kerala Waiting College", state="Kerala", status="pending")
    students = add_candidates(app, 3)
    with app.app_context():
        execute("UPDATE applications SET college_state = 'Tamil Nadu'")
        ids = {r["app_no"]: r["id"] for r in query("SELECT id, app_no FROM applications")}
        execute("UPDATE applications SET status = 'verified' WHERE app_no = ?", (students[0]["app_no"],))
        execute("UPDATE applications SET status = 'withdrawn' WHERE app_no = ?", (students[2]["app_no"],))
        execute("UPDATE institutions SET application_id = ?, winner_id = ? WHERE id = ?", (ids[students[0]["app_no"]], sid, tn))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (ids[students[1]["app_no"]], loyola))
    return app


def test_the_figures():
    from kts import dashboard as D
    app = _portal()
    with app.app_context():
        D._PIPE["data"] = None
        p = D.pipeline()
        assert D.pipeline() is p   # kept for half a minute
    c = p["counts"]
    assert (c["annexure"], c["registered"], c["pending"], c["participating"], c["testing"]) == (1000, 4, 1, 3, 1)
    assert (c["selected"], c["app_registered"], c["verified"], c["not_selected"], c["not_registered"]) == (2, 2, 1, 1, 0)
    assert (c["delegates"], c["delegates_verified"], c["states_active"]) == (2, 1, 2)
    rings = {r["key"]: r for r in p["rings"]}
    assert rings["participating"] == {"key": "participating", "n": 3, "total": 1000, "pct": 0, "share": 0.003}
    assert (rings["delegates"]["n"], rings["delegates"]["total"]) == (2, 1000) and (rings["verified"]["pct"], rings["testing"]["pct"]) == (50, 33)
    assert [(s["key"], s["n"], s["width"], s["pct"]) for s in p["stages"]] == [
        ("registered", 4, 100.0, 100), ("participating", 3, 75.0, 75), ("testing", 1, 25.0, 33), ("selected", 2, 50.0, 100),
        ("app_registered", 2, 50.0, 100), ("verified", 1, 25.0, 50)]
    # the last three weeks: everything of the test was made today
    assert len(p["days"]) == 21 and p["days"][-1] == p["today"]
    assert (p["series"]["inst"]["today"], p["series"]["inst"]["week"], p["series"]["app"]["today"]) == (4, 4, 2)
    assert p["series"]["inst"]["values"][-1] == 4 and sum(p["series"]["inst"]["values"][:-1]) == 0
    assert re.fullmatch(r"(\d+(\.\d)?,\d+(\.\d)? ?){21}", p["series"]["inst"]["points"]) and p["series"]["inst"]["area"].startswith("0,64 ")
    # the rows of Annexure-I furthest ahead: Tamil Nadu first (3 of 50), ten rows, the paired Union Territories within their row
    assert len(p["states"]) == 10 and p["states"][0]["state"] == "Tamil Nadu" and p["states"][0]["share"] == 6
    assert all(s["to_select"] for s in p["states"]) and "Lakshadweep" not in {s["state"] for s in p["states"]}
    # the milestones, in order, with at most one 'next'
    keys = [m["key"] for m in p["milestones"]]
    assert keys == ["hei_reg", "hei_select", "assess", "selection", "inauguration", "valedictory", "live", "internship", "papers"]
    assert [m["starts"] for m in p["milestones"]] == sorted(m["starts"] for m in p["milestones"])
    statuses = [m["status"] for m in p["milestones"]]
    assert statuses.count("next") <= 1 and set(statuses) <= {"done", "current", "next", "upcoming"}
    assert all(m["title_key"] or m["title"] for m in p["milestones"])


def test_the_page():
    from kts import dashboard as D
    app = _portal()
    with app.app_context():
        D._PIPE["data"] = None
    client = app.test_client()
    page = client.get("/progress?lang=en").get_data(as_text=True)
    assert "<h1>The progress of the institutions</h1>" in page and 'data-progress="/progress.json"' in page
    assert "Live figures, as on " in page and "The figures refresh every minute." in page
    # the rings: the figure written, the share for the arc
    assert page.count('class="card prog-ring') == 4 and '<circle class="arc" cx="60" cy="60" r="52" data-ring="participating" style="--share:0.003"/>' in page
    assert '<div class="num" data-count="3" data-k="participating">3</div>' in page and 'data-k="verified_pct">50%</text>' in page
    assert "Participating Institutions selected" in page and "Institutions assessing their students online" in page
    # the stages
    flow = page[page.index('class="card prog-flow"'):page.index('class="card prog-momentum"')]
    assert "From registration to verification" in flow and flow.count("<li class=\"stage stage-") == 6
    assert '<span class="st-n" data-count="4" data-k="st_registered">4</span>' in flow and 'style="--w:75.0%" data-bar="st_participating"' in flow
    assert "1 Participating Institutions yet to select their student" in flow and "0 selected students yet to register" in flow
    # the sparklines, the race, the milestones
    assert page.count('<polyline class="line"') == 2 and 'data-k="inst_today">Today: 4</bdi>' in page
    assert "Tamil Nadu and Andaman and Nicobar Islands" in page and "<bdi dir=\"ltr\">3/50</bdi>" in page
    track = page[page.index('class="prog-track"'):]
    assert track.count("<li class=\"ms-") == 9 and ("In " in track or "Now" in track or "Done" in track)
    assert 'href="/dashboard">KTS 5.0 by State/UT →</a>' in page
    # never a name
    for word in ("Presidency", "Loyola", "Student One", "Campus Student", "campus1@"):
        assert word not in page, word


def test_the_json_for_the_script():
    from kts import dashboard as D
    app = _portal()
    with app.app_context():
        D._PIPE["data"] = None
    client = app.test_client()
    r = client.get("/progress.json?lang=en")
    assert r.status_code == 200 and r.mimetype == "application/json" and r.headers["Cache-Control"] == "no-store"
    d = json.loads(r.get_data(as_text=True))
    assert set(d) == {"flat", "shares", "widths", "series", "as_of"}
    assert d["flat"]["participating"] == 3 and d["flat"]["st_verified"] == 1 and d["flat"]["st_verified_pct"] == "50%"
    assert d["flat"]["participating_of"] == "3 of 1,000" and d["flat"]["behind"] == "1 Participating Institutions yet to select their student"
    assert d["flat"]["inst_today"] == "Today: 4" and d["flat"]["as_of_text"].startswith("Live figures, as on ")
    assert d["shares"] == {"participating": 0.003, "delegates": 0.002, "verified": 0.5, "testing": 0.3333}
    assert d["widths"]["st_participating"] == 75.0 and set(d["series"]) == {"inst", "app"} and "points" in d["series"]["app"]
    assert "Presidency" not in r.get_data(as_text=True)
    # in Tamil, the texts of the visitor's language
    from kts.i18n import CATALOG
    d = json.loads(client.get("/progress.json?lang=ta").get_data(as_text=True))
    assert d["flat"]["inst_today"] == CATALOG["ta"]["pg.today"].replace("{n}", "4")


def test_the_switch_the_links_and_every_language():
    from kts.db import set_setting
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    assert '<a class="btn saffron dash-cta" href="/dashboard"' in home
    assert '<a class="btn dash-cta prog-cta" href="/progress"' in home and "📈</span> The institutions&#39; progress</a>" in home
    assert '<a class="btn sm secondary" href="/progress">📈 The institutions&#39; progress</a>' in client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "/progress</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    for code, catalogue in CATALOG.items():
        page = client.get(f"/progress?lang={code}").get_data(as_text=True)
        assert f"<h1>{escape(catalogue['pg.title'])}</h1>" in page, code
        assert str(escape(catalogue["pg.flow_title"])) in page and str(escape(catalogue["pg.miles_title"])) in page, code
    with app.app_context():
        set_setting("dashboard.public", "0")
    assert client.get("/progress").status_code == 404 and client.get("/progress.json").status_code == 404
    home = client.get("/?lang=en").get_data(as_text=True)
    assert 'href="/progress"' not in home and 'href="/dashboard"' not in home


def test_the_style_and_the_script():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert ".prog.prog-in .prog-ring .arc { stroke-dashoffset: calc(326.7 * (1 - var(--share, 0))); }" in css
    assert "@media (prefers-reduced-motion: reduce)" in css and ".prog .prog-live i { animation: none; }" in css
    assert 'document.querySelector("[data-progress]")' in js and "setInterval(refresh, 60000)" in js and "document.hidden" in js

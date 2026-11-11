"""
Institutions selected before they registered go back to "identified · invited" (1.2.173; the Nodal Institution of Maharashtra,
11 November 2026: "I request that these institutions be reverted to 'identified/invited' status and that individual selection be
enabled"). An institution that a Nodal Institution identified (its uploaded list) is selected only once it has registered with
its invitation; one selected, put on the reserve list or declined before that goes back, one by one or all of a State/UT at once,
each invited again by mail with a new link; one with an online assessment, students or a selected student stays as it is.

    python -m pytest tests/test_back_to_invited_1111.py -q
"""
import io

import pytest

from conftest import make_app
from test_institutions import _apply
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff


@pytest.fixture(autouse=True)
def empty_limiter():
    """The registrations here count against the limit of an address per hour; the other tests' count stays as it was."""
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _app():
    app = make_app(ADMIN_PASSWORD=None)
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.end", "2099-12-31")
    return app


def _invite(app, officer, state, names):
    """The Nodal Officer uploads a list: each institution identified and invited by mail."""
    from kts.db import query
    lines = ["Name of Institution,Official Email ID,District/City"]
    lines += [f"{name},{name.split()[0].lower()}@{state[:4].lower()}.example,Pune" for name in names]
    officer.post("/console/institutions/identified", data={"_csrf": _token(officer), "state": state,
                 "file": (io.BytesIO("\n".join(lines).encode("utf-8")), "list.csv")}, content_type="multipart/form-data")
    with app.app_context():
        return {r["name"]: r for r in query("SELECT * FROM institutions WHERE state = ?", (state,))}


def _as_on_10_november(app, iid, status="accepted"):
    """Selected straight from the list, as the Console allowed up to 1.2.172: the invitation used up, never registered."""
    from kts.db import execute
    with app.app_context():
        execute("UPDATE institutions SET status = ?, invite_token = NULL, decided_by = 1, decided_at = '2026-11-10T06:00:00Z' "
                "WHERE id = ?", (status, iid))


def _row(app, iid):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)


def _mails(app, to):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM outbox WHERE to_addr = ? ORDER BY id", (to,))


def test_an_identified_institution_is_selected_once_it_has_registered():
    app = _app()
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    rows = _invite(app, officer, "Maharashtra", ["Alpha College Pune"])
    alpha = rows["Alpha College Pune"]
    page = officer.get("/console/institutions?state=Maharashtra").get_data(as_text=True)
    assert "identified · invited" in page and 'value="accept"' not in page and 'value="invite"' in page
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": alpha["id"], "action": "accept"}, follow_redirects=True)
    assert "has not completed its registration yet" in r.get_data(as_text=True)
    row = _row(app, alpha["id"])
    assert row["status"] == "identified" and row["invite_token"] == alpha["invite_token"]
    assert officer.post("/console/institutions", data={"_csrf": _token(officer), "id": alpha["id"], "action": "reserve"}).status_code == 302
    assert _row(app, alpha["id"])["status"] == "identified"
    # registered with its invitation, it is selected on its own
    client = app.test_client()
    client.get(f"/institutions/register?invite={alpha['invite_token']}")
    with client.session_transaction() as s:
        s["_captcha"] = "7"
    _apply(client, invite=alpha["invite_token"], name="Alpha College Pune", state="Maharashtra", aishe_code="",
           coord_email="alpha@maha.example", head_email="head@alpha.example")
    assert _row(app, alpha["id"])["status"] == "pending"
    from test_institutions import _marked
    _marked(app)   # and, since 1.2.174, on its marks of Annexure-V
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": alpha["id"], "action": "accept"})
    assert _row(app, alpha["id"])["status"] == "accepted"


def test_one_institution_back_to_invited():
    from kts.db import query
    app = _app()
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    rows = _invite(app, officer, "Maharashtra", ["Alpha College Pune", "Beta College Pune"])
    alpha, beta = rows["Alpha College Pune"], rows["Beta College Pune"]
    _as_on_10_november(app, alpha["id"])
    _as_on_10_november(app, beta["id"])
    page = officer.get("/console/institutions?state=Maharashtra").get_data(as_text=True)
    assert page.count("not registered yet") == 2 and page.count('value="reinvite"') == 2
    assert "Selected before they registered" in page and "↩ Back to invited: all 2" in page
    assert "unregistered=1" in page
    listed = officer.get("/console/institutions?state=Maharashtra&unregistered=1").get_data(as_text=True)
    assert "Alpha College Pune" in listed and "Beta College Pune" in listed
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": alpha["id"], "action": "reinvite"}, follow_redirects=True)
    assert "back to identified · invited" in r.get_data(as_text=True)
    row = _row(app, alpha["id"])
    assert (row["status"], row["decided_at"], row["decided_by"]) == ("identified", None, None) and row["invite_token"]
    mail = _mails(app, "alpha@maha.example")[-1]
    assert "is invited to register" in mail["subject"] and f"/institutions/register?invite={row['invite_token']}" in mail["body"]
    with app.app_context():
        log = query("SELECT * FROM audit_log WHERE action = 'institution_reinvited'", one=True)
    assert log["actor"] == "nodal.mh@tests.example" and alpha["ref"] in log["detail"] and '"was": "accepted"' in log["detail"]
    # Beta is still selected; a registered institution has no way back, only Undo
    assert _row(app, beta["id"])["status"] == "accepted"
    _apply(app.test_client(), name="Gamma College Pune", state="Maharashtra", aishe_code="", head_email="h@gamma.example",
           coord_email="c@gamma.example")
    with app.app_context():
        gamma = query("SELECT * FROM institutions WHERE name = 'Gamma College Pune'", one=True)
    from test_institutions import _marked
    _marked(app)
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": gamma["id"], "action": "accept"})
    assert officer.post("/console/institutions", data={"_csrf": _token(officer), "id": gamma["id"], "action": "reinvite"}).status_code == 400
    assert officer.post("/console/institutions", data={"_csrf": _token(officer), "id": alpha["id"], "action": "reinvite"}).status_code == 400


def test_all_of_a_state_at_once():
    from kts.db import execute, query
    app = _app()
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    rows = _invite(app, officer, "Maharashtra", ["Alpha College Pune", "Beta College Pune", "Delta College Pune", "Theta College Pune"])
    for name, status in (("Alpha College Pune", "accepted"), ("Beta College Pune", "reserve"), ("Delta College Pune", "declined"),
                         ("Theta College Pune", "accepted")):
        _as_on_10_november(app, rows[name]["id"], status)
    with app.app_context():   # Theta has switched its online assessment on: it stays
        execute("UPDATE institutions SET test_on = 1 WHERE id = ?", (rows["Theta College Pune"]["id"],))
    kerala_officer = _nodal(app, "nodal.kl@tests.example", ["Kerala"])
    kerala = _invite(app, kerala_officer, "Kerala", ["Kappa College Kochi"])
    _as_on_10_november(app, kerala["Kappa College Kochi"]["id"])
    # another State's officer, and a viewer, cannot
    assert kerala_officer.post("/console/institutions/back-to-invited", data={"_csrf": _token(kerala_officer), "state": "Maharashtra"}).status_code == 404
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.post("/console/institutions/back-to-invited", data={"_csrf": _token(viewer), "state": "Maharashtra"}).status_code == 403
    r = officer.post("/console/institutions/back-to-invited", data={"_csrf": _token(officer), "state": "Maharashtra"}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "Maharashtra: 3 institution(s) back to identified · invited" in page and "Theta College Pune (its online assessment is switched on)" in page
    status = {name: _row(app, row["id"])["status"] for name, row in rows.items()}
    assert status == {"Alpha College Pune": "identified", "Beta College Pune": "identified", "Delta College Pune": "identified",
                      "Theta College Pune": "accepted"}
    assert _row(app, kerala["Kappa College Kochi"]["id"])["status"] == "accepted"
    for who in ("alpha", "beta", "delta"):
        assert "is invited to register" in _mails(app, f"{who}@maha.example")[-1]["subject"]
    with app.app_context():
        log = query("SELECT * FROM audit_log WHERE action = 'institutions_reinvited'", one=True)
    assert '"state": "Maharashtra"' in log["detail"] and rows["Alpha College Pune"]["ref"] in log["detail"]
    # CICT sees what is left, State/UT by State/UT
    admin = _staff(app, "admin@tests.example", "superadmin")
    console = admin.get("/console/institutions").get_data(as_text=True)
    card = console[console.index('id="unregistered"'):console.index("Invite institutions to register (a list)")]
    assert "Kerala and Lakshadweep" in card and "↩ Back to invited: all 1" in card and "Maharashtra</b>: " in card

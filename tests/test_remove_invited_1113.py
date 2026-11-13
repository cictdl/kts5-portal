"""
The invited list of a State/UT is removed (1.2.188). CICT, 13 November 2026, of Console › Institutions with Maharashtra and
"identified" chosen (4,849 institutions): "how to remove the email list of maharashtra". Until then the Console could not: an
institution of an uploaded list could only be declined, one by one, each with a mail to it.

CICT (super-administrator, administrator) removes the invited list of a row of Annexure-I at once: every institution of it that
is still identified and on which nothing rests - never registered, no marks, no students, no online assessment, no selected
student. Their invitation links stop working, the invitations still waiting in the mail queue are not sent, and nothing else is
touched: an institution that has registered stays, and so does the list of every other State/UT.

    python -m pytest tests/test_remove_invited_1113.py -q
"""
from test_back_to_invited_1111 import _app, _invite, _row, empty_limiter      # noqa: F401  (the fixture empties the limiter)
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff

NAMES = ["Alpha College Pune", "Beta College Nagpur", "Gamma College Nashik", "Delta College Thane", "Epsilon College Satara"]


def _outbox(app, to, status=None):
    from kts.db import query
    with app.app_context():
        rows = query("SELECT * FROM outbox WHERE to_addr = ? ORDER BY id", (to,))
    return [r for r in rows if status is None or r["status"] == status]


def _remove(client, state, typed):
    return client.post("/console/institutions/remove-invited", data={"_csrf": _token(client), "state": state, "confirm": typed},
                       follow_redirects=True)


def _maharashtra(app):
    """The list of Maharashtra as on the live site, in small: three still invited, one registered, one with marks."""
    from kts.db import execute
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    rows = _invite(app, officer, "Maharashtra", NAMES)
    assert all(rows[n]["status"] == "identified" and rows[n]["invite_token"] for n in NAMES)
    assert all(len(_outbox(app, f"{n.split()[0].lower()}@maha.example", "queued")) == 1 for n in NAMES)
    with app.app_context():
        # the invitation to Beta has gone out already
        execute("UPDATE outbox SET status = 'sent', sent_at = created_at WHERE to_addr = 'beta@maha.example'")
        # Gamma has registered with its invitation and awaits the selection
        execute("UPDATE institutions SET status = 'pending', head_name = 'Dr. Head', head_designation = 'Principal', "
                "head_email = 'head@gamma.example', invite_token = NULL WHERE id = ?", (rows["Gamma College Nashik"]["id"],))
        # the Evaluation Committee has recorded marks for Delta
        execute("UPDATE institutions SET sop_total = 70 WHERE id = ?", (rows["Delta College Thane"]["id"],))
    return officer, rows


def test_cict_removes_the_invited_list_of_a_state():
    from kts import heis
    from kts.db import query
    app = _app()
    officer, rows = _maharashtra(app)
    kerala = _invite(app, _nodal(app, "nodal.kl@tests.example", ["Kerala"]), "Kerala", ["Zeta College Kochi"])
    admin = _staff(app, "remove.admin@tests.example", "superadmin")

    # the card: where the State/UT is chosen, for CICT, with the number to type and a copy of the list to keep
    page = admin.get("/console/institutions?state=Maharashtra&status=identified").get_data(as_text=True)
    assert 'id="remove-invited"' in page and "Remove the invited list of Maharashtra" in page and "Type 3 to confirm" in page
    assert "1 other identified institution(s) of Maharashtra stay" in page
    assert 'href="/console/institutions/export.xlsx?state=Maharashtra&amp;status=identified"' in page
    assert 'id="remove-invited"' not in admin.get("/console/institutions").get_data(as_text=True)
    assert 'id="remove-invited"' not in admin.get("/console/institutions?state=Goa").get_data(as_text=True)
    # the Nodal Officer neither sees it nor can do it
    assert 'id="remove-invited"' not in officer.get("/console/institutions?state=Maharashtra&status=identified").get_data(as_text=True)
    assert _remove(officer, "Maharashtra", "3").status_code == 403

    # nothing without the number
    for typed in ("", "5", "three", "30"):
        r = _remove(admin, "Maharashtra", typed)
        assert r.status_code == 200 and "Nothing was removed: type 3" in r.get_data(as_text=True), typed
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM institutions WHERE state = 'Maharashtra'", one=True)["n"] == 5

    r = _remove(admin, "Maharashtra", "3")
    said = r.get_data(as_text=True)
    assert "Maharashtra: the invited list is removed" in said and "3 institution(s) deleted" in said
    assert "2 invitation(s) that still waited in the mail queue are not sent" in said and "1 identified institution(s) stay" in said
    with app.app_context():
        left = {x["name"]: x["status"] for x in query("SELECT name, status FROM institutions WHERE state = 'Maharashtra'")}
        log = query("SELECT * FROM audit_log WHERE action = 'institutions_invited_removed'")
    # the one that registered and the one with marks stay
    assert left == {"Gamma College Nashik": "pending", "Delta College Thane": "identified"}
    assert len(log) == 1 and '"removed": 3' in log[0]["detail"] and '"mails": 2' in log[0]["detail"] and "Maharashtra" in log[0]["detail"]
    # the invitations that waited are not sent; the one that went out stays in the record, and Delta's still waits
    assert _outbox(app, "alpha@maha.example") == [] and _outbox(app, "epsilon@maha.example") == []
    assert [m["status"] for m in _outbox(app, "beta@maha.example")] == ["sent"]
    assert [m["status"] for m in _outbox(app, "delta@maha.example")] == ["queued"]
    # the list of another State/UT is as it was
    zeta = _row(app, kerala["Zeta College Kochi"]["id"])
    assert zeta["status"] == "identified" and zeta["invite_token"] and len(_outbox(app, "zeta@kera.example", "queued")) == 1
    # nothing more to remove: the card is gone
    page = admin.get("/console/institutions?state=Maharashtra&status=identified").get_data(as_text=True)
    assert 'id="remove-invited"' not in page and "Delta College Thane" in page and "Alpha College Pune" not in page
    assert "There is no invited list to remove for Maharashtra" in _remove(admin, "Maharashtra", "0").get_data(as_text=True)

    # an invitation of the removed list: the page says so and shows the form, and the institution may register like any other
    visitor = app.test_client()
    r = visitor.get(f"/institutions/register?invite={rows['Alpha College Pune']['invite_token']}&lang=en")
    form = r.get_data(as_text=True)
    assert r.status_code == 200 and "This invitation link is not valid or has been used" in form and 'name="head_name"' in form
    with app.app_context():
        assert heis.duplicate({"name": "Alpha College Pune", "state": "Maharashtra", "aishe_code": ""}) is None
        assert heis.duplicate({"name": "Delta College Thane", "state": "Maharashtra", "aishe_code": ""}) is not None


def test_the_list_of_a_row_of_annexure_i_goes_with_its_union_territory():
    from kts import heis
    from kts.db import query
    app = _app()
    admin = _staff(app, "remove.admin2@tests.example", "superadmin")
    _invite(app, admin, "Kerala", ["Eta College Kollam", "Theta College Kannur"])
    _invite(app, admin, "Lakshadweep", ["Iota College Kavaratti"])
    _invite(app, admin, "Goa", ["Kappa College Panaji"])
    with app.app_context():
        assert heis.invited_counts("Kerala") == heis.invited_counts("Lakshadweep") == (3, 0) and heis.invited_counts("Goa") == (1, 0)
    page = admin.get("/console/institutions?state=Lakshadweep").get_data(as_text=True)
    assert "Remove the invited list of Kerala and Lakshadweep" in page and "Type 3 to confirm" in page
    said = _remove(admin, "Lakshadweep", "3").get_data(as_text=True)
    assert "Kerala and Lakshadweep: the invited list is removed" in said and "3 institution(s) deleted" in said
    with app.app_context():
        assert [x["name"] for x in query("SELECT name FROM institutions ORDER BY name")] == ["Kappa College Panaji"]
        assert query("SELECT COUNT(*) AS n FROM outbox WHERE status = 'queued'", one=True)["n"] == 1
    assert _remove(admin, "Atlantis", "1").status_code == 404


def test_who_may_remove_a_list():
    from kts.auth import PERMS
    assert PERMS["hei.remove"] == {"superadmin", "admin"}
    app = _app()
    chief = _staff(app, "remove.chief@tests.example", "superadmin")
    _invite(app, chief, "Goa", ["Lambda College Margao", "Mu College Vasco"])
    for n, role in enumerate(("verifier", "content", "viewer", "agency")):
        client = _staff(app, f"remove.{role}{n}@tests.example", role)
        assert _remove(client, "Goa", "2").status_code == 403, role
    # without a session: to the sign-in page
    r = app.test_client().post("/console/institutions/remove-invited", data={"state": "Goa", "confirm": "2"})
    assert r.status_code in (302, 400)
    officer = _staff(app, "remove.officer@tests.example", "admin")
    assert 'id="remove-invited"' in officer.get("/console/institutions?state=Goa").get_data(as_text=True)
    assert "2 institution(s) deleted" in _remove(officer, "Goa", "2").get_data(as_text=True)

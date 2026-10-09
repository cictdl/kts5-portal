"""
Nodal Officers of the States/UTs in the console (version 1.2.38): a console account limited to the applications of the institutions of
its States/UTs, and the page of CICT that follows them.

    python -m pytest tests -q
"""
import json

from conftest import ROOT, make_app
from test_public_fixes import STAFF_PASSWORD, _staff

STATES = ("Kerala", "Kerala", "Assam", "Delhi")


def _portal():
    """Four applications: two from Kerala, one from Assam, one from Delhi, each with its files on the disk."""
    from kts.db import execute, utcnow
    from kts.utils import make_app_no
    app = make_app(ADMIN_PASSWORD=None)
    ids = []
    with app.app_context():
        for n, state in enumerate(STATES, start=1):
            rid = execute("INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, "
                          "college_state, pref_lang, status, photo_path, idproof_path, nomination_path, created_at, updated_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,'submitted',?,?,?,?,?)",
                          (f"Student {n}", "F", "2004-05-06", f"98765{n:05d}", f"s{n}@tests.example", state, f"College {n}",
                           f"name:college {n}|{state.lower()}", state, "hi", f"photos/p{n}.png", f"idproofs/i{n}.png",
                           f"nominations/n{n}.png", utcnow(), utcnow()))
            execute("UPDATE applications SET app_no = ? WHERE id = ?", (make_app_no(rid), rid))
            ids.append(rid)
            for folder, name in (("photos", f"p{n}.png"), ("idproofs", f"i{n}.png"), ("nominations", f"n{n}.png")):
                path = app.config["UPLOAD_DIR"] / folder
                path.mkdir(parents=True, exist_ok=True)
                (path / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    return app, ids


def _nodal(app, email, states):
    client = _staff(app, email, "nodal")
    from kts.db import execute
    with app.app_context():
        execute("UPDATE users SET states = ? WHERE email = ?", ("|".join(states), email))
    return client


def _token(client):
    with client.session_transaction() as s:
        return s["_csrf"]


def test_a_nodal_officer_sees_and_verifies_the_applications_of_their_state_only():
    from kts.db import query
    app, ids = _portal()
    kerala = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    page = kerala.get("/console/applications").get_data(as_text=True)
    assert "Student 1" in page and "Student 2" in page and "Student 3" not in page and "Student 4" not in page
    assert "You see the applications of the students of the institutions of" in page and "<b>Kerala</b>" in page
    # asking for another state does not widen it
    assert "Student 3" not in kerala.get("/console/applications?state=Assam").get_data(as_text=True)
    # an application of another state does not exist for them, nor its files
    assert kerala.get(f"/console/applications/{ids[2]}").status_code == 404
    for path in ("photos/p3.png", "idproofs/i3.png", "nominations/n3.png"):
        assert kerala.get(f"/console/files/{path}").status_code == 404
    for path in ("photos/p1.png", "idproofs/i1.png", "nominations/n1.png"):
        assert kerala.get(f"/console/files/{path}").status_code == 200
    # verify one of their own
    token = _token(kerala)
    r = kerala.post(f"/console/applications/{ids[0]}", data={"_csrf": token, "action": "verify", "remarks": "Nomination checked"})
    assert r.status_code == 302
    # withdrawing and deleting stay with CICT; another state cannot be touched
    assert kerala.post(f"/console/applications/{ids[1]}", data={"_csrf": token, "action": "withdraw"}).status_code == 403
    assert kerala.post(f"/console/applications/{ids[2]}", data={"_csrf": token, "action": "verify"}).status_code == 404
    assert "Withdraw</button>" not in kerala.get(f"/console/applications/{ids[1]}").get_data(as_text=True)
    # several at once: only those of their state change
    kerala.post("/console/applications/bulk", data={"_csrf": token, "action": "verify", "ids": [str(i) for i in ids]})
    with app.app_context():
        status = {r["college_state"] + str(r["id"]): r["status"] for r in query("SELECT id, college_state, status FROM applications")}
    assert status == {f"Kerala{ids[0]}": "verified", f"Kerala{ids[1]}": "verified", f"Assam{ids[2]}": "submitted",
                      f"Delhi{ids[3]}": "submitted"}
    # the export: their state only
    csv = kerala.get("/console/applications/export.csv").get_data(as_text=True)
    assert "Student 1" in csv and "Student 3" not in csv and "Student 4" not in csv


def test_the_rest_of_the_console_is_closed_to_them():
    app, _ids = _portal()
    officer = _nodal(app, "nodal.assam@tests.example", ["Assam"])
    for path in ("/console/", "/console/settings", "/console/users", "/console/stipend", "/console/selection",
                 "/console/questions", "/console/exam", "/console/nodal", "/console/outbox", "/console/audit",
                 "/hub/", "/hub/tasks", "/hub/documents", "/hub/calendar"):
        assert officer.get(path).status_code == 403, path
    page = officer.get("/console/applications?status=submitted").get_data(as_text=True)
    assert "Dashboard</a>" not in page and "Settings</a>" not in page and "Verification queue</a>" in page
    # nor a link to the coordination hub, which is not theirs
    assert "Hub overview</a>" not in page and "Shared documents</a>" not in page and "Classroom quiz</a>" in page
    # the console's own files (notices, documents) stay closed too
    assert officer.get("/console/files/documents/x.pdf").status_code == 403


def test_after_the_sign_in_the_queue_of_their_state():
    app, _ids = _portal()
    _nodal(app, "nodal.delhi@tests.example", ["Delhi"])
    client = app.test_client()
    client.get("/console/login")
    r = client.post("/console/login", data={"_csrf": _token(client), "email": "nodal.delhi@tests.example", "password": STAFF_PASSWORD})
    assert r.status_code == 302 and r.headers["Location"].endswith("/console/applications?status=submitted")
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Student 4" in page and "Student 1" not in page


def test_an_account_without_a_state_sees_nothing():
    app, _ids = _portal()
    officer = _nodal(app, "nodal.none@tests.example", [])
    page = officer.get("/console/applications").get_data(as_text=True)
    assert "Student" not in page.split("<table")[-1] and "no State/UT yet" in page


def test_cict_creates_the_accounts_and_follows_the_states():
    from kts.db import query
    app, ids = _portal()
    admin = _staff(app, "admin@tests.example", "superadmin")
    page = admin.get("/console/nodal").get_data(as_text=True)
    heis = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))
    assert page.count('<tr><td class="num">') >= len(heis)
    assert "Central University of Kerala" in page and "+ Create the account" in page
    # Kerala: two applications awaiting, linked to the queue of that state
    assert 'href="/console/applications?state=Kerala&amp;status=submitted"><b>2</b></a>' in page
    # the form comes filled in from the page
    form = admin.get("/console/users/new?role=nodal&states=Kerala").get_data(as_text=True)
    assert '<option value="nodal" selected>' in form and "<option selected>Kerala</option>" in form
    token = _token(admin)
    # a Nodal Officer needs a State/UT
    r = admin.post("/console/users/new", data={"_csrf": token, "email": "nodal@ker.example", "name": "Dr. Nodal", "role": "nodal",
                                               "active": "1"}, follow_redirects=True)
    assert "needs the State/UT" in r.get_data(as_text=True)
    r = admin.post("/console/users/new", data={"_csrf": token, "email": "nodal@ker.example", "name": "Dr. Nodal", "role": "nodal",
                                               "states": ["Kerala", "Not a state"], "active": "1"}, follow_redirects=True)
    assert "User saved." in r.get_data(as_text=True)
    with app.app_context():
        user = query("SELECT * FROM users WHERE email = 'nodal@ker.example'", one=True)
        mail = query("SELECT body FROM outbox WHERE to_addr = 'nodal@ker.example'", one=True)["body"]
    assert user["role"] == "nodal" and user["states"] == "Kerala"
    assert "As Nodal Officer for Kerala" in mail and "Verification queue" in mail
    page = admin.get("/console/nodal").get_data(as_text=True)
    kerala_row = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert "Dr. Nodal" in kerala_row and "not signed in yet" in kerala_row
    # the list of users shows the state of a Nodal Officer
    assert "Kerala</div>" in admin.get("/console/users").get_data(as_text=True)
    # other roles keep no state
    r = admin.post(f"/console/users/{user['id']}/edit", data={"_csrf": token, "email": "nodal@ker.example", "name": "Dr. Nodal",
                                                              "role": "verifier", "states": ["Kerala"], "active": "1"}, follow_redirects=True)
    with app.app_context():
        assert query("SELECT states FROM users WHERE email = 'nodal@ker.example'", one=True)["states"] == ""


def test_the_account_form_shows_the_account_and_not_the_signed_in_user():
    """Up to 1.2.37 the form was filled in with the administrator's own name, e-mail and role (u of console/base.html)."""
    from kts.db import query
    app, _ids = _portal()
    admin = _staff(app, "admin@tests.example", "superadmin")
    _staff(app, "verifier@tests.example", "verifier")
    form = admin.get("/console/users/new").get_data(as_text=True)
    assert 'value="admin@tests.example"' not in form and 'id="email" name="email" value=""' in form
    assert '<option value="superadmin" selected>' not in form and "Issue a new temporary password" not in form
    with app.app_context():
        uid = query("SELECT id FROM users WHERE email = 'verifier@tests.example'", one=True)["id"]
    form = admin.get(f"/console/users/{uid}/edit").get_data(as_text=True)
    assert 'value="verifier@tests.example"' in form and 'value="admin@tests.example"' not in form
    assert '<option value="verifier" selected>' in form and "Issue a new temporary password" in form

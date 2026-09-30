"""
Console: an administrator deletes an application for good (a trial entry, one made by mistake).

    python -m pytest tests -q
"""
from pathlib import Path

from conftest import make_app
from test_public_fixes import _staff

PHOTO, PROOF = "photos/20261001-0123456789abcdef.jpg", "idproofs/20261001-fedcba9876543210.pdf"


def _application(app, n=1, photo=PHOTO, proof=PROOF):
    """An application with its two uploaded files and a test attempt; gives (id, number)."""
    from kts.db import execute, utcnow
    from kts.utils import make_app_no
    folder = Path(app.config["UPLOAD_DIR"])
    for name in filter(None, (photo, proof)):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"trial")
    with app.app_context():
        aid = execute(
            "INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, pref_lang, "
            "photo_path, idproof_path, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"Trial Entry {n}", "F", "2004-05-06", f"98765{n:05d}", f"trial{n}@tests.example", "Kerala",
             "Government College Thrissur", "name:government thrissur|kerala", "hi", photo, proof, utcnow(), utcnow()))
        execute("UPDATE applications SET app_no = ? WHERE id = ?", (make_app_no(aid), aid))
        execute("INSERT INTO exam_sessions(application_id, lang, paper_json, started_at, deadline_at) VALUES(?,?,?,?,?)",
                (aid, "hi", "[]", utcnow(), utcnow()))
    return aid, make_app_no(aid)


def _post(client, aid, **form):
    with client.session_transaction() as s:
        token = s["_csrf"]
    return client.post(f"/console/applications/{aid}", data={"_csrf": token, "action": "delete", **form})


def _count(app, table, where="1 = 1", args=()):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", args, one=True)["n"]


def test_an_administrator_deletes_a_trial_entry_with_all_that_belongs_to_it():
    app = make_app(ADMIN_PASSWORD=None)
    aid, number = _application(app)
    other, other_number = _application(app, 2, "photos/kept.jpg", "idproofs/kept.pdf")
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get(f"/console/applications/{aid}").get_data(as_text=True)
    assert "Delete this application" in page and f"Type {number} to confirm" in page
    assert "2 " in app.test_client().get("/?lang=en").get_data(as_text=True)
    r = _post(admin, aid, confirm_no=number.lower(), reason="trial entry before the launch")
    assert r.status_code == 302 and r.headers["Location"] == "/console/applications"
    assert _count(app, "applications", "id = ?", (aid,)) == 0 and _count(app, "exam_sessions", "application_id = ?", (aid,)) == 0
    folder = Path(app.config["UPLOAD_DIR"])
    assert not (folder / PHOTO).exists() and not (folder / PROOF).exists()
    # the other application is whole
    assert _count(app, "applications", "id = ?", (other,)) == 1 and _count(app, "exam_sessions", "application_id = ?", (other,)) == 1
    assert (folder / "photos/kept.jpg").exists() and (folder / "idproofs/kept.pdf").exists()
    assert admin.get(f"/console/applications/{aid}").status_code == 404
    # the log names the number and the reason, and nothing of the person
    from kts.db import query
    with app.app_context():
        entry = query("SELECT * FROM audit_log WHERE action = 'application_deleted'", one=True)
    assert entry["detail"] == f"{number} trial entry before the launch" and entry["entity_id"] == aid
    assert entry["actor"] == "admin@tests.example" and "Trial Entry" not in entry["detail"]
    listing = admin.get("/console/applications").get_data(as_text=True)
    assert number not in listing and other_number in listing


def test_the_number_is_not_given_again():
    app = make_app(ADMIN_PASSWORD=None)
    first, number = _application(app)
    admin = _staff(app, "admin@tests.example", "admin")
    assert _post(admin, first, confirm_no=number).status_code == 302
    assert _count(app, "applications") == 0
    second, second_number = _application(app, 2)
    assert second > first and second_number != number


def test_nothing_is_deleted_without_the_number():
    app = make_app(ADMIN_PASSWORD=None)
    aid, number = _application(app)
    admin = _staff(app, "admin@tests.example", "admin")
    for typed in ("", "yes", number[:-1], number + "0"):
        r = _post(admin, aid, confirm_no=typed)
        assert r.status_code == 302 and r.headers["Location"] == f"/console/applications/{aid}"
    assert _count(app, "applications", "id = ?", (aid,)) == 1 and _count(app, "exam_sessions") == 1
    assert (Path(app.config["UPLOAD_DIR"]) / PHOTO).exists()
    assert _count(app, "audit_log", "action = 'application_deleted'") == 0
    assert "Nothing was deleted" in admin.get(f"/console/applications/{aid}").get_data(as_text=True)


def test_a_verifier_cannot_delete():
    app = make_app(ADMIN_PASSWORD=None)
    aid, number = _application(app)
    verifier = _staff(app, "verifier@tests.example", "verifier")
    page = verifier.get(f"/console/applications/{aid}").get_data(as_text=True)
    assert "Withdraw" in page and "Delete this application" not in page
    assert _post(verifier, aid, confirm_no=number).status_code == 403
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert _post(viewer, aid, confirm_no=number).status_code == 403
    assert _count(app, "applications", "id = ?", (aid,)) == 1
    from kts.auth import PERMS
    assert PERMS["apps.delete"] == {"superadmin", "admin"}


def test_an_application_of_the_selection_list_is_not_deleted():
    from kts.db import execute, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    aid, number = _application(app)
    with app.app_context():
        execute("INSERT INTO merit_list(rank, application_id, score, college_key, outcome, run_id, created_at) VALUES(1,?,90,?,?,?,?)",
                (aid, "name:government thrissur|kerala", "selected", "run-1", utcnow()))
    admin = _staff(app, "admin@tests.example", "admin")
    r = _post(admin, aid, confirm_no=number)
    assert r.status_code == 302 and r.headers["Location"] == f"/console/applications/{aid}"
    assert _count(app, "applications", "id = ?", (aid,)) == 1 and (Path(app.config["UPLOAD_DIR"]) / PHOTO).exists()
    assert "selection list" in admin.get(f"/console/applications/{aid}").get_data(as_text=True)


def test_a_file_outside_the_upload_folder_is_not_touched():
    app = make_app(ADMIN_PASSWORD=None)
    outside = Path(app.config["UPLOAD_DIR"]).parent / "outside.txt"
    aid, number = _application(app, 1, "photos/../../outside.txt", "")
    outside.write_text("stays", encoding="utf-8")
    admin = _staff(app, "admin@tests.example", "admin")
    assert _post(admin, aid, confirm_no=number).status_code == 302
    assert _count(app, "applications") == 0 and outside.read_text(encoding="utf-8") == "stays"

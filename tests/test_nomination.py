"""
Registration follows the nomination of the institution: the Faculty Supervisor/Guide is required and the
signed nomination form is uploaded (version 1.2.22).

    python -m pytest tests -q
"""
import io

from conftest import ROOT, make_app
from test_public_fixes import PNG, _register, _staff, _stored


def test_the_supervisor_and_the_nomination_form_are_required():
    app = make_app(ADMIN_PASSWORD=None, RATE_REGISTER_PER_HOUR=50)
    for missing in ("mentor_name", "mentor_designation", "mentor_email", "mentor_phone"):
        r = _register(app, 1, **{missing: ""})
        assert r.status_code == 400 and "This field is required." in r.get_data(as_text=True), missing
    r = _register(app, 1, mentor_email="not an address")
    assert r.status_code == 400 and "Enter a valid email address." in r.get_data(as_text=True)
    # no form, or a file that is no document
    r = _register(app, 1, nomination=(io.BytesIO(b"plain text"), "form.txt"))
    assert r.status_code == 400 and "Upload the signed nomination form as PDF, JPG or PNG under 4 MB." in r.get_data(as_text=True)
    assert _stored(app) == 0
    r = _register(app, 1)
    assert r.status_code == 302
    from kts.db import query
    with app.app_context():
        row = query("SELECT * FROM applications", one=True)
    assert row["mentor_name"] == "Dr. K. Mentor" and row["mentor_phone"] == "9876000001"
    assert row["nomination_path"].startswith("nominations/") and (app.config["UPLOAD_DIR"] / row["nomination_path"]).is_file()
    # the staff open the form; the public does not
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get(f"/console/applications/{row['id']}").get_data(as_text=True)
    assert f'href="/console/files/{row["nomination_path"]}"' in page and "Open the signed form" in page
    assert "Faculty Supervisor/Guide" in page
    assert admin.get(f"/console/files/{row['nomination_path']}").status_code == 200
    assert app.test_client().get(f"/console/files/{row['nomination_path']}").status_code == 302
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.get(f"/console/files/{row['nomination_path']}").status_code == 200


def test_the_form_tells_the_nomination_and_offers_the_blank_form():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/register?lang=en").get_data(as_text=True)
    assert "Each participating institution nominates one eligible student" in page
    assert "5 · Faculty Supervisor/Guide" in page and "(optional)" not in page.split("5 · Faculty Supervisor/Guide")[1].split("6 ·")[0]
    assert 'name="nomination"' in page and 'data-max="4194304"' in page
    assert 'href="/static/KTS5-nomination-form.pdf" download' in page and "Download the nomination form" in page
    r = client.get("/static/KTS5-nomination-form.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"
    r.close()
    assert (ROOT / "static" / "KTS5-nomination-form.pdf").stat().st_size < 400_000

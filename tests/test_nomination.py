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
    assert "Each participating institution assesses its students, selects one on merit" in page
    assert "5 · Faculty Supervisor/Guide" in page and "(optional)" not in page.split("5 · Faculty Supervisor/Guide")[1].split("6 ·")[0]
    assert 'name="nomination"' in page and 'data-max="4194304"' in page
    assert 'href="/static/KTS5-nomination-form.pdf" download' in page and "Download the nomination form" in page
    r = client.get("/static/KTS5-nomination-form.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"
    r.close()
    assert (ROOT / "static" / "KTS5-nomination-form.pdf").stat().st_size < 400_000


def test_the_registration_page_offers_the_form_before_and_while_it_is_open():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    link = 'href="/static/KTS5-nomination-form.pdf" download>Download the nomination form (PDF)</a>'
    # open: at the top of the page, and again at the upload of step 6
    page = client.get("/register?lang=en").get_data(as_text=True)
    assert page.count('href="/static/KTS5-nomination-form.pdf" download') == 2 and link in page
    assert page.index(link) < page.index('name="full_name"')
    # before registration opens: the waiting page offers it, so the institutions can sign it in time
    with app.app_context():
        set_setting("reg.start", "2030-01-01")
    page = client.get("/register?lang=en").get_data(as_text=True)
    assert "Registration opens on" in page and link in page and 'name="full_name"' not in page
    assert "Nomination form, signed by the Head of the Institution" in page
    from kts.i18n import CATALOG
    tamil = client.get("/register?lang=ta").get_data(as_text=True)
    assert CATALOG["ta"]["reg.nomination_download"] in tamil
    # after it closes there is nothing to nominate
    with app.app_context():
        set_setting("reg.start", "2026-01-01")
        set_setting("reg.end", "2026-01-02")
    page = client.get("/register?lang=en").get_data(as_text=True)
    assert "KTS5-nomination-form.pdf" not in page


def test_the_form_gives_the_dates_of_the_timeline_of_8_october():
    """CICT's form (Canva, 9 October 2026): registration from 15 October, the form uploaded on or before 21 October."""
    import fitz
    text = " ".join(fitz.open(str(ROOT / "static" / "KTS5-nomination-form.pdf"))[0].get_text().split())
    assert "15 October" in text and "on or before 21 October 2026. The institution keeps" in text
    assert "16 October" not in text and "10 October" not in text

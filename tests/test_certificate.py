"""
The certificate of recognition of every registered student, signed by the Director of CICT.

    python -m pytest tests -q
"""
import io
import re
from pathlib import Path

import pytest

from conftest import make_app
from test_public_fixes import PNG, _staff

SIGNATURE = b"\x89PNG\r\n\x1a\n" + b"\0" * 64 + b"signature-of-the-tests"


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _registered(app, n=1, ip="198.51.100.60"):
    """A student registers through the form: (client of the student, application row)."""
    client = app.test_client()
    client.get("/register")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    form = {
        "_csrf": token, "full_name": f"Student Certificate {n}", "gender": "F", "dob": "2004-05-06", "category": "General",
        "mobile": f"98760{n:05d}", "email": f"cert{n}@tests.example", "state": "Kerala",
        "college_name": "Government College Thrissur", "college_type": "Government college", "college_state": "Kerala",
        "course_level": "Undergraduate", "year_of_study": "2nd year", "pref_lang": "hi", "declare_true": "1",
        "declare_participate": "1", "declare_consent": "1", "captcha": "7",
        "photo": (io.BytesIO(PNG), "photo.png"), "idproof": (io.BytesIO(PNG), "id.png"),
    }
    r = client.post("/register", data=form, content_type="multipart/form-data", environ_base={"REMOTE_ADDR": ip})
    assert r.status_code == 302 and "/register/done/" in r.headers["Location"], r.status_code
    from kts.db import query
    with app.app_context():
        row = query("SELECT * FROM applications WHERE email = ?", (f"cert{n}@tests.example",), one=True)
    return client, row


def _link(app, row):
    from kts.certificate import certificate_link
    from kts.db import query
    with app.test_request_context():
        with app.app_context():
            fresh = query("SELECT * FROM applications WHERE id = ?", (row["id"],), one=True)
            return certificate_link(fresh)


def _set(app, key, value):
    from kts.db import set_setting
    with app.app_context():
        set_setting(key, value)


def test_a_registered_student_has_a_certificate_signed_by_the_director():
    app = make_app(ADMIN_PASSWORD=None)
    client, row = _registered(app)
    link = _link(app, row)
    assert link and link.startswith(f"/certificate/{row['app_no']}/")
    r = app.test_client().get(link)
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "Student Certificate 1" in page and "Government College Thrissur, Kerala" in page
    assert "CERTIFICATE" in page and "OF RECOGNITION" in page and "Kashi Tamil Sangamam 5.0" in page
    number = "KTS5/CR/" + "/".join(row["app_no"].split("-")[1:])
    assert f"Certificate No. <b>{number}</b>" in page
    assert "<b>Prof. R. Chandrasekaran</b>" in page and "<span>Director</span>" in page
    assert "Central Institute of Classical Tamil, Chennai" in page
    # the QR code opens the same page on the portal
    from kts.utils import qr_data_uri
    if qr_data_uri("x"):
        assert 'src="data:image/png;base64,' in page
    # the name of a student is kept out of search engines and shared caches
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow" and "no-store" in r.headers["Cache-Control"]
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert "<script>" not in page and not re.search(r"\son[a-z]+=", page)
    # without a signature uploaded, the line stays empty
    assert 'alt="Signature"' not in page


def test_the_student_finds_the_certificate_after_registering_in_the_mail_on_the_status_page_and_in_the_portal():
    app = make_app(ADMIN_PASSWORD=None, BASE_URL="https://kts.example.org")
    client, row = _registered(app)
    link = _link(app, row)
    done = client.get(f"/register/done/{row['app_no']}?lang=en").get_data(as_text=True)
    assert f'href="{link}"' in done
    from kts.db import query
    with app.app_context():
        mail = query("SELECT body FROM outbox WHERE to_addr = ?", ("cert1@tests.example",), one=True)["body"]
    assert f"https://kts.example.org{link}" in mail
    lookup = app.test_client()
    lookup.get("/status")
    with lookup.session_transaction() as s:
        token = s["_csrf"]
    status = lookup.post("/status", data={"_csrf": token, "app_no": row["app_no"], "dob": "2004-05-06",
                                          "last4": row["mobile"][-4:]}).get_data(as_text=True)
    assert f'href="{link}"' in status
    # the card of the QR code names the portal by its address
    page = app.test_client().get(link).get_data(as_text=True)
    assert "<span>kts.example.org</span>" in page


def test_nobody_reaches_the_certificate_of_another_student():
    app = make_app(ADMIN_PASSWORD=None)
    _client, first = _registered(app, 1)
    _client, second = _registered(app, 2, ip="198.51.100.61")
    link = _link(app, first)
    seal = link.rsplit("/", 1)[1]
    client = app.test_client()
    assert client.get(f"/certificate/{second['app_no']}/{seal}").status_code == 404
    assert client.get(f"/certificate/{first['app_no']}/{'0' * len(seal)}").status_code == 404
    assert client.get(f"/certificate/KTS5-2026-999999/{seal}").status_code == 404
    assert client.get(f"/certificate/{first['app_no']}/{seal}").status_code == 200


@pytest.mark.parametrize("status", ["rejected", "withdrawn"])
def test_no_certificate_for_a_rejected_or_withdrawn_application(status):
    app = make_app(ADMIN_PASSWORD=None)
    client, row = _registered(app)
    link = _link(app, row)
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = ? WHERE id = ?", (status, row["id"]))
    assert app.test_client().get(link).status_code == 404
    assert _link(app, row) is None
    assert "/certificate/" not in client.get(f"/register/done/{row['app_no']}?lang=en").get_data(as_text=True)


def test_no_certificate_while_issuing_is_off():
    app = make_app(ADMIN_PASSWORD=None)
    client, row = _registered(app)
    link = _link(app, row)
    _set(app, "cert.on", "0")
    assert app.test_client().get(link).status_code == 404
    assert "/certificate/" not in client.get(f"/register/done/{row['app_no']}?lang=en").get_data(as_text=True)
    _set(app, "cert.on", "1")
    assert app.test_client().get(link).status_code == 200


def test_the_days_of_the_sangamam_stand_in_one_line_under_the_heading():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    page = app.test_client().get(_link(app, row)).get_data(as_text=True)
    line = '<p class="when">Kashi Tamil Sangamam 5.0 &middot; 28 November 2026 &ndash; 12 December 2026</p>'
    assert line in page
    assert page.index("OF RECOGNITION") < page.index(line) < page.index("Congratulations!")
    assert "thiruvalluvar" not in page.lower()
    # the days are those of the settings, and without them the line is left out
    _set(app, "kts.start", "2026-11-30")
    page = app.test_client().get(_link(app, row)).get_data(as_text=True)
    assert "30 November 2026 &ndash; 12 December 2026" in page and "28 November 2026" not in page
    _set(app, "kts.end", "")
    assert 'class="when"' not in app.test_client().get(_link(app, row)).get_data(as_text=True)


def test_the_signatory_follows_the_settings_of_the_head_of_the_institute():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _set(app, "director.name", "Prof. A. Example")
    _set(app, "director.designation", "Director (in charge)")
    page = app.test_client().get(_link(app, row)).get_data(as_text=True)
    assert "<b>Prof. A. Example</b>" in page and "Director (in charge)" in page and "Chandrasekaran" not in page


def test_an_administrator_uploads_and_removes_the_signature():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/certificate").get_data(as_text=True)
    assert "Image of the signature" in page and "Prof. R. Chandrasekaran" in page
    with admin.session_transaction() as s:
        token = s["_csrf"]
    r = admin.post("/console/certificate", data={"_csrf": token, "action": "signature",
                                                  "signature": (io.BytesIO(SIGNATURE), "sign.png")}, content_type="multipart/form-data")
    assert r.status_code == 302
    stored = Path(app.config["INSTANCE_DIR"]) / "certificate-signature.png"
    assert stored.read_bytes() == SIGNATURE
    page = app.test_client().get(_link(app, row)).get_data(as_text=True)
    assert 'alt="Signature"' in page and 'src="data:image/png;base64,' in page
    import base64
    assert base64.b64encode(SIGNATURE).decode("ascii") in page
    # the file itself is not served by the portal
    assert app.test_client().get("/instance/certificate-signature.png").status_code == 404
    assert app.test_client().get("/static/certificate-signature.png").status_code == 404
    # a file that is no image is refused, and the signature stays
    r = admin.post("/console/certificate", data={"_csrf": token, "action": "signature",
                                                  "signature": (io.BytesIO(b"%PDF-1.4"), "sign.png")}, content_type="multipart/form-data")
    assert stored.read_bytes() == SIGNATURE
    # a JPG replaces the PNG
    jpg = b"\xff\xd8\xff\xe0" + b"\0" * 40
    admin.post("/console/certificate", data={"_csrf": token, "action": "signature",
                                             "signature": (io.BytesIO(jpg), "sign.JPEG")}, content_type="multipart/form-data")
    assert not stored.exists() and (Path(app.config["INSTANCE_DIR"]) / "certificate-signature.jpg").read_bytes() == jpg
    assert 'src="data:image/jpeg;base64,' in app.test_client().get(_link(app, row)).get_data(as_text=True)
    admin.post("/console/certificate", data={"_csrf": token, "action": "remove"})
    assert 'alt="Signature"' not in app.test_client().get(_link(app, row)).get_data(as_text=True)
    from kts.db import query
    with app.app_context():
        actions = [r["action"] for r in query("SELECT action FROM audit_log WHERE action LIKE 'certificate_%' ORDER BY id")]
    assert actions == ["certificate_signature_set", "certificate_signature_set", "certificate_signature_removed"]


def test_issuing_is_switched_off_and_on_in_the_console_and_a_sample_is_shown():
    app = make_app(ADMIN_PASSWORD=None)
    admin = _staff(app, "admin@tests.example", "admin")
    admin.get("/console/certificate")
    with admin.session_transaction() as s:
        token = s["_csrf"]
    admin.post("/console/certificate", data={"_csrf": token, "action": "off"})
    from kts.db import get_setting
    with app.app_context():
        assert get_setting("cert.on") == "0"
    admin.post("/console/certificate", data={"_csrf": token, "action": "on"})
    with app.app_context():
        assert get_setting("cert.on") == "1"
    sample = admin.get("/console/certificate/sample")
    assert sample.status_code == 200 and "Sample Student Name" in sample.get_data(as_text=True)


def test_only_administrators_manage_the_certificate():
    app = make_app(ADMIN_PASSWORD=None)
    verifier = _staff(app, "verifier@tests.example", "verifier")
    for path in ("/console/certificate", "/console/certificate/sample"):
        assert verifier.get(path).status_code in (302, 403), path
    assert app.test_client().get("/console/certificate").status_code == 302


def test_the_toolbar_is_in_the_language_of_the_page_and_the_sheet_in_english():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    from markupsafe import escape
    from kts.i18n import CATALOG
    for lang in ("ta", "hi", "ur"):
        page = app.test_client().get(_link(app, row) + f"?lang={lang}").get_data(as_text=True)
        assert str(escape(CATALOG[lang]["cert.save_hint"])) in page
        assert '<main class="sheet" lang="en" dir="ltr">' in page and "OF RECOGNITION" in page

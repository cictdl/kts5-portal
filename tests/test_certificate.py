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
    # Thiruvalluvar, faint, in the background
    assert 'class="valluvar-bg" src="/static/img/thiruvalluvar-watermark.png"' in page
    r = app.test_client().get("/static/img/thiruvalluvar-watermark.png")
    assert r.status_code == 200 and r.mimetype == "image/png"
    r.close()


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
        assert '<main class="sheet recognition" lang="en" dir="ltr">' in page and "OF RECOGNITION" in page


# ---- certificate of merit ------------------------------------------------------------------------

def _selected(app, row, rank=7, outcome="selected", published="1"):
    """The student stands in the merit list with this rank and outcome."""
    from kts.db import execute, utcnow
    with app.app_context():
        execute("INSERT INTO merit_list(rank, application_id, score, college_key, outcome, run_id, created_at) VALUES(?,?,?,?,?,?,?)",
                (rank, row["id"], 88, row["college_key"], outcome, "run-1", "2026-10-21T06:30:00+00:00"))
        execute("UPDATE applications SET status = ?, exam_rank = ? WHERE id = ?", (outcome, rank, row["id"]))
    _set(app, "merit.published", published)


def _merit_link(app, row):
    from kts.certificate import merit_link
    from kts.db import query
    with app.test_request_context():
        with app.app_context():
            return merit_link(query("SELECT * FROM applications WHERE id = ?", (row["id"],), one=True))


def test_a_student_of_the_merit_list_has_a_certificate_of_merit():
    app = make_app(ADMIN_PASSWORD=None)
    client, row = _registered(app)
    _selected(app, row)
    link = _merit_link(app, row)
    assert link and link.startswith(f"/certificate/merit/{row['app_no']}/")
    r = app.test_client().get(link)
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert '<main class="sheet merit"' in page and "OF MERIT" in page and "OF RECOGNITION" not in page
    assert "&#9733; Merit List &middot; Rank 7 &#9733;" in page and "This certificate is awarded to" in page
    assert "Student Certificate 1" in page and "Government College Thrissur, Kerala" in page
    assert "as one of the 1,000 students chosen from colleges across India" in page and "held on 19 October 2026" in page
    number = "KTS5/CM/" + "/".join(row["app_no"].split("-")[1:])
    assert f"Certificate No. <b>{number}</b>" in page and "Date of issue: 21 Oct 2026" in page
    assert "<b>Prof. R. Chandrasekaran</b>" in page
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"
    # the certificate of recognition stays, and the two seals are not the same
    recognition = _link(app, row)
    assert recognition.rsplit("/", 1)[1] != link.rsplit("/", 1)[1]
    assert app.test_client().get(recognition).status_code == 200
    assert app.test_client().get(f"/certificate/merit/{row['app_no']}/{recognition.rsplit('/', 1)[1]}").status_code == 404
    assert app.test_client().get(f"/certificate/{row['app_no']}/{link.rsplit('/', 1)[1]}").status_code == 404


def test_the_student_finds_the_certificate_of_merit_on_the_status_page_and_in_the_portal():
    app = make_app(ADMIN_PASSWORD=None)
    client, row = _registered(app)
    _selected(app, row)
    link = _merit_link(app, row)
    lookup = app.test_client()
    lookup.get("/status")
    with lookup.session_transaction() as s:
        token = s["_csrf"]
    status = lookup.post("/status", data={"_csrf": token, "app_no": row["app_no"], "dob": "2004-05-06",
                                          "last4": row["mobile"][-4:]}).get_data(as_text=True)
    assert f'href="{link}"' in status and f'href="{_link(app, row)}"' in status
    assert status.index(link) < status.index(_link(app, row))
    home = Path(__file__).resolve().parent.parent / "templates" / "candidate" / "home.html"
    assert "merit_link(cand)" in home.read_text(encoding="utf-8")


@pytest.mark.parametrize("outcome, published", [("selected", "0"), ("waitlisted", "0"), ("not_selected", "1")])
def test_no_certificate_of_merit_before_the_list_is_published_or_outside_the_list(outcome, published):
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row, outcome=outcome, published=published)
    assert _merit_link(app, row) is None
    from kts.certificate import _seal
    with app.app_context():
        seal = _seal(row["app_no"], "merit")
    assert app.test_client().get(f"/certificate/merit/{row['app_no']}/{seal}").status_code == 404
    # the certificate of recognition is not touched
    assert app.test_client().get(_link(app, row)).status_code == 200


def test_a_waitlisted_student_has_a_certificate_of_merit_that_names_the_waiting_list():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row, rank=1042, outcome="waitlisted")
    link = _merit_link(app, row)
    assert link and link.startswith(f"/certificate/merit/{row['app_no']}/")
    page = app.test_client().get(link).get_data(as_text=True)
    assert "OF MERIT" in page and "&#9733; Merit List &middot; Waiting List &middot; Rank 1042 &#9733;" in page
    assert "for securing a place on the waiting list of the merit list of" in page and "held on 19 October 2026" in page
    # a waitlisted student is not said to be one of the students chosen
    assert "students chosen" not in page and "for being selected" not in page
    number = "KTS5/CM/" + "/".join(row["app_no"].split("-")[1:])
    assert f"Certificate No. <b>{number}</b>" in page
    # moved up into the selected list, the same address gives the certificate of the selected
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'selected' WHERE id = ?", (row["id"],))
    page = app.test_client().get(link).get_data(as_text=True)
    assert "for being selected in the merit list of" in page and "Waiting List" not in page


def test_a_withdrawal_after_the_selection_ends_the_certificate_of_merit():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    link = _merit_link(app, row)
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE id = ?", (row["id"],))
    assert app.test_client().get(link).status_code == 404


def test_certificates_of_merit_are_switched_off_and_on_and_a_sample_is_shown():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    link = _merit_link(app, row)
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/certificate").get_data(as_text=True)
    assert "Certificates of merit" in page and "to 1 selected or waitlisted student(s)" in page
    with admin.session_transaction() as s:
        token = s["_csrf"]
    admin.post("/console/certificate", data={"_csrf": token, "action": "merit_off"})
    assert app.test_client().get(link).status_code == 404
    # the certificates of recognition go on
    assert app.test_client().get(_link(app, row)).status_code == 200
    admin.post("/console/certificate", data={"_csrf": token, "action": "merit_on"})
    assert app.test_client().get(link).status_code == 200
    sample = admin.get("/console/certificate/sample?kind=merit").get_data(as_text=True)
    assert "OF MERIT" in sample and "Rank 1" in sample and "KTS5/CM/2026/000000" in sample and "Waiting List" not in sample
    sample = admin.get("/console/certificate/sample?kind=merit&waitlisted=1").get_data(as_text=True)
    assert "Waiting List" in sample and "for securing a place on the waiting list" in sample
    sample = admin.get("/console/certificate/sample").get_data(as_text=True)
    assert "OF RECOGNITION" in sample and "KTS5/CR/2026/000000" in sample


# ---- confirmation letter -------------------------------------------------------------------------

def _letter_link(app, row):
    from kts.certificate import letter_link
    from kts.db import query
    with app.test_request_context():
        with app.app_context():
            return letter_link(query("SELECT * FROM applications WHERE id = ?", (row["id"],), one=True))


def test_a_selected_student_has_a_confirmation_letter():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET mentor_name = ?, mentor_designation = ? WHERE id = ?",
                ("Dr. K. Mentor", "Assistant Professor of Tamil", row["id"]))
    _selected(app, row, rank=12)
    link = _letter_link(app, row)
    assert link and link.startswith(f"/letter/{row['app_no']}/")
    r = app.test_client().get(link)
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    number = "CICT/KTS5/CL/" + "/".join(row["app_no"].split("-")[1:])
    assert f"Ref. No. <b>{number}</b>" in page and "Date: <b>22 October 2026</b>" in page
    assert "<b>Student Certificate 1</b>" in page and "Government College Thrissur" in page and f"Application No. {row['app_no']}" in page
    assert "confirmation of selection" in page and "Dear Student Certificate 1," in page
    assert "one of the 1,000 students" in page and "held on 19 October 2026" in page and "<b>12</b>" in page
    assert "begins on 23 October 2026, under the guidance of your faculty mentor, Dr. K. Mentor, Assistant Professor of Tamil." in page
    assert "sessions in Hindi;" in page and "on or before 05 November 2026" in page and "on or before 15 November 2026" in page
    assert "&#8377;10,000" in page and "from 28 November 2026 to 12 December 2026" in page
    assert "<b>Prof. R. Chandrasekaran</b>" in page and "Copy to: The Principal / Head of the Institution, Government College Thrissur" in page
    assert "Chemmozhi Salai, Perumbakkam" in page
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow" and "no-store" in r.headers["Cache-Control"]
    assert "<script>" not in page and not re.search(r"\son[a-z]+=", page)
    # a seal of the letter opens no certificate, and the other way round
    seal = link.rsplit("/", 1)[1]
    assert app.test_client().get(f"/certificate/{row['app_no']}/{seal}").status_code == 404
    assert app.test_client().get(f"/letter/{row['app_no']}/{_merit_link(app, row).rsplit('/', 1)[1]}").status_code == 404


def test_the_dates_of_the_letter_follow_the_settings():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    for key, value in (("letter.date", "2026-10-24"), ("internship.start", "2026-10-26"), ("papers.due", "2026-11-09"),
                       ("present.due", ""), ("stipend.last_date", "2026-11-20")):
        _set(app, key, value)
    page = app.test_client().get(_letter_link(app, row)).get_data(as_text=True)
    assert "Date: <b>24 October 2026</b>" in page and "begins on 26 October 2026" in page
    assert "on or before 09 November 2026" in page and "on or before 20 November 2026" in page
    # without a last date the presentation is "on a date of your choice"
    assert "on a date of your choice." in page


@pytest.mark.parametrize("outcome, published", [("selected", "0"), ("waitlisted", "1"), ("not_selected", "1")])
def test_no_letter_before_the_list_is_published_or_outside_the_selected(outcome, published):
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row, outcome=outcome, published=published)
    assert _letter_link(app, row) is None
    from kts.certificate import _seal
    with app.app_context():
        seal = _seal(row["app_no"], "letter")
    assert app.test_client().get(f"/letter/{row['app_no']}/{seal}").status_code == 404


def test_the_student_finds_the_letter_on_the_status_page():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    link = _letter_link(app, row)
    lookup = app.test_client()
    lookup.get("/status")
    with lookup.session_transaction() as s:
        token = s["_csrf"]
    status = lookup.post("/status", data={"_csrf": token, "app_no": row["app_no"], "dob": "2004-05-06",
                                          "last4": row["mobile"][-4:]}).get_data(as_text=True)
    assert f'href="{link}"' in status and status.index(link) < status.index(_merit_link(app, row))
    home = Path(__file__).resolve().parent.parent / "templates" / "candidate" / "home.html"
    assert "letter_link(cand)" in home.read_text(encoding="utf-8")


def test_letters_are_switched_off_and_on_and_a_sample_is_shown():
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    link = _letter_link(app, row)
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/certificate").get_data(as_text=True)
    assert "Confirmation letters" in page and "to 1 selected student(s)" in page
    with admin.session_transaction() as s:
        token = s["_csrf"]
    admin.post("/console/certificate", data={"_csrf": token, "action": "letter_off"})
    assert app.test_client().get(link).status_code == 404
    admin.post("/console/certificate", data={"_csrf": token, "action": "letter_on"})
    assert app.test_client().get(link).status_code == 200
    sample = admin.get("/console/certificate/sample?kind=letter").get_data(as_text=True)
    assert "Sample Student Name" in sample and "CICT/KTS5/CL/2026/000000" in sample and "Dr. A. Sample" in sample
    from kts.admin import SETTING_GROUPS
    group = [items for title, items in SETTING_GROUPS if title.startswith("Internship")]
    assert [key for key, _l, _k in group[0]] == ["letter.date", "internship.start", "papers.due", "present.due"]

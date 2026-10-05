"""
The certificate of participation of the student delegates who attend the inauguration of KTS 5.0
online: the attendance recorded with the code of the live stream or by staff, and the certificate.

    python -m pytest tests -q
"""
import pytest

from conftest import make_app
from test_certificate import _link, _registered, _selected, _set
from test_public_fixes import _staff


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _signed_in(app, row):
    c = app.test_client()
    c.get("/candidate/login")
    with c.session_transaction() as s:
        token = s["_csrf"]
    r = c.post("/candidate/login", data={"_csrf": token, "app_no": row["app_no"], "dob": "2004-05-06", "last4": row["mobile"][-4:]})
    assert r.status_code == 302
    return c


def _record(client, code):
    with client.session_transaction() as s:
        token = s["_csrf"]
    return client.post("/candidate/inauguration", data={"_csrf": token, "code": code}, follow_redirects=True).get_data(as_text=True)


def _inaug_link(app, row):
    from kts.certificate import inaug_link
    from kts.db import query
    with app.test_request_context():
        with app.app_context():
            return inaug_link(query("SELECT * FROM applications WHERE id = ?", (row["id"],), one=True))


def _ready(code="KASHI 2026", start="2026-01-01"):
    """A delegate of the published merit list, the code set and the day of the inauguration come."""
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row)
    _set(app, "inaug.code", code)
    _set(app, "kts.start", start)
    _set(app, "inaug.link", "https://www.youtube.com/live/sample-stream")
    return app, row


def test_a_delegate_records_the_attendance_with_the_code_and_receives_the_certificate():
    app, row = _ready()
    student = _signed_in(app, row)
    home = student.get("/candidate/?lang=en").get_data(as_text=True)
    assert 'id="inaug-card"' in home and "Inauguration of KTS 5.0 · online" in home
    assert 'href="https://www.youtube.com/live/sample-stream"' in home and 'id="inaug-code"' in home
    assert _inaug_link(app, row) is None
    # a wrong code records nothing
    page = _record(student, "VARANASI")
    assert "This is not the attendance code." in page and _inaug_link(app, row) is None
    # the code as announced, in any case and spacing
    page = _record(student, "  kashi2026 ")
    assert "Your attendance at the inauguration is recorded." in page
    link = _inaug_link(app, row)
    assert link and link.startswith(f"/certificate/inaugural/{row['app_no']}/")
    assert f'href="{link}"' in page and 'id="inaug-code"' not in page
    r = app.test_client().get(link)
    assert r.status_code == 200 and r.headers["X-Robots-Tag"] == "noindex, nofollow"
    sheet = r.get_data(as_text=True)
    assert '<main class="sheet inaugural"' in sheet and "OF PARTICIPATION" in sheet and "OF RECOGNITION" not in sheet
    assert "&#9733; Student Delegate &middot; Online Participation &#9733;" in sheet
    assert "Student Certificate 1" in sheet and "Government College Thrissur, Kerala" in sheet
    assert "in the <b>Inauguration of Kashi Tamil Sangamam 5.0</b> on 01 January 2026" in sheet
    number = "KTS5/CP/" + "/".join(row["app_no"].split("-")[1:])
    assert f"Certificate No. <b>{number}</b>" in sheet
    assert "<b>Prof. R. Chandrasekaran</b>" in sheet and "An autonomous Institution under the Ministry of Education" in sheet
    # the seals of the other certificates do not open this one, nor this one the others
    other = _link(app, row).rsplit("/", 1)[1]
    assert app.test_client().get(f"/certificate/inaugural/{row['app_no']}/{other}").status_code == 404
    assert app.test_client().get(f"/certificate/{row['app_no']}/{link.rsplit('/', 1)[1]}").status_code == 404
    # the status page links it
    lookup = app.test_client()
    lookup.get("/status")
    with lookup.session_transaction() as s:
        token = s["_csrf"]
    status = lookup.post("/status", data={"_csrf": token, "app_no": row["app_no"], "dob": "2004-05-06",
                                          "last4": row["mobile"][-4:]}).get_data(as_text=True)
    assert f'href="{link}"' in status
    from kts.db import query
    with app.app_context():
        assert query("SELECT via FROM inaug_attendance WHERE application_id = ?", (row["id"],), one=True)["via"] == "code"


def test_no_recording_before_the_day_or_without_a_code():
    app, row = _ready(start="2099-11-28")
    student = _signed_in(app, row)
    home = student.get("/candidate/?lang=en").get_data(as_text=True)
    assert 'id="inaug-card"' in home and 'id="inaug-code"' not in home
    assert "The attendance code is announced during the live stream of the inauguration." in home
    assert "The attendance code is announced" in _record(student, "KASHI 2026") and _inaug_link(app, row) is None
    _set(app, "kts.start", "2026-01-01")
    _set(app, "inaug.code", "")
    assert 'id="inaug-code"' not in student.get("/candidate/").get_data(as_text=True)
    _record(student, "")
    assert _inaug_link(app, row) is None


@pytest.mark.parametrize("outcome, published", [("selected", "0"), ("waitlisted", "1"), ("not_selected", "1")])
def test_only_the_delegates_of_the_published_list(outcome, published):
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row, outcome=outcome, published=published)
    _set(app, "inaug.code", "KASHI")
    _set(app, "kts.start", "2026-01-01")
    student = _signed_in(app, row)
    assert 'id="inaug-card"' not in student.get("/candidate/").get_data(as_text=True)
    _record(student, "KASHI")
    from kts.db import query
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM inaug_attendance", one=True)["n"] == 0


def test_wrong_codes_are_limited():
    app, row = _ready()
    student = _signed_in(app, row)
    for _ in range(10):
        assert "This is not the attendance code." in _record(student, "WRONG")
    page = _record(student, "KASHI 2026")
    assert "Too many attempts from this connection." in page and _inaug_link(app, row) is None


def test_staff_record_and_remove_the_attendance_and_download_it():
    app, row = _ready(code="")
    _client2, other = _registered(app, n=2, ip="198.51.100.61")
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/certificate").get_data(as_text=True)
    assert "Certificates of participation (inauguration, online)" in page and "closed (no code)" in page
    with admin.session_transaction() as s:
        token = s["_csrf"]
    pasted = f"Attended: {row['app_no'].lower()}, {other['app_no']}\nKTS5-2026-999999 and nonsense"
    r = admin.post("/console/certificate", data={"_csrf": token, "action": "inaug_mark", "numbers": pasted}, follow_redirects=True)
    text = r.get_data(as_text=True)
    assert "Attendance recorded for 1 application(s)." in text and other["app_no"] in text and "KTS5-2026-999999" in text
    assert _inaug_link(app, row) and "attendance recorded for <b>1</b> delegate(s)" in text
    csv = admin.get("/console/certificate/attendance.csv")
    assert csv.status_code == 200 and csv.mimetype == "text/csv"
    lines = csv.data.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Application number,Name,College") and lines[1].startswith(f"{row['app_no']},Student Certificate 1,")
    assert ",selected,staff," in lines[1] and len(lines) == 2
    r = admin.post("/console/certificate", data={"_csrf": token, "action": "inaug_unmark", "numbers": row["app_no"]}, follow_redirects=True)
    assert "Attendance removed for 1 application(s)." in r.get_data(as_text=True) and _inaug_link(app, row) is None
    r = admin.post("/console/certificate", data={"_csrf": token, "action": "inaug_mark", "numbers": "none here"}, follow_redirects=True)
    assert "No application number" in r.get_data(as_text=True)


def test_certificates_of_participation_are_switched_off_and_on_and_a_sample_is_shown():
    app, row = _ready()
    _record(_signed_in(app, row), "KASHI 2026")
    link = _inaug_link(app, row)
    admin = _staff(app, "admin@tests.example", "admin")
    with admin.session_transaction() as s:
        token = s["_csrf"]
    admin.post("/console/certificate", data={"_csrf": token, "action": "inaug_off"})
    assert app.test_client().get(link).status_code == 404 and _inaug_link(app, row) is None
    admin.post("/console/certificate", data={"_csrf": token, "action": "inaug_on"})
    assert app.test_client().get(link).status_code == 200
    sample = admin.get("/console/certificate/sample?kind=inaugural").get_data(as_text=True)
    assert "Sample Student Name" in sample and "OF PARTICIPATION" in sample and "KTS5/CP/2026/000000" in sample
    # a withdrawal after the selection ends it
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE id = ?", (row["id"],))
    assert app.test_client().get(link).status_code == 404
    # only administrators record the attendance
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.get("/console/certificate/attendance.csv").status_code == 403

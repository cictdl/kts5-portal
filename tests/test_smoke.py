"""
End-to-end smoke test on a throw-away database:
public pages render, a student registers, checks status, the administrator
signs in, generates a question bank, opens the test window, the candidate
takes the test, the selection runs and the merit list is published.

    python -m pytest tests -q
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mkdtemp(prefix="kts5-test-")
    os.environ["KTS_DATABASE"] = str(Path(tmp) / "test.sqlite3")
    os.environ["KTS_UPLOAD_DIR"] = str(Path(tmp) / "uploads")
    os.environ["KTS_ADMIN_PASSWORD"] = "Admin@KTS5"
    from config import Config
    from kts import create_app
    app = create_app(Config)
    app.config["TESTING"] = True
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.start", "2026-01-01")
        set_setting("reg.end", "2030-12-31")
    with app.test_client() as c:
        yield c


def _csrf(client):
    client.get("/lang/en")
    client.get("/candidate/login")
    with client.session_transaction() as s:
        return s["_csrf"]


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), (200, 120, 40)).save(buf, "PNG")
    return buf.getvalue()


def test_public_pages(client):
    for path in ["/", "/about", "/programme", "/register", "/status", "/examination", "/merit-list", "/resources",
                 "/thirukkural", "/thirukkural?ch=133&l=hi", "/thirukkural/1330", "/daily-kural?l=te", "/orientation",
                 "/notices", "/schedule", "/partners", "/contact", "/healthz", "/robots.txt", "/lang/ta", "/?lang=hi"]:
        r = client.get(path, follow_redirects=True)
        assert r.status_code == 200, path


def test_daily_calendar_csv(client):
    r = client.get("/daily-kural/calendar.csv?l=hi")
    assert r.status_code == 200
    assert r.data.count(b"\n") >= 200


def test_register_and_status(client):
    token = _csrf(client)
    with client.session_transaction() as s:
        s["_captcha"] = "7"
    form = {
        "_csrf": token, "full_name": "Test Student", "gender": "F", "dob": "2004-05-06", "category": "General",
        "mobile": "9876543210", "email": "test.student@example.edu", "state": "Kerala", "college_name": "Government College Thrissur",
        "college_type": "Government college", "college_state": "Kerala", "course_level": "Undergraduate", "year_of_study": "2nd year",
        "pref_lang": "hi", "declare_true": "1", "declare_participate": "1", "declare_consent": "1", "captcha": "7",
        "photo": (io.BytesIO(_png_bytes()), "photo.png"), "idproof": (io.BytesIO(_png_bytes()), "id.png"),
    }
    r = client.post("/register", data=form, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert b"KTS5-2026-" in r.data
    # duplicate email is refused
    with client.session_transaction() as s:
        s["_captcha"] = "7"
    form["photo"] = (io.BytesIO(_png_bytes()), "photo.png")
    form["idproof"] = (io.BytesIO(_png_bytes()), "id.png")
    form["mobile"] = "9876543211"
    r = client.post("/register", data=form, content_type="multipart/form-data")
    assert r.status_code == 400
    # status check
    r = client.post("/status", data={"_csrf": token, "app_no": "KTS5-2026-000001", "dob": "2004-05-06", "last4": "3210"})
    assert b"Test Student" in r.data
    r = client.post("/status", data={"_csrf": token, "app_no": "KTS5-2026-000001", "dob": "2004-05-06", "last4": "0000"})
    assert b"Test Student" not in r.data


def test_admin_flow(client):
    token = _csrf(client)
    r = client.post("/console/login", data={"_csrf": token, "email": "admin@kts5.local", "password": "Admin@KTS5"}, follow_redirects=True)
    assert r.status_code == 200
    # forced password change
    r = client.post("/console/password", data={"_csrf": token, "current": "Admin@KTS5", "new": "Sangamam2026X", "confirm": "Sangamam2026X"}, follow_redirects=True)
    assert b"Password updated" in r.data
    assert client.get("/console/").status_code == 200
    # verify the application
    r = client.post("/console/applications/1", data={"_csrf": token, "action": "verify", "remarks": ""}, follow_redirects=True)
    assert b"verified" in r.data
    # question bank
    r = client.post("/console/questions/generate", data={"_csrf": token, "langs": ["hi", "en"], "count": "30"}, follow_redirects=True)
    assert b"Generated 60 questions" in r.data
    # open the test window now
    r = client.post("/console/exam", data={"_csrf": token, "action": "open"}, follow_redirects=True)
    assert b"open now" in r.data, r.data[:3000]
    for path in ["/console/applications", "/console/applications/export.xlsx", "/console/applications/export.csv", "/console/questions",
                 "/console/exam", "/console/selection", "/console/notices", "/console/resources", "/console/events", "/console/agencies",
                 "/console/messages", "/console/users", "/console/settings", "/console/audit", "/console/outbox", "/hub/", "/hub/tasks",
                 "/hub/documents", "/hub/calendar"]:
        assert client.get(path).status_code == 200, path
    client.post("/console/logout", data={"_csrf": token})


def test_candidate_exam(client):
    token = _csrf(client)
    r = client.post("/candidate/login", data={"_csrf": token, "app_no": "KTS5-2026-000001", "dob": "2004-05-06", "last4": "3210"}, follow_redirects=True)
    assert b"KTS5-2026-000001" in r.data and b"Welcome" in r.data
    assert client.get("/candidate/admit-card").status_code == 200
    r = client.post("/candidate/exam", data={"_csrf": token}, follow_redirects=True)
    assert b"Time left" in r.data or b"timer" in r.data
    with client.session_transaction() as s:
        cid = s["cand_id"]
    from kts.db import query
    exam = query("SELECT * FROM exam_sessions WHERE application_id = ?", (cid,), one=True)
    paper = json.loads(exam["paper_json"])
    assert len(paper) == 25
    qid = str(paper[0]["q"])
    r = client.post("/candidate/exam/save", data=json.dumps({"answers": {qid: "A"}}), content_type="application/json", headers={"X-CSRF-Token": token})
    assert r.get_json()["ok"] is True
    r = client.post("/candidate/exam/submit", data={"_csrf": token, "answers": json.dumps({str(p["q"]): "B" for p in paper})}, follow_redirects=True)
    assert b"Test submitted" in r.data
    exam = query("SELECT * FROM exam_sessions WHERE application_id = ?", (cid,), one=True)
    assert exam["status"] == "submitted" and exam["score"] is not None
    client.post("/candidate/logout", data={"_csrf": token})


def test_selection_and_merit(client):
    token = _csrf(client)
    client.post("/console/login", data={"_csrf": token, "email": "admin@kts5.local", "password": "Sangamam2026X"})
    r = client.post("/console/selection", data={"_csrf": token, "action": "run", "select_count": "1000", "wait_count": "300"}, follow_redirects=True)
    assert b"1 institutions ranked" in r.data
    r = client.post("/console/selection", data={"_csrf": token, "action": "publish", "note": "Provisional"}, follow_redirects=True)
    assert b"published" in r.data
    r = client.get("/merit-list")
    assert b"Test Student" in r.data
    assert client.get("/merit-list.csv").status_code == 200
    assert client.get("/console/selection/export.xlsx").status_code == 200

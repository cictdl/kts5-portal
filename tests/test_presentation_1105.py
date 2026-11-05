"""
The video recording of the student's one-hour presentation (1.2.158; Annexure-III C-4 of the D.O. letter of 31 October 2026, as CICT
asked on 5 November 2026: "Create a page for to submit the videos ... by the Institute in our web portal"): the institution's page ›
Presentation video, open from the start of the engagement once the nomination is submitted, as a link with its details; the
Console's list, where CICT accepts or returns each; the Excel.

    python -m pytest tests/test_presentation_1105.py -q
"""
import io

import pytest

from test_campus import _mails, _portal
from test_coordinator_nomination_1105 import _form, _selected
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff


@pytest.fixture(autouse=True)
def empty_limiter():
    """Each test signs in to the institution's page several times: the limit of codes per address and hour starts afresh."""
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()

VALID = {"title": "Thirukkural on friendship", "held_on": "2026-11-03", "minutes": "62", "audience": "140",
         "video_url": "https://drive.google.com/file/d/abc123/view", "material_url": "https://example.edu/slides.pdf",
         "note": "Held in the seminar hall.", "shared": "1"}


def _nominated(app, start="2026-11-01", due="2027-01-14"):
    from kts.db import set_setting
    with app.app_context():
        set_setting("internship.start", start)
        set_setting("present.due", due)
    inst, coord, _page, link = _selected(app)
    _page, data = _form(coord, link)
    assert coord.post("/register", data=data, content_type="multipart/form-data").status_code == 302
    with coord.session_transaction() as s:
        token = s["_csrf"]
    return inst, coord, token


def _post(coord, token, **changes):
    return coord.post("/institution/presentation", data=dict(VALID, _csrf=token, **changes))


def test_closed_before_the_nomination_and_before_the_engagement():
    from kts.db import set_setting
    from test_campus import _accepted, _coordinator
    app = _portal()
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    page = coord.get("/institution/presentation").get_data(as_text=True)
    assert "<h1>Presentation video</h1>" in page and "This page opens once the nomination of your student is submitted." in page
    assert _post(coord, token).status_code == 403
    assert "Submit the presentation video" not in coord.get("/institution").get_data(as_text=True)
    app2 = _portal()
    inst2, coord2, token2 = _nominated(app2, start="2099-01-01")
    page = coord2.get("/institution/presentation").get_data(as_text=True)
    assert "The submission opens on" in page and 'name="video_url"' not in page
    assert _post(coord2, token2).status_code == 403
    assert app.test_client().get("/institution/presentation").status_code == 302   # not signed in


def test_the_institution_submits_and_changes_the_video():
    from kts.db import query
    app = _portal()
    inst, coord, token = _nominated(app)
    page = coord.get("/institution/presentation").get_data(as_text=True)
    assert 'name="video_url"' in page and "Student: <b>Arun Student</b>" in page
    # the mistakes are named
    r = _post(coord, token, video_url="drive.google.com/x", held_on="2026-10-01", minutes="0", shared="", title="")
    body = r.get_data(as_text=True)
    assert r.status_code == 400
    for message in ("Give the full link to the video", "during the one-month engagement", "Give the duration in minutes",
                    "Confirm that CICT can open the video", "Give the title or topic"):
        assert message in body, message
    r = _post(coord, token, held_on="2099-01-01")
    assert r.status_code == 400 and "not after today" in r.get_data(as_text=True)
    # submitted
    r = _post(coord, token)
    assert r.status_code == 302 and r.headers["Location"].endswith("/institution/presentation")
    with app.app_context():
        row = query("SELECT * FROM presentations", one=True)
        app_id = query("SELECT id FROM applications", one=True)["id"]
    assert (row["institution_id"], row["application_id"], row["title"], row["minutes"], row["audience"], row["status"]) == \
        (inst["id"], app_id, "Thirukkural on friendship", 62, 140, "submitted")
    mail = _mails(app, inst["coord_email"])[-1]
    assert mail["subject"] == f"KTS 5.0: the video of the presentation is submitted ({inst['ref']})" and VALID["video_url"] in mail["body"]
    page = coord.get("/institution/presentation").get_data(as_text=True)
    assert "Submitted to CICT" in page and VALID["video_url"] in page and "Change the submission" in page
    assert "submitted" in coord.get("/institution").get_data(as_text=True).split('id="presentation"')[1][:1500]
    # changed: still one row
    assert _post(coord, token, title="Thirukkural and friendship", audience="").status_code == 302
    with app.app_context():
        rows = query("SELECT * FROM presentations")
    assert len(rows) == 1 and rows[0]["title"] == "Thirukkural and friendship" and rows[0]["audience"] is None


def test_cict_accepts_or_returns_it_in_the_console():
    from kts.db import query, set_setting
    app = _portal()
    inst, coord, token = _nominated(app)
    assert _post(coord, token).status_code == 302
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/presentations").get_data(as_text=True)
    assert "<title>Presentation videos" in page and 'href="/console/presentations">🎬 Presentation videos</a>' in page
    assert "Thirukkural on friendship" in page and 'href="https://drive.google.com/file/d/abc123/view"' in page
    assert '<div class="lbl">Submitted</div><div class="num">1</div>' in page and '<div class="lbl">Awaiting review</div><div class="num">1</div>' in page
    with app.app_context():
        pid = query("SELECT id FROM presentations", one=True)["id"]
    # a return needs a remark
    r = admin.post("/console/presentations", data={"_csrf": _token(admin), "id": str(pid), "action": "return", "note": ""}, follow_redirects=True)
    assert "Write the remark" in r.get_data(as_text=True)
    admin.post("/console/presentations", data={"_csrf": _token(admin), "id": str(pid), "action": "return", "note": "The link does not open."})
    with app.app_context():
        assert query("SELECT status, review_note FROM presentations", one=True)["status"] == "returned"
    mail = _mails(app, inst["coord_email"])[-1]
    assert "is returned" in mail["subject"] and "The link does not open." in mail["body"]
    page = coord.get("/institution/presentation").get_data(as_text=True)
    assert "Returned by CICT" in page and "The link does not open." in page and 'name="video_url"' in page
    # submitted again, then accepted: closed to changes
    assert _post(coord, token, video_url="https://youtu.be/abcdefghijk").status_code == 302
    with app.app_context():
        assert query("SELECT status, review_note FROM presentations", one=True)["review_note"] == ""
    admin.post("/console/presentations", data={"_csrf": _token(admin), "id": str(pid), "action": "accept", "note": ""})
    with app.app_context():
        assert query("SELECT status FROM presentations", one=True)["status"] == "accepted"
    assert "is accepted" in _mails(app, inst["coord_email"])[-1]["subject"]
    page = coord.get("/institution/presentation").get_data(as_text=True)
    assert "Accepted by CICT" in page and 'name="video_url"' not in page
    assert _post(coord, token).status_code == 403
    # after the last date: marked
    with app.app_context():
        set_setting("present.due", "2026-11-02")
    assert "after the last date" in admin.get("/console/presentations").get_data(as_text=True)


def test_the_scope_of_a_nodal_officer_and_the_excel():
    import openpyxl
    app = _portal()
    _inst, coord, token = _nominated(app)
    assert _post(coord, token).status_code == 302
    kerala = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    assam = _nodal(app, "nodal.assam@tests.example", ["Assam"])
    assert "Thirukkural on friendship" in kerala.get("/console/presentations").get_data(as_text=True)
    assert "Thirukkural on friendship" not in assam.get("/console/presentations").get_data(as_text=True)
    # a Nodal Officer sees, CICT reviews
    r = kerala.post("/console/presentations", data={"_csrf": _token(kerala), "id": "1", "action": "accept"})
    assert r.status_code == 403
    admin = _staff(app, "admin@tests.example", "admin")
    r = admin.get("/console/presentations.xlsx")
    assert r.status_code == 200 and "KTS5-presentation-videos.xlsx" in r.headers["Content-Disposition"]
    rows = list(openpyxl.load_workbook(io.BytesIO(r.data)).active.values)
    assert rows[0][6] == "Title of the presentation" and rows[1][6] == "Thirukkural on friendship" and rows[1][10] == VALID["video_url"]
    assert len(list(openpyxl.load_workbook(io.BytesIO(assam.get("/console/presentations.xlsx").data)).active.values)) == 1

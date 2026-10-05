"""
The research papers of the student delegates: sending, replacing, the review, the period of
submission, and who sees what.

    python -m pytest tests -q
"""
import io

import pytest

from conftest import make_app
from test_certificate import _registered, _selected, _set
from test_inaugural import _signed_in
from test_public_fixes import _staff

PDF = b"%PDF-1.4\n% a research paper of the tests\n" + b"0" * 2000
DOCX = b"PK\x03\x04" + b"\0" * 2000


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _ready(n=1, ip="198.51.100.70"):
    """A delegate of the published merit list, with a mentor in the application; the period of papers open."""
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app, n=n, ip=ip)
    _selected(app, row)
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET mentor_name = 'Dr. Mentor of the Tests', mentor_designation = 'Professor of Tamil' WHERE id = ?",
                (row["id"],))
    _set(app, "internship.start", "2026-01-01")
    _set(app, "papers.due", "2099-12-31")
    return app, row


def _form(client, **values):
    with client.session_transaction() as s:
        token = s["_csrf"]
    data = {"_csrf": token, "title": "Learning in the Thirukkural", "lang": "hi",
            "abstract": "The chapter on learning read with students of a college.\nA second paragraph.",
            "keywords": "learning, education", "couplets": "Kural 391-400", "mentor_name": "Dr. Mentor of the Tests",
            "mentor_designation": "Professor of Tamil", "mentor_email": "", "declare": "1"}
    data.update(values)
    return data


def _send(client, file=(PDF, "paper.pdf"), **values):
    data = _form(client, **values)
    if file is not None:
        data["file"] = (io.BytesIO(file[0]), file[1])
    return client.post("/candidate/paper", data=data, content_type="multipart/form-data", follow_redirects=True)


def _paper(app, row):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM papers WHERE application_id = ?", (row["id"],), one=True)


def _mails(app, email):
    from kts.db import query
    with app.app_context():
        return [r["subject"] for r in query("SELECT subject FROM outbox WHERE to_addr = ? ORDER BY id", (email,))]


def test_a_delegate_sends_the_paper_and_may_replace_it_until_the_review():
    app, row = _ready()
    student = _signed_in(app, row)
    home = student.get("/candidate/?lang=en").get_data(as_text=True)
    assert 'id="paper-card"' in home and "Not yet sent" in home and 'href="/candidate/paper"' in home
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    # the mentor of the application stands in the form
    assert 'value="Dr. Mentor of the Tests"' in page and 'value="Professor of Tamil"' in page
    assert '<option value="hi" selected>' in page
    # what is missing, too long or not a paper is refused, and nothing is kept
    for values, file, message in (({"title": ""}, (PDF, "paper.pdf"), "This field is required."),
                                  ({"abstract": "x" * 3001}, (PDF, "paper.pdf"), "This is too long."),
                                  ({"declare": ""}, (PDF, "paper.pdf"), "Confirm the declaration"),
                                  ({}, None, "Choose a PDF or Word (DOCX) file"),
                                  ({}, (b"plain text", "paper.txt"), "Choose a PDF or Word (DOCX) file"),
                                  ({}, (b"not a zip archive", "paper.docx"), "Choose a PDF or Word (DOCX) file"),
                                  ({}, (b"not a pdf at all", "paper.pdf"), "Choose a PDF or Word (DOCX) file"),
                                  ({"mentor_email": "not an address"}, (PDF, "paper.pdf"), "Enter a valid email address.")):
        assert message in _send(student, file, **values).get_data(as_text=True), message
        assert _paper(app, row) is None
    page = _send(student).get_data(as_text=True)
    assert "Your research paper has been received." in page and "Received" in page
    number = "KTS5/RP/" + "/".join(row["app_no"].split("-")[1:])
    assert number in page and "paper.pdf" in page
    paper = _paper(app, row)
    assert paper["status"] == "submitted" and paper["version"] == 1 and paper["lang"] == "hi"
    assert paper["abstract"] == "The chapter on learning read with students of a college.\nA second paragraph."
    assert _mails(app, row["email"]) [-1] == f"KTS 5.0: research paper received ({number})"
    r = student.get("/candidate/paper/file")
    assert r.status_code == 200 and r.data == PDF and "attachment" in r.headers["Content-Disposition"]
    # replaced by a Word file before the review: version 2; changes without a file keep it
    _send(student, (DOCX, "revised.docx"), title="Learning, revised")
    paper = _paper(app, row)
    assert paper["version"] == 2 and paper["file_name"] == "revised.docx" and paper["title"] == "Learning, revised"
    mails = len(_mails(app, row["email"]))
    _send(student, None, keywords="learning")
    paper = _paper(app, row)
    assert paper["version"] == 2 and paper["keywords"] == "learning" and len(_mails(app, row["email"])) == mails
    # the paper of another student is not reached: the file goes with the sign-in
    assert app.test_client().get("/candidate/paper/file").status_code == 302


def test_the_review_returns_and_accepts_the_paper():
    app, row = _ready()
    student = _signed_in(app, row)
    _send(student)
    reviewer = _staff(app, "content@tests.example", "content")
    listing = reviewer.get("/console/papers").get_data(as_text=True)
    assert "Learning in the Thirukkural" in listing and "Received, to review" in listing
    entry = reviewer.get(f"/console/papers/{row['id']}").get_data(as_text=True)
    assert "Dr. Mentor of the Tests" in entry and "Version 1 (current)" in entry
    r = reviewer.get(f"/console/papers/{row['id']}/file/1")
    assert r.status_code == 200 and r.data == PDF
    with reviewer.session_transaction() as s:
        token = s["_csrf"]
    # to return a paper, the remarks are needed
    page = reviewer.post(f"/console/papers/{row['id']}", data={"_csrf": token, "action": "return", "version": "1", "remarks": ""},
                         follow_redirects=True).get_data(as_text=True)
    assert "Write the remarks" in page and _paper(app, row)["status"] == "submitted"
    reviewer.post(f"/console/papers/{row['id']}", data={"_csrf": token, "action": "return", "version": "1",
                                                        "remarks": "Cite the commentary of Parimelazhagar."})
    assert _paper(app, row)["status"] == "returned"
    assert _mails(app, row["email"])[-1].startswith("KTS 5.0: research paper returned for changes")
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert "Returned for changes" in page and "Cite the commentary of Parimelazhagar." in page
    # the last date has passed: a returned paper is sent again all the same
    _set(app, "papers.due", "2026-01-02")
    assert "Your research paper has been received." in _send(student, (DOCX, "second.docx")).get_data(as_text=True)
    paper = _paper(app, row)
    assert paper["status"] == "submitted" and paper["version"] == 2
    # a review made on an older version is not taken
    page = reviewer.post(f"/console/papers/{row['id']}", data={"_csrf": token, "action": "accept", "version": "1"},
                         follow_redirects=True).get_data(as_text=True)
    assert "The paper changed since this page was opened" in page and _paper(app, row)["status"] == "submitted"
    reviewer.post(f"/console/papers/{row['id']}", data={"_csrf": token, "action": "accept", "version": "2", "score": "86"})
    paper = _paper(app, row)
    assert paper["status"] == "accepted" and paper["score"] == 86
    assert _mails(app, row["email"])[-1].startswith("KTS 5.0: research paper accepted")
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert "Your paper has been accepted." in page and 'name="title"' not in page
    assert _send(student).status_code == 403
    # the export of the list
    xlsx = reviewer.get("/console/papers?export=xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    csv = reviewer.get("/console/papers?export=csv&state=accepted").data.decode("utf-8-sig").splitlines()
    assert len(csv) == 2 and csv[1].startswith(f"{row['app_no']},KTS5/RP/") and ",accepted," in csv[1] and ",86," in csv[1]


def test_the_period_of_submission():
    app, row = _ready()
    student = _signed_in(app, row)
    _set(app, "internship.start", "2099-01-01")
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert "Papers can be sent from the start of the internship:" in page and 'name="title"' not in page
    assert _send(student).status_code == 403
    _set(app, "internship.start", "2026-01-01")
    _set(app, "papers.due", "2026-01-02")
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert "The submission of research papers is closed." in page and 'name="title"' not in page
    # an administrator opens it again
    _set(app, "papers.open", "1")
    assert "Your research paper has been received." in _send(student).get_data(as_text=True)
    # and closes it, also for returned papers
    from kts.db import execute
    with app.app_context():
        execute("UPDATE papers SET status = 'returned', remarks = 'More' WHERE application_id = ?", (row["id"],))
    _set(app, "papers.open", "0")
    assert _send(student).status_code == 403


@pytest.mark.parametrize("outcome, published", [("selected", "0"), ("waitlisted", "1")])
def test_only_the_delegates_send_a_paper(outcome, published):
    app = make_app(ADMIN_PASSWORD=None)
    _client, row = _registered(app)
    _selected(app, row, outcome=outcome, published=published)
    student = _signed_in(app, row)
    assert 'id="paper-card"' not in student.get("/candidate/").get_data(as_text=True)
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert "The research paper is written by the students selected as delegates of KTS 5.0." in page
    assert _send(student).status_code == 403 and _paper(app, row) is None


def test_who_sees_and_who_reviews_the_papers():
    app, row = _ready()
    _send(_signed_in(app, row))
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.get("/console/papers").status_code == 200
    page = viewer.get(f"/console/papers/{row['id']}").get_data(as_text=True)
    assert "Accept the paper" not in page
    with viewer.session_transaction() as s:
        token = s["_csrf"]
    assert viewer.post(f"/console/papers/{row['id']}", data={"_csrf": token, "action": "accept", "version": "1"}).status_code == 403
    agency = _staff(app, "agency@tests.example", "agency")
    assert agency.get("/console/papers").status_code == 403
    assert agency.get(f"/console/papers/{row['id']}/file/1").status_code == 403
    assert app.test_client().get(f"/console/papers/{row['id']}/file/1").status_code == 302


def test_the_guidelines_link_is_an_address():
    app, row = _ready()
    student = _signed_in(app, row)
    _set(app, "papers.guide_url", "javascript:alert(1)")
    assert "javascript:" not in student.get("/candidate/paper").get_data(as_text=True)
    _set(app, "papers.guide_url", "https://www.cict.in/kts5-paper-guidelines.pdf")
    _set(app, "papers.note", "Between 3,000 and 5,000 words.")
    page = student.get("/candidate/paper?lang=en").get_data(as_text=True)
    assert 'href="https://www.cict.in/kts5-paper-guidelines.pdf"' in page and "Between 3,000 and 5,000 words." in page

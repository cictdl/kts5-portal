"""
The nomination submitted by the Institutional Coordinator (1.2.158; Roles and Responsibilities B-3 of the D.O. letter of 31 October
2026, as CICT asked on 5 November 2026: "The student submission format is same change the submission by institute co-ordinator"):
the student is informed, the coordinator submits the same form from the institution's page, in the coordinator's voice; a link
mailed to a student before keeps the student's form; the reminders, the mails and the guides say so.

    python -m pytest tests/test_coordinator_nomination_1105.py -q
"""
import io
import re

import pytest

from conftest import make_app
from test_campus import _accepted, _coordinator, _mails, _portal
from test_public_fixes import PNG


@pytest.fixture(autouse=True)
def empty_limiter():
    """Each test signs in to the institution's page several times: the limit of codes per address and hour starts afresh."""
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()

NAME = "Government Arts College Thrissur"


def _selected(app):
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Arun Student", "email": "arun@student.example",
                                                    "mobile": "9123456781", "roll_no": "21ENG003", "course": "B.Sc Physics", "lang": "en"},
                      follow_redirects=True).get_data(as_text=True)
    link = re.search(r'href="(https?://[^"]+/register\?token=[A-Za-z0-9_-]+)"', page).group(1)
    return inst, coord, page, link


def _form(client, link, lang="en"):
    token_value = link.split("token=")[1]
    page = client.get(f"/register?token={token_value}&lang={lang}").get_data(as_text=True)
    with client.session_transaction() as s:
        csrf = s["_csrf"]
        s["_captcha"] = "7"
    data = {"_csrf": csrf, "token": token_value, "full_name": "Arun Student", "gender": "M", "dob": "2004-05-06", "category": "General",
            "mobile": "9123456781", "email": "arun@student.example", "state": "Kerala", "course_level": "Undergraduate",
            "year_of_study": "2nd year", "pref_lang": "en", "declare_true": "1", "declare_participate": "1", "declare_consent": "1",
            "captcha": "7", "mentor_name": "Dr. K. Mentor", "mentor_designation": "Assistant Professor of Tamil",
            "mentor_email": "mentor@tests.example", "mentor_phone": "9876012345",
            "photo": (io.BytesIO(PNG), "photo.png"), "idproof": (io.BytesIO(PNG), "id.png"), "nomination": (io.BytesIO(PNG), "nomination.png")}
    return page, data


def test_the_student_is_informed_and_the_coordinator_is_asked_to_submit():
    app = _portal()
    inst, _coord, page, _link = _selected(app)
    assert "Arun Student is selected and informed by e-mail" in page
    assert ">Submit the nomination</a>" in page and "Registration link, mailed" not in page and "<code" not in page.split('id="winner"')[1][:3000]
    student = _mails(app, "arun@student.example")[-1]
    assert student["subject"] == f"KTS 5.0: you are selected by {NAME}"
    assert "submits your nomination on the KTS 5.0 portal" in student["body"] and "/register?token=" not in student["body"]
    mail = _mails(app, inst["coord_email"])[-1]
    assert mail["subject"].startswith("KTS 5.0: submit the nomination of Arun Student")
    assert "/institution, and press" in mail["body"] and "/register?token=" not in mail["body"]


def test_the_coordinator_submits_the_nomination_on_the_same_form():
    from kts.db import query
    app = _portal()
    inst, coord, _page, link = _selected(app)
    page, data = _form(coord, link)
    # the same form, in the coordinator's voice
    assert "<h1>Nomination of the selected student</h1>" in page and f"Nomination by {NAME}: as the Institutional Coordinator" in page
    assert "The nominating institution" in page and 'value="Arun Student"' in page
    assert "On behalf of the institution, I declare that the information given above is true" in page
    assert "The student has agreed to join the Inaugural and Valedictory Functions" in page and "The student consents to CICT" in page
    assert "I declare that the information given above is true and that I am" not in page
    assert ">Submit the nomination</button>" in page and "The student&#39;s own e-mail address" in page
    for name in ("photo", "idproof", "nomination", "declare_true", "declare_participate", "declare_consent", "mentor_name"):
        assert f'name="{name}"' in page, name
    r = coord.post("/register", data=data, content_type="multipart/form-data")
    assert r.status_code == 302 and "/register/done/" in r.headers["Location"]
    done = coord.get(r.headers["Location"] + "?lang=en").get_data(as_text=True)
    assert "<b>Nomination submitted.</b> The application number of the student is" in done and 'href="/institution"' in done
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        row = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
        audit = query("SELECT * FROM audit_log WHERE action = 'nomination_submitted'", one=True)
    assert row["application_id"] == a["id"] and a["institution_id"] == inst["id"] and a["status"] == "submitted"
    assert audit is not None and audit["detail"] == a["app_no"]
    student = _mails(app, "arun@student.example")[-1]
    assert student["subject"] == f"KTS 5.0 application received: {a['app_no']}"
    assert f"Your nomination for Kashi Tamil Sangamam 5.0 (Thirukkural Payilvom) has been submitted by {NAME}." in student["body"]
    mail = _mails(app, inst["coord_email"])[-1]
    assert mail["subject"] == f"KTS 5.0: the nomination of Arun Student is submitted ({a['app_no']})"
    home = coord.get("/institution").get_data(as_text=True)
    assert "The nomination of <b>Arun Student</b> is submitted" in home and a["app_no"] in home
    assert ">Submit the presentation video</a>" in home


def test_a_student_with_the_link_has_no_form():
    """Since 1.2.182 (CICT, 12 November 2026: "Not student directly but the institution can"): a link mailed to a student before
    1.2.158, or passed on by the coordinator, opens no form without the coordinator signed in, and a form sent with it stores nothing."""
    from kts.db import query
    app = _portal()
    inst, _coord, _page, link = _selected(app)
    student = app.test_client()
    student.get("/candidate/login")   # a page with a form, for the token of the session
    page, data = _form(student, link)
    assert "<h1>Nomination of the selected student</h1>" in page and 'name="full_name"' not in page
    assert "Your Institutional Coordinator submits your nomination on the portal." in page and 'href="/institution/login"' in page
    r = student.post("/register", data=data, content_type="multipart/form-data")
    assert r.status_code == 403 and "Your Institutional Coordinator submits your nomination" in r.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM applications", one=True)["n"] == 0
        assert query("SELECT application_id FROM institutions WHERE id = ?", (inst["id"],), one=True)["application_id"] is None


def test_the_form_of_the_coordinator_in_another_language():
    from markupsafe import escape
    from kts.i18n import CATALOG
    app = _portal()
    _inst, coord, _page, link = _selected(app)
    page, _data = _form(coord, link, "hi")
    hi = CATALOG["hi"]
    for key in ("reg.nom_title", "reg.cdeclare_true", "reg.cdeclare_participate", "reg.cdeclare_consent", "reg.nom_submit"):
        assert str(escape(hi[key])) in page, key


def test_the_reminder_goes_to_the_coordinator_only():
    from kts import progress as P
    from kts.db import execute, set_setting
    from test_progress import _inst, _student
    app = make_app(ADMIN_PASSWORD=None)
    iid = _inst(app, "Reminder College", state="Kerala")
    sid = _student(app, iid, "Ravi Student")
    with app.app_context():
        set_setting("reg.end", "2026-11-20")
        execute("UPDATE institutions SET winner_id = ?, winner_at = '2026-11-18T10:00:00+00:00', reg_token = 'tok' WHERE id = ?", (sid, iid))
    with app.test_request_context():
        row = P.institutions(ids=[iid])[0]
        assert row["stage"] == "selected"
        mails = P.mails_for(row, "register")
    assert len(mails) == 1 and mails[0][0] == "coord@reminder.college.example"
    assert mails[0][1] == "Reminder – KTS 5.0: submit the nomination of Ravi Student by 20 November 2026"
    assert "the nomination of the student is not submitted yet" in mails[0][2] and "/register?token=" not in mails[0][2]


def test_the_guides_and_the_mail_of_the_selection():
    from kts.db import query
    app = _portal()
    client = app.test_client()
    hs = client.get("/how-to-submit-the-student?lang=en").get_data(as_text=True)
    assert "Submit the nomination" in hs and 'dir="ltr">Select the student</b>' in hs and 'dir="ltr">Presentation video</b>' in hs
    assert "personal registration link" not in hs and "Select and send the registration link" not in hs
    guide = client.get("/how-to-take-part?lang=en").get_data(as_text=True)
    assert "Submit the nomination by" in guide and "Your Institutional Coordinator submits your nomination on the portal" in guide
    assert "personal registration link" not in guide
    help_page = client.get("/help?lang=en").get_data(as_text=True)
    assert "Its Institutional Coordinator submits the student's nomination on the institution's page" in help_page
    for lang, words in (("hi", "संस्थान समन्वयक"), ("ta", "நிறுவன ஒருங்கிணைப்பாளர்")):
        assert words in client.get(f"/help?lang={lang}").get_data(as_text=True), lang
    inst = _accepted(app)
    with app.app_context():
        decision = query("SELECT body FROM outbox WHERE to_addr = ? AND subject LIKE '%is a Participating Institution' ORDER BY id DESC LIMIT 1",
                         (inst["coord_email"],), one=True)
    assert decision is not None and "submit the nomination there" in decision["body"]
    assert "personal registration link" not in decision["body"]

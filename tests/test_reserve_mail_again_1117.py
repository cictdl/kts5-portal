"""
A second mail to the institutions that came off the reserve list (1.2.200). CICT, 17 November 2026: "selected should be sent once
again an email stating there are selected. The reserve list entries only", with a draft of the mail; and, a little later,
"every institute is registered not selected" - asked, the mail says "registered": its subject "... is registered as a
Participating Institution" and its first sentences "Further to our earlier e-mail: your institution is registered ...".

The institutions are those that release 1.2.198 made selected (the lines "release 1.2.198" of the audit log), while they are still
selected. Once for each database, at the start of the portal; not after the last day of the nomination; not at a start at which
the first mail has just gone out. The institutions here are of the tests' own.

    python -m pytest tests/test_reserve_mail_again_1117.py -q
"""
import pytest

from conftest import make_app
from test_no_reserve_1117 import MAIL, MARK, MOVED, _app, _before, _count, _newest, _value

AGAIN = "mail.reserve_selected_again_1117"
SUBJECT = "KTS 5.0: {} is registered as a Participating Institution"
HEAD = ("Dear Sir/Madam,\n\nFurther to our earlier e-mail: your institution is registered as a Participating Institution of Kashi Tamil "
        "Sangamam 5.0 – Thirukkural Payilvom. The Nodal Institution of {} had placed it in the reserve list. The reserve list has been "
        "discontinued, and every institution that was in it is now a registered Participating Institution.\n\nReference: KTS5-HEI-")


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _live(app):
    """The database of the live site as this release finds it: 1.2.198 has made the institutions selected and told them once."""
    from kts import heis as HEI
    from kts.db import execute, init_db
    ids = _before(app)
    init_db(app)
    with app.app_context():
        assert HEI.mail_reserve_selected() == 3
        execute("DELETE FROM settings WHERE key = ?", (AGAIN,))
    return ids


def test_a_database_that_starts_with_this_release_has_nobody_to_tell():
    app = _app()
    assert _value(app, AGAIN) == "mailed 0 institutions" and _count(app, "outbox") == 0


def test_the_institutions_that_came_off_the_reserve_list_are_told_once_again():
    from kts import heis as HEI
    from kts.db import init_db
    app = _app()
    _live(app)
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_reserve_selected_again() == 3
    sent = _newest(app, "outbox", mails)
    # the reserve list entries only: the Head and the Coordinator of each, one mail where the two share an address; nobody else
    assert [(m["to_addr"], m["subject"]) for m in sent] == [
        ("head@marked.example", SUBJECT.format("Marked Reserve College")), ("coord@marked.example", SUBJECT.format("Marked Reserve College")),
        ("one@unmarked.example", SUBJECT.format("Unmarked Reserve College")), ("coord@kerala.example", SUBJECT.format("Kerala Reserve College"))]
    body = sent[0]["body"]
    assert body.startswith(HEAD.format("Puducherry")) and sent[3]["body"].startswith(HEAD.format("Kerala"))
    # ... and then the mail of a selected institution as it is: its details, the days, the steps
    assert "\nInstitution: Marked Reserve College\n" in body and "\nState/UT: Puducherry\n" in body
    assert "Please assess your interested students on the Thirukkural by " in body
    assert "and nominate one student on merit, with one Faculty Supervisor/Guide, by " in body
    assert "How to nominate: sign in to the institution's page at " in body and "/institution/login" in body
    assert "/static/KTS5-nomination-form.pdf" in body and "/how-to-submit-the-student" in body
    assert body.endswith("/institutions\n\nCentral Institute of Classical Tamil, Chennai")
    assert "has selected your institution" not in body and "is now a selected Participating Institution" not in body
    assert _value(app, AGAIN) == "mailed 3 institutions"
    # once: no second start of the portal, and no second making of the database, sends it again
    with app.app_context():
        assert HEI.mail_reserve_selected_again() == 0
    init_db(app)
    with app.app_context():
        assert HEI.mail_reserve_selected_again() == 0 and HEI.mail_reserve_selected() == 0
    assert _count(app, "outbox") == mails + 4 and _value(app, AGAIN) == "mailed 3 institutions"


def test_the_first_mail_and_the_mail_of_a_selection_are_as_they_were():
    from kts.db import query
    from test_nodal_access import _nodal
    from test_reserve_1111 import _act
    app = _app()
    _before(app)
    from kts import heis as HEI
    from kts.db import init_db
    init_db(app)
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_reserve_selected() == 3
    first = _newest(app, "outbox", mails)[0]
    assert first["subject"] == "KTS 5.0: Marked Reserve College is a Participating Institution"
    assert first["body"].startswith("Dear Sir/Madam,\n\nYour institution is now a selected Participating Institution of Kashi Tamil Sangamam")
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    with app.app_context():
        pending = query("SELECT id FROM institutions WHERE name = 'Pending College'", one=True)["id"]
    before = _count(app, "outbox")
    assert "Pending College: accepted" in _act(officer, pending, "accept").get_data(as_text=True)
    last = _newest(app, "outbox", before)[-1]
    assert last["subject"] == "KTS 5.0: Pending College is a Participating Institution"
    assert last["body"].startswith("Dear Sir/Madam,\n\nThe Nodal Institution of Puducherry has selected your institution as a Participating ")


def test_an_institution_that_is_no_longer_selected_is_left_out():
    from kts import heis as HEI
    from kts.db import execute
    app = _app()
    ids = _live(app)
    with app.app_context():
        # one declined since by its Nodal Officer, one returned to pending; an institution selected in the ordinary way is none of them
        execute("UPDATE institutions SET status = 'declined' WHERE id = ?", (ids["Marked Reserve College"],))
        execute("UPDATE institutions SET status = 'pending' WHERE id = ?", (ids["Unmarked Reserve College"],))
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_reserve_selected_again() == 1
    assert [m["to_addr"] for m in _newest(app, "outbox", mails)] == ["coord@kerala.example"]
    assert _value(app, AGAIN) == "mailed 1 institutions"


def test_the_start_of_the_portal_sends_it():
    app = _app()
    _live(app)
    mails = _count(app, "outbox")
    again = make_app(DATABASE=app.config["DATABASE"], INSTANCE_DIR=app.config["INSTANCE_DIR"], UPLOAD_DIR=app.config["UPLOAD_DIR"],
                     ADMIN_PASSWORD=None)
    sent = _newest(again, "outbox", mails)
    assert len(sent) == 4 and {m["subject"] for m in sent} == {SUBJECT.format(name) for name in MOVED}
    assert _value(again, AGAIN) == "mailed 3 institutions"
    # the start after that sends nothing
    third = make_app(DATABASE=app.config["DATABASE"], INSTANCE_DIR=app.config["INSTANCE_DIR"], UPLOAD_DIR=app.config["UPLOAD_DIR"],
                     ADMIN_PASSWORD=None)
    assert _count(third, "outbox") == mails + 4


def test_not_at_the_start_that_sends_the_first_mail():
    # a database of before 1.2.198 that starts with this release: the first mail goes out, and no second one on its heels
    from kts.db import execute
    app = _app()
    _before(app)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (AGAIN,))
    mails = _count(app, "outbox")
    again = make_app(DATABASE=app.config["DATABASE"], INSTANCE_DIR=app.config["INSTANCE_DIR"], UPLOAD_DIR=app.config["UPLOAD_DIR"],
                     ADMIN_PASSWORD=None)
    sent = _newest(again, "outbox", mails)
    assert len(sent) == 4 and all(m["subject"].endswith(" is a Participating Institution") for m in sent)
    assert _value(again, MAIL) == "mailed 3 institutions" and _value(again, MARK) == "3"
    assert _value(again, AGAIN) == "not mailed: the first mail went out at this start"


def test_two_starts_at_once_send_it_once():
    # the other start has put the mark in already: this one sends nothing
    from kts import heis as HEI
    from kts.db import execute
    app = _app()
    _live(app)
    mails = _count(app, "outbox")
    with app.app_context():
        execute("INSERT INTO settings(key, value, updated_at) VALUES(?, 'mailing', '2026-11-17T00:00:00+00:00')", (AGAIN,))
        assert HEI.mail_reserve_selected_again() == 0
    assert _count(app, "outbox") == mails and _value(app, AGAIN) == "mailing"


def test_no_mail_after_the_last_day_of_the_nomination():
    from kts import heis as HEI
    from kts.db import set_setting
    app = _app()
    _live(app)
    mails = _count(app, "outbox")
    with app.app_context():
        set_setting("reg.end", "2020-01-01")
        assert HEI.mail_reserve_selected_again() == 0
    assert _count(app, "outbox") == mails and _value(app, AGAIN) == "not mailed: after the last day of the nomination"

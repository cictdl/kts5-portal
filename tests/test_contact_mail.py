"""
The contact form: every message is kept in the console and also e-mailed to the helpdesk address.

    python -m pytest tests -q
"""
from conftest import make_app
from test_public_fixes import _write


def _mails(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM outbox ORDER BY id")


def test_a_message_of_the_contact_form_is_mailed_to_the_helpdesk():
    app = make_app(ADMIN_PASSWORD=None, BASE_URL="https://kts.example.org")
    page = _write(app, subject="Registration closed?", body="Line one.\nLine two.", phone="9000000011")
    assert "Your message has been received" in page
    mails = _mails(app)
    assert len(mails) == 1 and mails[0]["to_addr"] == "kts@cict.in"
    assert mails[0]["subject"] == "[KTS 5.0 contact] Registration closed?"
    body = mails[0]["body"]
    assert "From: A visitor <visitor@tests.example>, 9000000011" in body and "Topic: general" in body
    assert "Line one.\nLine two." in body and "https://kts.example.org/console/messages" in body
    assert "Reply to the visitor at visitor@tests.example" in body
    from kts.db import query
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM messages", one=True)["n"] == 1


def test_the_address_follows_the_setting_and_an_empty_one_sends_nothing():
    app = make_app(ADMIN_PASSWORD=None)
    from kts.db import set_setting
    with app.app_context():
        set_setting("contact.notify", "helpdesk@tests.example")
    _write(app, ip="198.51.100.61")
    assert [m["to_addr"] for m in _mails(app)] == ["helpdesk@tests.example"]
    with app.app_context():
        set_setting("contact.notify", "")
    _write(app, ip="198.51.100.62")
    assert len(_mails(app)) == 1
    with app.app_context():
        set_setting("contact.notify", "not an address")
    _write(app, ip="198.51.100.63")
    assert len(_mails(app)) == 1


def test_a_refused_message_is_not_mailed():
    app = make_app(ADMIN_PASSWORD=None)
    _write(app, ip="198.51.100.64", captcha="wrong")
    assert _mails(app) == []


def test_the_settings_page_offers_the_address():
    from kts.admin import SETTING_GROUPS
    group = [items for title, items in SETTING_GROUPS if title == "Contact"][0]
    assert [key for key, _l, _k in group] == ["contact.email", "contact.phone", "contact.address", "contact.notify"]

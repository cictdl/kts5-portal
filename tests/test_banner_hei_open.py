"""
The strip at the top of every page (version 1.2.147): "Registration is now open for Participating Institutions." in every language, instead of "Registration will open after the launch of the portal. The date is yet to be announced."; while the
registration of institutions is open, a link to it after the sentence, and a button on the students' closed registration page.

    python -m pytest tests -q
"""
from markupsafe import escape

from conftest import make_app


def _app(hei_open="1", hei_end="2099-12-31"):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        # the portal as it is now: registration of students off, the launch over and switched off, institutions registering
        for key, value in (("reg.open", "0"), ("launch.on", "0"), ("reg.end", "2099-12-31"), ("hei.open", hei_open), ("hei.end", hei_end)):
            set_setting(key, value)
    return app


def _strip(page):
    start = page.index('<div class="banner')
    return page[start:page.index("</div></div>", start)]


def test_the_sentence_in_every_language():
    from kts.i18n import CATALOG
    assert CATALOG["en"]["reg.after_launch_note"] == "Registration is now open for Participating Institutions."
    client = _app().test_client()
    for code, catalogue in CATALOG.items():
        note = catalogue["reg.after_launch_note"]
        assert "launch" not in note.lower() and (code == "en" or note != CATALOG["en"]["reg.after_launch_note"]), code
        strip = _strip(client.get(f"/?lang={code}").get_data(as_text=True))
        assert str(escape(note)) in strip, code
        assert f'<a class="banner-go" href="/institutions/register">{escape(catalogue["hei.cta"])} ' in strip, code


def test_the_link_only_while_institutions_register():
    # once the registration of institutions is off or over: the nomination by the Participating Institutions, while it is open
    # (1.2.154; the sentence alone before)
    for app in (_app(hei_open="0"), _app(hei_end="2020-01-01")):
        strip = _strip(app.test_client().get("/?lang=en").get_data(as_text=True))
        assert "Each Participating Institution nominates one student on merit through the CICT portal" in strip
        assert 'href="/how-to-submit-the-student"' in strip and 'href="/institutions/register"' not in strip
        # with the nomination closed by CICT: the sentence alone
        from kts.db import set_setting
        with app.app_context():
            set_setting("nominate.open", "0")
        strip = _strip(app.test_client().get("/?lang=en").get_data(as_text=True))
        assert "Registration is now open for Participating Institutions." in strip and "banner-go" not in strip


def test_the_students_closed_registration_page():
    page = _app().test_client().get("/register?lang=en").get_data(as_text=True)
    assert "<h2>Registration is now open for Participating Institutions.</h2>" in page and '<a class="btn saffron" href="/institutions/register">Register your institution</a>' in page
    page = _app(hei_open="0").test_client().get("/register?lang=en").get_data(as_text=True)
    assert "<h2>Registration is now open for Participating Institutions.</h2>" in page and '<a class="btn saffron" href="/institutions/register">' not in page

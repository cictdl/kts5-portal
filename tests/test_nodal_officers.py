"""
The two nodal officers of KTS 5.0 on the contact page, under the institute; kept as settings.

    python -m pytest tests -q
"""
from conftest import make_app

OFFICERS = [
    ("Dr. R. Bhuvaneshwari", "Registrar", "registrar@cict.in", "9790325518"),
    ("Dr. R. Akilan", "Programmer", "akilan.r@cict.in", "9965734497"),
]


def _card(page):
    from kts import i18n
    start = page.index("<h3>" + i18n.text("site.coordinating", "en") + "</h3>")
    return page[start:page.index("</div>", start)]


def test_the_two_officers_stand_under_the_institute():
    app = make_app(ADMIN_PASSWORD=None)
    from kts.db import nodal_officers
    with app.app_context():
        assert [(o["name"], o["designation"], o["email"], o["phone"]) for o in nodal_officers()] == OFFICERS
    card = _card(app.test_client().get("/contact?lang=en").get_data(as_text=True))
    assert "Nodal Officers of KTS 5.0" in card
    for name, designation, email, phone in OFFICERS:
        assert name in card and designation in card
        assert f'href="mailto:{email}"' in card and f'href="tel:{phone}"' in card
    # the two stand in the given order, after the office contact
    assert card.index("office@cict.in") < card.index(OFFICERS[0][0]) < card.index(OFFICERS[1][0])


def test_the_heading_is_in_the_language_of_the_page():
    from kts import i18n
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for lang in ("ta", "hi", "ur"):
        page = client.get(f"/contact?lang={lang}").get_data(as_text=True)
        assert i18n.text("site.nodal", lang) in page, lang
        assert "Dr. R. Akilan" in page


def test_an_officer_without_a_name_is_hidden_and_the_rest_edited():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("nodal.2.name", "")
        set_setting("nodal.1.phone", "044-22540125")
    card = _card(app.test_client().get("/contact?lang=en").get_data(as_text=True))
    assert "Dr. R. Akilan" not in card and "akilan.r@cict.in" not in card
    assert 'href="tel:044-22540125"' in card and "9790325518" not in card


def test_no_officer_no_heading():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("nodal.1.name", "")
        set_setting("nodal.2.name", "")
    card = _card(app.test_client().get("/contact?lang=en").get_data(as_text=True))
    assert "Nodal Officers" not in card


def test_a_database_of_an_earlier_version_receives_them():
    import sqlite3
    app = make_app(ADMIN_PASSWORD=None)
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("DELETE FROM settings WHERE key LIKE 'nodal.%'")
    conn.commit()
    conn.close()
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    card = _card(again.test_client().get("/contact?lang=en").get_data(as_text=True))
    assert all(name in card for name, _d, _e, _p in OFFICERS)


def test_the_settings_page_offers_them():
    from kts.admin import SETTING_GROUPS
    group = [items for title, items in SETTING_GROUPS if title.startswith("Nodal officers")]
    assert len(group) == 1
    assert [key for key, _label, _kind in group[0]] == [f"nodal.{n}.{f}" for n in (1, 2) for f in ("name", "designation", "email", "phone")]

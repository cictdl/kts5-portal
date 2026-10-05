"""
CICT on social media: nine links in the footer of every page and on the contact page, kept as
settings so that an administrator can change or remove one.

    python -m pytest tests -q
"""
import re

import pytest

from conftest import make_app

LINKS = [
    ("X", "https://x.com/cictofficial"),
    ("Instagram", "https://instagram.com/cict_chennai/"),
    ("YouTube", "https://youtube.com/@cicttamil"),
    ("Facebook", "https://facebook.com/chennaicict"),
    ("Threads", "https://threads.com/@cict_chennai"),
    ("WhatsApp", "https://whatsapp.com/channel/0029Vb0wjUvGOj9r7LmmgU0e"),
    ("LinkedIn", "https://linkedin.com/in/central-institute-of-classical-tamil-chennai-1b735a367/"),
    ("Telegram", "https://t.me/Classicaltamil"),
    ("Arattai", "https://aratt.ai/@cict_chennai"),
]


def _footer_links(page):
    row = page.split('class="langs social"')[1].split("</ul>")[0]
    # each link carries a small icon (an inline svg) in front of its name
    return re.findall(r'<a href="([^"]+)" target="_blank" rel="noopener noreferrer">(?:<svg class="si si-[a-z]+".*?</svg>)?([^<]+)</a>', row, re.S)


def test_the_nine_links_are_the_settings():
    from kts.db import SOCIAL_LINKS, social_links
    assert [(name, address) for _key, name, address in SOCIAL_LINKS] == LINKS
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert social_links() == LINKS


@pytest.mark.parametrize("path", ["/?lang=en", "/register?lang=ta", "/thirukkural?lang=ur", "/candidate/login?lang=hi",
                                  "/no-such-page?lang=sat"])
def test_every_page_carries_them_in_its_footer(path):
    page = make_app(ADMIN_PASSWORD=None).test_client().get(path).get_data(as_text=True)
    assert [(name, address) for address, name in _footer_links(page)] == LINKS


def test_the_contact_page_lists_them():
    from kts import i18n
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/contact?lang=en").get_data(as_text=True)
    card = page.split("<h3>" + i18n.text("site.follow", "en") + "</h3>")[1].split("</div>")[0]
    assert re.findall(r'href="([^"]+)"', card) == [address for _name, address in LINKS]


def test_an_emptied_address_hides_its_link_and_only_web_addresses_become_links():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("social.threads", "")
        set_setting("social.x", "javascript:alert(1)")
        set_setting("social.telegram", "https://t.me/another")
    page = app.test_client().get("/?lang=en").get_data(as_text=True)
    found = _footer_links(page)
    assert [name for _address, name in found] == ["Instagram", "YouTube", "Facebook", "WhatsApp", "LinkedIn", "Telegram", "Arattai"]
    assert ("https://t.me/another", "Telegram") in found and "javascript:" not in page


def test_no_link_no_row():
    from kts.db import SOCIAL_LINKS, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, _name, _address in SOCIAL_LINKS:
            set_setting(key, "")
    client = app.test_client()
    assert 'class="langs social"' not in client.get("/?lang=en").get_data(as_text=True)
    from kts import i18n
    assert i18n.text("site.follow", "en") not in client.get("/contact?lang=en").get_data(as_text=True)


def test_a_database_of_an_earlier_version_receives_the_links():
    import sqlite3
    app = make_app(ADMIN_PASSWORD=None)
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("DELETE FROM settings WHERE key LIKE 'social.%'")
    conn.commit()
    conn.close()
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    page = again.test_client().get("/?lang=en").get_data(as_text=True)
    assert [(name, address) for address, name in _footer_links(page)] == LINKS


def test_the_settings_page_offers_them():
    from kts.admin import SETTING_GROUPS
    group = [items for title, items in SETTING_GROUPS if title.startswith("Social media")]
    assert len(group) == 1 and [key for key, _label, _kind in group[0]] == [
        "social.x", "social.instagram", "social.youtube", "social.facebook", "social.threads", "social.whatsapp",
        "social.linkedin", "social.telegram", "social.arattai"]


def test_every_link_carries_the_icon_of_its_service():
    from kts.db import SOCIAL_LINKS
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/contact?lang=en").get_data(as_text=True)
    for _key, name, address in SOCIAL_LINKS:
        link = page[page.index(f'href="{address}"'):]
        link = link[:link.index("</a>")]
        assert f'<svg class="si si-{name.lower()}"' in link and 'aria-hidden="true"' in link, name
        # the icon is drawn in the page: nothing is loaded from the service
        assert "<img" not in link and "http" not in link.split(">", 1)[1]
    footer = page.split('class="langs social"')[1].split("</ul>")[0]
    assert footer.count("<svg") == len(SOCIAL_LINKS)
    # a service the portal does not know gets the plain round icon
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("social.x", "")
    page = app.test_client().get("/contact?lang=en").get_data(as_text=True)
    assert 'si-x' not in page and page.count('class="si si-') == len(SOCIAL_LINKS) * 2 - 2

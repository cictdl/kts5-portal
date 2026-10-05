"""
The earlier editions of the Sangamam, linked to the press releases of PIB, on the About and home pages.

    python -m pytest tests -q
"""
import pytest

from conftest import make_app

PIB = {
    "KTS 1.0": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1877283",
    "KTS 2.0": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1987518",
    "KTS 3.0": ("https://www-pib-gov-in.translate.goog/PressReleasePage.aspx?PRID=2103308&amp;reg=48&amp;lang=2"
                "&amp;_x_tr_sl=en&amp;_x_tr_tl=ta&amp;_x_tr_hl=ta&amp;_x_tr_pto=tc"),
    "KTS 4.0": "https://www.pib.gov.in/PressNoteDetails.aspx?id=156270&amp;NoteId=156270&amp;ModuleId=3&amp;reg=6&amp;lang=1",
}


@pytest.mark.parametrize("path", ["/about?lang=en", "/?lang=en", "/about?lang=ta", "/?lang=ur"])
def test_each_edition_opens_its_press_release(path):
    page = make_app(ADMIN_PASSWORD=None).test_client().get(path).get_data(as_text=True)
    for edition, url in PIB.items():
        link = f'href="{url}" target="_blank" rel="noopener"'
        assert link in page, (edition, path)
        assert page.index(link) < page.index(edition, page.index(link))


def test_the_about_page_names_the_days_of_each_edition():
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/about?lang=en").get_data(as_text=True)
    for text in ("KTS 1.0 · 16 Nov 2022 – 16 Dec 2022", "KTS 2.0 · 17 Dec 2023 – 30 Dec 2023",
                 "KTS 3.0 · 15 Feb 2025 – 24 Feb 2025", "KTS 4.0 · 2025 – 2026", "KTS 5.0 · 28 Nov 2026 – 12 Dec 2026"):
        assert text in page, text
    assert 'href="/schedule"><bdi>KTS 5.0' in page
    home = make_app(ADMIN_PASSWORD=None).test_client().get("/?lang=en").get_data(as_text=True)
    assert "KTS 4.0 · 2025 – 2026 ↗" in home

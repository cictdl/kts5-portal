"""
KTS 5.0 in the news (version 1.2.99): /in-the-news shows, day by day and the latest first, the press releases of
data/news.json (the headline in the visitor's language where PIB published one, and links to every language) and the
newspaper clippings of the Gallery album "KTS 5.0 in the news"; the menu, the home page, the Notices page and the sitemap
lead to it.

    python -m pytest tests -q
"""
import json

from conftest import ROOT, make_app

NEWS = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_press_release_of_the_launch_in_ten_languages():
    from kts import kural as K
    assert len(NEWS) == 1 and NEWS[0]["date"] == "2026-10-22" and NEWS[0]["kind"] == "press"
    versions = NEWS[0]["versions"]
    assert [v["lang"] for v in versions] == ["en", "as", "gu", "hi", "kn", "ml", "mr", "or", "ta", "ur"]
    assert all(v["lang"] in K.ORIENTATION_LANGS and v["title"] and v["office"].startswith("PIB ") for v in versions)
    assert all(v["url"].startswith("https://www.pib.gov.in/PressReleasePage.aspx?PRID=") and "_gl" not in v["url"] for v in versions)
    assert len({v["url"] for v in versions}) == 10


def test_the_page_day_by_day():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/in-the-news?lang=en")
    assert "KTS 5.0 in the news" in page
    # the clippings of 23 October before the press release of 22 October
    assert page.index("23 Oct 2026") < page.index("22 Oct 2026")
    day23 = page[page.index("23 Oct 2026"):page.index("22 Oct 2026")]
    assert day23.count('<figure class="photo">') == 5 and "In the newspapers" in day23 and "Dinathanthi, 23 October 2026" in day23
    day22 = page[page.index("22 Oct 2026"):]
    assert "Kashi Tamil Sangamam 5.0 to be organised from Nov 28 to Dec 12, 2026" in day22
    assert "Union Minister for Education, Shri Pralhad Joshi, launches Registration Portal for KTS 5.0" in day22
    assert "Read it in:" in day22 and day22.count('target="_blank" rel="noopener" lang=') == 10
    assert '<a href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2326724" target="_blank" rel="noopener" lang="ta">தமிழ்</a>' in day22
    # in Tamil, the Tamil headline; in Telugu, which PIB did not publish, the English one
    tamil = _page(client, "/in-the-news?lang=ta")
    assert "திருக்குறள் பயில்வோம் என்ற தலைப்பில் காசி தமிழ் சங்கமம் 5.0" in tamil and "PIB Chennai" in tamil
    telugu = _page(client, "/in-the-news?lang=te")
    assert "Kashi Tamil Sangamam 5.0 to be organised from Nov 28 to Dec 12, 2026" in telugu


def test_a_clipping_added_in_the_console_takes_its_day():
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        from kts.db import execute, utcnow
        execute("INSERT INTO gallery_photos(album, caption, taken_on, file_path, file_name, file_size, published, sort_order, "
                "created_at) VALUES(?,?,?,?,?,?,1,100,?)", ("KTS 5.0 in the news", "The Hindu, 25 October 2026: a report",
                                                          "2026-10-25", "gallery/x.jpg", "x.jpg", 10, utcnow()))
    page = _page(app.test_client(), "/in-the-news?lang=en")
    assert page.index("25 Oct 2026") < page.index("23 Oct 2026") < page.index("22 Oct 2026")
    assert "The Hindu, 25 October 2026: a report" in page


def test_the_page_is_reached_from_the_menu_the_home_page_and_the_notices():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    about = _page(client, "/about?lang=en")
    assert '<li><a href="/in-the-news">KTS 5.0 in the news</a></li>' in about
    assert 'href="/in-the-news"' in _page(client, "/?lang=en")
    assert 'href="/in-the-news"' in _page(client, "/notices?lang=en")
    assert 'href="/in-the-news"' in _page(client, "/sitemap?lang=en")
    assert "/in-the-news" in _page(client, "/search?lang=en&q=news")

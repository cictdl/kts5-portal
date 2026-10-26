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
    press = [n for n in NEWS if n["kind"] == "press"]
    assert len(press) == 1 and press[0]["date"] == "2026-10-22"
    versions = press[0]["versions"]
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
    # the report of NDTV Education of the same day, before the clippings, with its outlet and byline, without "Read it in"
    ndtv = day23[:day23.index("In the newspapers")]
    assert '<div class="card news-article"' in ndtv and '<span class="pill">NDTV Education</span>' in ndtv
    assert "Edited by Tulsi Gupta" in ndtv and "7:27 AM" in ndtv and "ndtv.com ↗" in ndtv and "Read it in" not in ndtv
    assert ('<a href="https://www.ndtv.com/education/from-thirukkural-to-classrooms-kashi-tamil-sangamam-5-0-opens-registration-12223050"'
            ' target="_blank" rel="noopener">From Thirukkural To Classrooms: Kashi Tamil Sangamam 5.0 Opens Registration</a>') in ndtv
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


def test_the_reports_of_the_web():
    # a news report is one version, in the language of its outlet, linked to the outlet's own page (1.2.100); DD News,
    # Dinamalar, Daily Thanthi and Akashvani News (1.2.101); the file in the order of the days and the hours
    reports = [n for n in NEWS if n["kind"] == "article"]
    assert [n["source"] for n in reports] == ["DD News", "Dinamalar", "Daily Thanthi", "NDTV Education", "Akashvani News"]
    hosts = {"DD News": "https://ddnews.gov.in/en/", "Dinamalar": "https://www.dinamalar.com/",
             "Daily Thanthi": "https://www.dailythanthi.com/", "NDTV Education": "https://www.ndtv.com/",
             "Akashvani News": "https://newsonair.gov.in/"}
    for n in reports:
        assert len(n["versions"]) == 1 and n["versions"][0]["url"].startswith(hosts[n["source"]])
        assert "translate.goog" not in n["versions"][0]["url"] and n["versions"][0]["time"]
    assert [n["date"] for n in NEWS] == sorted(n["date"] for n in NEWS)
    assert len({n["key"] for n in NEWS}) == len(NEWS)


def test_the_reports_of_22_to_25_october_on_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/in-the-news?lang=en")
    assert page.index("25 Oct 2026") < page.index("23 Oct 2026") < page.index("22 Oct 2026")
    day25 = page[page.index("25 Oct 2026"):page.index("23 Oct 2026")]
    assert '<span class="pill">Akashvani News</span>' in day25 and "8:55 AM" in day25 and "newsonair.gov.in ↗" in day25
    day23 = page[page.index("23 Oct 2026"):page.index("22 Oct 2026")]
    # the Tamil report in Tamil, marked as Tamil, before NDTV (3:46 and 7:27 in the morning)
    assert day23.index("Daily Thanthi") < day23.index("NDTV Education")
    assert '<h3 style="margin:0;line-height:1.4" lang="ta" dir="auto"><a href="https://www.dailythanthi.com/' in day23
    day22 = page[page.index("22 Oct 2026"):]
    assert day22.index("Press release") < day22.index("DD News") < day22.index("Dinamalar")
    assert "Kashi Tamil Sangamam 5.0 to Be Held from November 28 to December 12" in day22 and "ddnews.gov.in ↗" in day22
    assert "காசி தமிழ் சங்கமம் நவ., 28ல் தொடக்கம்" in day22 and "dinamalar.com ↗" in day22

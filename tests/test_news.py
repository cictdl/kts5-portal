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


def test_the_press_release_of_the_launch_in_eleven_languages():
    # ten languages in 1.2.99, Punjabi (PIB Chandigarh) in 1.2.112
    from kts import kural as K
    press = [n for n in NEWS if n["kind"] == "press"]
    assert len(press) == 1 and press[0]["date"] == "2026-10-22"
    versions = press[0]["versions"]
    assert [v["lang"] for v in versions] == ["en", "as", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "ur"]
    assert all(v["lang"] in K.ORIENTATION_LANGS and v["title"] and v["office"].startswith("PIB ") for v in versions)
    assert all(v["url"].startswith("https://www.pib.gov.in/PressReleasePage.aspx?PRID=") and "_gl" not in v["url"] for v in versions)
    assert len({v["url"] for v in versions}) == 11


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
    # the 11 of PIB and, since 1.2.141, the English and Hindi of Akashvani News and of DD News
    assert "Read it in:" in day22 and day22.count('target="_blank" rel="noopener" lang=') == 15
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
    # Dinamalar, Daily Thanthi and Akashvani News (1.2.101); Careers360, Akashvani News, DD India, Punjab Kesari (IANS),
    # ETV Bharat and Akashvani News again (1.2.112); Awaz-The Voice, REVOI, The New Indian Express, The Indian Express, DT Next,
    # Education Post, Hindustan Times, Organiser, Jagran Josh and Hindu Tamil Thisai (1.2.127); 23 more of 22-26 October and the
    # Hindi of Akashvani News and DD News as versions in Hindi, on the same sites (1.2.141); the file in the order of the days and the hours
    reports = [n for n in NEWS if n["kind"] == "article"]
    assert [n["source"] for n in reports] == ["Dainik Bhaskar", "Akashvani News", "Akashvani News", "Bhaskar Hindi", "ThePrint", "Careers360", "Akashvani News", "DD News", "DD India", "ThePrint Hindi", "Awaz-The Voice", "Punjab Kesari", "REVOI", "EdexLive", "ETV Bharat", "Hindu Tamil Thisai", "Dinamalar", "Dinamalar", "The Hindu", "The New Indian Express", "Public TV", "Dinamalar TV", "Dainik Jagran", "The Indian Express", "Daily Thanthi", "Dinamani", "NDTV Education", "DT Next", "Hindu Tamil Thisai", "Education Post", "Hindustan Times", "News18", "Organiser", "CNBCTV18", "Jagran Josh", "Times Now Tamil", "Dinamalar Kalvimalar", "Eenadu", "Akashvani News", "Akashvani News", "Akashvani News", "Prabhat Khabar", "Amar Ujala", "Hindu Tamil Thisai"]
    hosts = {"DD News": "https://ddnews.gov.in/", "Dinamalar": "https://www.dinamalar.com/",
             "Daily Thanthi": "https://www.dailythanthi.com/", "NDTV Education": "https://www.ndtv.com/",
             "Akashvani News": "https://newsonair.gov.in/", "Careers360": "https://news.careers360.com/",
             "DD India": "https://ddindia.co.in/", "Punjab Kesari": "https://english.punjabkesari.com/",
             "ETV Bharat": "https://www.etvbharat.com/ta/", "Awaz-The Voice": "https://www.hindi.awazthevoice.in/",
             "REVOI": "https://hindi.revoi.in/", "The New Indian Express": "https://www.newindianexpress.com/",
             "Education Post": "https://educationpost.in/", "Organiser": "https://organiser.org/",
             "Hindu Tamil Thisai": "https://www.hindutamil.in/", "Hindustan Times": "https://www.hindustantimes.com/",
             "The Indian Express": "https://indianexpress.com/", "DT Next": "https://www.dtnext.in/",
             "Jagran Josh": "https://www.jagranjosh.com/",
             # 1.2.141
             "Dainik Bhaskar": "https://www.bhaskar.com/", "Bhaskar Hindi": "https://www.bhaskarhindi.com/", "ThePrint": "https://theprint.in/",
             "ThePrint Hindi": "https://hindi.theprint.in/", "EdexLive": "https://www.edexlive.com/", "The Hindu": "https://www.thehindu.com/",
             "Public TV": "https://publictv.in/", "Dinamalar TV": "https://www.dinamalar.com/dinamalartv/", "Dainik Jagran": "https://www.jagran.com/",
             "Dinamani": "https://www.dinamani.com/", "News18": "https://www.news18.com/", "CNBCTV18": "https://www.cnbctv18.com/",
             "Times Now Tamil": "https://tamil.timesnownews.com/", "Dinamalar Kalvimalar": "https://www.dinamalar.com/news/kalvimalar-news-en/",
             "Eenadu": "https://www.eenadu.net/", "Prabhat Khabar": "https://www.prabhatkhabar.com/", "Amar Ujala": "https://www.amarujala.com/"}
    for n in reports:
        assert len({v["lang"] for v in n["versions"]}) == len(n["versions"]) <= 2, n["key"]
        for v in n["versions"]:
            assert v["url"].startswith(hosts[n["source"]]) and "translate.goog" not in v["url"] and v["time"]
            assert "?" not in v["url"] and "fbclid" not in v["url"]
    assert [n["key"] for n in reports if len(n["versions"]) == 2] == ["air-2026-10-22-kts5-portal", "ddnews-2026-10-22-kts5", "air-2026-10-25-kts5"]
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


INSTAGRAM = "https://www.instagram.com/reel/Deg6QD_A4F3/"
FACEBOOK = "https://www.facebook.com/reel/1797045828084084"


def test_the_reel_of_15_october():
    # the reel of the official Kashi Tamil Sangamam account: on the home page from 1.2.79 (Instagram) and 1.2.80
    # (Facebook) to 1.2.104, in KTS 5.0 in the news on its day since 1.2.105
    reels = [n for n in NEWS if n["kind"] == "reel"]
    assert len(reels) == 1 and NEWS[1] is reels[0]
    reel = reels[0]
    assert reel["date"] == "2026-10-15" and reel["account"] == "ktsangamam" and reel["source"] == "Kashi Tamil Sangamam"
    assert reel["versions"][0]["url"] == INSTAGRAM and reel["facebook"] == FACEBOOK
    assert "?" not in INSTAGRAM and "?" not in FACEBOOK
    assert reel["tags"] == ["KashiTamilSangamam5", "KTS5", "VanakkamKashi", "UnityInDiversity", "EkBharatShreshthaBharat"]
    assert not (ROOT / "data" / "home_reel.json").exists()


def test_the_facebook_button_is_the_instagram_one_with_the_other_name():
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert catalogue["home.reel_watch_fb"] == catalogue["home.reel_watch"].replace("Instagram", "Facebook"), code


def test_the_reel_is_on_the_news_page_and_no_longer_on_the_home_page():
    from markupsafe import escape
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/in-the-news?lang={code}")
        card = page[page.index('<div class="card news-reel"'):]
        card = card[:card.index("</div>")]
        assert (f'<a href="{INSTAGRAM}" target="_blank" rel="noopener">{escape(catalogue["home.reel_title"])}</a></h3>') in card, code
        assert (f'<a class="btn saffron sm" href="{INSTAGRAM}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert (f'<a class="btn sm reel-fb" href="{FACEBOOK}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_fb"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert '<span lang="en" dir="ltr">Instagram · @ktsangamam · Facebook</span>' in card
        assert "#KashiTamilSangamam5 #KTS5 #VanakkamKashi #UnityInDiversity #EkBharatShreshthaBharat" in card
        assert str(escape("“India’s diversity is best experienced through its people, languages and traditions.”")) in card
        # links only: nothing of Instagram or Facebook is loaded by the page
        for gone in ("<iframe", "instagram.com/embed", "cdninstagram", "connect.facebook.net", "facebook.com/plugins", "fbcdn"):
            assert gone not in page, (code, gone)
        home = _page(client, f"/?lang={code}")
        assert INSTAGRAM not in home and FACEBOOK not in home and 'aria-labelledby="home-reel-title"' not in home, code
    # on its own day, the earliest, after those of 22 October
    page = _page(client, "/in-the-news?lang=en")
    assert page.index("22 Oct 2026") < page.index("15 Oct 2026") < page.index('<div class="card news-reel"')


def test_the_thirukkural_in_uzbek_in_the_news():
    # 1.2.106: the card of the home page (1.2.102) in the news too, on the day of the post of ANI, 31 August 2026
    from markupsafe import escape
    from kts.i18n import CATALOG
    uz = json.loads((ROOT / "data" / "home_uzbek.json").read_text(encoding="utf-8"))
    posts = [n for n in NEWS if n["kind"] == "post"]
    assert len(posts) == 1 and NEWS[0] is posts[0] and posts[0]["date"] == "2026-08-31"
    assert [lk["url"] for lk in posts[0]["links"]] == [uz["x"]["url"], uz["youtube"]["url"]]
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/in-the-news?lang={code}")
        card = page[page.index('<div class="card news-post"'):]
        card = card[:card.index("</div>")]
        assert f'target="_blank" rel="noopener">{escape(catalogue["home.uz_title"])}</a></h3>' in card, code
        before, after = catalogue["home.uz_text"].split("{date}")
        assert str(escape(before)) in card and str(escape(after)) in card and "{date}" not in card, code
        assert (f'<a class="btn sm saffron" href="{uz["x"]["url"]}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_x"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert (f'<a class="btn sm reel-yt" href="{uz["youtube"]["url"]}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_yt"])} <span aria-hidden="true">↗</span></a>') in card, code
        for gone in ("<iframe", "platform.twitter.com", "twimg.com", "youtube.com/embed"):
            assert gone not in page, (code, gone)
    page = _page(client, "/in-the-news?lang=en")
    assert '<span lang="en" dir="ltr">X · @ANI</span> · <bdi>31 Aug 2026</bdi> · <span lang="en" dir="ltr">YouTube · @cicttamil</span> · <bdi>23 Sep 2026</bdi>' in page
    assert "the first meeting was held online on 23 Sep 2026." in page
    # the latest day first: its day, 31 August, after that of the reel, 15 October
    assert page.index('<div class="card news-reel"') < page.rindex("31 Aug 2026") and \
        page.index('<div class="card news-reel"') < page.index('<div class="card news-post"')
    # and still on the home page
    assert "home-uzbek" in _page(client, "/?lang=en")


def test_the_news_added_on_27_october():
    # the Punjabi release of PIB and six reports of 22 and 24 October (1.2.112), each in its day, in the order of the hours
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/in-the-news?lang=en")
    assert page.index("25 Oct 2026") < page.index("24 Oct 2026") < page.index("23 Oct 2026") < page.index("22 Oct 2026")
    day24 = page[page.index("24 Oct 2026"):page.index("23 Oct 2026")]
    assert day24.count('<div class="card news-article"') == 3 and "1:02 PM" in day24 and "newsonair.gov.in ↗" in day24   # 3 since 1.2.141
    assert ('<a href="https://newsonair.gov.in/registration-opens-for-fifth-edition-of-kashi-tamil-sangamam/" target="_blank"'
            ' rel="noopener">Registration Opens for Fifth Edition of Kashi Tamil Sangamam</a>') in day24
    day22 = page[page.index("22 Oct 2026"):]
    assert day22.count('<div class="card news-article"') == 23 and day22.count('<div class="card news-press"') == 1   # 23 since 1.2.141
    marks = ["Press release", "Careers360", "4:10 PM", "DD News", "DD India", "Punjab Kesari", "ETV Bharat", "Dinamalar"]
    assert [day22.index(m) for m in marks] == sorted(day22.index(m) for m in marks)
    assert "<bdi>Soumi Roy</bdi> · 3:59 PM" in day22 and "<bdi>IANS</bdi> · 5:11 PM" in day22
    assert "english.punjabkesari.com ↗" in day22 and "ddindia.co.in ↗" in day22 and "news.careers360.com ↗" in day22
    assert '<h3 style="margin:0;line-height:1.4" lang="ta" dir="auto"><a href="https://www.etvbharat.com/ta/' in day22
    assert 'href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2327441"' in day22
    # in Punjabi, the Punjabi headline of PIB Chandigarh
    punjabi = _page(client, "/in-the-news?lang=pa")
    assert "ਕਾਸ਼ੀ ਤਮਿਲ ਸੰਗਮਮ 5.0 ਦਾ ਆਯੋਜਨ" in punjabi and "PIB Chandigarh" in punjabi


def test_the_news_added_on_30_october():
    # the reports sent by the user (Hindu Tamil Thisai of 30 October, its link without the Facebook tracking parameter;
    # The New Indian Express; Hindustan Times; The Indian Express; DT Next; Jagran Josh) and those of 22 and 23 October
    # found on the web (1.2.127), each in its day, in the order of the hours
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/in-the-news?lang=en")
    assert page.index("30 Oct 2026") < page.index("25 Oct 2026")
    day30 = page[page.index("30 Oct 2026"):page.index("29 Oct 2026")]
    assert day30.count('<div class="card news-article"') == 1 and "hindutamil.in ↗" in day30
    assert ('<h3 style="margin:0;line-height:1.4" lang="ta" dir="auto"><a href="https://www.hindutamil.in/news/india/'
            'thirukkural-in-23-languages-at-kashi-tamil-sangamam-50-event"') in day30
    assert "<bdi>ஆர்.ஷபிமுன்னா</bdi> · 10:18 AM" in day30 and "fbclid" not in page
    day23 = page[page.index("23 Oct 2026"):page.index("22 Oct 2026")]
    marks = ["The Indian Express", "Daily Thanthi", "NDTV Education", "DT Next", "Education Post", "Hindustan Times",
             "Organiser", "Jagran Josh"]
    assert [day23.index(m) for m in marks] == sorted(day23.index(m) for m in marks)
    assert "<bdi>Pragya Kumari</bdi> · 8:36 AM" in day23 and "organiser.org ↗" in day23
    assert "<bdi>Sanjay Maurya</bdi> · 9:39 AM" in day23 and "hindustantimes.com ↗" in day23
    assert "<bdi>Express News Service</bdi> · 2:43 AM" in day23 and "indianexpress.com ↗" in day23
    assert "<bdi>DT NEXT Bureau</bdi> · 7:37 AM" in day23 and "dtnext.in ↗" in day23
    assert "<bdi>Apeksha Agarwal</bdi> · 11:49 AM" in day23 and "jagranjosh.com ↗" in day23
    day22 = page[page.index("22 Oct 2026"):]
    marks = ["DD India", "Awaz-The Voice", "Punjab Kesari", "REVOI", "ETV Bharat", "Dinamalar", "The New Indian Express"]
    assert [day22.index(m) for m in marks] == sorted(day22.index(m) for m in marks)
    assert '<h3 style="margin:0;line-height:1.4" lang="hi" dir="auto"><a href="https://www.hindi.awazthevoice.in/' in day22
    assert '<h3 style="margin:0;line-height:1.4" lang="hi" dir="auto"><a href="https://hindi.revoi.in/' in day22
    assert "<bdi>Express News Service</bdi> · 8:51 PM" in day22 and "newindianexpress.com ↗" in day22



def test_the_news_added_on_3_november():
    # 1.2.141: the posts of the official accounts on social media (the Ministry of Education, the Minister, PIB, CICT and Kashi
    # Tamil Sangamam), one card per announcement with a button for each network, each at its hour among the reports of the day
    # (the hour of a post on X read from its id); the Hindi reports of Akashvani News and DD News, in Hindi, as versions
    social = [n for n in NEWS if n["kind"] == "social"]
    assert len(social) == 21 and sum(len(n["links"]) for n in social) == 39
    assert {n["source"] for n in social} == {"CICT", "Kashi Tamil Sangamam", "Ministry of Education", "Press Information Bureau",
                                             "Shri Pralhad Joshi, Union Minister of Education", "PIB Chennai"}
    assert all(n["gov"] for n in social if n["source"] not in ("CICT", "Kashi Tamil Sangamam")) and \
        not any(n.get("gov") for n in social if n["source"] in ("CICT", "Kashi Tamil Sangamam"))
    for n in social:
        assert all(l["url"].startswith(("https://x.com/", "https://www.facebook.com/", "https://www.instagram.com/", "https://t.me/",
                                        "https://www.threads.com/")) for l in n["links"])
        assert len(n["quote"]) <= 182 and n["versions"][0]["url"] == n["links"][0]["url"]
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/in-the-news?lang=en")
    day22 = page[page.index("22 Oct 2026"):page.index("15 Oct 2026")]
    at = day22.index("The Ministry of Education: the Union Minister of Education launches the registration portal")
    moe = day22[day22.rindex('<div class="card news-social"', 0, at):][:1600]
    assert '<span class="pill saffron">Ministry of Education</span> <span lang="en" dir="ltr">@EduMinOfIndia</span> · 3:24 PM' in moe
    assert '<a class="btn sm secondary" lang="en" dir="ltr" title="@EduMinOfIndia" href="https://x.com/EduMinOfIndia/status/2113207438438744542"' in moe
    assert 'rel="noopener">X <span aria-hidden="true">↗</span></a>' in moe and "“Union Education Minister, Shri @JoshiPralhad launches registration portal" in moe
    # in the order of the hours: the Minister at 12:26 PM, PIB's release at 2:24 PM, PIB India at 3:04 PM, the Ministry at 3:24 PM
    marks = ["@JoshiPralhad</span> · 12:26 PM", "Press release", "@PIB_India</span> · 3:04 PM", "@EduMinOfIndia</span> · 3:24 PM",
             "@EduMinOfIndia</span> · 6:45 PM", "@PIBChennai</span> · 7:08 PM"]
    assert [day22.index(m) for m in marks] == sorted(day22.index(m) for m in marks)
    # a card with five networks
    nov2 = page[page.index("2 Nov 2026"):page.index("1 Nov 2026")]
    assert all(f'>{site} <span aria-hidden="true">↗</span></a>' in nov2 for site in ("X", "Facebook", "Instagram", "Threads", "Telegram"))
    assert "@cict_chennai" in nov2 and "@Classicaltamil" in nov2
    assert '<p class="reel-quote" style="margin:6px 0 0" lang="ta" dir="auto">“5-வது காசி தமிழ்ச் சங்கமம் (KTS 5.0)' in day22
    assert "platform.twitter.com" not in page and "connect.facebook.net" not in page and "<iframe" not in page
    # in Hindi, the Hindi headline of Akashvani News and of DD News
    hindi = _page(client, "/in-the-news?lang=hi")
    assert "शिक्षा मंत्री प्रल्हाद जोशी ने काशी तमिल संगमम् के पांचवें संस्करण के लिए पंजीकरण पोर्टल का शुभारंभ किया" in hindi
    assert "काशी तमिल संगमम 5.0 का रजिस्ट्रेशन पोर्टल लॉन्च, 28 नवंबर से 12 दिसंबर तक होगा आयोजन" in hindi

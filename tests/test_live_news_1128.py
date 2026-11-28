"""
KTS 5.0 in the news: the live stream of the inauguration on Doordarshan National (1.2.234). CICT, 28 November 2026:
"https://www.youtube.com/watch?v=0bV8uPVhtbg this link put on the news". A card of its own on 28 November, as the posts of the official
accounts before it.

    python -m pytest tests/test_live_news_1128.py -q
"""
import json

from conftest import ROOT, make_app

URL = "https://www.youtube.com/watch?v=0bV8uPVhtbg"
TITLE = "DD National live: the Hon'ble Vice-President, Shri C. P. Radhakrishnan, inaugurates Kashi Tamil Sangamam 5.0 in Varanasi"
QUOTE = ("Hon'ble Vice President of India Shri C. P. Radhakrishnan inaugurates the 5th edition of Kashi Tamil Sangamam in Varanasi, "
         "celebrating the enduring cultural, linguistic and civilisational bonds between Kashi and Tamil Nadu.")


def test_the_card():
    news = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
    (card,) = [n for n in news if URL in json.dumps(n)]
    assert card == {"key": "social-2026-11-28-101", "date": "2026-11-28", "kind": "social", "source": "DD National", "gov": True,
                    "title": TITLE, "quote": QUOTE, "quote_lang": "en",
                    "links": [{"site": "YouTube", "account": "DoordarshanNational", "date": "2026-11-28", "kind": "video", "url": URL}],
                    "versions": [{"lang": "en", "title": TITLE, "url": URL, "time": "9:40 AM"}]}
    # the first of its day; since 1.2.239 the Ministry's own stream (12:30 PM) after it, the last
    assert [n["key"] for n in news if n["date"] == "2026-11-28"] == [card["key"], "social-2026-11-28-106"]
    assert news[-1]["date"] == "2026-11-28" and [n["date"] for n in news] == sorted(n["date"] for n in news)
    assert len({n["key"] for n in news}) == len(news) == 168      # 163: three reports of Hindu Tamil Thisai, 1.2.235; 168 since 1.2.239


def test_on_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in ("en", "ta", "hi"):
        page = client.get(f"/in-the-news?lang={code}").get_data(as_text=True)
        at = page.index(f'href="{URL}"')
        block = page[page.rindex('<div class="card news-social"', 0, at):page.index("</div>", at)]
        # an official account (saffron), its handle and hour; the headline; the stream's own words; the button "YouTube ▶"
        assert '<span class="pill saffron">DD National</span> <span lang="en" dir="ltr">@DoordarshanNational</span> · 9:40 AM' in block, code
        assert f'<h3 style="margin:0;line-height:1.4" lang="en" dir="ltr"><a href="{URL}" target="_blank" rel="noopener">{TITLE.replace("&#39;", "&#39;").replace(chr(39), "&#39;")}</a></h3>' in block, code
        assert QUOTE.replace("'", "&#39;") in block and "YouTube ▶" in block, code
        # 28 November first, the latest of the days
        assert page.index(URL) < page.index("PRID=2342468"), code

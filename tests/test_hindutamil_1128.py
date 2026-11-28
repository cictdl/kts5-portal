"""
KTS 5.0 in the news: the reports of Hindu Tamil Thisai on its topic "காசி தமிழ் சங்கமம்" (1.2.235). CICT, 28 November 2026: "Add news
from காசி தமிழ் சங்கமம் https://www.hindutamil.in/topic/...". Three reports not on the page before, each at its hour (IST), with its
byline: 3, 24 and 26 November 2026; the three of 22, 23 and 30 October were there already.

    python -m pytest tests/test_hindutamil_1128.py -q
"""
import datetime as dt
import json

from conftest import ROOT, make_app

NEW = {
    "hindutamil-2026-11-03-kts5": ("2026-11-03", "4:57 PM", "ஜெ.கு.லிஸ்பன் குமார்",
                                   "“தமிழகம் - காசி இடையே பல நூற்றாண்டுகளாக கலாச்சார தொடர்பு” - ஆளுநர் அர்லேகர் பெருமிதம்",
                                   "https://www.hindutamil.in/news/tamilnadu/cultural-connection-between-tn-and-kashi-has-existed-for-centuries-governor-arlekar-pride"),
    "hindutamil-2026-11-24-kts5": ("2026-11-24", "7:08 AM", "ஆர்.ஷபிமுன்னா",
                                   "காசி தமிழ் சங்கமம் 5.0: விழிப்புணர்வு ஏற்படுத்த வாராணசியில் பிஎச்யு சார்பில் ரங்கோலி, புகைப்பட போட்டி",
                                   "https://www.hindutamil.in/news/india/kashi-tamil-sangamam-bhu-organizes-rangoli-photography-contest-in-varanasi"),
    "hindutamil-2026-11-26-kts5": ("2026-11-26", "5:27 PM", "மு.வேல்சங்கர்",
                                   "காசி தமிழ் சங்கமம் 5.0: சென்னையில் சிறப்பு ரயிலை ஆளுநர் அர்லேகர் தொடங்கி வைத்தார்",
                                   "https://www.hindutamil.in/news/tamilnadu/governor-arlekar-flags-off-special-train-in-chennai-for-kashi-tamil-sangamam-50"),
}


def test_the_reports():
    news = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
    by = {n["key"]: n for n in news}
    for key, (day, time, byline, title, url) in NEW.items():
        assert by[key] == {"key": key, "date": day, "kind": "article", "source": "Hindu Tamil Thisai",
                           "versions": [{"lang": "ta", "byline": byline, "title": title, "time": time, "url": url}]}, key
        # each day in the order of its hours
        times = [dt.datetime.strptime(n["versions"][0]["time"], "%I:%M %p") for n in news if n["date"] == day and n["versions"][0].get("time")]
        assert times == sorted(times), day
    # every report of the site once; six of KTS 5.0 in all
    urls = [v["url"] for n in news for v in n["versions"] if "hindutamil.in" in v["url"]]
    assert len(urls) == len(set(urls)) == 6
    assert len(news) == len({n["key"] for n in news}) == 163 and [n["date"] for n in news] == sorted(n["date"] for n in news)


def test_on_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in ("en", "ta"):
        page = client.get(f"/in-the-news?lang={code}").get_data(as_text=True)
        for key, (_day, time, byline, title, url) in NEW.items():
            at = page.index(f'href="{url}"')
            block = page[page.rindex('<div class="card news-article"', 0, at):page.index("</div>", at)]
            assert f'<span class="pill">Hindu Tamil Thisai</span> <bdi>{byline}</bdi> · {time}' in block, (code, key)
            assert f'<h3 style="margin:0;line-height:1.4" lang="ta" dir="auto"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>' in block, (code, key)
            assert "hindutamil.in ↗" in block, (code, key)

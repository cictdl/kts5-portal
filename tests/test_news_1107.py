"""
The news of 3 and 4 November 2026 on the registration of the Higher Educational Institutions for KTS 5.0 (1.2.166; CICT, 7 November
2026: "add the news"): three reports and 18 posts on social media, links only.

    python -m pytest tests/test_news_1107.py -q
"""
import datetime as dt
import json
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
NEWS = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NEW = [n for n in NEWS if n["date"] in ("2026-11-03", "2026-11-04")]


def test_the_entries():
    social = [n for n in NEW if n["kind"] == "social"]
    reports = [n for n in NEW if n["kind"] == "article"]
    assert len(NEW) == 21 and len(social) == 18 and len(reports) == 3
    assert [n["source"] for n in reports] == ["News9", "TV9 Bangla", "TV9 Hindi"]
    assert {n["source"] for n in social} == {
        "MyGov Hindi", "PIB Karnataka", "PIB Andhra Pradesh", "PIB Sri Vijaya Puram", "PIB Bihar", "Akashvani News Vijayawada",
        "DD News Uttar Pradesh", "DD India", "DD Tamil", "PIB Chandigarh", "TV9 Gujarati", "TV9 Marathi", "CBC Hyderabad",
        "DD Sahyadri", "PIB Bhubaneswar", "TV9 Telugu", "TV9 Tamil", "TV9 Malayalam"}
    # the media houses are not of the Government
    assert {n["source"] for n in social if not n["gov"]} == {"TV9 Gujarati", "TV9 Marathi", "TV9 Telugu", "TV9 Tamil", "TV9 Malayalam"}
    assert len({n["key"] for n in NEWS}) == len(NEWS)
    for n in social:
        link = n["links"][0]
        assert len(n["links"]) == 1 and n["versions"][0]["url"] == link["url"] and n["quote"] == ""
        assert "?" not in link["url"] and link["url"].startswith(("https://x.com/", "https://www.instagram.com/p/", "https://www.facebook.com/share/"))
        # the hour of a post on X is read from its id
        if link["site"] == "X":
            when = dt.datetime.fromtimestamp(((int(link["url"].rsplit("/", 1)[1]) >> 22) + 1288834974657) / 1000, IST)
            assert n["date"] == when.date().isoformat() and n["versions"][0]["time"] == when.strftime("%I:%M %p").lstrip("0")
            assert link["account"] == link["url"].split("/")[3]
        else:
            assert link["account"] == ""
    # day by day, each in the order of its hours; the file stays in the order of the days
    assert [n["date"] for n in NEWS] == sorted(n["date"] for n in NEWS)
    for day in ("2026-11-03", "2026-11-04"):
        times = [dt.datetime.strptime(n["versions"][0]["time"], "%I:%M %p") for n in NEW if n["date"] == day and n["versions"][0]["time"]]
        assert times == sorted(times), day


def test_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/in-the-news?lang=en").get_data(as_text=True)
    nov4 = page[page.index("04 Nov 2026"):page.index("03 Nov 2026")]
    nov3 = page[page.index("03 Nov 2026"):page.index("02 Nov 2026")]
    assert nov3.count('<div class="card news-social"') == 10 and nov4.count('<div class="card news-social"') == 8
    assert nov4.count('<div class="card news-article"') == 3 and "news9live.com ↗" in nov4 and "tv9bangla.com ↗" in nov4
    assert "Kashi Tamil Sangamam 2026: How students can get ₹10,000 to study Thirukkural" in nov4
    assert '<span class="pill saffron">PIB Karnataka</span> <span lang="en" dir="ltr">@pibbengaluru</span> · 5:18 PM' in nov3
    assert '<span class="pill">TV9 Marathi</span> <span lang="en" dir="ltr">@TV9Marathi</span> · 12:05 PM' in nov4
    # no empty "@" where the account is not known
    assert '<span class="pill saffron">PIB Bhubaneswar</span>  · 4:32 PM' in nov4 and "@<" not in page and 'title="@"' not in page
    assert '<span class="pill">TV9 Telugu</span> </p>' in nov4
    assert 'href="https://www.facebook.com/share/1DsSFQ6nwY/" target="_blank" rel="noopener">Facebook <span aria-hidden="true">↗</span></a>' in nov4
    # the newspaper clippings of 4 November stay on the same day
    assert nov4.count('<figure class="photo">') == 4
    assert "platform.twitter.com" not in page and "connect.facebook.net" not in page and "<iframe" not in page

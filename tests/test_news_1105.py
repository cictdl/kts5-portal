"""
KTS 5.0 in the news (1.2.159): four newspaper clippings of 4 November 2026, the day after the curtain raiser of KTS 5.0 at
IIT Madras, Chennai (Hindu Tamil Thisai, Dinamani, The New Indian Express, Dinakaran), as CICT sent them on 5 November 2026
("Add the four news article images on gallery with caption"): carried in data/gallery/ and put once in the gallery album
"KTS 5.0 in the news", which /in-the-news shows day by day.

    python -m pytest tests/test_news_1105.py -q
"""
import json
import re
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-04"


def _seeds():
    return [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["key"].startswith("news-" + DAY)]


def test_the_four_clippings_of_4_november():
    seeds = _seeds()
    assert [s["caption"].split(",")[0] for s in seeds] == ["Hindu Tamil Thisai", "Dinamani", "The New Indian Express", "Dinakaran"]
    assert {s["album"] for s in seeds} == {"KTS 5.0 in the news"} and {s["taken_on"] for s in seeds} == {DAY}
    assert all(s["caption"].split(",")[1].startswith(" 4 November 2026: “") for s in seeds)
    assert len({s["file"] for s in seeds}) == 4 and len({s["key"] for s in seeds}) == 4
    for s in seeds:
        data = (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        # JPEG, re-saved without metadata, small enough for a phone
        assert data[:3] == b"\xff\xd8\xff" and len(data) < 400_000 and b"Exif" not in data[:200] and b"Exif" not in data


def test_shown_in_the_gallery_and_in_the_news():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    seeds = _seeds()
    page = client.get("/gallery?lang=en&album=KTS+5.0+in+the+news").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 9 and "9 photographs" in page
    # the newest first, in the order given
    at = [page.index(s["file"]) for s in seeds]
    assert at == sorted(at) and at[-1] < page.index("kts5-news-2026-10-23-dinamani.jpg")
    assert "Curtain raiser for Kashi Tamil Sangamam 5.0 held in Chennai" in page
    assert "தமிழகம் - காசி இடையே பல நூற்றாண்டு கலாச்சார தொடர்பு" in page and "காசி தமிழ்ச் சங்கமம் நிகழ்ச்சி முன்னோட்டம்" in page
    assert "Prof. R. Chandrasekaran, Director of CICT, presents CICT&#39;s books on Kashi" in page
    news = client.get("/in-the-news?lang=en").get_data(as_text=True)
    # a day of its own, above the days before it
    sections = news.split('<section class="news-day"')[1:]
    heads = [re.sub(r"<[^>]+>", "", re.search(r"<h2[^>]*>(.*?)</h2>", x, re.S).group(1)).strip() for x in sections]
    assert heads.index("04 Nov 2026") < heads.index("02 Nov 2026") < heads.index("23 Oct 2026")
    day = sections[heads.index("04 Nov 2026")]
    assert day.count('<figure class="photo">') == 4
    for s in seeds:
        assert f'src="/files/gallery/{s["file"]}"' in day
        r = client.get(f"/files/gallery/{s['file']}")
        assert r.status_code == 200 and r.data == (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        r.close()

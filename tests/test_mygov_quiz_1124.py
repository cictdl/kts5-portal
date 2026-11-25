"""
The Kashi Tamil Sangamam 5.0 Quiz on Thirukkural of MyGov (1.2.213). CICT, 24 November 2026, with the poster of the Ministry of
Education and MyGov and the text of its post: "add this"; asked where: "Pinned notice", "Poster in the Gallery", "In the news".
The quiz: quiz.mygov.in, 24 November 2026, 12:00 AM - 12 December 2026, 11:45 PM; 10 questions in 300 seconds, in English; open to
all Indian citizens; a participation certificate, Rs 1,000 to each of 10 winners (MyGov's terms).

    python -m pytest tests/test_mygov_quiz_1124.py -q
"""
import json

from conftest import ROOT, make_app
from test_timeline import _sql, _start

QUIZ = "https://quiz.mygov.in/quiz/kashi-tamil-sangamam-5-0-quiz-on-thirukkural/"
TITLE = "Kashi Tamil Sangamam 5.0 – Quiz on Thirukkural on MyGov, 24 November – 12 December 2026"
MARK = "seed.notice.mygov_quiz"
ALBUM = "Ministry of Education – KTS 5.0 Posters"


def test_the_notice():
    from kts.db import MYGOV_QUIZ_NOTICE
    assert MYGOV_QUIZ_NOTICE[0] == TITLE
    body = MYGOV_QUIZ_NOTICE[1]
    for words in ("from 24 November 2026 to 12 December 2026, 11:45 PM", "Open to all Indian citizens", "10 questions in 300 seconds",
                  "a participation certificate", "₹1,000", QUIZ, "MyGov"):
        assert words in body, words
    assert len(body) < 1200
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _sql(app, "SELECT title, category, lang, pinned, published, attachment, link FROM notices WHERE title = ?", (TITLE,))
    assert rows == [(TITLE, "general", "en", 1, 1, "", QUIZ)]
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert TITLE in page and "Pinned" in page[page.index(TITLE) - 400:page.index(TITLE)]
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (TITLE,))[0][0]
    one = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert f'href="{QUIZ}"' in one and "Open to all Indian citizens" in one
    # the newest notice: the home page names it among the latest (the others put in on an earlier day, as on the live site)
    _sql(app, "UPDATE notices SET created_at = '2026-11-22T06:00:00+00:00' WHERE title != ?", (TITLE,))
    assert TITLE in client.get("/?lang=en").get_data(as_text=True)


def test_a_live_database_takes_the_notice_once():
    app = make_app(ADMIN_PASSWORD=None)
    _sql(app, "DELETE FROM notices WHERE title = ?", (TITLE,))
    _sql(app, "DELETE FROM settings WHERE key = ?", (MARK,))
    _sql(app, "UPDATE notices SET created_at = '2026-11-22T06:00:00+00:00'")
    again = _start(app)
    first = _sql(again, "SELECT title FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC, id DESC LIMIT 1")
    assert first == [(TITLE,)] and _sql(again, "SELECT value FROM settings WHERE key = ?", (MARK,)) == [("1",)]
    # once: a notice that CICT takes off stays off
    _sql(again, "DELETE FROM notices WHERE title = ?", (TITLE,))
    third = _start(again)
    assert _sql(third, "SELECT COUNT(*) FROM notices WHERE title = ?", (TITLE,)) == [(0,)]


def test_the_poster_in_the_gallery():
    seeds = [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["key"] == "moe-mygov-quiz-poster"]
    assert len(seeds) == 1
    s = seeds[0]
    assert s["album"] == ALBUM and s["taken_on"] == "2026-11-24" and s["sort_order"] == 90
    assert s["caption"].startswith("Ministry of Education and MyGov: the Kashi Tamil Sangamam 5.0 Quiz on Thirukkural")
    data = (ROOT / "data" / "gallery" / s["file"]).read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 200_000 and b"EXIF" not in data and b"XMP " not in data
    from PIL import Image
    with Image.open(ROOT / "data" / "gallery" / s["file"]) as im:
        assert im.size == (526, 526)
    client = make_app(ADMIN_PASSWORD=None).test_client()
    album = client.get("/gallery?lang=en&album=" + ALBUM).get_data(as_text=True)
    assert album.count('<figure class="photo">') == 9 and f"/files/gallery/{s['file']}" in album
    r = client.get(f"/files/gallery/{s['file']}")
    assert r.status_code == 200 and r.mimetype == "image/webp"
    r.close()


def test_in_the_news():
    news = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
    item = next(n for n in news if n["key"] == "mygov-2026-11-24-kts5-quiz")
    assert item["date"] == "2026-11-24" and item["kind"] == "article" and item["source"] == "MyGov"
    assert item["versions"] == [{"lang": "en", "title": "KASHI TAMIL SANGAMAM 5.0 – QUIZ ON THIRUKKURAL", "time": "12:00 AM", "url": QUIZ}]
    assert [n["date"] for n in news] == sorted(n["date"] for n in news)
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/in-the-news?lang=en").get_data(as_text=True)
    day = page[page.index(">24 Nov 2026</h2>"):page.index(">22 Nov 2026</h2>")]
    assert '<span class="pill">MyGov</span>' in day and "KASHI TAMIL SANGAMAM 5.0 – QUIZ ON THIRUKKURAL" in day and "quiz.mygov.in ↗" in day

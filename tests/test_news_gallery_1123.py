"""
New in the Gallery and in "KTS 5.0 in the news" (1.2.211). CICT, 23 November 2026: "Gallery - add new KTS5.0 from Ministry of
education and other news"; of the four photographs of the Ministry of Education in two press releases of the Press Information
Bureau: "Yes, add the 4 photos".

* The Gallery: a new album, "Ministry of Education – KTS 5.0 preparations and pre-events" - the high-level meeting at Banaras Hindu
  University on 3 November 2026 (two photographs) and the rangoli competition at Assi Ghat on 21 November 2026 (two), each credited
  to the Press Information Bureau.
* The news: the PIB release of 4 November 2026 on that meeting, in six languages; five reports of the press, of 3, 20, 21 and
  22 November 2026 - headlines and links only.

    python -m pytest tests/test_news_gallery_1123.py -q
"""
import datetime as dt
import json

from conftest import ROOT, make_app

ALBUM = "Ministry of Education – KTS 5.0 preparations and pre-events"
NEWS = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
NEW = ["uni-2026-11-03-kts5-bhu-review", "pib-2026-11-04-kts5-bhu-meeting", "chirauri-2026-11-20-kts5-bhu-vc",
       "dinamalar-2026-11-21-kts5-sinthanai-kalam", "etvbharat-2026-11-21-kts5-rangoli", "amarujala-2026-11-22-kts5-rangoli"]


def _seeds():
    return [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["album"] == ALBUM]


def test_the_four_photographs():
    seeds = _seeds()
    assert [s["key"] for s in seeds] == ["moe-prep-bhu-meeting-1", "moe-prep-bhu-meeting-2", "moe-pre-rangoli-assi-ghat-1",
                                         "moe-pre-rangoli-assi-ghat-2"]
    assert [s["taken_on"] for s in seeds] == ["2026-11-03", "2026-11-03", "2026-11-21", "2026-11-21"]
    assert [s["sort_order"] for s in seeds] == [10, 20, 30, 40]
    from PIL import Image
    sizes = []
    for s in seeds:
        # each says what it shows and where it comes from; no name is put to a face
        assert s["caption"].endswith("Photo: Press Information Bureau.") and len(s["caption"]) <= 300, s["key"]
        assert "Kashi Tamil Sangamam 5.0" in s["caption"]
        path = ROOT / "data" / "gallery" / s["file"]
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 200_000 and b"EXIF" not in data and b"XMP " not in data, s["file"]
        with Image.open(path) as im:
            sizes.append(im.size)
    assert sizes == [(470, 353), (559, 419), (624, 468), (427, 499)]      # as the Press Information Bureau published them
    assert "Banaras Hindu University" in seeds[0]["caption"] and "3 November 2026" in seeds[0]["caption"]
    assert "Assi Ghat" in seeds[2]["caption"] and "21 November 2026" in seeds[3]["caption"]


def test_the_album_on_the_gallery():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    # before the albums of earlier days (since 1.2.213 the posters of the Ministry, with the poster of the MyGov quiz of 24 November,
    # stand first)
    assert f"<bdi>{ALBUM}</bdi> <span" in page
    assert page.index("<bdi>Ministry of Education – KTS 5.0 Posters</bdi>") < page.index(f"<bdi>{ALBUM}</bdi>") < page.index("<bdi>KTS 5.0 in the news</bdi>")
    album = client.get("/gallery?lang=en&album=" + ALBUM).get_data(as_text=True)
    assert album.count('<figure class="photo">') == 4 and "4 photographs" in album
    at = [album.index(f"/files/gallery/{s['file']}") for s in _seeds()]
    assert all(a > 0 for a in at)
    assert "Photo: Press Information Bureau." in album and "rangoli competition at Assi Ghat" in album
    for s in _seeds():
        r = client.get(f"/files/gallery/{s['file']}")
        assert r.status_code == 200 and r.data == (ROOT / "data" / "gallery" / s["file"]).read_bytes() and r.mimetype == "image/webp"
        r.close()
    # put in once: a photograph that the Console deletes does not come back
    from test_timeline import _sql, _start
    assert _sql(app, "SELECT COUNT(*), MIN(published) FROM gallery_photos WHERE album = ?", (ALBUM,)) == [(4, 1)]
    _sql(app, "DELETE FROM gallery_photos WHERE album = ? AND sort_order = 10", (ALBUM,))
    again = _start(app)
    assert _sql(again, "SELECT sort_order FROM gallery_photos WHERE album = ? ORDER BY sort_order", (ALBUM,)) == [(20,), (30,), (40,)]


def test_the_news():
    by = {n["key"]: n for n in NEWS}
    assert all(key in by for key in NEW) and len(by) == len(NEWS)
    # the file stays in the order of the days, and each of these days in the order of its hours
    assert [n["date"] for n in NEWS] == sorted(n["date"] for n in NEWS)
    for day in sorted({by[k]["date"] for k in NEW}):
        times = [dt.datetime.strptime(n["versions"][0]["time"], "%I:%M %p") for n in NEWS if n["date"] == day and n["versions"][0]["time"]]
        assert times == sorted(times), day
    press = by["pib-2026-11-04-kts5-bhu-meeting"]
    assert press["kind"] == "press" and press["source"] == "Press Information Bureau"
    assert [v["lang"] for v in press["versions"]] == ["en", "as", "hi", "pa", "ta", "ur"]
    assert [v["office"] for v in press["versions"]] == ["PIB Delhi", "PIB Guwahati", "PIB Delhi", "PIB Chandigarh", "PIB Chennai", "PIB Delhi"]
    assert all(v["time"] == "8:06 PM" and v["title"] and v["url"].startswith("https://www.pib.gov.in/PressReleasePage.aspx?PRID=2332")
               for v in press["versions"])
    assert len({v["url"] for v in press["versions"]}) == 6 and all("?PRID=" in v["url"] and "&" not in v["url"] for v in press["versions"])
    assert press["versions"][0]["title"] == "High-Level Meeting at Banaras Hindu University, Varanasi reviews preparations for Kashi Tamil Sangamam 5.0"
    reports = [by[k] for k in NEW if by[k]["kind"] == "article"]
    assert [(n["date"], n["source"], n["versions"][0]["lang"], n["versions"][0]["time"]) for n in reports] == [
        ("2026-11-03", "UNI", "en", "6:54 PM"), ("2026-11-20", "Chirauri News", "hi", "4:46 PM"),
        ("2026-11-21", "Dinamalar", "ta", "6:27 PM"), ("2026-11-21", "ETV Bharat Uttar Pradesh", "hi", "8:18 PM"),
        ("2026-11-22", "Amar Ujala", "hi", "1:12 AM")]
    for n in reports:      # one version each, the headline and the link to the outlet's own page, no tracking
        assert len(n["versions"]) == 1 and set(n["versions"][0]) <= {"lang", "byline", "title", "time", "url"}
        assert n["versions"][0]["url"].startswith("https://www.") and "?" not in n["versions"][0]["url"]


def test_the_news_on_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/in-the-news?lang=en").get_data(as_text=True)
    heads = ["22 Nov 2026", "21 Nov 2026", "20 Nov 2026", "04 Nov 2026", "03 Nov 2026"]
    at = [page.index(f">{h}</h2>") for h in heads]
    assert at == sorted(at)      # day by day, the latest first
    nov21 = page[at[1]:at[2]]
    # the day of 21 November in the order of its hours: the column of Dinamalar, the release of the Ministry, ETV Bharat
    order = [nov21.index("காசி - தமிழகம் இடையே பண்பாட்டு பாலம் திருக்குறள்"), nov21.index("Rangoli competition at Assi Ghat"),
             nov21.index("अस्सी घाट पर रंगोली के रंगों में झलकी भारतीय संस्कृति और परंपरा")]
    assert order == sorted(order)
    assert '<span class="pill">ETV Bharat Uttar Pradesh</span>' in nov21 and "etvbharat.com ↗" in nov21
    nov4 = page[at[3]:at[4]]
    assert "High-Level Meeting at Banaras Hindu University, Varanasi reviews preparations for Kashi Tamil Sangamam 5.0" in nov4
    assert "PIB Delhi" in nov4 and "PRID=2332761" in nov4 and "PRID=2332933" in nov4
    nov3 = page[at[4]:]
    assert '<span class="pill">UNI</span>' in nov3[:nov3.index("</section>")] and "uniindia.com ↗" in nov3
    assert '<span class="pill">Amar Ujala</span>' in page[at[0]:at[1]] and '<span class="pill">Chirauri News</span>' in page[at[2]:at[3]]
    # in Hindi and in Tamil the release of 4 November carries its headline in that language
    hindi = client.get("/in-the-news?lang=hi").get_data(as_text=True)
    assert "बनारस हिंदू विश्वविद्यालय, वाराणसी में उच्च स्तरीय बैठक में काशी तमिल संगमम 5.0 की तैयारियों की समीक्षा" in hindi
    tamil = client.get("/in-the-news?lang=ta").get_data(as_text=True)
    assert "நிகழ்விற்கான ஏற்பாடுகள் குறித்த உயர்மட்ட ஆய்வுக் கூட்டம்" in tamil

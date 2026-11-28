"""
The special supplement of Hindu Tamil Thisai on Kashi Tamil Sangamam 5.0 (Chennai edition, 28 November 2026) in the Gallery and in "KTS
5.0 in the news" (1.2.237). CICT, 28 November 2026: the four pages of the supplement, "add in today's news and gallery". Five clippings of
its reports, articles and messages, the advertisements of others left out, in the album "KTS 5.0 in the news".

    python -m pytest tests/test_supplement_1128.py -q
"""
import json

from conftest import ROOT, make_app

DAY = "2026-11-28"
ALBUM = "KTS 5.0 in the news"
HEADS = ["“வாரணாசியில் இன்று காசி தமிழ் சங்கமத்தைக் குடியரசு துணைத் தலைவர் சி.பி.ராதாகிருஷ்ணன் துவங்கி வைக்கிறார்”",
         "“பழங்கால ஞானம், நவீன லட்சியங்கள்”", "“காசிக்கானத் தமிழ்ப் பயணம், பல்லாயிரம் ஆண்டுகள் பழமையானது”",
         "“புனிதநகரமான வாரணாசியின் வியக்க வைக்கும் ஆன்மிக வளர்ச்சி”", "“காசித் தமிழ்ச் சங்கமம் 5.0”"]


def _seeds():
    return [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["key"].startswith("news-" + DAY)]


def test_the_five_clippings():
    from PIL import Image
    seeds = _seeds()
    assert [s["key"] for s in seeds] == [f"news-{DAY}-hindu-tamil-{n}" for n in range(1, 6)]
    assert {s["album"] for s in seeds} == {ALBUM} and {s["taken_on"] for s in seeds} == {DAY}
    assert [s["sort_order"] for s in seeds] == [10, 20, 30, 40, 50]
    for s, head, page in zip(seeds, HEADS, (1, 2, 3, 4, 4)):
        assert s["caption"].startswith(f"Hindu Tamil Thisai, 28 November 2026: {head}"), s["key"]
        assert s["caption"].endswith(f"– the special supplement on Kashi Tamil Sangamam 5.0, Chennai edition, page {page}"), s["key"]
        path = ROOT / "data" / "gallery" / s["file"]
        data = path.read_bytes()
        assert data[:3] == b"\xff\xd8\xff" and b"Exif" not in data and len(data) < (800_000 if page == 2 and "-2." in s["file"] else 400_000)
        with Image.open(path) as im:
            assert im.format == "JPEG" and im.width <= 1400 and im.height > 900
    assert "Director, Central Institute of Classical Tamil" in seeds[2]["caption"]
    assert "the page of the Central Institute of Classical Tamil" in seeds[4]["caption"]
    gallery = json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8"))
    assert len(gallery) == 38 and len({g["key"] for g in gallery}) == 38 and len({g["file"] for g in gallery}) == 38


def test_on_the_gallery_and_the_news_page():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    album = client.get("/gallery?lang=en&album=KTS+5.0+in+the+news").get_data(as_text=True)
    assert album.count('<figure class="photo">') == 14 and "14 photographs" in album
    for s in _seeds():
        assert f"/files/gallery/{s['file']}" in album
        r = client.get(f"/files/gallery/{s['file']}")
        assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data == (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        r.close()
    # on the page "KTS 5.0 in the news", on 28 November, in their order
    news = client.get("/in-the-news?lang=en").get_data(as_text=True)
    at = [news.index(f"/files/gallery/{s['file']}") for s in _seeds()]
    assert at == sorted(at) and at[-1] < news.index("kts5-news-2026-11-04-hindu-tamil.jpg")
    day = news[news.index('<h2 id="day-1"'):news.index('<h2 id="day-2"')]
    assert "28 Nov 2026" in day and all(f"/files/gallery/{s['file']}" in day for s in _seeds())
    # put in once: a photograph that the Console deletes does not come back
    from test_timeline import _sql, _start
    assert _sql(app, "SELECT COUNT(*), MIN(published) FROM gallery_photos WHERE album = ? AND taken_on = ?", (ALBUM, DAY)) == [(5, 1)]
    _sql(app, "DELETE FROM gallery_photos WHERE file_path = ?", (f"gallery/{_seeds()[4]['file']}",))
    again = _start(app)
    assert _sql(again, "SELECT COUNT(*) FROM gallery_photos WHERE album = ? AND taken_on = ?", (ALBUM, DAY)) == [(4,)]

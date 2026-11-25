"""
The posters of the Ministry of Education in the Gallery (1.2.206). CICT, 19 November 2026: "in gallery add the Ministry of
Education KTS5.0 Posters"; of the material received on 18 November: "Both (8 images)"; the album: "Ministry of Education – KTS 5.0
Posters". The infographic of the three initiatives of KTS 5.0 and the seven hoardings in Hindi, carried in data/gallery/ and put
in the gallery of every installation once.

    python -m pytest tests/test_gallery_moe_posters_1119.py -q
"""
import json

from conftest import ROOT, make_app

ALBUM = "Ministry of Education – KTS 5.0 Posters"


def _seeds():
    return [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["key"].startswith("moe-poster-")]


def _rows(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM gallery_photos WHERE album = ? ORDER BY sort_order, id", (ALBUM,))


def test_the_eight_pictures():
    seeds = _seeds()
    assert [s["key"] for s in seeds] == ["moe-poster-three-initiatives"] + [f"moe-poster-hoarding-hindi-{n}" for n in range(1, 8)]
    assert {s["album"] for s in seeds} == {ALBUM} and {s["taken_on"] for s in seeds} == {"2026-11-18"}
    assert [s["sort_order"] for s in seeds] == [10, 20, 30, 40, 50, 60, 70, 80]
    assert seeds[0]["caption"].startswith("Ministry of Education: the three initiatives of Kashi Tamil Sangamam 5.0")
    assert seeds[3]["caption"] == ("Ministry of Education: hoarding of Kashi Tamil Sangamam 5.0 in Hindi, 28 November – 12 December "
                                   "2026, Namo Ghat, Varanasi (design 3 of 7).")
    from PIL import Image
    for s in seeds:
        assert len(s["caption"]) <= 300
        path = ROOT / "data" / "gallery" / s["file"]
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 200_000 and b"EXIF" not in data and b"XMP " not in data, s["file"]
        with Image.open(path) as im:
            assert im.size == ((1080, 1350) if "three" in s["file"] else (1600, 839)), s["file"]


def test_the_album_on_the_gallery():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    # the newest album, first among the albums and the pictures
    assert f"<bdi>{ALBUM}</bdi> <span" in page
    assert page.index(f"<bdi>{ALBUM}</bdi>") < page.index("<bdi>KTS 5.0 in the news</bdi>")
    first = page.index('<figure class="photo">')
    assert page.index("/files/gallery/kts5-moe-three-initiatives.webp", first) < page.index("/files/gallery/kts5-news-", first)
    album = client.get("/gallery?lang=en&album=" + ALBUM).get_data(as_text=True)
    # ... and the poster of the MyGov quiz, of 24 November, since 1.2.213 (tests/test_mygov_quiz_1124.py)
    assert album.count('<figure class="photo">') == 9 and "9 photographs" in album and "18 Nov 2026" in album
    at = [album.index(f"/files/gallery/{s['file']}") for s in _seeds()]
    assert at == sorted(at)                                                   # in the order given
    assert "Ministry of Education: the three initiatives of Kashi Tamil Sangamam 5.0" in album
    # each served as it is in data/gallery/
    for s in _seeds():
        r = client.get(f"/files/gallery/{s['file']}")
        assert r.status_code == 200 and r.data == (ROOT / "data" / "gallery" / s["file"]).read_bytes() and r.mimetype == "image/webp"
        r.close()


def test_put_in_once():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    rows = _rows(app)
    assert len(rows) == 9 and all(r["published"] == 1 for r in rows)      # with the poster of the MyGov quiz (1.2.213)
    with app.app_context():
        execute("DELETE FROM gallery_photos WHERE id = ?", (rows[0]["id"],))
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    assert [r["id"] for r in _rows(again)] == [r["id"] for r in rows[1:]]

"""
The gallery: photographs uploaded in albums by the content staff, shown on the public page.

    python -m pytest tests -q
"""
import io

from conftest import ROOT, make_app
from test_public_fixes import PNG, _staff

JPG = b"\xff\xd8\xff\xe0" + b"\0" * 400 + b"\xff\xd9"


def _post(client, **data):
    with client.session_transaction() as s:
        token = s["_csrf"]
    data["_csrf"] = token
    return client.post("/console/gallery", data=data, content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)


def _empty():
    """The portal with an empty gallery: without the photographs of the launch that every installation carries (1.2.95)."""
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        from kts.db import execute
        execute("DELETE FROM gallery_photos")
    return app


def _rows(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM gallery_photos ORDER BY id")


def test_photographs_are_uploaded_in_albums_and_shown():
    app = _empty()
    client = app.test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    assert "Photographs will appear here as the programme unfolds." in page and 'class="photo-grid"' not in page
    assert '<a href="/gallery" class="active">Gallery</a>' in page
    assert '<a href="/gallery" class="">Gallery</a>' in client.get("/?lang=en").get_data(as_text=True)
    content = _staff(app, "content@tests.example", "content")
    page = _post(content, action="upload", album="Inauguration, Varanasi", caption="The lamp is lit", taken_on="2026-11-28",
                 photos=[(io.BytesIO(JPG), "lamp.jpg"), (io.BytesIO(PNG), "hall.png"), (io.BytesIO(b"plain text"), "notes.txt")])
    assert "2 photograph(s) added to the album “Inauguration, Varanasi”" in page and "notes.txt (not a JPG, PNG or WebP)" in page
    rows = _rows(app)
    assert [r["file_name"] for r in rows] == ["lamp.jpg", "hall.png"] and all(r["published"] == 1 for r in rows)
    assert rows[0]["file_path"].startswith("gallery/") and rows[0]["taken_on"] == "2026-11-28"
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 2 and "2 photographs" in page
    assert f'src="/files/{rows[0]["file_path"]}"' in page and 'alt="The lamp is lit"' in page and "28 Nov 2026" in page
    assert "<bdi>Inauguration, Varanasi</bdi> <span" in page
    # the file is served while the photograph is published
    r = client.get(f"/files/{rows[0]['file_path']}")
    assert r.status_code == 200 and r.data == JPG
    r.close()
    # a second album, and the tab of each
    _post(content, action="upload", album="Campus programme, Thrissur", photos=[(io.BytesIO(JPG), "talk.jpg")])
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 3 and "Campus programme, Thrissur" in page
    page = client.get("/gallery?album=Campus+programme,+Thrissur&lang=en").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 1 and 'alt="Campus programme, Thrissur"' in page


def test_hidden_and_deleted_photographs_leave_the_page():
    app = _empty()
    content = _staff(app, "content@tests.example", "content")
    _post(content, action="upload", album="Orientation", photos=[(io.BytesIO(JPG), "a.jpg"), (io.BytesIO(JPG), "b.jpg")])
    first, second = _rows(app)
    client = app.test_client()
    _post(content, action="toggle", id=str(first["id"]))
    page = client.get("/gallery").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 1 and first["file_path"] not in page
    assert client.get(f"/files/{first['file_path']}").status_code == 404
    # the staff still see it, with its file
    admin_page = content.get("/console/gallery").get_data(as_text=True)
    assert admin_page.count('class="photo card flat"') == 2 and "hidden" in admin_page
    r = content.get(f"/console/files/{first['file_path']}")
    assert r.status_code == 200
    r.close()
    # a caption changed, an album renamed
    _post(content, action="caption", id=str(second["id"]), caption="New caption", album="Orientation 2026", taken_on="", sort_order="5")
    row = [r for r in _rows(app) if r["id"] == second["id"]][0]
    assert (row["caption"], row["album"], row["sort_order"]) == ("New caption", "Orientation 2026", 5)
    # deleted: gone from the page, the table and the disk
    path = app.config["UPLOAD_DIR"] / second["file_path"]
    assert path.is_file()
    _post(content, action="delete", id=str(second["id"]))
    assert [r["id"] for r in _rows(app)] == [first["id"]] and not path.exists()
    assert client.get(f"/files/{second['file_path']}").status_code == 404


def test_only_content_staff_manage_the_gallery():
    app = _empty()
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.get("/console/gallery").status_code == 403
    assert app.test_client().get("/console/gallery").status_code == 302
    content = _staff(app, "content@tests.example", "content")
    assert "Name the album" in _post(content, action="upload", album="", photos=[(io.BytesIO(JPG), "a.jpg")])
    assert "Choose one or more photographs." in _post(content, action="upload", album="X")
    # a photograph larger than the limit is refused
    big = b"\xff\xd8\xff" + b"\0" * (8 * 1024 * 1024 + 1)
    assert "(too large)" in _post(content, action="upload", album="X", photos=[(io.BytesIO(big), "big.jpg")])
    assert _rows(app) == []


def test_the_photographs_of_the_launch():
    # the launch of the KTS 5.0 web portal and registration by the Hon'ble Minister of Education on 22 October 2026: four
    # photographs, carried in data/gallery/ and put in the gallery of every installation once (1.2.95)
    import json
    seeds = json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8"))
    assert len(seeds) == 4 and {s["taken_on"] for s in seeds} == {"2026-10-22"}
    assert {s["album"] for s in seeds} == {"Launch of the KTS 5.0 web portal and registration"}
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    assert page.count('<figure class="photo">') == 4 and "4 photographs" in page and "22 Oct 2026" in page
    assert "<bdi>Launch of the KTS 5.0 web portal and registration</bdi> <span" in page
    assert "Shri Pralhad Joshi, Hon&#39;ble Union Minister of Education, launches the KTS 5.0 web portal" in page
    rows = _rows(app)
    assert [r["caption"] for r in rows] == [s["caption"] for s in seeds] and all(r["published"] == 1 for r in rows)
    # in the order given, each served as it is in data/gallery/
    assert [page.index(r["file_path"]) for r in rows] == sorted(page.index(r["file_path"]) for r in rows)
    for s, r in zip(seeds, rows):
        assert r["file_path"] == "gallery/" + s["file"]
        got = client.get(f"/files/{r['file_path']}")
        data = (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        assert got.status_code == 200 and got.data == data and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        assert len(data) < 200_000
        got.close()
    # put in once: one deleted in the console does not come back when the portal starts again
    with app.app_context():
        from kts.db import execute
        execute("DELETE FROM gallery_photos WHERE id = ?", (rows[0]["id"],))
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    assert [r["id"] for r in _rows(again)] == [r["id"] for r in rows[1:]]

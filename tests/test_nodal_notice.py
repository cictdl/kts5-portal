"""
The State/UT-wise list of the Nodal Higher Educational Institutions among the notices and circulars
(version 1.2.51): a pinned circular, put in once for each database.

    python -m pytest tests -q
"""
import json

from conftest import ROOT, make_app

TITLE = "State/UT-wise list of Nodal Higher Educational Institutions"


def _notices(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM notices WHERE title = ?", (TITLE,))


def test_the_circular_holds_every_state_and_its_nodal_institution():
    app = make_app(ADMIN_PASSWORD=None)
    rows = _notices(app)
    assert len(rows) == 1
    n = rows[0]
    assert (n["category"], n["pinned"], n["published"], n["lang"], n["link"]) == ("circular", 1, 1, "en", "/nodal-institutions")
    heis = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))
    for i, h in enumerate(heis, 1):
        assert f"\n{i}. {h['state']}: {h['name']} ({h['allocation']})\n" in n["body"]
    assert "1. Andhra Pradesh: Central University of Andhra Pradesh (65)" in n["body"]
    assert "23. Tamil Nadu: Central University of Tamil Nadu (150)" in n["body"]
    assert "Total: 1,385 participating HEIs." in n["body"]
    assert "Nodal Institutions may nominate additional HEIs beyond the indicated allocation." in n["body"]


def test_it_is_shown_among_the_notices_and_on_the_home_page():
    app = make_app(ADMIN_PASSWORD=None)
    nid = _notices(app)[0]["id"]
    client = app.test_client()
    listing = client.get("/notices?lang=en").get_data(as_text=True)
    assert f'href="/notices/{nid}"><b><bdi>{TITLE}</bdi></b></a>' in listing
    assert '<span class="pill kumkum">Pinned</span> <span class="pill grey">Circular</span>' in listing
    page = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "31. Puducherry: Pondicherry University (10)" in page and 'href="/nodal-institutions"' in page
    home = client.get("/?lang=en").get_data(as_text=True)
    assert f'href="/notices/{nid}"><bdi>{TITLE}</bdi></a>' in home
    # in every language of the portal: the notice itself is in English, as the list of the Ministry is
    assert TITLE in client.get("/notices?lang=ta").get_data(as_text=True)


def test_put_in_once_and_left_as_cict_leaves_it():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    init_db(app)
    assert len(_notices(app)) == 1
    with app.app_context():
        assert query("SELECT value FROM settings WHERE key = 'seed.notice.nodal_heis'", one=True)["value"] == "1"
        # changed in the console: stays changed
        execute("UPDATE notices SET pinned = 0, body = 'Shortened by CICT' WHERE title = ?", (TITLE,))
    init_db(app)
    assert [(n["pinned"], n["body"]) for n in _notices(app)] == [(0, "Shortened by CICT")]
    # deleted in the console: does not come back
    with app.app_context():
        execute("DELETE FROM notices WHERE title = ?", (TITLE,))
    init_db(app)
    assert _notices(app) == []


def test_not_twice_where_cict_has_put_it_in_already():
    from kts.db import execute, init_db, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM notices")
        execute("DELETE FROM settings WHERE key = 'seed.notice.nodal_heis'")
        execute("INSERT INTO notices(title, body, category, created_at, updated_at) VALUES(?, 'By hand', 'general', ?, ?)",
                (TITLE, utcnow(), utcnow()))
    init_db(app)
    assert [n["body"] for n in _notices(app)] == ["By hand"]

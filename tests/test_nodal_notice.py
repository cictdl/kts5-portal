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
    assert "1. Andhra Pradesh: Central University of Andhra Pradesh (30)" in n["body"]
    assert "23. Tamil Nadu: Central University of Tamil Nadu (150)" in n["body"] and "26. Uttar Pradesh: Banaras Hindu University (350)" in n["body"]
    assert "Total: 1,000 Participating HEIs." in n["body"]
    assert "Registration does not by itself confer selection." in n["body"] and "tentative" not in n["body"]
    assert "up to 10 November 2026" in n["body"] and "between 11 and 15 November 2026" in n["body"] and "by 20 November 2026" in n["body"]


def test_it_is_shown_among_the_notices_and_on_the_home_page():
    app = make_app(ADMIN_PASSWORD=None)
    nid = _notices(app)[0]["id"]
    client = app.test_client()
    listing = client.get("/notices?lang=en").get_data(as_text=True)
    assert f'href="/notices/{nid}"><b><bdi>{TITLE}</bdi></b></a>' in listing
    assert '<span class="pill kumkum">Pinned</span> <span class="pill grey">Circular</span>' in listing
    page = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "31. Puducherry: Pondicherry University (5)" in page and 'href="/nodal-institutions"' in page
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


def test_the_live_circular_takes_the_numbers_of_the_revised_letter_once():
    # the live database holds the circular as 1.2.51 put it in, with the tentative allocation: at the next start it takes the
    # numbers and the text of the revised D.O. letter (1.2.110), once; a circular CICT rewrites afterwards stays as it is
    import sqlite3
    from config import Config
    from kts import create_app
    app = make_app(ADMIN_PASSWORD=None)
    old = "1. Andhra Pradesh: Central University of Andhra Pradesh (65)\n\nThe State/UT-wise allocation is tentative and indicates ..."
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE notices SET body = ? WHERE title = ?", (old, TITLE))
    conn.execute("DELETE FROM settings WHERE key = 'migrate.revised_do.notice'")
    conn.commit()
    conn.close()
    names = ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")
    again = create_app(type("Again", (Config,), {n: app.config[n] for n in names} | {"ADMIN_PASSWORD": None}))
    body = _notices(again)[0]["body"]
    assert "(30)" in body and "Total: 1,000 Participating HEIs." in body and "tentative" not in body
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE notices SET body = 'CICT wrote this; the allocation is tentative.' WHERE title = ?", (TITLE,))
    conn.commit()
    conn.close()
    third = create_app(type("Third", (Config,), {n: app.config[n] for n in names} | {"ADMIN_PASSWORD": None}))
    assert _notices(third)[0]["body"] == "CICT wrote this; the allocation is tentative."

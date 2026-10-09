"""
Backups of the database (version 1.2.40): copies at the hours of backup.times and by hand, each one
checked; download; restore into the running portal, which keeps its state of before.

    python -m pytest tests -q
"""
import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from conftest import ROOT, add_candidates, make_app
from test_public_fixes import _staff


def _token(client):
    with client.session_transaction() as s:
        return s["_csrf"]


def _at(day, hour, minute=0):
    from kts.utils import IST
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def _count(app, table="applications"):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT COUNT(*) AS n FROM {table}", one=True)["n"]


def test_a_copy_holds_the_database_the_key_and_the_steps():
    from kts import backup
    app = make_app(ADMIN_PASSWORD=None)
    add_candidates(app, 3)
    (Path(app.config["INSTANCE_DIR"]) / "stipend.key").write_bytes(b"k" * 64)
    info = backup.make(app, "manual", _at(9, 15, 30))
    assert info["file"] == "kts5-backup-20261009-153000-manual.zip" and info["ok"] and info["applications"] == 3
    path = backup.folder(app) / info["file"]
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ["RESTORE.txt", "kts5.sqlite3", "stipend.key"]
        assert z.read("stipend.key") == b"k" * 64
        readme = z.read("RESTORE.txt").decode("utf-8")
        z.extract("kts5.sqlite3", path.parent / "x")
    assert "Applications: 3" in readme and "Console > Backups > Restore" in readme and "never send it by e-mail" in readme
    copy = sqlite3.connect(path.parent / "x" / "kts5.sqlite3")
    assert copy.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 3
    # one file: the copy does not need the -wal of the portal
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    copy.close()
    assert [r["name"] for r in backup.listing(app)] == [info["file"]]
    assert not [p for p in backup.folder(app).iterdir() if p.name.startswith(".")]
    with app.app_context():
        assert backup.state()["last"]["file"] == info["file"]


def test_the_hours_of_copying():
    from kts import backup
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("backup.times", "02:00, 14:00")
        assert backup.latest_slot(_at(9, 15)) == "2026-10-09 14:00"
        assert backup.latest_slot(_at(10, 1)) == "2026-10-09 14:00"
    made = backup.tick(app, _at(9, 15))           # the first look after an update copies at once
    assert made and made["file"] == "kts5-backup-20261009-150000.zip"
    assert backup.tick(app, _at(9, 15, 5)) is None
    assert backup.tick(app, _at(10, 1, 55)) is None
    assert backup.tick(app, _at(10, 2, 3))["file"] == "kts5-backup-20261010-020300.zip"
    assert backup.tick(app, _at(10, 13)) is None
    with app.app_context():
        set_setting("backup.on", "0")
    assert backup.tick(app, _at(10, 14, 1)) is None
    # the oldest copies made at the hours go; those made by hand are kept apart
    with app.app_context():
        set_setting("backup.on", "1")
        set_setting("backup.keep", "2")
    backup.make(app, "manual", _at(10, 16))
    for day in (11, 12, 13):
        backup.make(app, "scheduled", _at(day, 2))
    kinds = [(r["name"], r["kind"]) for r in backup.listing(app)]
    assert kinds == [("kts5-backup-20261013-020000.zip", "scheduled"), ("kts5-backup-20261012-020000.zip", "scheduled"),
                     ("kts5-backup-20261010-160000-manual.zip", "manual")]
    # two copies in the same second keep both
    a, b = backup.make(app, "manual", _at(14, 9)), backup.make(app, "manual", _at(14, 9))
    assert (a["file"], b["file"]) == ("kts5-backup-20261014-090000-manual.zip", "kts5-backup-20261014-090000-manual-2.zip")
    assert {a["file"], b["file"]} <= {r["name"] for r in backup.listing(app)}
    # served, the portal starts the scheduler
    for entry in ("serve.py", "run.py"):
        assert "backup.start(app)" in (ROOT / entry).read_text(encoding="utf-8")


def test_the_console_page_and_who_sees_it():
    from kts import backup
    app = make_app(ADMIN_PASSWORD=None)
    add_candidates(app, 2)
    root = _staff(app, "root@tests.example", "superadmin")
    admin = _staff(app, "admin@tests.example", "admin")
    # no copy yet: the dashboard of the superadmin says so, not that of others
    assert "There is no copy of the database yet." in root.get("/console/").get_data(as_text=True)
    assert "no copy of the database" not in admin.get("/console/").get_data(as_text=True)
    assert admin.get("/console/backups").status_code == 403
    page = root.get("/console/backups").get_data(as_text=True)
    assert "02:00, 14:00" in page and "No copy yet." in page and "Backups</a>" in page
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "now"}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "Copy made: kts5-backup-" in page and "2 applications, check ok" in page
    assert "There is no copy" not in root.get("/console/").get_data(as_text=True)
    name = backup.listing(app)[0]["name"]
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "download", "name": name})
    assert r.status_code == 200 and r.mimetype == "application/zip" and r.data[:2] == b"PK"
    assert name in r.headers["Content-Disposition"]
    r.close()
    for bad in ("../test.sqlite3", "kts5-backup-20261009-1530.zip/../../x", "portal.env"):
        assert root.post("/console/backups", data={"_csrf": _token(root), "action": "download", "name": bad}).status_code == 404
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "now_download"})
    assert r.status_code == 200 and r.data[:2] == b"PK"
    assert "backup.times" in root.get("/console/settings").get_data(as_text=True)


def test_a_restore_puts_the_copy_back_and_keeps_the_state_of_before():
    from kts import backup
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    add_candidates(app, 3)
    root = _staff(app, "root@tests.example", "superadmin")
    first = backup.make(app, "manual", _at(9, 10))
    add_candidates(app, 2)
    with app.app_context():
        execute("DELETE FROM applications WHERE id = 1")
    assert _count(app) == 4
    # not without RESTORE typed
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "restore", "name": first["file"], "confirm": "restore"},
                  follow_redirects=True)
    assert "type RESTORE" in r.get_data(as_text=True) and _count(app) == 4
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "restore", "name": first["file"], "confirm": "RESTORE"},
                  follow_redirects=True)
    page = r.get_data(as_text=True)
    assert _count(app) == 3
    assert "Restored kts5-backup-20261009-100000-manual.zip: 3 applications" in page
    before = [r for r in backup.listing(app) if r["kind"] == "before-restore"]
    assert len(before) == 1 and before[0]["name"] in page
    # the portal goes on as before: the database is still in WAL mode and takes writes
    from kts.db import get_db
    with app.app_context():
        assert get_db().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    add_candidates(app, 1)
    assert _count(app) == 4
    # and the restore is undone with the copy of before
    root = _staff(app, "root2@tests.example", "superadmin")
    root.post("/console/backups", data={"_csrf": _token(root), "action": "restore", "name": before[0]["name"], "confirm": "RESTORE"})
    assert _count(app) == 4


def test_a_restore_from_an_upload_of_an_older_version():
    from kts import backup
    app = make_app(ADMIN_PASSWORD=None)
    add_candidates(app, 2)
    root = _staff(app, "root@tests.example", "superadmin")
    info = backup.make(app, "manual", _at(9, 11))
    data = (backup.folder(app) / info["file"]).read_bytes()
    # a copy of a version before 1.2.38, without users.states
    folder = backup.folder(app) / "old"
    folder.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extract("kts5.sqlite3", folder)
    old = sqlite3.connect(folder / "kts5.sqlite3")
    old.execute("ALTER TABLE users DROP COLUMN states")
    old.commit()
    old.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(folder / "kts5.sqlite3", "kts5.sqlite3")
        z.writestr("stipend.key", b"s" * 64)
    add_candidates(app, 3)
    r = root.post("/console/backups", data={"_csrf": _token(root), "action": "restore", "confirm": "RESTORE",
                                            "file": (io.BytesIO(buf.getvalue()), "kts5-copy.zip")},
                  content_type="multipart/form-data", follow_redirects=True)
    assert "Restored kts5-copy.zip: 2 applications" in r.get_data(as_text=True)
    assert _count(app) == 2
    from kts.db import query
    with app.app_context():
        assert "states" in {r["name"] for r in query("PRAGMA table_info(users)")}
    # the key of the copy is the key of the database put back
    assert (Path(app.config["INSTANCE_DIR"]) / "stipend.key").read_bytes() == b"s" * 64
    # what is not a copy is refused, and nothing changes
    root = _staff(app, "root3@tests.example", "superadmin")
    for blob, name, says in ((b"hello", "x.zip", "neither a copy"), (b"PK\x03\x04broken", "y.zip", "damaged"),
                             (_zip({"other.txt": b"x"}), "z.zip", "holds no kts5.sqlite3")):
        r = root.post("/console/backups", data={"_csrf": _token(root), "action": "restore", "confirm": "RESTORE",
                                                "file": (io.BytesIO(blob), name)},
                      content_type="multipart/form-data", follow_redirects=True)
        assert says in r.get_data(as_text=True)
    assert _count(app) == 2


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()

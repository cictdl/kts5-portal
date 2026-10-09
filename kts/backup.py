"""
Backups of the database (version 1.2.40).

The portal keeps everything in one SQLite file (instance/kts5.sqlite3): every application, every
answer of the test, every account and setting. It copies that file by itself:

* at the hours of backup.times (default 02:00 and 14:00 IST) into instance/backups/, as a ZIP with
  the database, the key of the stipend module (instance/stipend.key: without it the bank details in
  the database cannot be read) and RESTORE.txt. backup.keep of these copies are kept (default 28,
  two weeks), and the KEEP_BY_HAND newest of those made by hand. A portal that was not running at
  the hour makes the copy as soon as it runs again.
* by hand, from Console > Backups, where every copy can also be downloaded, to keep one off the server.

A copy is taken with the backup interface of SQLite: a consistent picture of the database while the
portal goes on writing to it. It is checked (PRAGMA quick_check) and counted before it is kept.

The uploads (photographs, ID proofs, nomination forms) are not in these copies: they are many and
large, and the backup of the subscription in Plesk keeps them.

A copy is put back (restore) from the console, into the running portal, with the backup interface the
other way round: no file has to be replaced by hand while the portal holds it open. The state of
before is kept first as a copy of its own ('before-restore'), so that a restore can be undone.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .db import audit, get_db, get_setting, init_db, set_setting, utcnow
from .utils import IST, now_ist

DB_NAME = "kts5.sqlite3"
KEY_NAME = "stipend.key"
NAME = re.compile(r"^kts5-backup-(\d{8})-(\d{6})(?:-(manual|before-restore))?(?:-(\d+))?\.zip$")
KEEP_BY_HAND = 10
TICK_SECONDS = 300
# what the console shows as a warning: no copy for this long while copies are on
STALE_HOURS = 26


def folder(app):
    return Path(app.config["INSTANCE_DIR"]) / "backups"


def _key_path(app):
    return Path(app.config["INSTANCE_DIR"]) / KEY_NAME


def listing(app):
    """The copies kept, the newest first: name, kind (scheduled, manual, before-restore), when (IST), bytes."""
    rows = []
    d = folder(app)
    if d.is_dir():
        for p in d.iterdir():
            m = NAME.match(p.name)
            if m and p.is_file():
                when = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=IST)
                rows.append({"name": p.name, "kind": m.group(3) or "scheduled", "when": when, "bytes": p.stat().st_size})
    return sorted(rows, key=lambda r: (r["when"], r["name"]), reverse=True)


def path_of(app, name):
    """The file of a copy named in a request: a name of the listing only, never a path."""
    if not NAME.match(name or ""):
        return None
    p = folder(app) / name
    return p if p.is_file() else None


def _remove(*paths):
    for p in paths:
        for q in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm"), p.with_name(p.name + "-journal")):
            try:
                q.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _copy_db(source, target, timeout=30):
    src = sqlite3.connect(str(source), timeout=timeout)
    dst = sqlite3.connect(str(target), timeout=timeout)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _check(path):
    """
    Checks a copy and counts what it holds; leaves it a single file (journal mode DELETE). Raises
    ValueError when it is not a database of the portal.
    """
    try:
        conn = sqlite3.connect(str(path))
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"applications", "users", "settings"} <= tables:
                raise ValueError("this is not a database of the KTS 5.0 portal")
            ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            facts = {"ok": ok}
            for label, table in (("applications", "applications"), ("accounts", "users"), ("tests", "exam_sessions")):
                facts[label] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if table in tables else 0
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"the file is not a readable database ({exc})") from exc
    return facts


def _readme(app, when, kind, facts, with_key):
    from .version import VERSION
    return "\r\n".join([
        "KTS 5.0 portal: a copy of the database",
        "",
        f"Made: {when:%d %B %Y, %H:%M} IST ({kind}), by version {VERSION} of the portal",
        f"Applications: {facts['applications']} · accounts: {facts['accounts']} · tests: {facts['tests']} · "
        f"check: {'ok' if facts['ok'] else 'NOT OK'}",
        "",
        f"{DB_NAME}   the database: every application, account, answer of the test and setting",
        (f"{KEY_NAME}    the key of the stipend module: without it the bank details in the database cannot be read"
         if with_key else f"(no {KEY_NAME}: the portal had none when this copy was made)"),
        "",
        "This file holds the personal data of every applicant. Keep it on an encrypted drive or in the",
        "storage of CICT; never send it by e-mail.",
        "",
        "To put it back: Console > Backups > Restore (upload this file, or choose it among the copies on",
        "the server). The portal first keeps a copy of its state of before.",
        f"By hand, with the portal stopped: replace instance\\{DB_NAME} with {DB_NAME} of this file, delete",
        f"instance\\{DB_NAME}-wal and -shm if they exist, put {KEY_NAME} into instance\\ if it is not there,",
        "and start the portal.",
        "",
        "The photographs, ID proofs and nomination forms (uploads\\) are not in this file: the backup of",
        "the subscription in Plesk keeps them.",
        ""])


def make(app, kind="scheduled", now=None):
    """
    A copy of the database in the folder of the backups, checked; then the oldest are let go.
    Gives what the console shows of it: at, file, bytes, kind, ok, applications, accounts, tests.
    """
    now = (now or now_ist()).astimezone(IST)
    d = folder(app)
    d.mkdir(parents=True, exist_ok=True)
    base = f"kts5-backup-{now:%Y%m%d-%H%M%S}" + ("" if kind == "scheduled" else f"-{kind}")
    # never over an earlier copy, which may be on its way to a browser
    name, n = base + ".zip", 1
    while (d / name).exists():
        n += 1
        name = f"{base}-{n}.zip"
    tmp = d / f".copy-{os.getpid()}-{threading.get_ident()}.sqlite3"
    part = d / (name + f".{os.getpid()}-{threading.get_ident()}.part")
    try:
        _copy_db(app.config["DATABASE"], tmp)
        facts = _check(tmp)
        key = _key_path(app)
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, DB_NAME)
            if key.is_file():
                z.write(key, KEY_NAME)
            z.writestr("RESTORE.txt", _readme(app, now, kind, facts, key.is_file()))
        os.replace(part, d / name)
    finally:
        _remove(tmp, part)
    info = {"at": now.isoformat(timespec="seconds"), "file": name, "bytes": (d / name).stat().st_size, "kind": kind, **facts}
    with app.app_context():
        set_setting("backup.last", json.dumps(info))
        _prune(app)
    return info


def _prune(app):
    try:
        keep = max(1, int(get_setting("backup.keep") or 28))
    except ValueError:
        keep = 28
    rows = listing(app)
    scheduled = [r for r in rows if r["kind"] == "scheduled"]
    by_hand = [r for r in rows if r["kind"] != "scheduled"]
    for r in scheduled[keep:] + by_hand[KEEP_BY_HAND:]:
        try:
            (folder(app) / r["name"]).unlink()
        except OSError:
            pass


def _times():
    out = []
    for part in re.split(r"[,\s;]+", get_setting("backup.times") or ""):
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", part.strip())
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            out.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(out))


def latest_slot(now):
    """The hour of copying that came last before now: 'YYYY-MM-DD HH:MM', or '' when none is set."""
    times = _times()
    if not times:
        return ""
    passed = [t for t in times if t <= (now.hour, now.minute)]
    day = now.date() if passed else now.date() - timedelta(days=1)
    h, m = passed[-1] if passed else times[-1]
    return f"{day.isoformat()} {h:02d}:{m:02d}"


def tick(app, now=None):
    """
    One look of the scheduler: when an hour of copying has come and its copy is not made yet, makes
    it. Only the one that writes the hour into backup.slot makes it. Gives the copy, or None.
    """
    now = (now or now_ist()).astimezone(IST)
    with app.app_context():
        if get_setting("backup.on") != "1":
            return None
        slot = latest_slot(now)
        if not slot:
            return None
        conn = get_db()
        cur = conn.execute("INSERT INTO settings(key, value, updated_at) VALUES('backup.slot', ?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at "
                           "WHERE settings.value < excluded.value", (slot, utcnow()))
        conn.commit()
        if cur.rowcount != 1:
            return None
    try:
        info = make(app, "scheduled", now)
    except Exception as exc:
        with app.app_context():
            set_setting("backup.error", json.dumps({"at": now.isoformat(timespec="seconds"), "error": str(exc)[:300]}))
            audit("backup_failed", "backup", None, detail={"error": str(exc)[:300]})
        raise
    with app.app_context():
        audit("backup_made", "backup", None, detail=info)
    return info


def state():
    """What the console says about the copies: the last one, how old, a failure after it, and whether to warn."""
    last = json.loads(get_setting("backup.last") or "{}")
    error = json.loads(get_setting("backup.error") or "{}")
    on = get_setting("backup.on") == "1"
    age = None
    if last.get("at"):
        age = (now_ist() - datetime.fromisoformat(last["at"])).total_seconds() / 3600
    failing = bool(error.get("at")) and (not last.get("at") or error["at"] > last["at"])
    warn = ""
    if not on:
        warn = "The portal makes no copies of its database by itself (Settings › Backups of the database)."
    elif failing:
        warn = f"The last copy of the database failed: {error.get('error')}"
    elif age is None:
        warn = "There is no copy of the database yet."
    elif age > STALE_HOURS:
        warn = f"The last copy of the database is {int(age)} hours old."
    return {"last": last, "error": error, "on": on, "age_hours": age, "failing": failing, "warn": warn}


def _put_key(app, key_bytes, now):
    """The key of the stipend module of the copy: it is the key of the database put back."""
    if key_bytes is None:
        return "The copy holds no key of the stipend module; the key on the server stays."
    path = _key_path(app)
    if path.is_file() and path.read_bytes() == key_bytes:
        return "The key of the stipend module is the same."
    if path.is_file():
        aside = path.with_name(f"{KEY_NAME}.before-restore-{now:%Y%m%d-%H%M%S}")
        os.replace(path, aside)
        path.write_bytes(key_bytes)
        return f"The key of the stipend module of the copy was put in place; the key of before is kept as {aside.name}."
    path.write_bytes(key_bytes)
    return "The key of the stipend module of the copy was put in place."


def restore(app, source, now=None):
    """
    Puts a copy back into the running portal. source: the path of a copy of the listing, or the bytes
    of an uploaded one (the ZIP of a copy, or a bare database). Keeps the state of before as a copy
    first. Gives what it did: before (that copy), key, and the facts of the copy put back.
    """
    now = (now or now_ist()).astimezone(IST)
    data = source.read_bytes() if isinstance(source, Path) else bytes(source)
    d = folder(app)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".restore-{os.getpid()}-{threading.get_ident()}.sqlite3"
    key_bytes = None
    try:
        if data[:4] == b"PK\x03\x04":
            try:
                z = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile as exc:
                raise ValueError("the ZIP file is damaged") from exc
            with z:
                names = z.namelist()
                if DB_NAME not in names:
                    raise ValueError(f"the ZIP file holds no {DB_NAME}: it is not a copy made by the portal")
                if z.getinfo(DB_NAME).file_size > 4 * 1024 ** 3:
                    raise ValueError("the database in the ZIP file is too large")
                with z.open(DB_NAME) as f, open(tmp, "wb") as out:
                    shutil.copyfileobj(f, out)
                if KEY_NAME in names:
                    key_bytes = z.read(KEY_NAME)
        elif data[:16] == b"SQLite format 3\x00":
            tmp.write_bytes(data)
        else:
            raise ValueError("the file is neither a copy made by the portal (ZIP) nor a database")
        facts = _check(tmp)
        if not facts["ok"]:
            raise ValueError("the database in the copy is damaged (quick_check)")
        before = make(app, "before-restore", now)
        _copy_db(tmp, app.config["DATABASE"])
        # the tables, columns and settings of this version, as at a start of the portal
        init_db(app)
        key = _put_key(app, key_bytes, now)
    finally:
        _remove(tmp)
    return {"before": before["file"], "key": key, **facts}


def start(app):
    """
    The scheduler in the background: one thread, started by serve.py (and run.py) when the portal
    is served, never by create_app, so that tests and scripts have none. Looks every TICK_SECONDS.
    """
    if app.config.get("TESTING") or not app.config.get("BACKUPS", True):
        return None
    if app.extensions.get("kts_backup"):
        return app.extensions["kts_backup"]

    def loop():
        while True:
            try:
                tick(app)
            except Exception:  # noqa: BLE001 - the scheduler never stops for one failed copy
                app.logger.exception("backup: the copy of the database failed")
            time.sleep(TICK_SECONDS)

    thread = threading.Thread(target=loop, name="kts-backup", daemon=True)
    app.extensions["kts_backup"] = thread
    thread.start()
    return thread


def uploads_size(app):
    """Files and bytes of the uploads, which these copies do not hold."""
    files = size = 0
    stack = [Path(app.config["UPLOAD_DIR"])]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                stack.append(Path(e.path))
            elif e.is_file(follow_symlinks=False):
                files += 1
                size += e.stat().st_size
    return files, size

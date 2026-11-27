"""
Gallery (from 1.2.20): photographs of Kashi Tamil Sangamam 5.0, in albums, on a public page.

Staff of the content role upload the photographs in the console (several at once; JPG, PNG or WebP
of up to 8 MB each), with a caption and an album (an event: a campus programme, an orientation
session, the Sangamam itself). The files lie in uploads/gallery/ and are served at /files/gallery/…;
no thumbnail is made (the live server has no image library), so the browser scales the photograph
as uploaded. A photograph that is not published is seen in the console only.
"""
import json
import posixpath
from functools import lru_cache
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, url_for

from .admin import bp as console
from .auth import current_user, login_required
from .db import audit, execute, query, utcnow
from .public import bp as public
from .utils import client_ip, safe_int, save_upload

PHOTO_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_BYTES = 8 * 1024 * 1024
MOST_AT_ONCE = 30


def albums(published_only=True):
    """The albums with their counts, the newest event first; an album is the event named on its photographs."""
    where = " WHERE published = 1" if published_only else ""
    return query(f"SELECT album, COUNT(*) AS n, MAX(taken_on) AS last FROM gallery_photos{where} GROUP BY album "
                 "ORDER BY last DESC, album")


# the YouTube channels of the shorts of KTS 5.0 (1.2.231), the Ministry's first
SHORT_CHANNELS = (
    {"key": "moe", "name": "Ministry of Education, Government of India", "account": "Eduminofindia",
     "url": "https://www.youtube.com/@Eduminofindia/shorts"},
    {"key": "kts", "name": "Kashi Tamil Sangamam", "account": "KashiTamilSangamam", "url": "https://www.youtube.com/@KashiTamilSangamam/shorts"},
)


@lru_cache(maxsize=4)
def _shorts(path, static):
    rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    videos = []
    for r in rows:
        cover = f"img/shorts/{r['id']}.webp"
        if not (static / cover).is_file():      # a short is shown with its cover only
            continue
        videos.append(dict(r, cover=cover, url=f"https://www.youtube.com/shorts/{r['id']}", duration=f"{r['seconds'] // 60}:{r['seconds'] % 60:02d}"))
    channels = [dict(c, videos=[v for v in videos if v["channel"] == c["key"]]) for c in SHORT_CHANNELS]
    latest = sorted(videos, key=lambda v: (v["date"], v.get("time", "")), reverse=True)[:6]      # by the day and the hour (IST)
    return {"count": len(videos), "channels": [c for c in channels if c["videos"]], "latest": latest}


def shorts():
    """
    The shorts of KTS 5.0 on YouTube (1.2.231; CICT, 27 November 2026: "kts5.0 2026 ministry of education add all shorts in the
    youtube"): data/shorts.json, those of the Ministry of Education's channel and of the Kashi Tamil Sangamam channel, each with its
    cover kept on the portal (static/img/shorts/), newest first within its channel; the six latest of both for the page of all the
    albums.
    """
    return _shorts(Path(current_app.config["DATA_DIR"]) / "shorts.json", Path(current_app.static_folder))


@public.route("/gallery")
def gallery():
    album = (request.args.get("album") or "").strip()
    sql = "SELECT * FROM gallery_photos WHERE published = 1"
    args = []
    if album:
        sql += " AND album = ?"
        args.append(album)
    photos = query(sql + " ORDER BY taken_on DESC, sort_order, id DESC", args)
    return render_template("public/gallery.html", photos=photos, albums=albums(), album=album, shorts=shorts(), shorts_page=False)


@public.route("/gallery/shorts")
def gallery_shorts():
    """The shorts of KTS 5.0 on YouTube, channel by channel (1.2.231): played on the page."""
    return render_template("public/gallery.html", photos=[], albums=albums(), album="", shorts=shorts(), shorts_page=True)


# ---- the console ----------------------------------------------------------------------------------

@console.route("/gallery", methods=["GET", "POST"])
@login_required("content")
def gallery_admin():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action") or "upload"
        if action == "upload":
            album = " ".join((request.form.get("album") or "").split())[:120]
            caption = " ".join((request.form.get("caption") or "").split())[:300]
            taken = (request.form.get("taken_on") or "").strip()[:10]
            files = [f for f in request.files.getlist("photos") if f and f.filename][:MOST_AT_ONCE]
            if not album:
                flash("Name the album (the event the photographs belong to).", "error")
            elif not files:
                flash("Choose one or more photographs.", "error")
            else:
                saved, refused = 0, []
                for f in files:
                    try:
                        path, name, size = save_upload(f, "gallery", PHOTO_EXT, MAX_BYTES)
                    except ValueError as exc:
                        refused.append(f"{f.filename} ({'too large' if str(exc) == 'size' else 'not a JPG, PNG or WebP'})")
                        continue
                    execute("INSERT INTO gallery_photos(album, caption, taken_on, file_path, file_name, file_size, published, "
                            "sort_order, created_by, created_at) VALUES(?,?,?,?,?,?,1,100,?,?)",
                            (album, caption, taken, path, name, size, user["id"], utcnow()))
                    saved += 1
                audit("gallery_upload", "gallery", None, detail={"album": album, "saved": saved, "refused": len(refused)},
                      user=user, ip=client_ip())
                if saved:
                    flash(f"{saved} photograph(s) added to the album “{album}”.", "success")
                if refused:
                    flash("Not taken: " + "; ".join(refused[:10]) + (" …" if len(refused) > 10 else ""), "warning")
        else:
            pid = safe_int(request.form.get("id"))
            row = query("SELECT * FROM gallery_photos WHERE id = ?", (pid,), one=True)
            if row is None:
                abort(404)
            if action == "toggle":
                execute("UPDATE gallery_photos SET published = 1 - published WHERE id = ?", (pid,))
            elif action == "caption":
                execute("UPDATE gallery_photos SET caption = ?, album = ?, taken_on = ?, sort_order = ? WHERE id = ?",
                        (" ".join((request.form.get("caption") or "").split())[:300],
                         " ".join((request.form.get("album") or "").split())[:120] or row["album"],
                         (request.form.get("taken_on") or "").strip()[:10], safe_int(request.form.get("sort_order"), 100), pid))
            elif action == "delete":
                execute("DELETE FROM gallery_photos WHERE id = ?", (pid,))
                folder = current_app.config["UPLOAD_DIR"]
                try:
                    (folder / posixpath.normpath(row["file_path"])).unlink()
                except OSError:
                    pass
                audit("gallery_delete", "gallery", pid, detail=row["file_name"], user=user, ip=client_ip())
            else:
                abort(400)
        return redirect(url_for("admin.gallery_admin", album=request.form.get("show") or ""))
    album = (request.args.get("album") or "").strip()
    sql = "SELECT p.*, u.name AS by_name FROM gallery_photos p LEFT JOIN users u ON u.id = p.created_by"
    args = []
    if album:
        sql += " WHERE p.album = ?"
        args.append(album)
    photos = query(sql + " ORDER BY p.taken_on DESC, p.sort_order, p.id DESC LIMIT 400", args)
    return render_template("console/gallery.html", photos=photos, albums=albums(published_only=False), album=album,
                           most=MOST_AT_ONCE)

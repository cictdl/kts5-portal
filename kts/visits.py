"""
Visitors of the portal, counted without keeping who they are (version 1.2.31).

A visitor is one browser on one day: its address and the name of the browser, mixed with a random
key of that day which is never written anywhere (BLAKE2b). Neither the address nor the mixture can be
traced back, and both are forgotten when the day ends; the table visit_days keeps only the day, the
number of visitors and the number of pages they opened.

Counted: pages (text/html, GET, answer 200) of the public site, the candidate portal and the quiz.
Not counted: the console and the hub of the staff, files, the answers of the quiz and of the test
(JSON), the health check, and robots (search engines, link previews, monitors, scripts).

The counts stay in memory and are written once a minute (FLUSH_SECONDS), not once a page: the portal
answers many students at once on the day of the test. A restart of the portal forgets the visitors
of the day it already counted, so a visitor who comes back that day is counted again; at most the
last minute of pages is lost.
"""
import hashlib
import re
import secrets
import threading
import time

from flask import current_app, request

from .db import get_db, query
from .utils import client_ip, now_ist

FLUSH_SECONDS = 60
TOTAL_SECONDS = 60
NOT_COUNTED = ("/console", "/hub", "/static/", "/healthz", "/lang/", "/robots.txt", "/favicon")
ROBOTS = re.compile(r"bot|crawl|spider|slurp|archiver|curl|wget|python|httpx|aiohttp|java/|go-http|okhttp|libwww|"
                    r"headless|phantom|monitor|uptime|pingdom|preview|facebookexternalhit|whatsapp|telegram|"
                    r"skype|slack|discord|lighthouse|scan|check", re.I)


class Visits:
    def __init__(self):
        self.lock = threading.Lock()
        self.day = None
        self.key = b""
        self.seen = set()
        self.visitors = 0      # not yet written, of self.day
        self.views = 0
        self.flushed = time.monotonic()
        self.total = None      # (sum of the table, when it was read)

    def _new_day(self, day):
        """A new day: what is left of the day before goes to its own row."""
        if self.day is not None and (self.visitors or self.views):
            self._write()
        self.day, self.key, self.seen = day, secrets.token_bytes(32), set()

    def _write(self):
        conn = get_db()
        conn.execute("INSERT INTO visit_days(day, visitors, views) VALUES(?, ?, ?) "
                     "ON CONFLICT(day) DO UPDATE SET visitors = visitors + excluded.visitors, views = views + excluded.views",
                     (self.day, self.visitors, self.views))
        conn.commit()
        self.visitors = self.views = 0
        self.flushed = time.monotonic()
        self.total = None

    def record(self, resp):
        if request.method != "GET" or resp.status_code != 200 or resp.mimetype != "text/html":
            return
        if request.path.startswith(NOT_COUNTED):
            return
        agent = request.headers.get("User-Agent", "")
        if not agent or ROBOTS.search(agent):
            return
        day = now_ist().date().isoformat()
        with self.lock:
            if day != self.day:
                self._new_day(day)
            mark = hashlib.blake2b(f"{client_ip()}|{agent}".encode("utf-8", "replace"), key=self.key, digest_size=16).digest()
            if mark not in self.seen:
                self.seen.add(mark)
                self.visitors += 1
            self.views += 1
            if time.monotonic() - self.flushed >= current_app.config.get("VISITS_FLUSH_SECONDS", FLUSH_SECONDS):
                self._write()

    def flush(self):
        with self.lock:
            if self.day is not None and (self.visitors or self.views):
                self._write()

    def figures(self):
        """{"total": visitors since the counting began, "today": visitors of today}, for the footer."""
        today = now_ist().date().isoformat()
        with self.lock:
            if self.total is None or time.monotonic() - self.total[1] >= TOTAL_SECONDS:
                row = query("SELECT COALESCE(SUM(visitors), 0) AS n FROM visit_days", one=True)
                self.total = (row["n"], time.monotonic())
            written_today = query("SELECT visitors FROM visit_days WHERE day = ?", (today,), one=True)
            pending = self.visitors if self.day == today else 0
            return {"total": self.total[0] + pending, "today": (written_today["visitors"] if written_today else 0) + pending}


def visits(app=None):
    app = app or current_app
    return app.extensions.setdefault("kts_visits", Visits())


def days(count=30):
    """The last `count` days, newest first: (day, visitors, pages), with what is not yet written."""
    v = visits()
    v.flush()
    rows = {r["day"]: r for r in query("SELECT * FROM visit_days ORDER BY day DESC LIMIT ?", (count,))}
    out = []
    from datetime import timedelta
    for i in range(count):
        d = (now_ist() - timedelta(days=i)).date().isoformat()
        r = rows.get(d)
        out.append((d, r["visitors"] if r else 0, r["views"] if r else 0))
    return out

"""
Application factory for the Kashi Tamil Sangamam 5.0 portal.
"""
import logging
import os
from pathlib import Path

from flask import Flask, render_template, request

from config import Config


def create_app(config_object=Config):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
                static_folder=str(Path(__file__).resolve().parent.parent / "static"))
    app.config.from_object(config_object)
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from . import admin, agency, auth, candidate, db, i18n, public, utils
    from . import kural as K

    db.init_app(app)
    i18n.register(app)
    auth.register(app)

    app.register_blueprint(public.bp)
    app.register_blueprint(candidate.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(agency.bp)

    # ---- request guards -------------------------------------------------
    @app.before_request
    def _csrf():
        if request.endpoint in ("public.healthz",) or request.path.startswith("/static/"):
            return
        utils.check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith(("/console", "/candidate", "/hub")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---- template helpers -------------------------------------------------
    # Dates carry English month names only in the English interface; every other language gets
    # 25-09-2026 and the 24-hour clock, which need no translation.
    def _numeric():
        return i18n.get_lang() != "en"

    def _ltr(text):
        # In a right-to-left sentence the parts of 25-09-2026 would change places; the invisible
        # marks U+2066 and U+2069 keep the date together, left to right.
        if text and i18n.LANG_INFO[i18n.get_lang()]["dir"] == "rtl":
            return f"⁦{text}⁩"
        return text

    app.jinja_env.filters["date"] = lambda value: _ltr(utils.fmt_date(value, _numeric()))
    app.jinja_env.filters["datetime"] = lambda value: _ltr(utils.fmt_dt(value, _numeric()))
    app.jinja_env.filters["time"] = lambda value: _ltr(utils.fmt_time(value, _numeric()))
    app.jinja_env.filters["size"] = utils.human_size
    app.jinja_env.filters["langname"] = lambda code: (K.lang_info(code) or {}).get("name", code)
    app.jinja_env.filters["langnative"] = lambda code: (K.lang_info(code) or {}).get("native", code)

    logos_dir = Path(app.static_folder) / "img" / "logos"

    def agency_logo(code):
        """Static path of an agency's logo (static/img/logos/<code>.png), or None when there is none."""
        name = (code or "").strip().lower()
        return f"img/logos/{name}.png" if name and (logos_dir / f"{name}.png").is_file() else None

    @app.context_processor
    def _globals():
        return {
            "agency_logo": agency_logo,
            "csrf_token": utils.csrf_token,
            "site": {
                "name": app.config["SITE_NAME"], "short": app.config["SITE_SHORT"],
                "theme_en": app.config["SITE_THEME_EN"], "theme_ta": app.config["SITE_THEME_TA"],
                "theme_hi": app.config["SITE_THEME_HI"], "organiser": app.config["ORGANISER"],
                "ministry": app.config["MINISTRY"], "base_url": app.config["BASE_URL"],
            },
            "get_setting": db.get_setting,
            "now_ist": utils.now_ist,
        }

    # ---- errors ---------------------------------------------------------
    def _error(code, text=None):
        return render_template("error.html", code=code, title=i18n.t(f"err.{code}.t"),
                               text=text or i18n.t(f"err.{code}.d")), code

    @app.errorhandler(403)
    def _forbidden(_e):
        return _error(403)

    @app.errorhandler(404)
    def _not_found(_e):
        return _error(404)

    @app.errorhandler(413)
    def _too_large(_e):
        return _error(413)

    @app.errorhandler(400)
    def _bad(e):
        # the description of a 400 raised by the portal is the key of its message
        key = getattr(e, "description", "") or ""
        return _error(400, i18n.t(key) if key.startswith("err.") else key)

    @app.errorhandler(500)
    def _server(_e):
        return _error(500)

    # ---- hosting: reverse proxy headers and URL prefix -------------------
    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    prefix = app.config.get("URL_PREFIX")
    if prefix:
        app.wsgi_app = _PrefixMiddleware(app.wsgi_app, prefix)

    if os.environ.get("KTS_LAZY_CORPUS") != "1":
        K.corpus()  # warm the corpus cache at start-up (skipped for per-request CGI hosting)
    return app


class _PrefixMiddleware:
    """Mount the application under a path prefix (IIS application, sub-path proxy)."""

    def __init__(self, wsgi_app, prefix):
        self.app = wsgi_app
        self.prefix = "/" + prefix.strip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            return self.app(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [f"Not found. The portal is served under {self.prefix}/".encode("utf-8")]

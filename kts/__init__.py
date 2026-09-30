"""
Application factory for the Kashi Tamil Sangamam 5.0 portal.
"""
import logging
import os
from pathlib import Path

from flask import Flask, make_response, render_template, request
from jinja2 import pass_context
from werkzeug.routing import IntegerConverter

from config import Config


class _RowNumber(IntegerConverter):
    """
    <int:...> in an address: 1 to 18 digits. A longer number is no row of the database, which
    holds numbers up to 9223372036854775807, and answers 404 like any address that does not exist.
    """
    regex = r"\d{1,18}"


def create_app(config_object=Config):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
                static_folder=str(Path(__file__).resolve().parent.parent / "static"))
    app.config.from_object(config_object)
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    # /about/ is served like /about; set before the blueprints bring their routes
    app.url_map.strict_slashes = False
    # the same for the numbers: a route reads its converter when it is added
    app.url_map.converters["int"] = _RowNumber
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    unused = app.config.get("SETTINGS_UNUSED_LINES")
    if unused:
        # the numbers of the lines, never their text: a line that went wrong may hold a password
        app.logger.warning("%s: no setting could be read from %s %s. A setting is written NAME=value.",
                           Path(app.config["INSTANCE_DIR"]) / "portal.env", "line" if len(unused) == 1 else "lines",
                           ", ".join(str(n) for n in unused))
    unusable = app.config.get("SETTINGS_UNUSABLE")
    if unusable:
        # the names, never the values; the value may come from the environment or from the file
        app.logger.warning("These settings have a value that cannot be used (a limit is a whole number above "
                           "zero, a switch is 1 or 0): %s. In portal.env nothing may follow the value on its line.",
                           ", ".join(unusable))

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
        # Scripts, styles, fonts and frames come from the portal alone; the QR code is a data: image
        # and the templates carry style attributes. No template may have a script or an onclick.
        # For pages and SVG pictures only: a PDF that the browser shows in its own viewer must not
        # carry the policy. An SVG picture that is opened by itself is a document of the portal,
        # and an uploaded one may hold a script.
        if resp.mimetype in ("text/html", "image/svg+xml"):
            resp.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                    "script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
                                    "frame-ancestors 'self'")
        if request.path.startswith(("/console", "/candidate", "/hub", "/register", "/status", "/contact")):
            resp.headers["Cache-Control"] = "no-store"
        if app.config.get("HSTS") and app.config.get("SESSION_COOKIE_SECURE"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
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

    # Jinja works out a filter on a literal ({{ '2022-11-16'|date }}) once, when it compiles the
    # template, and the language of that moment would stay in the page. A filter that takes the
    # context is never worked out in advance.
    @pass_context
    def _date(_ctx, value):
        return _ltr(utils.fmt_date(value, _numeric()))

    @pass_context
    def _datetime(_ctx, value):
        return _ltr(utils.fmt_dt(value, _numeric()))

    @pass_context
    def _when(_ctx, value):
        return _ltr(utils.fmt_when(value, _numeric()))

    @pass_context
    def _time(_ctx, value):
        return _ltr(utils.fmt_time(value, _numeric()))

    app.jinja_env.filters["date"] = _date
    app.jinja_env.filters["datetime"] = _datetime
    app.jinja_env.filters["when"] = _when
    app.jinja_env.filters["time"] = _time
    app.jinja_env.filters["size"] = utils.human_size
    app.jinja_env.filters["langname"] = lambda code: (K.lang_info(code) or {}).get("name", code)
    app.jinja_env.filters["langnative"] = lambda code: (K.lang_info(code) or {}).get("native", code)
    app.jinja_env.filters["langtag"] = K.lang_tag

    logos_dir = Path(app.static_folder) / "img" / "logos"

    def agency_logo(code):
        """Static path of an agency's logo (static/img/logos/<code>.png), or None when there is none."""
        name = (code or "").strip().lower()
        return f"img/logos/{name}.png" if name and (logos_dir / f"{name}.png").is_file() else None

    def banner_state():
        """
        What the banner says: "own" for wording of the administrator. The wording the portal came
        with announces that applications are open, so with it the banner follows the registration:
        "open", "not_yet" (it names the first day) or "closed".
        """
        settings = db.all_settings()
        if settings.get("site.banner") != db.DEFAULT_SETTINGS["site.banner"]:
            return "own"
        return utils.registration_state(settings)

    @app.context_processor
    def _globals():
        return {
            "agency_logo": agency_logo,
            "csrf_token": utils.csrf_token,
            "site": {
                "name": app.config["SITE_NAME"], "short": app.config["SITE_SHORT"],
                "theme_en": app.config["SITE_THEME_EN"], "theme_ta": app.config["SITE_THEME_TA"],
                "theme_hi": app.config["SITE_THEME_HI"], "theme_meaning": app.config["SITE_THEME_MEANING"],
                "organiser": app.config["ORGANISER"],
                "ministry": app.config["MINISTRY"], "base_url": app.config["BASE_URL"],
            },
            "get_setting": db.get_setting,
            "banner_state": banner_state,
            "social_links": db.social_links,
            "nodal_officers": db.nodal_officers,
            "now_ist": utils.now_ist,
        }

    # ---- errors ---------------------------------------------------------
    def _error(code, text=None, title=None):
        return render_template("error.html", code=code, title=title or i18n.t(f"err.{code}.t"),
                               text=text or i18n.t(f"err.{code}.d")), code

    @app.errorhandler(403)
    def _forbidden(_e):
        return _error(403)

    @app.errorhandler(404)
    def _not_found(_e):
        return _error(404)

    @app.errorhandler(405)
    def _method(e):
        # a GET on an address that takes POST only, such as /console/logout: there is no page
        # to show at this address, so the page says what the 404 page says
        page, _code = _error(405, i18n.t("err.404.d"), i18n.t("err.404.t"))
        resp = make_response(page, 405)
        if getattr(e, "valid_methods", None):
            resp.headers["Allow"] = ", ".join(e.valid_methods)
        return resp

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

    # ---- hosting: URL prefix ---------------------------------------------
    # No forwarding header is read here. Behind a proxy (KTS_BEHIND_PROXY=1) Waitress puts the
    # visitor's address into REMOTE_ADDR, see server_options() in serve.py.
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

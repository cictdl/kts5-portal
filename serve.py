"""
Production entry point: Waitress WSGI server (works on Windows and Linux).

    python serve.py                      -> 0.0.0.0:8905, 8 threads
    KTS_PORT=8080 KTS_THREADS=16 python serve.py

Put a reverse proxy (IIS with ARR/URL Rewrite, nginx or Apache) in front for
TLS, and set KTS_HTTPS=1 so session cookies are marked Secure. With a proxy on
the same machine set KTS_BEHIND_PROXY=1 as well: the visitor's address is then
taken from the entry that the proxy adds to X-Forwarded-For.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Vendored dependencies (Plesk package): lib/ next to this file is used when present,
# so the portal runs with only python.exe installed on the server.
_LIB = Path(__file__).resolve().parent / "lib"
if _LIB.is_dir():
    sys.path.insert(0, str(_LIB))

from waitress import serve  # noqa: E402

from config import _env, _int_env  # noqa: E402
from kts import create_app  # noqa: E402


class _ShortArguments(logging.Filter):
    """
    Cuts the long arguments of a log record. Waitress writes a forwarding header that it refuses
    into the log with its whole value, and the log of the web server is never rotated.
    """

    def filter(self, record):
        # a record with one dictionary as argument has no tuple here
        if isinstance(record.args, tuple):
            record.args = tuple(a[:200] + "..." if isinstance(a, str) and len(a) > 200 else a
                                for a in record.args)
        return True


# the logger that Waitress hands to its reading of the forwarding headers; the records of other
# loggers, the portal's own among them, stay as they are
logging.getLogger("waitress").addFilter(_ShortArguments())


def port():
    """
    The port to listen on: KTS_PORT, or the port that the web server chose when it started the
    portal (HTTP_PLATFORM_PORT under IIS's HttpPlatformHandler, ASPNETCORE_PORT under IIS's
    ASP.NET Core Module, PORT elsewhere), else 8905.
    """
    for name in ("KTS_PORT", "HTTP_PLATFORM_PORT", "ASPNETCORE_PORT", "PORT"):
        value = (os.environ.get(name) or "").strip()
        if value.isdigit():
            return int(value)
    return 8905


def server_options():
    """
    The arguments for Waitress, in a function so that the tests can read them without starting
    a server.
    """
    options = {
        "host": _env("KTS_HOST", "0.0.0.0"),
        "port": port(),
        "threads": _int_env("KTS_THREADS", 8),
        "url_scheme": "https" if _env("KTS_HTTPS") == "1" else "http",
        # no "Server: waitress" in the answers
        "ident": None,
        # X-Forwarded-For, -Host, -Proto, -Port, -By and Forwarded never reach the portal as the
        # visitor wrote them
        "clear_untrusted_proxy_headers": True,
    }
    if _env("KTS_BEHIND_PROXY") == "1":
        # The web server in front connects from this address and appends the visitor's address
        # to X-Forwarded-For; only that last entry is believed. The scheme comes from KTS_HTTPS
        # and the host name from the Host header, so no other forwarding header is trusted.
        options["trusted_proxy"] = _env("KTS_TRUSTED_PROXY", "127.0.0.1")
        options["trusted_proxy_count"] = 1
        options["trusted_proxy_headers"] = {"x-forwarded-for"}
    return options


if __name__ == "__main__":
    app = create_app()
    # the mails of the outbox go out in the background, within the limits of the mail account (1.2.35)
    from kts import mailq  # noqa: E402
    mailq.start(app)
    # the copies of the database at the hours of backup.times (1.2.40)
    from kts import backup  # noqa: E402
    backup.start(app)
    serve(app, **server_options())

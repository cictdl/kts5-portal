"""
KTS 5.0 portal · CGI launcher for Plesk "Python support" (fallback when the
HttpPlatformHandler module is not available).

Place this file in the subdomain folder next to kts/, lib/, static/ and
templates/. With Plesk's Python support switched on, every request to
https://<subdomain>/kts5.py/... runs this script once (CGI), so the portal is
reachable at https://<subdomain>/kts5.py/ and generates all its links under
that prefix. Slower than the normal mode (each request starts Python) but it
needs nothing installed by the server administrator.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
os.chdir(HERE)

script = os.environ.get("SCRIPT_NAME") or "/kts5.py"
os.environ.setdefault("KTS_URL_PREFIX", script)
os.environ.setdefault("KTS_BEHIND_PROXY", "0")
os.environ.setdefault("KTS_HTTPS", "1" if os.environ.get("HTTPS", "").lower() in ("on", "1") else "0")
os.environ.setdefault("KTS_LAZY_CORPUS", "1")
if "KTS_BASE_URL" not in os.environ:
    scheme = "https" if os.environ["KTS_HTTPS"] == "1" else "http"
    os.environ["KTS_BASE_URL"] = f"{scheme}://{os.environ.get('SERVER_NAME', 'localhost')}{script}"

from wsgiref.handlers import CGIHandler  # noqa: E402

from kts import create_app  # noqa: E402

# IIS hands the part after the script name in PATH_INFO; the app's prefix
# middleware expects the full path, so put the two back together.
os.environ["PATH_INFO"] = script + (os.environ.get("PATH_INFO") or "/")
os.environ["SCRIPT_NAME"] = ""
CGIHandler().run(create_app())

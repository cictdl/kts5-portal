"""
Production entry point: Waitress WSGI server (works on Windows and Linux).

    python serve.py                      -> 0.0.0.0:8905, 8 threads
    KTS_PORT=8080 KTS_THREADS=16 python serve.py

Put a reverse proxy (IIS with ARR/URL Rewrite, nginx or Apache) in front for
TLS, and set KTS_HTTPS=1 so session cookies are marked Secure.
"""
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

from kts import create_app  # noqa: E402

if __name__ == "__main__":
    app = create_app()
    serve(app, host=os.environ.get("KTS_HOST", "0.0.0.0"), port=int(os.environ.get("KTS_PORT", "8905")),
          threads=int(os.environ.get("KTS_THREADS", "8")), url_scheme="https" if os.environ.get("KTS_HTTPS") == "1" else "http")

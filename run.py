"""
Development server for the KTS 5.0 portal.

    python run.py            -> http://127.0.0.1:8905

Set KTS_DEBUG=1 for Flask's debugger (never in production).
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

from kts import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("KTS_PORT", "8905"))
    app.run(host=os.environ.get("KTS_HOST", "127.0.0.1"), port=port,
            debug=os.environ.get("KTS_DEBUG") == "1", use_reloader=False, threaded=True)

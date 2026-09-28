"""
Every test works on a throw-away database and upload folder.

config.py reads KTS_DATABASE and KTS_UPLOAD_DIR once, when it is first imported. They are therefore
set here, which pytest loads before any test module, and never inside a fixture: a test that
imported the `kts` package before its fixture ran would otherwise open the real
instance/kts5.sqlite3. `make_app` refuses to start on anything but the temporary database.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="kts5-test-"))

os.environ["KTS_INSTANCE_DIR"] = str(TMP / "instance")
os.environ["KTS_DATABASE"] = str(TMP / "instance" / "test.sqlite3")
os.environ["KTS_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["KTS_SECRET_KEY"] = "tests-only-" + TMP.name
os.environ["KTS_ADMIN_PASSWORD"] = "Admin@KTS5"
for name in ("KTS_URL_PREFIX", "KTS_BEHIND_PROXY", "KTS_HTTPS", "KTS_SMTP_HOST"):
    os.environ.pop(name, None)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def make_app():
    from config import Config
    from kts import create_app
    database = Path(Config.DATABASE).resolve()
    if TMP.resolve() not in database.parents:
        raise RuntimeError(f"the tests would run on {database}; config.py was imported before tests/conftest.py")
    app = create_app(Config)
    app.config["TESTING"] = True
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.start", "2026-01-01")
        set_setting("reg.end", "2030-12-31")
    return app


@pytest.fixture(scope="session")
def app():
    return make_app()


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c

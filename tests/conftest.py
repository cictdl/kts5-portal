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
# a password of the tests' own; the tests read it from here
os.environ["KTS_ADMIN_PASSWORD"] = "Tests-Only-" + TMP.name[-8:] + "-7Q"
for name in ("KTS_URL_PREFIX", "KTS_BEHIND_PROXY", "KTS_TRUSTED_PROXY", "KTS_HTTPS", "KTS_HSTS", "KTS_SMTP_HOST",
             "KTS_SMTP_PORT", "KTS_SMTP_TLS",
             "KTS_ADMIN_EMAIL", "KTS_BASE_URL", "KTS_HOST", "KTS_THREADS", "KTS_RATE_REGISTER_PER_HOUR",
             "KTS_RATE_CONTACT_PER_HOUR", "KTS_RATE_STATUS_FAILS", "KTS_RATE_LOGIN_FAILS",
             "KTS_RATE_CANDIDATE_FAILS_IP", "KTS_RATE_CANDIDATE_FAILS_APP"):
    os.environ.pop(name, None)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def make_app(**settings):
    """
    The application on the temporary database. With settings (names of config.Config, for
    example HSTS=True or ADMIN_PASSWORD=None) it is an application of its own, with a database,
    an instance folder and an upload folder of its own inside the temporary folder.
    """
    from config import Config
    from kts import create_app
    config = Config
    if settings:
        folder = Path(tempfile.mkdtemp(prefix="app-", dir=TMP))
        values = {"INSTANCE_DIR": folder / "instance", "DATABASE": folder / "instance" / "test.sqlite3",
                  "UPLOAD_DIR": folder / "uploads"}
        values.update(settings)
        config = type("TestConfig", (Config,), values)
    for name in ("DATABASE", "INSTANCE_DIR", "UPLOAD_DIR"):
        path = Path(getattr(config, name)).resolve()
        if TMP.resolve() not in path.parents:
            raise RuntimeError(f"the tests would run on {path}; config.py was imported before tests/conftest.py")
    app = create_app(config)
    app.config["TESTING"] = True
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.start", "2026-01-01")
        set_setting("reg.end", "2030-12-31")
    return app


def add_candidates(app, count):
    """
    Applications written straight into the database of this application, one per student of a
    campus. Gives the details of each as the sign-in and the status page ask for them.
    """
    from kts.db import execute, utcnow
    from kts.utils import make_app_no
    students = []
    with app.app_context():
        for n in range(1, count + 1):
            mobile = f"98765{n:05d}"
            row_id = execute(
                "INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, "
                "pref_lang, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f"Campus Student {n}", "F", "2004-05-06", mobile, f"campus{n}@tests.example", "Kerala",
                 "Government College Thrissur", "name:government thrissur|kerala", "hi", utcnow(), utcnow()))
            execute("UPDATE applications SET app_no = ? WHERE id = ?", (make_app_no(row_id), row_id))
            students.append({"app_no": make_app_no(row_id), "dob": "2004-05-06", "last4": mobile[-4:]})
    return students


@pytest.fixture(scope="session")
def app():
    return make_app()


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c

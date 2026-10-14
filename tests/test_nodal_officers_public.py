"""
The Nodal Officer of each State/UT on the Nodal HEIs and Partners pages (1.2.70): the active Nodal Officer accounts with
the name, designation, e-mail and phone given for them, in the row of each State/UT they look after; accounts that are
switched off and other roles are never shown; CICT can switch the column off in the Console.

    python -m pytest tests -q
"""
import re

from conftest import make_app


def _account(email, name, states, phone="", designation="", active=1, role="nodal"):
    from kts.db import execute, utcnow
    execute("INSERT INTO users(email, name, password_hash, role, phone, active, created_at, states, designation) "
            "VALUES(?,?,?,?,?,?,?,?,?)", (email, name, "-", role, phone, active, utcnow(), "|".join(states), designation))


def _row(page, state):
    m = re.search(r"<tr>(?:(?!</tr>).)*?" + re.escape(state) + r"(?:(?!</tr>).)*</tr>", page, re.S)
    assert m, state
    return m.group(0)


def test_the_nodal_officers_on_the_public_pages():
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        _account("nodal.tn@example.org", "Dr. A. Arasu", ["Tamil Nadu"], "044-2254 0125", "Professor, Nodal Officer for KTS 5.0")
        _account("nodal.south@example.org", "Dr. B. Bhaskar", ["Andhra Pradesh", "Telangana"], "9876543210")
        _account("gone@example.org", "Dr. C. Gone", ["Kerala"], "9000000000", active=0)
        _account("staff@example.org", "A Staff Member", ["Kerala"], role="viewer")
    client = app.test_client()
    page = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert "<th>Nodal Officer</th>" in page
    tn = _row(page, "Tamil Nadu")
    for text in ("<b>Dr. A. Arasu</b>", "Professor, Nodal Officer for KTS 5.0", '<a href="mailto:nodal.tn@example.org">nodal.tn@example.org</a>',
                 '<a href="tel:044-22540125">044-2254 0125</a>'):
        assert text in tn, text
    # one officer for two States/UTs: in both rows; a State/UT without an officer shows a dash
    assert "Dr. B. Bhaskar" in _row(page, "Andhra Pradesh") and "Dr. B. Bhaskar" in _row(page, "Telangana")
    assert ">–</td>" in _row(page, "Goa")
    # never an account that is switched off, nor another role
    assert "Dr. C. Gone" not in page and "A Staff Member" not in page and "9000000000" not in page
    # the heading in the language of the page, and the Partners page with the same table
    assert "<th>பொறுப்பு அலுவலர்</th>" in client.get("/nodal-institutions?lang=ta").get_data(as_text=True)
    assert "Dr. A. Arasu" in client.get("/partners?lang=en").get_data(as_text=True)
    # switched off in the Console: no column at all
    with app.app_context():
        from kts.db import set_setting
        set_setting("nodal.officers_public", "0")
    page = app.test_client().get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert "Nodal Officer</th>" not in page and "Dr. A. Arasu" not in page and 'colspan="2"' in page


def test_no_column_without_officers():
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert "Nodal Officer</th>" not in page and "Central University of Andhra Pradesh" in page

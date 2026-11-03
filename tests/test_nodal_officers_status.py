"""
The Nodal Officers on the portal (version 1.2.139): a section of the public page of the Nodal Institutions - three rings (the
rows of Annexure-I with a Nodal Officer, those yet to nominate, the Participating Institutions under an officer), the four steps
by which an officer is added, a dot in the table for each row - and the same as a one-page report in Word made by the portal,
in the 23 languages; both only while CICT shows the officers on the public pages (nodal.officers_public).

    python -m pytest tests -q
"""
import io
import zipfile

from markupsafe import escape

from conftest import make_app
from test_nodal_access import _nodal
from test_public_fixes import _staff

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _portal():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    _nodal(app, "nodal.kl@cuk.example", ["Kerala"])
    _nodal(app, "nodal.tn@cutn.example", ["Tamil Nadu"])
    with app.app_context():
        execute("UPDATE users SET name = 'Dr. K. Officer', designation = 'Registrar, Central University of Kerala' WHERE email = 'nodal.kl@cuk.example'")
        execute("UPDATE users SET name = 'Dr. T. N. Officer', designation = 'Professor' WHERE email = 'nodal.tn@cutn.example'")
    return app


def test_the_section_and_the_dots_of_the_table():
    app = _portal()
    page = app.test_client().get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert '<section class="card prog prog-in no-status" id="officers"' in page
    assert '<h2 id="no-h" style="margin-top:0">The Nodal Officers on the portal</h2>' in page and "As the portal shows them on " in page
    # the rings: 2 of 31 with an officer, 29 to nominate, 71 of 1,000 Participating Institutions under an officer (Kerala 21 + Tamil Nadu 50)
    rings = page[page.index('class="prog-rings no-rings"'):page.index('class="no-steps-h"')]
    assert rings.count('class="card prog-ring') == 3
    assert '<div class="num">2</div>' in rings and '<div class="num">29</div>' in rings and '<div class="num">71</div>' in rings
    assert "2 of 31" in rings and "29 of 31" in rings and "71 of 1,000" in rings and 'style="--share:0.0645"' in rings and 'style="--share:0.0710"' in rings
    assert ">6%</text>" in rings and ">94%</text>" in rings and ">7%</text>" in rings
    assert "Nodal Institutions with a Nodal Officer on the portal" in rings and "Yet to nominate a Nodal Officer" in rings
    # the four steps, the download, the legend
    steps = page[page.index('<ol class="no-steps">'):page.index("</ol>", page.index('<ol class="no-steps">'))]
    assert "How a Nodal Officer is added" in page and steps.count("<li><b>") == 4 and "CICT creates the account" in steps
    assert 'href="/nodal-institutions/officers-report.docx?lang=en">Download the one-page report (Word)</a>' in page
    # the dots of the table: a filled one before each officer, a hollow one with the words for the 29 rows without
    table = page[page.index('<table class="table nodal">'):page.index("</table>")]
    assert table.count('<i class="no-dot on" aria-hidden="true"></i><b>') == 2
    assert table.count('<span class="small no-pending"><i class="no-dot off" aria-hidden="true"></i>Yet to be nominated</span>') == 29
    assert "Dr. K. Officer" in table and "Dr. T. N. Officer" in table


def test_the_report_in_word():
    from kts.i18n import CATALOG
    app = _portal()
    client = app.test_client()
    r = client.get("/nodal-institutions/officers-report.docx?lang=en")
    assert r.status_code == 200 and r.mimetype == DOCX and r.headers["Content-Disposition"] == "attachment; filename=KTS5-nodal-officers-en.docx"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    doc = z.read("word/document.xml").decode("utf-8")
    assert "word/media/lockup.png" in z.namelist() and "The Nodal Officers of the State/UT Nodal Institutions on the KTS 5.0 portal" in doc
    assert "Nodal Institutions with a Nodal Officer on the portal" in doc and ">2<" in doc and ">29<" in doc and ">71<" in doc
    assert "2 of 31 · 6%" in doc and "71 of 1,000 · 7%" in doc
    assert doc.count('w:fill="1B7F3B"') == 1 and doc.count('w:fill="B3261E"') == 1 and doc.count('w:fill="1C3F94"') == 2   # the three bars, the band
    assert "How a Nodal Officer is added" in doc and "CICT creates the account" in doc
    # the rows: a filled dot and the officer for Kerala and Tamil Nadu, a hollow one and the words for the 29 others
    assert "● " in doc and "Kerala and Lakshadweep" in doc and "Dr. K. Officer" in doc and "Registrar · Annexure-I: 21" in doc
    assert doc.count("Yet to be nominated") == 29 + 1 and doc.count("○ ") == 29 + 1   # and the legend
    assert "Goa" in doc and "Annexure-I: 7" in doc and 'w:fill="FBF6F5"' in doc and 'w:fill="F3F1EC"' in doc
    assert "<w:bidi/>" not in doc and "Annexure-I of the Ministry" in doc
    # in Tamil and in Urdu
    doc = zipfile.ZipFile(io.BytesIO(client.get("/nodal-institutions/officers-report.docx?lang=ta").data)).read("word/document.xml").decode("utf-8")
    assert CATALOG["ta"]["no.report_title"] in doc and "கேரளா மற்றும் லட்சத்தீவு" in doc and 'w:cs="Nirmala UI"' in doc
    doc = zipfile.ZipFile(io.BytesIO(client.get("/nodal-institutions/officers-report.docx?lang=ur").data)).read("word/document.xml").decode("utf-8")
    assert "<w:bidi/>" in doc and "<w:bidiVisual/>" in doc
    assert client.get("/nodal-institutions/officers-report.docx?lang=xx").status_code == 404


def test_the_switch_the_console_and_every_language():
    from kts.db import set_setting
    from kts.i18n import CATALOG
    app = _portal()
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/nodal-institutions?lang={code}").get_data(as_text=True)
        assert f'<h2 id="no-h" style="margin-top:0">{escape(catalogue["no.title"])}</h2>' in page, code
        assert str(escape(catalogue["no.s2_t"])) in page and str(escape(catalogue["no.download"])) in page, code
    admin = _staff(app, "admin@tests.example", "superadmin")
    console = admin.get("/console/nodal").get_data(as_text=True)
    assert 'href="/nodal-institutions#officers">the Nodal Officers on the portal</a>' in console
    assert 'href="/nodal-institutions/officers-report.docx?lang=en">one-page report (Word)</a>' in console
    with app.app_context():
        set_setting("nodal.officers_public", "0")
    page = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert 'id="officers"' not in page and "Yet to be nominated" not in page
    assert client.get("/nodal-institutions/officers-report.docx?lang=en").status_code == 404

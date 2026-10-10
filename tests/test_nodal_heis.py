"""
The State/UT-wise Nodal Higher Educational Institutions on the partners page, and how the programme reaches them.

    python -m pytest tests -q
"""
import json

from conftest import ROOT, make_app

HEIS = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))


def test_the_list_is_the_one_of_the_ministry():
    assert len(HEIS) == 31
    # Annexure-I of the D.O. letter of 9 October 2026, with the tentative allocation of participating institutions
    assert HEIS[0] == {"state": "Andhra Pradesh", "type": "central_university", "name": "Central University of Andhra Pradesh", "allocation": 65}
    assert HEIS[22]["name"] == "Central University of Tamil Nadu" and HEIS[25]["name"] == "Banaras Hindu University"
    assert HEIS[30] == {"state": "Puducherry", "type": "central_university", "name": "Pondicherry University", "allocation": 10}
    assert {h["type"] for h in HEIS} == {"central_university", "nit"} and sum(h["allocation"] for h in HEIS) == 1385
    assert len({h["state"] for h in HEIS}) == 31 and len({h["name"] for h in HEIS}) == 31


def test_the_page_shows_them_in_the_language_of_the_reader():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/partners?lang=en").get_data(as_text=True)
    assert "State/UT-wise list of Nodal Higher Educational Institutions" in page
    assert "The Nodal Higher Educational Institution of each State/UT identifies the participating institutions" in page
    assert page.count('<td lang="en" dir="ltr">') == 31
    assert '<td lang="en" dir="ltr">Central University of Tamil Nadu</td>' in page
    assert page.index("Central University of Andhra Pradesh") < page.index("Pondicherry University")
    assert "<td>Central University</td>" in page and "<td>NIT</td>" in page
    assert "How the programme reaches the institutions" in page and "selects one student on merit and nominates them with one Faculty Supervisor/Guide" in page
    # the names of the States follow the language of the page; the names of the institutions stay in English
    tamil = client.get("/partners?lang=ta").get_data(as_text=True)
    assert "<td>தமிழ்நாடு</td>" in tamil and '<td lang="en" dir="ltr">Central University of Tamil Nadu</td>' in tamil
    # the heading in Tamil, once the texts are translated
    from kts.i18n import CATALOG
    assert CATALOG["ta"]["nodal.title"] in tamil and "State/UT-wise list" not in tamil

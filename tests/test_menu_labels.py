"""
The menu calls the Examination page by its own title, "Institution-level assessment", in every language, since there is
no CICT test (D.O. letter of 9 October 2026); the Console's sign-in names the partner and Nodal agencies (version 1.2.72).

    python -m pytest tests -q
"""
from conftest import make_app


def test_the_menu_names_the_assessment_in_every_language():
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert catalogue["nav.exam"] == catalogue["exam.title"], code
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    assert '<a href="/examination" class="">Institution-level assessment</a>' in page and ">Examination<" not in page
    assert "நிறுவன அளவிலான மதிப்பீடு" in client.get("/?lang=ta").get_data(as_text=True)


def test_the_console_sign_in_names_the_nodal_agencies():
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/console/login").get_data(as_text=True)
    assert "CICT · partner / Nodal agencies" in page and "CICT · partner agencies" not in page
    assert "For the KTS 5.0 secretariat at CICT and the Nodal Officers and coordinators of participating agencies." in page

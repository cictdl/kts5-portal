"""
"Download the Student nomination form" (1.2.193). CICT, 16 November 2026: "Download the nomination form as Download the Student
nomination form"; the form itself has been headed STUDENT NOMINATION FORM since 1.2.192 (tests/test_list_1116.py).

    python -m pytest tests/test_student_form_1116.py -q
"""
from markupsafe import escape

from conftest import make_app

KEY = "reg.nomination_download"
LINK = 'href="/static/KTS5-nomination-form.pdf"'


def test_the_label_names_the_student_in_every_language():
    from kts.i18n import CATALOG
    assert CATALOG["en"][KEY] == "Download the Student nomination form" and len(CATALOG) == 23
    for code, cat in CATALOG.items():
        label = cat[KEY]
        assert label and label.strip() == label and (code == "en" or label != CATALOG["en"][KEY]), code
        # the word of the language for "student" (the tab "Student"), or its stem, stands in the label
        student = cat["hub.tab_student"]
        stem = student[:-1] if code in ("sa", "sd") else student
        assert stem in label or code == "en", (code, label)
    assert CATALOG["hi"][KEY] == "विद्यार्थी नामांकन-पत्र डाउनलोड करें" and CATALOG["bn"][KEY] == "শিক্ষার্থী মনোনয়নপত্র ডাউনলোড করুন"
    assert CATALOG["ta"][KEY] == "மாணவர் பரிந்துரைப் படிவத்தைப் பதிவிறக்க" and CATALOG["sa"][KEY] == "छात्र-नामनिर्देश-पत्रं डाउनलोड् करोतु"
    assert CATALOG["ur"][KEY] == "طالب علم نامزدگی فارم ڈاؤن لوڈ کریں"


def test_the_pages_show_it_on_the_button_of_the_form():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for path in ("/how-to-take-part", "/how-to-take-part/institutions", "/how-to-submit-the-student"):
        page = client.get(path + "?lang=en").get_data(as_text=True)
        assert LINK in page and "Download the Student nomination form</a>" in page and "Download the nomination form" not in page, path
    for code in ("hi", "ta", "ur", "sat"):
        page = client.get(f"/how-to-take-part?lang={code}").get_data(as_text=True)
        assert f">{escape(CATALOG[code][KEY])}</a>" in page, code

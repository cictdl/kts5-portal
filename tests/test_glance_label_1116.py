"""
"Participating Institutions registered" under the number of "At a glance" (1.2.194). CICT, 16 November 2026: "527 Participating
institutions change as 527 Participating institutions registered". The home page and the page of the Participating Institutions
label the number as the dashboard and the page of the progress have since 1.2.189; the menu keeps "Participating institutions".

    python -m pytest tests/test_glance_label_1116.py -q
"""
from markupsafe import escape

from test_1110 import _app, _get, _main

CARD = '<div class="num">5</div><div class="lbl">{}</div>'


def test_the_number_is_labelled_registered_on_both_pages():
    client = _app().test_client()
    home = _main(_get(client, "/?lang=en"))
    assert CARD.format("Participating Institutions registered") in home
    assert '<div class="lbl">Participating institutions</div>' not in home
    page = _main(_get(client, "/institutions?lang=en"))
    assert CARD.format("Participating Institutions registered") in page and '<div class="lbl">Participating institutions</div>' not in page
    # the menu and the heading of the page keep their name
    whole = _get(client, "/institutions?lang=en")
    assert "<h1>Participating institutions</h1>" in whole and ">Participating institutions</a>" in whole


def test_in_every_language():
    from kts.i18n import CATALOG
    client = _app().test_client()
    for code, cat in CATALOG.items():
        label = str(escape(cat["dash.inst_sel"]))
        for path in ("/", "/institutions"):
            assert CARD.format(label) in _main(_get(client, f"{path}?lang={code}")), (code, path)

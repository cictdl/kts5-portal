"""
Interface strings in 23 languages: English and the 22 languages of the
Eighth Schedule to the Constitution of India.

Each language is one flat JSON file, data/i18n/<code>.json (key -> text).
English is the source; any key a language does not have yet falls back to
English, so a partly translated language never shows a blank.

Adding or correcting a translation needs no code change: edit the JSON file
and restart the portal. `python tools/check_i18n.py` reports missing keys,
wrong scripts and lost numbers.
"""
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from flask import g, request, session

I18N_DIR = Path(__file__).resolve().parent.parent / "data" / "i18n"

# code, English name, native name, direction, stream of the Thirukkural corpus shown with this interface language
LANGUAGES = [
    ("en", "English", "English", "ltr", "en"),
    ("as", "Assamese", "অসমীয়া", "ltr", "as"),
    ("bn", "Bengali", "বাংলা", "ltr", "bn"),
    ("brx", "Bodo", "बड़ो", "ltr", "brx"),
    ("doi", "Dogri", "डोगरी", "ltr", "doi"),
    ("gu", "Gujarati", "ગુજરાતી", "ltr", "gu"),
    ("hi", "Hindi", "हिन्दी", "ltr", "hi"),
    ("kn", "Kannada", "ಕನ್ನಡ", "ltr", "kn"),
    ("ks", "Kashmiri", "کٲشُر", "rtl", "ksn"),
    ("kok", "Konkani", "कोंकणी", "ltr", "gom"),
    ("mai", "Maithili", "मैथिली", "ltr", "mai"),
    ("ml", "Malayalam", "മലയാളം", "ltr", "ml"),
    ("mni", "Manipuri", "মৈতৈলোন্", "ltr", "mni"),
    ("mr", "Marathi", "मराठी", "ltr", "mr"),
    ("ne", "Nepali", "नेपाली", "ltr", "ne"),
    ("or", "Odia", "ଓଡ଼ିଆ", "ltr", "or"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ", "ltr", "pa"),
    ("sa", "Sanskrit", "संस्कृतम्", "ltr", "sa"),
    ("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "ltr", "sat"),
    ("sd", "Sindhi", "सिन्धी", "ltr", "sd"),
    ("ta", "Tamil", "தமிழ்", "ltr", "ta"),
    ("te", "Telugu", "తెలుగు", "ltr", "te"),
    ("ur", "Urdu", "اُردُو", "rtl", "ur"),
]
LANG_INFO = {code: {"code": code, "name": name, "native": native, "dir": direction, "corpus": corpus}
             for code, name, native, direction, corpus in LANGUAGES}
LANG_NAMES = {code: info["native"] for code, info in LANG_INFO.items()}

# Interface languages whose wording has been reviewed; the others carry a "draft" note.
REVIEWED = {"en", "ta", "hi"}

# Text that accompanies a stream of the corpus (the question stems of the test) is taken from the
# interface language written in the same script as that stream. Streams in another script than the
# interface language (Kashmiri in Devanagari, Konkani in the Kannada script, Santali in Devanagari,
# Manipuri in Meetei Mayek) and streams without an interface language stay in English.
STREAM_UI = {info["corpus"]: code for code, info in LANG_INFO.items()}
STREAM_UI.update({"ks": None, "kok": None, "sat": None, "mei": None, "bho": None})


def _load():
    catalog = {}
    for code in LANG_INFO:
        path = I18N_DIR / f"{code}.json"
        if path.exists():
            try:
                catalog[code] = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                catalog[code] = {}
        else:
            catalog[code] = {}
    return catalog


CATALOG = _load()

# Kept for tools that expect the old three-language table (the static-site builder).
STRINGS = {key: (text, CATALOG["ta"].get(key, text), CATALOG["hi"].get(key, text))
           for key, text in CATALOG["en"].items()}


def reload():
    """Re-read the JSON files (used by the console after a translation file is replaced)."""
    global CATALOG
    CATALOG = _load()
    return {code: len(table) for code, table in CATALOG.items()}


def available():
    """Languages offered in the menu: English plus every language that has a catalogue."""
    return [LANG_INFO[code] | {"keys": len(CATALOG.get(code, {})), "draft": code not in REVIEWED}
            for code in LANG_INFO if code == "en" or CATALOG.get(code)]


def coverage():
    total = len(CATALOG["en"]) or 1
    return {code: round(100 * len([k for k in CATALOG["en"] if CATALOG.get(code, {}).get(k)]) / total) for code in LANG_INFO}


def offered(code):
    """True when `code` is an interface language that can be chosen now."""
    return code in LANG_INFO and (code == "en" or bool(CATALOG.get(code)))


def get_lang():
    lang = getattr(g, "lang", None)
    if lang:
        return lang
    lang = request.args.get("lang") or session.get("lang") or request.cookies.get("lang")
    if not offered(lang):
        lang = "en"
    g.lang = lang
    return lang


def text(key, lang):
    """Translation of `key` in the interface language `lang`, falling back to English."""
    value = CATALOG.get(lang, {}).get(key)
    if value:
        return value
    return CATALOG["en"].get(key, key)


def t(key, lang=None):
    return text(key, lang or get_lang())


def stream_text(key, stream):
    """
    Text that accompanies the corpus stream `stream`, in the language of that stream.

    Reviewed languages give their own wording. A draft language gives its wording followed by the
    English on a second line, so that a test question is never left to a draft translation alone.
    Streams without an interface language in the same script give English.
    """
    english = CATALOG["en"].get(key, key)
    ui = STREAM_UI.get(stream)
    own = CATALOG.get(ui, {}).get(key) if ui else None
    if not own or ui == "en":
        return english
    if ui in REVIEWED:
        return own
    return f"{own}\n{english}"


def corpus_lang(lang=None):
    """Stream of the Thirukkural corpus that matches an interface language."""
    return LANG_INFO.get(lang or get_lang(), LANG_INFO["en"])["corpus"]


def tag(name, lang=None):
    """Label of a category stored in the database (kind of event, category of notice, kind of agency)."""
    key = f"tag.{name}"
    if key in CATALOG["en"]:
        return text(key, lang or get_lang())
    return (name or "").replace("_", " ").capitalize()


def place(name, lang=None):
    """Name of a State or Union Territory; the database keeps the English name."""
    key = "state." + re.sub(r"[^a-z]+", "_", (name or "").lower()).strip("_")
    if key in CATALOG["en"]:
        return text(key, lang or get_lang())
    return name or ""


# Settings whose default wording has a translation. Wording entered by the administrator is
# shown as entered, in every language.
SETTING_KEYS = {
    "site.banner": "set.banner",
    "orientation.note": "set.orientation_note",
    "home.pm_quote": "set.pm_quote",
    "home.pm_quote_by": "set.pm_quote_by",
    "home.pm_caption": "set.pm_caption",
}


def _setting(key, lang=None):
    """(text, translated) of a setting."""
    from .db import DEFAULT_SETTINGS, get_setting
    value = get_setting(key)
    lang = lang or get_lang()
    tkey = SETTING_KEYS.get(key)
    if lang != "en" and tkey and value == DEFAULT_SETTINGS.get(key):
        own = CATALOG.get(lang, {}).get(tkey)
        if own:
            return own, True
    return value, False


def setting_text(key, lang=None):
    return _setting(key, lang)[0]


def setting_dir(key, lang=None):
    """
    Direction in which a setting is written: that of the interface when its translation is shown;
    "auto" (decided by the first letter) for wording entered by the administrator. A translation may
    begin with "KTS 5.0", which must not turn an Urdu sentence into a left-to-right one.
    """
    lang = lang or get_lang()
    return LANG_INFO[lang]["dir"] if _setting(key, lang)[1] else "auto"


def agency_text(row, field, lang=None):
    """
    Name ('name') or role ('role') of a participating agency. The translation is used while the
    database still holds the wording the portal was installed with (data/agencies.json).
    """
    return _agency(row, field, lang)[0]


def _agency(row, field, lang=None):
    value = row["name"] if field == "name" else row["role_desc"]
    lang = lang or get_lang()
    key = f"agency.{(row['code'] or '').lower()}.{field}"
    if lang != "en" and value == CATALOG["en"].get(key):
        own = CATALOG.get(lang, {}).get(key)
        if own:
            return own, True
    return value, False


def agency_dir(row, field, lang=None):
    """Direction of that text: the interface's for a translation, "auto" for wording from the console."""
    lang = lang or get_lang()
    return LANG_INFO[lang]["dir"] if _agency(row, field, lang)[1] else "auto"


def alternates():
    """
    (hreflang, address) of the page in every language, for <link rel="alternate">: the address
    asked for with all its parameters except 'lang', plus lang=<code>; "x-default" is the address
    without lang. Nothing for a request other than GET or HEAD, for an address that is no page of
    the portal, and for the areas behind a sign-in.
    """
    if request.method not in ("GET", "HEAD") or not request.endpoint:
        return []
    if request.path.startswith(("/candidate", "/console", "/hub")):
        return []
    # read from the address itself, which keeps the order also of a parameter given twice
    asked = parse_qsl(request.query_string.decode("utf-8", "replace"), keep_blank_values=True)
    args = [(name, value) for name, value in asked if name != "lang"]

    def address(*more):
        query = urlencode(args + list(more))
        return request.base_url + ("?" + query if query else "")

    return [(info["code"], address(("lang", info["code"]))) for info in available()] + [("x-default", address())]


def js_strings(lang=None):
    """The few strings the browser script needs."""
    lang = lang or get_lang()
    keys = ("js.wait", "js.saving", "js.saved", "js.not_saved", "js.offline", "js.file_big", "js.unanswered",
            "exam.answered")
    return {key: text(key, lang) for key in keys}


def register(app):
    @app.before_request
    def _pick_lang():
        chosen = request.args.get("lang")
        if offered(chosen):
            session["lang"] = chosen
        lang = session.get("lang") or request.cookies.get("lang") or app.config["DEFAULT_LANG"]
        if not offered(lang):
            lang = "en"
        g.lang = lang

    @app.context_processor
    def _inject():
        lang = get_lang()
        rtl = LANG_INFO[lang]["dir"] == "rtl"
        return {
            "t": t,
            "lang": lang,
            "lang_dir": LANG_INFO[lang]["dir"],
            "lang_draft": lang not in REVIEWED,
            "LANG_NAMES": LANG_NAMES,
            "LANGUAGES": available(),
            "alternates": alternates,
            "js_strings": js_strings(lang),
            "tag": tag,
            "place": place,
            "st": setting_text,
            "st_dir": setting_dir,
            "agency_text": agency_text,
            "agency_dir": agency_dir,
            # arrows of "next" and "previous" links follow the direction of reading
            "fwd": "←" if rtl else "→",
            "back": "→" if rtl else "←",
        }

"""
The Thirukkural corpus used by the portal.

Data comes from CICT's multilingual Tirukkural app (data/kurals): 133 chapter
files with the Tamil source text, transliteration and the institute's
translations into the languages of the Eighth Schedule, plus meta.json.

This module loads it once, and provides
  * chapter / couplet lookups for the public browser,
  * the Kural of the Day and the 200-day school calendar,
  * an MCQ generator that turns the corpus into a language-wise question bank
    for the online selection test.
"""
import json
import random
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kurals"

# The 22 languages of the Eighth Schedule, in the order used by the app.
# Script variants (Kashmiri Nastaliq, Konkani Devanagari, Manipuri Meetei
# Mayek) are offered as alternatives in the browser, not as separate languages.
SCHEDULED = [
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
    "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
]
VARIANTS = {"ks": "ksn", "kok": "gom", "mni": "mei"}
EXTRA = ["en", "bho"]

# Languages in which the orientation series and the test are offered:
# the 21 scheduled languages other than Tamil, plus English.
ORIENTATION_LANGS = ["en"] + [c for c in SCHEDULED if c != "ta"]

PAL_NAMES = {
    1: ("அறத்துப்பால்", "Virtue", "अरत्तुप्पाल (धर्म)"),
    2: ("பொருட்பால்", "Wealth", "पोरुट्पाल (अर्थ)"),
    3: ("காமத்துப்பால்", "Love", "कामत्तुप्पाल (प्रेम)"),
}

DAILY_EPOCH = date(2026, 1, 1)


@lru_cache(maxsize=1)
def corpus():
    meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    chapters = []
    kurals = {}
    for i in range(1, 134):
        ch = json.loads((DATA_DIR / f"{i:03d}.json").read_text(encoding="utf-8"))
        chapters.append(ch)
        for k in ch["kurals"]:
            k["adhigaram"] = ch["adhigaram"]
            k["chapter_name"] = ch["name"]
            k["chapter_name_en"] = ch["nameEn"]
            k["pal_num"] = ch["palNum"]
            k["iyal"] = ch["iyal"]
            k["iyal_en"] = ch["iyalEn"]
            kurals[k["n"]] = k
    return {"meta": meta, "chapters": chapters, "kurals": kurals}


def languages():
    """Ordered list of (code, display name, native name) for the picker."""
    meta = corpus()["meta"]["languages"]
    out = []
    for code in ["ta"] + [c for c in SCHEDULED if c != "ta"] + EXTRA:
        info = meta.get(code)
        if info:
            out.append({"code": code, "name": info["name"], "native": info["native"],
                        "script": info["script"], "dir": info.get("dir", "ltr"),
                        "scheduled": code in SCHEDULED})
    return out


def lang_info(code):
    return corpus()["meta"]["languages"].get(code)


def lang_label(code):
    info = lang_info(code)
    if not info:
        return code
    return f"{info['name']} · {info['native']}" if info["native"] != info["name"] else info["name"]


def chapters():
    return corpus()["chapters"]


def chapter(n):
    n = int(n)
    if 1 <= n <= 133:
        return corpus()["chapters"][n - 1]
    return None


def kural(n):
    return corpus()["kurals"].get(int(n))


def lines(k, lang):
    """Text of couplet `k` in `lang` as a list of lines (Tamil source for 'ta')."""
    if lang == "ta":
        return [k["l1"], k["l2"]]
    tr = k.get("tr", {}).get(lang)
    if not tr:
        return []
    return [ln for ln in tr if ln and ln.strip()]


def has_two_lines(k, lang):
    return len(lines(k, lang)) == 2


def pal_label(num, lang):
    ta, en, hi = PAL_NAMES[num]
    if lang == "ta":
        return ta
    if lang == "hi":
        return hi
    return f"{en} ({ta})"


def chapter_label(ch, lang):
    if lang == "ta":
        return ch["name"]
    if lang == "en":
        return f"{ch['nameEn']} ({ch['transliteration']})"
    return f"{ch['nameEn']} · {ch['name']}"


# ---- Daily Kural ------------------------------------------------------------

def daily_number(day=None):
    day = day or date.today()
    offset = (day - DAILY_EPOCH).days
    return offset % 1330 + 1


def daily(day=None):
    return kural(daily_number(day))


def calendar_rows(lang, start=None, days=200):
    """Rows for the 200-day school calendar: (day no, date, kural no, chapter, Tamil, translation)."""
    from datetime import timedelta
    start = start or date.today()
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        k = daily(d)
        rows.append({
            "day": i + 1,
            "date": d.isoformat(),
            "kural": k["n"],
            "chapter": k["chapter_name"],
            "chapter_en": k["chapter_name_en"],
            "tamil": " / ".join([k["l1"], k["l2"]]),
            "translation": " / ".join(lines(k, lang)),
            "prose_en": (k.get("prose") or {}).get("en", "") if isinstance(k.get("prose"), dict) else "",
        })
    return rows


# ---- Question bank generator -----------------------------------------------

STEMS = {
    "chapter": {
        "en": "To which chapter (adhikāram) of the Thirukkural does this couplet belong?",
        "ta": "இக்குறள் எந்த அதிகாரத்தைச் சேர்ந்தது?",
        "hi": "यह कुरल तिरुक्कुरल के किस अध्याय (अधिकारम्) से है?",
    },
    "complete": {
        "en": "Choose the correct second line of this couplet.",
        "ta": "இக்குறளின் சரியான இரண்டாம் அடியைத் தேர்ந்தெடுக்க.",
        "hi": "इस कुरल की सही दूसरी पंक्ति चुनें।",
    },
    "section": {
        "en": "This couplet belongs to which section (pāl) of the Thirukkural?",
        "ta": "இக்குறள் திருக்குறளின் எந்தப் பாலைச் சேர்ந்தது?",
        "hi": "यह कुरल तिरुक्कुरल के किस खंड (पाल) से है?",
    },
    "none": {"en": "None of these", "ta": "இவற்றில் எதுவும் இல்லை", "hi": "इनमें से कोई नहीं"},
}

GK = {
    "en": [
        ("How many couplets does the Thirukkural contain?", ["1,330", "1,000", "1,300", "1,430"], 0),
        ("Who composed the Thirukkural?", ["Thiruvalluvar", "Kambar", "Ilango Adigal", "Avvaiyar"], 0),
        ("How many chapters (adhikārams) does the Thirukkural have?", ["133", "100", "130", "1,330"], 0),
        ("How many couplets are there in each chapter?", ["10", "7", "12", "13"], 0),
        ("The three sections of the Thirukkural are:", ["Aram, Porul, Inbam", "Iyal, Isai, Natakam", "Akam, Puram, Neethi", "Kural, Venba, Kalippa"], 0),
        ("How many lines does a kural have?", ["2", "4", "1", "3"], 0),
        ("The metre in which the Thirukkural is composed is:", ["Kural venba", "Akaval", "Viruttam", "Kalippa"], 0),
        ("The first couplet of the Thirukkural begins with which letter?", ["அ (a)", "க (ka)", "த (ta)", "ம (ma)"], 0),
        ("How many words (cīr) make up one kural?", ["7", "4", "8", "10"], 0),
        ("Which section deals with kingship, ministers and the state?", ["Porutpāl", "Arattuppāl", "Kāmattuppāl", "Pāyiram"], 0),
        ("The Thirukkural is often called 'Ulaga Podhu Marai', meaning:", ["The universal scripture", "The royal chronicle", "The temple hymn", "The book of grammar"], 0),
        ("The first chapter of the Thirukkural is:", ["Praise of God (Kadavul Vazhthu)", "The Blessing of Rain", "The Greatness of Ascetics", "Assertion of Virtue"], 0),
        ("How many chapters are there in Arattuppāl (Virtue)?", ["38", "70", "25", "33"], 0),
        ("How many chapters are there in Porutpāl (Wealth)?", ["70", "38", "25", "100"], 0),
        ("How many chapters are there in Kāmattuppāl (Love)?", ["25", "38", "70", "13"], 0),
        ("The Central Institute of Classical Tamil has published the Thirukkural in how many scheduled languages?", ["22", "12", "18", "25"], 0),
    ],
    "ta": [
        ("திருக்குறளில் மொத்தம் எத்தனை குறள்கள் உள்ளன?", ["1,330", "1,000", "1,300", "1,430"], 0),
        ("திருக்குறளை இயற்றியவர் யார்?", ["திருவள்ளுவர்", "கம்பர்", "இளங்கோவடிகள்", "ஔவையார்"], 0),
        ("திருக்குறளில் எத்தனை அதிகாரங்கள் உள்ளன?", ["133", "100", "130", "1,330"], 0),
        ("ஒவ்வொரு அதிகாரத்திலும் எத்தனை குறள்கள் உள்ளன?", ["10", "7", "12", "13"], 0),
        ("திருக்குறளின் மூன்று பால்கள்:", ["அறம், பொருள், இன்பம்", "இயல், இசை, நாடகம்", "அகம், புறம், நீதி", "குறள், வெண்பா, கலிப்பா"], 0),
        ("ஒரு குறளில் எத்தனை அடிகள்?", ["2", "4", "1", "3"], 0),
        ("திருக்குறள் எந்தப் பாவகையில் அமைந்தது?", ["குறள் வெண்பா", "ஆசிரியப்பா", "விருத்தம்", "கலிப்பா"], 0),
        ("திருக்குறளின் முதல் குறள் எந்த எழுத்தில் தொடங்குகிறது?", ["அ", "க", "த", "ம"], 0),
        ("ஒரு குறளில் எத்தனை சீர்கள் உள்ளன?", ["7", "4", "8", "10"], 0),
        ("அரசியல், அமைச்சியல் பற்றிக் கூறும் பால் எது?", ["பொருட்பால்", "அறத்துப்பால்", "காமத்துப்பால்", "பாயிரம்"], 0),
        ("‘உலகப் பொதுமறை’ என்று அழைக்கப்படும் நூல்:", ["திருக்குறள்", "சிலப்பதிகாரம்", "தொல்காப்பியம்", "கம்பராமாயணம்"], 0),
        ("திருக்குறளின் முதல் அதிகாரம்:", ["கடவுள் வாழ்த்து", "வான்சிறப்பு", "நீத்தார் பெருமை", "அறன் வலியுறுத்தல்"], 0),
        ("அறத்துப்பாலில் எத்தனை அதிகாரங்கள்?", ["38", "70", "25", "33"], 0),
        ("பொருட்பாலில் எத்தனை அதிகாரங்கள்?", ["70", "38", "25", "100"], 0),
        ("காமத்துப்பாலில் எத்தனை அதிகாரங்கள்?", ["25", "38", "70", "13"], 0),
        ("செம்மொழித் தமிழாய்வு மத்திய நிறுவனம் திருக்குறளை எத்தனை அட்டவணை மொழிகளில் வெளியிட்டுள்ளது?", ["22", "12", "18", "25"], 0),
    ],
    "hi": [
        ("तिरुक्कुरल में कुल कितने कुरल (दोहे) हैं?", ["1,330", "1,000", "1,300", "1,430"], 0),
        ("तिरुक्कुरल की रचना किसने की?", ["तिरुवल्लुवर", "कंबर", "इळंगो अडिगळ", "औवैयार"], 0),
        ("तिरुक्कुरल में कितने अध्याय (अधिकारम्) हैं?", ["133", "100", "130", "1,330"], 0),
        ("प्रत्येक अध्याय में कितने कुरल हैं?", ["10", "7", "12", "13"], 0),
        ("तिरुक्कुरल के तीन खंड हैं:", ["अरम, पोरुळ, इन्बम", "इयल, इसै, नाटकम", "अकम, पुरम, नीति", "कुरल, वेण्बा, कलिप्पा"], 0),
        ("एक कुरल में कितनी पंक्तियाँ होती हैं?", ["2", "4", "1", "3"], 0),
        ("तिरुक्कुरल किस छंद में रचित है?", ["कुरल वेण्बा", "अकवल", "विरुत्तम", "कलिप्पा"], 0),
        ("तिरुक्कुरल का पहला कुरल किस अक्षर से आरंभ होता है?", ["अ", "क", "त", "म"], 0),
        ("एक कुरल में कितने शब्द (सीर) होते हैं?", ["7", "4", "8", "10"], 0),
        ("राजा, मंत्री और राज्य के बारे में कौन-सा खंड है?", ["पोरुट्पाल", "अरत्तुप्पाल", "कामत्तुप्पाल", "पायिरम"], 0),
        ("तिरुक्कुरल को 'उलग पोदु मरै' कहा जाता है, जिसका अर्थ है:", ["विश्व का सार्वभौमिक ग्रंथ", "राजकीय इतिहास", "मंदिर का भजन", "व्याकरण ग्रंथ"], 0),
        ("तिरुक्कुरल का पहला अध्याय है:", ["ईश्वर वंदना (कडवुळ वाऴ्त्तु)", "वर्षा की महिमा", "संन्यासियों की महिमा", "धर्म का आग्रह"], 0),
        ("अरत्तुप्पाल (धर्म) में कितने अध्याय हैं?", ["38", "70", "25", "33"], 0),
        ("पोरुट्पाल (अर्थ) में कितने अध्याय हैं?", ["70", "38", "25", "100"], 0),
        ("कामत्तुप्पाल (प्रेम) में कितने अध्याय हैं?", ["25", "38", "70", "13"], 0),
        ("केंद्रीय शास्त्रीय तमिल संस्थान ने तिरुक्कुरल को कितनी अनुसूचित भाषाओं में प्रकाशित किया है?", ["22", "12", "18", "25"], 0),
    ],
}


def _stem(kind, lang):
    table = STEMS[kind]
    return table.get(lang) or table["en"]


def _shuffle_options(rng, options, correct_idx):
    """Return (opt_a..opt_d, correct_letter) with options shuffled."""
    order = list(range(len(options)))
    rng.shuffle(order)
    shuffled = [options[i] for i in order]
    letter = "ABCD"[order.index(correct_idx)]
    return shuffled, letter


def generate_questions(lang, count=40, seed=None):
    """
    Build `count` MCQs in `lang` from the corpus.

    Mix: ~40% complete-the-couplet, ~30% identify-the-chapter, ~15% identify-
    the-section, ~15% general knowledge. Returns dicts ready for the
    questions table. Stems for languages other than en/ta/hi fall back to
    English while the couplet text itself is in the chosen language.
    """
    rng = random.Random(seed)
    data = corpus()
    all_k = list(data["kurals"].values())
    chs = data["chapters"]
    out = []

    n_complete = round(count * 0.40)
    n_chapter = round(count * 0.30)
    n_section = round(count * 0.15)
    n_gk = count - n_complete - n_chapter - n_section

    # complete the couplet
    pool = [k for k in all_k if has_two_lines(k, lang)]
    rng.shuffle(pool)
    made = 0
    for k in pool:
        if made >= n_complete:
            break
        same = [o for o in chapter(k["adhigaram"])["kurals"] if o["n"] != k["n"] and has_two_lines(o, lang)]
        if len(same) < 3:
            near = [o for o in all_k if o["n"] != k["n"] and abs(o["adhigaram"] - k["adhigaram"]) <= 2 and has_two_lines(o, lang)]
            same = same + [o for o in near if o not in same]
        if len(same) < 3:
            continue
        distractors = rng.sample(same, 3)
        l1, l2 = lines(k, lang)
        options = [l2] + [lines(o, lang)[1] for o in distractors]
        if len(set(options)) < 4:
            continue
        opts, letter = _shuffle_options(rng, options, 0)
        out.append(dict(lang=lang, qtype="complete", text=f"{_stem('complete', lang)}\n\n“{l1} …”",
                        opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3],
                        correct=letter, kural_no=k["n"], difficulty=2))
        made += 1

    # identify the chapter
    pool = [k for k in all_k if lines(k, lang)]
    rng.shuffle(pool)
    made = 0
    for k in pool:
        if made >= n_chapter:
            break
        ch = chapter(k["adhigaram"])
        others = rng.sample([c for c in chs if c["adhigaram"] != ch["adhigaram"]], 3)
        options = [chapter_label(ch, lang)] + [chapter_label(c, lang) for c in others]
        opts, letter = _shuffle_options(rng, options, 0)
        text = f"{_stem('chapter', lang)}\n\n“{' / '.join(lines(k, lang))}”"
        out.append(dict(lang=lang, qtype="chapter", text=text,
                        opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3],
                        correct=letter, kural_no=k["n"], difficulty=2))
        made += 1

    # identify the section
    rng.shuffle(pool)
    for k in pool[:n_section]:
        options = [pal_label(1, lang), pal_label(2, lang), pal_label(3, lang), _stem("none", lang)]
        opts, letter = _shuffle_options(rng, options, k["pal_num"] - 1)
        text = f"{_stem('section', lang)}\n\n“{' / '.join(lines(k, lang))}”"
        out.append(dict(lang=lang, qtype="section", text=text,
                        opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3],
                        correct=letter, kural_no=k["n"], difficulty=1))

    # general knowledge
    gk = GK.get(lang) or GK["en"]
    for stem, options, ci in rng.sample(gk, min(n_gk, len(gk))):
        opts, letter = _shuffle_options(rng, options, ci)
        out.append(dict(lang=lang, qtype="gk", text=stem,
                        opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3],
                        correct=letter, kural_no=None, difficulty=1))

    rng.shuffle(out)
    return out

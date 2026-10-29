"""
The Thirukkural study companion (1.2.119): a question in any of the 23 languages of the portal, answered with the
couplets of the Thirukkural that speak of it. It runs on the portal alone and costs nothing to use: no service outside
is asked, and nothing is shown that is not already in the portal (the couplets, their translations, the Tamil
commentaries, the chapter names).

How a question is matched:
  * its words are split as a reader sees them: the vowel signs and the virama of the Indian scripts stay inside the word
    (the \\w of Python's regular expressions would cut हिन्दी into ह न द);
  * a word matches a word of the text, and also by its first letters (4 to 8 of them), so that the endings of Tamil,
    Hindi or English (நட்பு, நட்பின்; friend, friendship) do not stand in the way;
  * words that every question has (what, how, Valluvar, என்ன, क्या ...) are left out, and a few modern words are also
    read as the words of the old texts (கோபம் as சினம், गुस्सा as क्रोध, alcohol as toddy);
  * each chapter carries the everyday words for its subject in the 23 languages (data/companion_lexicon.json: Friendship
    is also दोस्ती, ਦੋਸਤੀ, സൗഹൃദം ...), since the translators wrote in a language of their own;
  * each couplet is scored (BM25) on its Tamil text, its transliteration, the three English translations, the English
    and Tamil prose, the Tamil commentary, its chapter's names and the translation in the language of the page; each
    chapter is scored on its ten couplets together, and a couplet's score adds a part of its chapter's, so that a
    question about a subject finds the chapter on it.
"""
import json
import math
import re
import sys
import unicodedata
from array import array
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from . import kural as K
from .search import INVISIBLE

LEXICON = Path(__file__).resolve().parent.parent / "data" / "companion_lexicon.json"
MAX_QUERY = 160       # characters of a question that are read
MAX_WORDS = 16
SHOWN = 5             # couplets shown at first; "more" shows up to MAX_SHOWN
MAX_SHOWN = 20
K1, B = 1.2, 0.75     # BM25
PREFIX = 0.35         # the weight of a match by the first letters of a word, against 1 for the whole word
CHAPTER_PART = 0.45   # the part of a couplet's score that comes from its chapter
MIN_SCORE = 1.5       # below this the question matched nothing that counts
SUBJECT = 1.5         # the weight of a word of a question that names a subject (a keyword of a chapter of its own)
PHRASE = 0.25         # what a couplet gains when the question holds a whole phrase of its chapter's keywords

# the fields of a couplet and their weights
W_TAMIL, W_TRANSLIT, W_ENGLISH, W_PROSE, W_COMMENTARY, W_CHAPTER, W_STREAM, W_TOPIC = 1.0, 0.5, 1.0, 0.7, 0.5, 1.5, 1.4, 1.5

# words of questions, not of subjects, in the languages that most students will write in; a word of the other
# languages that is common in the translations weighs little anyway (BM25)
STOP = set("""
a an the is are was were be been being am do does did doing have has had what which who whom whose when where why how
about of in on at to for from by with as into than then that this these those it its i me my mine we us our you your he
him his she her they them their there here what's whats say says said saying tell tells told teach teaches taught
thiruvalluvar thiruvalluvars valluvar valluvars tiruvalluvar thirukkural thirukural tirukkural kural kurals couplet couplets
according should would could can may might must shall will please explain explains meaning mean means give show some any
one ones person people someone anyone man men life lives way ways thing things do does make makes get gets also more
most very much many about regarding not no yes or and but if so such important importance significance
significant necessary need needed essential matter matters happen happens happened right wrong ever good bad better best
benefit benefits advantage advantages
என்ன எப்படி ஏன் யார் எது எவை எங்கு எப்போது எவ்வாறு பற்றி குறித்து கூறுகிறார் கூறுகிறது கூறுவது கூறும் சொல்கிறார்
சொல்கிறது சொல்வது வள்ளுவர் வள்ளுவரின் திருவள்ளுவர் திருவள்ளுவரின் திருக்குறள் திருக்குறளில் குறள் குறளில் குறள்கள்
விளக்குக விளக்கம் என்பது என்றால் நாம் நான் நமக்கு எனக்கு வேண்டும் வேண்டுமா ஒரு இந்த அந்த உள்ளது பெருமை
சிறப்பு முக்கியம் முக்கியத்துவம் அவசியம் நல்லது கெட்டது தீமையா நன்மை நன்மைகள் பயன் பயன்கள்
क्या कैसे क्यों कौन किस किसे कब कहाँ के की का को में से पर है हैं था थे बारे वल्लुवर तिरुवल्लुवर तिरुक्कुरल कुरल
कहते कहा कहता बताइए बताओ बताएं हम हमें मुझे मैं चाहिए करना करें एक यह वह और या भी नहीं संबंध विषय महत्व
ज़रूरी जरूरी आवश्यक अच्छा बुरा सही गलत ग़लत लाभ फायदा
""".split())

# modern words read also as the words of the old texts and their translations (a question gets both)
SYNONYMS = {
    # English
    "angry": "anger wrath", "temper": "anger wrath", "rage": "anger wrath", "furious": "anger wrath",
    "alcohol": "toddy palm-wine drink drunkenness liquor", "liquor": "toddy drink", "drinking": "drink toddy",
    "wine": "toddy drink", "drunk": "toddy drink", "beer": "toddy drink",
    "education": "learning learn", "study": "learning learn", "studies": "learning learn", "school": "learning",
    "students": "learning learn", "student": "learning learn", "teacher": "learning learned",
    "knowledge": "knowledge wisdom", "wise": "wisdom wise", "smart": "wisdom knowledge",
    "friends": "friendship friend", "friend": "friendship", "friendships": "friendship",
    "lies": "falsehood truth veracity", "lying": "falsehood truth veracity",
    "honest": "truth veracity", "honesty": "truth veracity", "truthful": "truth veracity",
    "truth": "veracity falsehood", "lie": "falsehood veracity",
    "meat": "flesh", "vegetarian": "flesh", "nonveg": "flesh", "vegetarianism": "flesh",
    "farmer": "plough farming", "farmers": "plough farming", "agriculture": "plough farming", "farming": "plough",
    "rain": "rain clouds", "rains": "rain", "water": "rain water",
    "money": "wealth riches", "rich": "wealth riches", "riches": "wealth", "economy": "wealth",
    "poor": "poverty", "begging": "beg mendicancy", "beggar": "beg mendicancy",
    "guest": "guests hospitality", "guests": "hospitality", "visitors": "guests hospitality",
    "grateful": "gratitude benefit", "thankful": "gratitude benefit", "thanks": "gratitude", "help": "benefit aid",
    "jealous": "envy", "jealousy": "envy", "envious": "envy",
    "lazy": "sloth sluggishness idleness", "laziness": "sloth sluggishness idleness",
    "work": "effort labour exertion", "hardwork": "effort labour exertion", "effort": "effort exertion",
    "patience": "patience forbearance bear", "patient": "patience forbearance", "forgive": "forbearance forgive",
    "forgiveness": "forbearance forgive",
    "health": "medicine disease food", "healthy": "medicine disease food", "disease": "disease medicine",
    "doctor": "physician medicine", "food": "food eat", "eating": "eat food",
    "kind": "kindness", "kindness": "grace compassion", "compassion": "grace compassion",
    "animals": "living creatures", "kill": "killing", "violence": "killing harm",
    "ruler": "king", "leader": "king", "government": "king sceptre", "governance": "king sceptre",
    "justice": "sceptre justice impartiality", "fair": "impartiality justice", "fairness": "impartiality",
    "minister": "minister", "spy": "spies", "army": "army soldiers", "soldier": "army",
    "enemy": "foe enemy hatred", "enemies": "foe enemy hatred", "hate": "hatred",
    "speech": "speech words speak", "talk": "speech words", "speaking": "speech speak",
    "sweet": "pleasant sweet", "rude": "harsh words", "gossip": "backbiting slander",
    "god": "god", "pray": "god", "prayer": "god",
    "wife": "wife spouse", "husband": "wife spouse", "marriage": "domestic wife", "family": "domestic family",
    "children": "children sons", "kids": "children", "parents": "children sons",
    "love": "love", "lover": "love", "romance": "love",
    "pride": "honour", "respect": "honour", "dignity": "honour", "selfrespect": "honour",
    "greedy": "covet greed", "greed": "covet", "desire": "desire craving", "rid": "curb destroy",
    "choose": "test investigate select", "choosing": "test investigate select", "select": "test investigate",
    "giving": "gift charity give", "charity": "giving gift", "donate": "giving gift", "donation": "giving gift",
    "shared": "benefaction share", "share": "benefaction",
    "time": "time season", "timing": "time season", "opportunity": "time",
    "difficulties": "trouble sorrow", "problems": "trouble sorrow", "stress": "trouble sorrow",
    "failure": "trouble effort", "success": "effort", "goal": "effort",
    # Tamil
    "கோபம்": "சினம் வெகுளி", "கோபத்தை": "சினம் வெகுளி", "கோபப்படுதல்": "சினம் வெகுளி", "ஆத்திரம்": "சினம்",
    "நண்பர்": "நட்பு நண்பன்", "நண்பர்கள்": "நட்பு", "நண்பன்": "நட்பு", "நண்பர்களை": "நட்பு",
    "படிப்பு": "கல்வி கற்க", "கல்வியின்": "கல்வி", "மாணவர்": "கல்வி கற்க", "மாணவர்கள்": "கல்வி",
    "பொய்": "வாய்மை பொய்", "உண்மை": "வாய்மை மெய்", "நேர்மை": "வாய்மை நடுவு",
    "மது": "கள் கள்ளுண்ணாமை", "குடி": "கள்", "சாராயம்": "கள்",
    "இறைச்சி": "புலால் ஊன்", "அசைவம்": "புலால் ஊன்",
    "விவசாயம்": "உழவு உழுது", "விவசாயி": "உழவு உழவர்", "விவசாயிகள்": "உழவு உழவர்",
    "மழை": "மழை வான்", "பணம்": "பொருள் செல்வம்", "செல்வம்": "செல்வம் பொருள்",
    "ஏழை": "நல்குரவு வறுமை", "வறுமை": "நல்குரவு வறுமை", "பிச்சை": "இரவு இரத்தல்",
    "விருந்தினர்": "விருந்து விருந்தோம்பல்", "நன்றி": "நன்றி செய்ந்நன்றி",
    "பொறாமை": "அழுக்காறு", "சோம்பல்": "மடி", "உழைப்பு": "ஆள்வினை முயற்சி", "முயற்சி": "முயற்சி ஆள்வினை",
    "பொறுமை": "பொறை பொறுத்தல்", "மன்னிப்பு": "பொறை பொறுத்தல்",
    "உடல்நலம்": "மருந்து நோய்", "நோய்": "நோய் மருந்து", "உணவு": "உணவு உண்டி",
    "அன்பு": "அன்பு", "இரக்கம்": "அருள்", "கருணை": "அருள்", "கொலை": "கொல்லாமை கொல்",
    "அரசன்": "மன்னன் இறை வேந்தன்", "அரசு": "மன்னன் இறை", "ஆட்சி": "செங்கோல் கோல்", "நீதி": "செங்கோல் நடுவு",
    "எதிரி": "பகை பகைவர்", "எதிரிகள்": "பகை பகைவர்", "பேச்சு": "சொல்", "இனிமையாக": "இனிய இன்சொல்",
    "கடவுள்": "இறைவன் கடவுள்", "மனைவி": "வாழ்க்கைத்துணை இல்லாள்", "குடும்பம்": "இல்வாழ்க்கை குடி",
    "குழந்தைகள்": "மக்கள் மக்கட்பேறு", "பிள்ளைகள்": "மக்கள் மக்கட்பேறு", "மானம்": "மானம்", "மரியாதை": "மானம்",
    "பேராசை": "அவா வெஃகாமை", "ஆசை": "அவா", "நேரம்": "காலம்", "துன்பம்": "இடுக்கண் துன்பம்",
    "கஷ்டம்": "இடுக்கண் துன்பம்", "சூதாட்டம்": "சூது", "தீய": "தீ தீமை",
    # Hindi
    "गुस्सा": "क्रोध", "ग़ुस्सा": "क्रोध", "क्रोध": "क्रोध", "दोस्त": "मित्र मैत्री", "दोस्ती": "मित्र मैत्री",
    "मित्रता": "मित्र मैत्री", "पढ़ाई": "विद्या शिक्षा", "शिक्षा": "विद्या शिक्षा", "छात्र": "विद्या",
    "झूठ": "सत्य असत्य", "सच": "सत्य", "सच्चाई": "सत्य", "शराब": "मद्य मदिरा ताड़ी", "मांस": "मांस",
    "किसान": "कृषि खेती हल", "खेती": "कृषि खेती", "बारिश": "वर्षा बादल मेघ", "पैसा": "धन संपत्ति",
    "गरीबी": "दरिद्रता निर्धनता", "मेहमान": "अतिथि", "धन्यवाद": "कृतज्ञता उपकार", "ईर्ष्या": "ईर्ष्या डाह",
    "आलस": "आलस्य", "मेहनत": "उद्यम प्रयत्न", "धैर्य": "क्षमा सहन", "माफ़ी": "क्षमा", "माफी": "क्षमा",
    "स्वास्थ्य": "औषध रोग", "बीमारी": "रोग", "दया": "दया करुणा", "राजा": "राजा नृप", "दुश्मन": "शत्रु बैर",
    "भगवान": "ईश्वर भगवान", "पत्नी": "पत्नी गृहिणी", "बच्चे": "संतान पुत्र", "जुआ": "जुआ द्यूत",
    "कृतज्ञता": "उपकार कृतज्ञ",
}

# the script of a question that is not that of the page reads also the translation in that script
SCRIPT_STREAMS = {
    "DEVANAGARI": "hi", "BENGALI": "bn", "GUJARATI": "gu", "GURMUKHI": "pa", "ORIYA": "or", "KANNADA": "kn",
    "MALAYALAM": "ml", "TELUGU": "te", "ARABIC": "ur", "MEETEI": "mei",
}


# marks that writers put in or leave out (the short vowels of the Arabic script, the Ol Chiki ahad), and the Kashmiri vowel
# letters read as the plain ones: غصہٕ as غصہ, ᱮᱫᱽᱨᱮ as ᱮᱫᱨᱮ
FOLD = dict.fromkeys(list(range(0x064B, 0x0660)) + [0x0670, 0x1C7D])
FOLD.update({0x0672: "ا", 0x06C4: "و", 0x06C5: "و", 0x0620: "ی", 0x06CD: "ی"})


def words(text):
    """
    The words of a text: NFC, without the invisible joiners and the optional marks, case-folded; letters with their
    vowel signs.
    """
    text = unicodedata.normalize("NFC", str(text or "")).translate(INVISIBLE).translate(FOLD).casefold()
    out, word = [], []
    for ch in text:
        if unicodedata.category(ch)[0] in "LMN":
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def _stem(word):
    """An English word without the endings of the plural and of verbs (friends, learning, learned)."""
    if not word.isascii() or len(word) < 5:
        return word
    for ending, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(ending) and not word.endswith("ss") and len(word) - len(ending) >= 3:
            return word[:-len(ending)] + repl
    return word


def terms(word):
    """
    The terms of a word with their weights: the word itself, and its beginnings of 3 to 8 letters (4 to 8 in Latin
    letters), the whole word among them, so that "friend" finds "friendship" and மழையின் finds மழை.
    """
    word = _stem(word)
    out = [(word, 1.0)]
    for k in range(4 if word.isascii() else 3, min(len(word), 8) + 1):
        out.append((word[:k] + "*", PREFIX))
    return out


def _bag(texts, weight, bag):
    for text in texts:
        for w in words(text):
            if w in STOP or len(w) < 2:
                continue
            for term, tw in terms(w):
                bag[term] += weight * tw


def _topic_bag(phrases):
    """
    The everyday words of a chapter: each term once, whatever the number of phrases it is in, and a word of a phrase at
    half the weight of a keyword of its own (కోపం for Restraining Anger weighs more than in కపట కోపం, feigned anger).
    """
    bag = Counter()
    for phrase in phrases:
        ws = [w for w in words(phrase) if w not in STOP and len(w) >= 2]
        weight = W_TOPIC if len(ws) == 1 else W_TOPIC / 2
        for w in ws:
            for term, tw in terms(w):
                bag[term] = max(bag[term], weight * tw)
    return bag


def _list(value):
    if not value:
        return []
    return [value] if isinstance(value, str) else [v for v in value if v]


@lru_cache(maxsize=1)
def lexicon():
    """The everyday words of each chapter's subject: {chapter number: [words in all languages]}."""
    try:
        data = json.loads(LEXICON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = defaultdict(list)
    for table in data.values():
        for ch, ws in table.items():
            found[int(ch)] += ws
    return dict(found)


class _Postings:
    """
    An inverted index of weighted terms, kept small: for each term the couplets that have it (array of numbers) and its
    weight in each (array of floats), and the length of each couplet (index = number of the couplet).
    """

    def __init__(self, bags):
        found = defaultdict(lambda: ([], []))
        self.length = array("f", [0.0] * 1331)
        for n, bag in bags:
            self.length[n] = sum(bag.values())
            for term, tf in bag.items():
                docs, tfs = found[term]
                docs.append(n)
                tfs.append(tf)
        self.post = {sys.intern(term): (array("H", docs), array("f", tfs)) for term, (docs, tfs) in found.items()}


@lru_cache(maxsize=1)
def _keywords():
    """
    The single keywords of all chapters (stemmed), and the phrases of each chapter as tuples of words: a question with
    "anger" asks about a subject, one with "control" not necessarily; "தீய நண்பர்கள்" whole is the chapter on evil friends.
    """
    single, phrases = set(), defaultdict(set)
    for ch, found in lexicon().items():
        for phrase in found:
            ws = tuple(_stem(w) for w in words(phrase) if w not in STOP and len(w) >= 2)
            if len(ws) == 1:
                single.add(ws[0])
                # in the Indian scripts the keyword may carry an ending in the question (गुस्से for गुस्सा)
                if not ws[0].isascii() and len(ws[0]) >= 5:
                    single.add(ws[0][:-1])
            elif ws:
                phrases[ch].add(ws)
    return single, dict(phrases)


def _subject(word):
    """Whether a word of a question names a subject: a keyword, or in the Indian scripts a keyword with an ending."""
    single = _keywords()[0]
    word = _stem(word)
    if word.isascii():
        return word in single
    return any(word[:k] in single for k in range(3, len(word) + 1))


@lru_cache(maxsize=1)
def _shared():
    """The index of the fields that do not depend on the language of the page."""
    topics = lexicon()

    def bags():
        for ch in K.chapters():
            names = [ch["name"], ch["nameEn"], ch["transliteration"]]
            everyday = _topic_bag(topics.get(ch["adhigaram"], []))
            for k in ch["kurals"]:
                bag = Counter()
                prose = k.get("prose") if isinstance(k.get("prose"), dict) else {}
                tr = k.get("tr") or {}
                _bag([k["l1"], k["l2"]], W_TAMIL, bag)
                _bag(_list(k.get("tl")), W_TRANSLIT, bag)
                for stream in ("en", "ena", "enm"):
                    _bag(_list(tr.get(stream)), W_ENGLISH, bag)
                _bag(_list(prose.get("en")) + _list(prose.get("ta_mv")), W_PROSE, bag)
                _bag(_list(prose.get("tac")) or _list(tr.get("tac")), W_COMMENTARY, bag)
                _bag(names, W_CHAPTER, bag)
                bag.update(everyday)
                yield k["n"], bag
    return _Postings(bags())


@lru_cache(maxsize=40)
def _stream(stream):
    """The index of one translation."""
    def bags():
        for k in K.corpus()["kurals"].values():
            bag = Counter()
            _bag(_list((k.get("tr") or {}).get(stream)), W_STREAM, bag)
            yield k["n"], bag
    return _Postings(bags())


@lru_cache(maxsize=1)
def _chapter_of():
    found = array("B", [0] * 1331)
    for n, k in K.corpus()["kurals"].items():
        found[n] = k["adhigaram"]
    return found


@lru_cache(maxsize=40)
def _lengths(streams):
    """The length of each couplet and of each chapter, and their averages, for the shared fields with `streams`."""
    parts = [_shared()] + [_stream(s) for s in streams]
    couplet = [sum(p.length[n] for p in parts) for n in range(1331)]
    chapter = [0.0] * 134
    of = _chapter_of()
    for n in range(1, 1331):
        chapter[of[n]] += couplet[n]
    return couplet, sum(couplet) / 1330, chapter, sum(chapter) / 133


def _bm25(tf, length, avg, idf):
    return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / avg))


def _scores(qterms, streams):
    """The BM25 score of each couplet and of each chapter for the weighted terms of a question."""
    parts = [_shared()] + [_stream(s) for s in streams]
    couplet_len, couplet_avg, chapter_len, chapter_avg = _lengths(streams)
    of = _chapter_of()
    cs, hs = defaultdict(float), defaultdict(float)
    for term, qw in qterms:
        tfs = defaultdict(float)
        for part in parts:
            found = part.post.get(term)
            if found:
                for n, tf in zip(*found):
                    tfs[n] += tf
        if not tfs:
            continue
        idf = math.log(1 + (1330 - len(tfs) + 0.5) / (len(tfs) + 0.5))
        by_chapter = defaultdict(float)
        for n, tf in tfs.items():
            cs[n] += qw * _bm25(tf, couplet_len[n], couplet_avg, idf)
            by_chapter[of[n]] += tf
        idf = math.log(1 + (133 - len(by_chapter) + 0.5) / (len(by_chapter) + 0.5))
        for ch, tf in by_chapter.items():
            hs[ch] += qw * _bm25(tf, chapter_len[ch], chapter_avg, idf)
    return cs, hs


def streams_for(question, stream):
    """The translations a question is read in: that of the page and, for a question in another script, that script's."""
    found = {stream} if stream not in ("en", "ta") else set()
    variant = K.VARIANTS.get(stream)
    if variant:
        found.add(variant)
    for ch in question:
        if ch.isalpha() and not ch.isascii():
            name = unicodedata.name(ch, "").split(" ")[0]
            other = SCRIPT_STREAMS.get(name)
            if other and other != stream and not (name == "DEVANAGARI" and _script(stream) == "Devanagari"):
                found.add(other)
    return tuple(sorted(found))


def _script(stream):
    info = K.lang_info(stream) or {}
    return info.get("script", "")


def synonyms(word):
    """
    The old words for a modern word of a question. In the Indian scripts the word may carry an ending: a key is found
    at its start (மழையின் for மழை), or without the key's last letter when the key has five or more (गुस्से for गुस्सा).
    """
    if word.isascii():
        stem = _stem(word)
        return [s for key, value in SYNONYMS.items() if key.isascii() and _stem(key) == stem for s in value.split()]
    found = []
    for key, value in SYNONYMS.items():
        if not key.isascii() and (word.startswith(key) or (len(key) >= 5 and word.startswith(key[:-1]))):
            found += value.split()
    return found


def query_terms(question):
    """The weighted terms of a question, its synonyms included (at a little less than its own words)."""
    found = Counter()
    ws = [w for w in words((question or "")[:MAX_QUERY]) if w not in STOP and len(w) >= 2][:MAX_WORDS]
    for w in ws:
        weight = SUBJECT if _subject(w) else 1.0
        for term, tw in terms(w):
            found[term] = max(found[term], weight * tw)
        for syn in synonyms(w):
            for s in words(syn):
                for term, tw in terms(s):
                    found[term] = max(found[term], 0.8 * tw)
    return list(found.items())


def ask(question, stream):
    """
    The answer to a question: a dict with
      number   the couplet a number (1 to 1330) names, if the question is one
      kurals   the numbers of the couplets that match best (at most MAX_SHOWN), the best first
      chapters the numbers of the chapters that match best (at most three), the best first
    Empty lists when nothing in the question counts.
    """
    question = " ".join((question or "").split())[:MAX_QUERY]
    number = None
    digits = re.findall(r"\d+", question)
    if len(digits) == 1 and 1 <= int(digits[0]) <= 1330 and len(words(question)) <= 3:
        number = int(digits[0])
    qterms = query_terms(question)
    cs, hs = _scores(qterms, streams_for(question, stream))
    if not cs or max(cs.values()) < MIN_SCORE:
        return {"question": question, "number": number, "kurals": [number] if number else [],
                "chapters": [K.kural(number)["adhigaram"]] if number else []}
    top_c, top_h = max(cs.values()), max(hs.values()) if hs else 1.0
    combined = {}
    for n, s in cs.items():
        ch = K.kural(n)["adhigaram"]
        combined[n] = (1 - CHAPTER_PART) * s / top_c + CHAPTER_PART * hs.get(ch, 0.0) / top_h
    ranked = sorted(combined, key=lambda n: (-combined[n], n))
    if number:
        ranked = [number] + [n for n in ranked if n != number]
    # a whole phrase of a chapter's keywords in the question
    asked = tuple(_stem(w) for w in words(question) if w not in STOP and len(w) >= 2)
    hit = {ch for ch, phrases in _keywords()[1].items()
           if any(asked[i:i + len(ph)] == ph for ph in phrases for i in range(len(asked) - len(ph) + 1))}
    if hit:
        for n in combined:
            if K.kural(n)["adhigaram"] in hit:
                combined[n] += PHRASE
        ranked = sorted(combined, key=lambda n: (-combined[n], n))
        if number:
            ranked = [number] + [n for n in ranked if n != number]
    tops = defaultdict(list)
    for n in ranked:
        tops[K.kural(n)["adhigaram"]].append(combined[n])
    strength = {ch: sum(sorted(v, reverse=True)[:3]) / 3 + hs.get(ch, 0.0) / top_h for ch, v in tops.items()}
    chapter_rank = sorted(strength, key=lambda ch: (-strength[ch], ch))
    chapters = [ch for ch in chapter_rank if strength[ch] >= 0.6 * strength[chapter_rank[0]]][:3]
    if number:
        lead = K.kural(number)["adhigaram"]
        chapters = [lead] + [ch for ch in chapters if ch != lead][:2]
    return {"question": question, "number": number, "kurals": ranked[:MAX_SHOWN], "chapters": chapters}

"""
The Tamil text of the 1,330 couplets, as proofread against CICT's own editions, the concordance and
the palm-leaf transcription (12 October 2026): four words on the first line and three on the second,
no letter sequence that cannot occur in Tamil, and none of the slips that were corrected.

    python -m pytest tests -q
"""
import re

from kts import kural as K

CONS = "கஙசஞடணதநபமயரலவழளறன"
# a consonant that cannot end a word may stand before these only (geminate, homorganic nasal, ட்/ற் sandhi)
FOLLOWS = {"க": "க", "ச": "ச", "த": "த", "ப": "ப", "ங": "கங", "ஞ": "சஞ", "ந": "தந", "ட": "டகசப", "ற": "றகசப"}


def couplets():
    return K.corpus()["kurals"].values()


def words(line):
    return line.replace(".", " ").replace("?", " ").split()


def test_every_couplet_is_four_words_then_three():
    assert len(couplets()) == 1330
    assert [k["n"] for k in couplets() if (len(words(k["l1"])), len(words(k["l2"]))) != (4, 3)] == []


def test_no_letter_sequence_that_cannot_occur_in_tamil():
    bad = []
    for k in couplets():
        for line in (k["l1"], k["l2"]):
            if re.search("[ாிீுூெேைொோௌ்][ாிீுூெேைொோௌ்]", line) or re.search("ெள(?![ாிீுூெேைொோௌ்])", line):
                bad.append(k["n"])
            for w in words(line):
                if re.match(f"[{CONS}]்", w):
                    bad.append(k["n"])
                for a, b in re.findall(f"([{''.join(FOLLOWS)}])்([{CONS}])", w):
                    if b not in FOLLOWS[a]:
                        bad.append(k["n"])
    assert bad == []


def test_the_transliteration_has_no_broken_characters():
    assert [k["n"] for k in couplets() if any("�" in t for t in k["tl"])] == []


def test_the_corrected_slips_stay_corrected():
    k = K.corpus()["kurals"]
    assert k[90]["l2"] == "நோக்கக் குழையும் விருந்து."
    assert k[298]["l1"] == "புறந்தூய்மை நீரான் அமையும் அகந்தூய்மை"
    assert k[100]["l2"] == "கனியிருப்பக் காய்கவர்ந் தற்று."
    assert k[262]["l1"] == "தவமும் தவமுடையார்க்கு ஆகும் அவமதனை"
    assert k[1117]["l1"] == "அறுவாய் நிறைந்த அவிர்மதிக்குப் போல"
    assert "கௌவை" in k[1143]["l1"] and "கெளவை" not in k[1143]["l1"]


def test_the_couplet_page_shows_the_corrected_text(client):
    page = client.get("/thirukkural/90").get_data(as_text=True)
    assert "குழையும் விருந்து" in page and "குநழ்யும்" not in page

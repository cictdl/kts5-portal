"""
At a glance on the home page (version 1.2.118): its first count is named "Student delegates registered" in every language,
as "Applications received" was before; it counts the same, the students registered through their institutions, withdrawn
ones left out.

    python -m pytest tests -q
"""
from markupsafe import escape

from conftest import add_candidates, make_app

LABELS = {
    "en": "Student delegates registered",
    "as": "পঞ্জীয়ন কৰা শিক্ষাৰ্থী প্ৰতিনিধি",
    "bn": "নিবন্ধিত শিক্ষার্থী-প্রতিনিধি",
    "brx": "मुं थिसननाय फरायसा थान्दैफोर",
    "doi": "पंजीकृत विद्यार्थी नुमाइंदे",
    "gu": "નોંધાયેલા વિદ્યાર્થી પ્રતિનિધિઓ",
    "hi": "पंजीकृत विद्यार्थी प्रतिनिधि",
    "kn": "ನೋಂದಾಯಿತ ವಿದ್ಯಾರ್ಥಿ ಪ್ರತಿನಿಧಿಗಳು",
    "kok": "नोंदणी केल्ले विद्यार्थी प्रतिनिधी",
    "ks": "رجسٹر شُدٕ طالبِ علم نُمایَندٕ",
    "mai": "पंजीकृत विद्यार्थी प्रतिनिधि",
    "ml": "രജിസ്റ്റർ ചെയ്ത വിദ്യാർഥി പ്രതിനിധികൾ",
    "mni": "রেজিষ্টর তৌরবা মহৈরোয় মীহুৎশিং",
    "mr": "नोंदणी झालेले विद्यार्थी प्रतिनिधी",
    "ne": "दर्ता भएका विद्यार्थी प्रतिनिधि",
    "or": "ପଞ୍ଜୀକୃତ ଛାତ୍ରଛାତ୍ରୀ ପ୍ରତିନିଧି",
    "pa": "ਰਜਿਸਟਰਡ ਵਿਦਿਆਰਥੀ ਪ੍ਰਤੀਨਿਧੀ",
    "sa": "पञ्जीकृताः छात्र-प्रतिनिधयः",
    "sat": "ᱧᱩᱛᱩᱢ ᱚᱞ ᱟᱠᱟᱱ ᱯᱟᱹᱴᱷᱩᱣᱟᱹ ᱯᱨᱚᱛᱤᱱᱤᱫᱷᱤ ᱠᱚ",
    "sd": "रजिस्टर्ड शागिर्द नुमाइंदा",
    "ta": "பதிவு செய்த மாணவப் பிரதிநிதிகள்",
    "te": "నమోదైన విద్యార్థి ప్రతినిధులు",
    "ur": "رجسٹرڈ طلبہ مندوبین",
}
# the names of the count before 1.2.118
OLD = {
    "en": "Applications received",
    "as": "প্ৰাপ্ত আবেদন",
    "bn": "প্রাপ্ত আবেদন",
    "brx": "मोननाय आर’ज बिलाइ",
    "doi": "आई दियां अर्जियां",
    "gu": "મળેલી અરજીઓ",
    "hi": "प्राप्त आवेदन",
    "kn": "ಸ್ವೀಕರಿಸಿದ ಅರ್ಜಿಗಳು",
    "kok": "आयिल्ले अर्ज",
    "ks": "موصوٗل درخواستہٕ",
    "mai": "प्राप्त आवेदन",
    "ml": "ലഭിച്ച അപേക്ഷകൾ",
    "mni": "ফংলবা এপ্লিকেসনশিং",
    "mr": "प्राप्त अर्ज",
    "ne": "प्राप्त आवेदन",
    "or": "ପ୍ରାପ୍ତ ଆବେଦନ",
    "pa": "ਪ੍ਰਾਪਤ ਅਰਜ਼ੀਆਂ",
    "sa": "प्राप्तानि आवेदनानि",
    "sat": "ᱧᱟᱢ ᱟᱠᱟᱱ ᱟᱹᱨᱡᱤ ᱠᱚ",
    "sd": "मिलियल दरख़्वास्तूं",
    "ta": "பெறப்பட்ட விண்ணப்பங்கள்",
    "te": "అందిన దరఖాస్తులు",
    "ur": "موصولہ درخواستیں",
}


def test_the_name_in_every_language():
    from kts.i18n import CATALOG
    assert sorted(CATALOG) == sorted(LABELS)
    for code, catalogue in CATALOG.items():
        assert catalogue["home.stat_apps"] == LABELS[code], code


def test_the_count_on_the_home_page_in_every_language():
    from kts.db import execute
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    students = add_candidates(app, 3)
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE app_no = ?", (students[2]["app_no"],))
    client = app.test_client()
    for code in CATALOG:
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        start = page.index('<div class="card stat indigo">')
        glance = page[page.rindex("<h2>", 0, start):page.index("</section>", start)]
        # the first of the four counts: two students, the third withdrew
        assert ('<div class="card stat indigo"><div class="num">2</div><div class="lbl">'
                f'{escape(LABELS[code])}</div></div>') in glance, code
        assert glance.count('<div class="card stat ') == 4 and str(escape(OLD[code])) not in glance, code

"""
Posters and charts (portal 1.2.67): four A3 posters on the Thirukkural in each of the 23 languages of the portal,
as vector PDFs printed by headless Microsoft Edge, with a thumbnail each, into static/posters (the page /posters offers them).
Needs Edge and PyMuPDF (fitz); the working files go to the temporary folder (kts5-posters), with report.json.

    python tools/build_posters.py en ta hi        # a few languages
    python tools/build_posters.py all             # the 23

  1  the programme poster: the theme, a couplet, the four steps of a student, the dates, the stipend, the QR
  2  ten couplets on learning (chapter 40), Tamil with the translation
  3  twelve couplets for every day, Tamil with the translation, their chapters
  4  the Thirukkural at a glance: 3 sections, 133 chapters, 1,330 couplets, the form of a couplet
The texts come from the portal's own interface strings (data/i18n) and corpus (data/kurals): nothing new is written here.
"""
import base64
import html
import json
import time
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
ORIENT = HERE.parent
sys.path.insert(0, str(ORIENT / "tests"))
sys.path.insert(0, str(ORIENT))
import conftest  # noqa: E402  (temporary folders before config)

from kts import i18n as portal_i18n  # noqa: E402
from kts import kural as K  # noqa: E402
from kts.utils import qr_data_uri  # noqa: E402

APP = conftest.make_app(ADMIN_PASSWORD=None)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUT = Path(tempfile.gettempdir()) / "kts5-posters"
STATIC = ORIENT / "static" / "posters"
DATA = ORIENT / "data"
I18N = DATA / "i18n"
BASE = "https://kts.cict.in"

# the twelve couplets for every day: chapter, couplet
TWELVE = [391, 423, 291, 108, 152, 100, 211, 991, 611, 621, 945, 972]


def stream_of(lang):
    """The stream of the corpus that the portal shows with this interface language (Kashmiri: Nastaliq; Konkani: Devanagari),
    so that the couplets' translation is in the script of the poster's other text."""
    return portal_i18n.LANG_INFO.get(lang, {}).get("corpus", lang)


# the script of the interface strings, where it is not that of the language's stream (Santali: Ol Chiki; its stream, Devanagari)
INTERFACE_TAG = {"sat": "sat-Olck"}


def rtl_stream(lang):
    """Whether the couplets' translation shown with this language is in the Arabic script (Urdu, Kashmiri)."""
    first = (K.lines(K.kural(391), stream_of(lang)) or [""])[0]
    return any("؀" <= ch <= "ݿ" for ch in first if ch.isalpha())


def rtl_interface(lang):
    """Whether the interface strings of this language read right to left (Urdu, Kashmiri)."""
    return portal_i18n.LANG_INFO.get(lang, {}).get("dir") == "rtl"
# the fonts of the scripts, all on this machine (Nirmala UI covers the Indic scripts and Ol Chiki; Segoe UI the Arabic script)
FONT_OF = {"ta": "'Noto Serif Tamil', Latha, 'Nirmala UI'", "en": "Georgia, Cambria, serif", "ur": "'Segoe UI', 'Urdu Typesetting'",
           "ks": "'Segoe UI', 'Urdu Typesetting'"}
DEVANAGARI = {"hi", "mr", "ne", "mai", "sa", "doi", "brx", "sd", "kok"}
GOOGLE = "https://fonts.googleapis.com/css2?family=Noto+Serif+Tamil:wght@500;700&family=Barlow+Condensed:wght@600;700&display=block"


def esc(x):
    return html.escape(str(x), quote=False)


def data_uri(path):
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


IMG = ORIENT / "static" / "img"


def flat_logo(path, height):
    """A logo flattened on the cream of the page as a small JPEG, so that the four cost a few KB in each PDF."""
    import io
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    bg = Image.new("RGB", im.size, (251, 248, 242))
    bg.paste(im, mask=im.split()[3])
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=86, optimize=True)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


LOGOS = {k: flat_logo(IMG / p, h) for k, p, h in (("goi", "logos/goi.png", 180), ("moe", "logos/moe.png", 180), ("cict", "cict-logo.png", 200),
                                                 ("kts", "kts-logo.png", 240))}
EN = json.loads((I18N / "en.json").read_text(encoding="utf-8"))


def catalogue(lang):
    cat = dict(EN)
    if lang != "en":
        cat.update(json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8")))
    return cat


def font_of(lang):
    if lang in FONT_OF:
        return FONT_OF[lang]
    return "'Nirmala UI', 'Segoe UI'"


CSS = """
@page { size: 297mm 420mm; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0; padding: 0; background: #fff; }
body { width: 297mm; height: 420mm; overflow: hidden; color: #1F2633; font-family: var(--f-lang); font-size: 11pt; line-height: 1.35; }
.page { position: relative; width: 297mm; height: 420mm; padding: 12mm 14mm 12mm; display: flex; flex-direction: column; gap: 5mm;
  background: linear-gradient(180deg, #FBF8F2 0%, #FFFFFF 38%); }
.page::before { content: ""; position: absolute; inset: 6mm; border: .6mm solid #E3B04B; border-radius: 3mm; pointer-events: none; }
.page::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4mm; background: linear-gradient(90deg, #E07B1A 0 33%, #ffffff 33% 66%, #17694A 66%); }
.top { display: flex; align-items: center; justify-content: space-between; gap: 6mm; margin-top: 2mm; }
.top img { height: 15mm; width: auto; display: block; }
.top .l, .top .r { display: flex; align-items: center; gap: 6mm; }
.top .cict { height: 17mm; } .top .kts { height: 20mm; }
.kicker { font-family: 'Barlow Condensed', 'Bahnschrift', sans-serif; font-weight: 600; font-size: 12pt; letter-spacing: .14em; text-transform: uppercase; color: #8A1C1C; }
.ta { font-family: 'Noto Serif Tamil', Latha, 'Nirmala UI', serif; }
.en { font-family: Georgia, Cambria, serif; }
h1 { margin: 0; font-size: 34pt; line-height: 1.15; color: #1B2A4A; font-weight: 700; }
h1 .ta { font-size: 30pt; }
.sub { font-size: 15pt; color: #4A4F5A; margin-top: 2mm; }
.rule { height: .5mm; background: linear-gradient(90deg, #E3B04B, transparent); margin: 1mm 0; }
.lead { font-size: 13.5pt; line-height: 1.45; color: #3A3F4A; }
.card { background: #FFF3DA; border-left: 3mm solid #8A1C1C; border-radius: 3mm; padding: 6mm 8mm; }
.couplet { margin: 0; font-weight: 700; color: #1B2A4A; line-height: 1.45; }
.couplet span { display: block; white-space: nowrap; }
.tr { color: #3A3F4A; line-height: 1.4; margin-top: 2mm; }
.tr.rtl { direction: rtl; text-align: right; }
.tr.ltr { direction: ltr; text-align: left; }
/* Santali in Devanagari writes a dot below its vowels (U+0323): Nirmala UI has no glyph for it, Sanskrit Text has */
.tr[lang="sat-Deva"] { font-family: 'Sanskrit Text', 'Arial Unicode MS', 'Nirmala UI'; }
/* a poster in Urdu or Kashmiri flows right to left; the Tamil couplets, their chapters and the Latin lines keep their direction */
html[dir=rtl] .couplet, html[dir=rtl] .cite, html[dir=rtl] .ch, html[dir=rtl] .sub, html[dir=rtl] .kicker, html[dir=rtl] .band .val,
html[dir=rtl] .foot .org, html[dir=rtl] .col, html[dir=rtl] .form, html[dir=rtl] .counts { direction: ltr; }
html[dir=rtl] .couplet, html[dir=rtl] .cite, html[dir=rtl] .ch, html[dir=rtl] .sub, html[dir=rtl] .kicker { text-align: right; }
html[dir=rtl] .tr.ltr { text-align: right; }
html[dir=rtl] .stipend b { order: 2; }
.cite { font-family: 'Barlow Condensed', 'Bahnschrift', sans-serif; font-size: 10pt; letter-spacing: .08em; color: #8A1C1C; margin-top: 2mm; }
.cite .ta { letter-spacing: 0; }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5mm; }
.step { background: #fff; border: .4mm solid #DDD3C0; border-top: 2.5mm solid #E07B1A; border-radius: 3mm; padding: 5mm 5mm 4mm; min-width: 0; }
.step b { display: block; font-size: 13.5pt; color: #1B2A4A; line-height: 1.25; }
.step .n { display: inline-flex; width: 10mm; height: 10mm; border-radius: 50%; background: #E07B1A; color: #fff; font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700; font-size: 15pt; align-items: center; justify-content: center; margin-bottom: 3mm; }
.step small { display: block; font-size: 10.5pt; color: #4A4F5A; margin-top: 2mm; line-height: 1.35; }
.band { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.band > div { background: #1B2A4A; color: #fff; border-radius: 3mm; padding: 5mm 7mm; }
.band .lbl { font-family: 'Barlow Condensed', sans-serif; font-size: 10pt; letter-spacing: .12em; text-transform: uppercase; color: #E3B04B; }
.band .val { font-size: 19pt; font-weight: 700; margin-top: 1mm; }
.band .val .en { font-weight: 600; }
.stipend { background: #E8F5EE; border: .4mm solid #17694A; border-radius: 3mm; padding: 4mm 7mm; font-size: 12.5pt; color: #0F4A33; display: flex; gap: 6mm; align-items: center; }
.stipend b { font-size: 20pt; white-space: nowrap; font-family: 'Barlow Condensed', sans-serif; }
.foot { margin-top: auto; display: flex; align-items: flex-end; justify-content: space-between; gap: 8mm; border-top: .4mm solid #DDD3C0; padding-top: 4mm; }
.foot .org { font-size: 10pt; color: #4A4F5A; line-height: 1.4; }
.foot .org b { color: #1B2A4A; }
.foot .url { font-family: 'Barlow Condensed', sans-serif; font-weight: 700; font-size: 22pt; color: #E07B1A; letter-spacing: .02em; }
.foot .qr { display: flex; align-items: center; gap: 4mm; }
.foot .qr img { width: 26mm; height: 26mm; display: block; }
.rows { display: grid; gap: 3.2mm; }
.row { display: grid; grid-template-columns: 12mm 1fr; gap: 4mm; padding: 2.6mm 0; border-bottom: .3mm solid #E9E1CF; min-width: 0; }
.row > div, .step, .col, .band > div { min-width: 0; }
.row .no { font-family: 'Barlow Condensed', sans-serif; font-weight: 700; font-size: 17pt; color: #E07B1A; line-height: 1.1; padding-top: 1mm; }
.row .couplet { font-size: 17pt; }
.row .tr { font-size: 11.5pt; margin-top: 1mm; }
.row .ch { font-family: 'Barlow Condensed', sans-serif; font-size: 9.5pt; letter-spacing: .06em; color: #8A1C1C; margin-bottom: 1mm; }
.row .ch .ta { letter-spacing: 0; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 0 9mm; }
.two .row { grid-template-columns: 12mm 1fr; padding: 4mm 0; }
.two .row .couplet { font-size: 21pt; }
.two .row .tr { font-size: 12.5pt; }
.rows .row .couplet { font-size: 19pt; }
.rows .row .tr { font-size: 12.5pt; }
.credit { font-size: 9pt; color: #6A6F7A; }
/* the programme poster: larger type, the six steps of the guide */
h1.big { font-size: 44pt; }
.p1 .lead { font-size: 16pt; }
.p1 .card .couplet { font-size: 26pt; }
.p1 .card .tr { font-size: 15pt; }
.p1 .step b { font-size: 15.5pt; } .p1 .step small { font-size: 12pt; }
.p1 .band .val { font-size: 22pt; }
.p1 .stipend { font-size: 14pt; } .p1 .stipend b { font-size: 24pt; }
.hows { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm 5mm; margin-top: 2mm; }
.how { display: flex; gap: 3mm; align-items: center; background: #fff; border: .4mm solid #DDD3C0; border-radius: 3mm; padding: 3mm 4mm; font-size: 13pt; color: #1B2A4A; min-width: 0; }
.how .n { flex: none; display: inline-flex; width: 9mm; height: 9mm; border-radius: 50%; background: #1B2A4A; color: #fff; font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700; font-size: 13pt; align-items: center; justify-content: center; }
/* the chart: four columns of chapters */
.glance { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5mm; flex: 1; min-height: 0; }
.col { background: #fff; border: .4mm solid #DDD3C0; border-radius: 3mm; padding: 4mm 4.5mm; min-width: 0; min-height: 0; }
.col h3 { margin: 0 0 1.5mm; font-size: 12.5pt; color: #1B2A4A; line-height: 1.2; }
.col h3 .en { font-weight: 500; color: #4A4F5A; font-size: 11pt; }
.col h4 { margin: 3mm 0 1mm; font-family: 'Barlow Condensed', sans-serif; font-size: 9pt; letter-spacing: .1em; text-transform: uppercase; color: #8A1C1C; }
.col h4 .ta { letter-spacing: 0; text-transform: none; font-size: 9.5pt; }
.col ol { margin: 0; padding: 0; list-style: none; }
.col li { font-size: 8.6pt; line-height: 1.32; display: grid; grid-template-columns: 7mm 1fr; gap: 1.5mm; padding: .35mm 0; border-bottom: .2mm solid #F1ECE0; }
.col li i { font-style: normal; color: #E07B1A; font-family: 'Barlow Condensed', sans-serif; font-weight: 600; text-align: right; }
.col li .en { color: #4A4F5A; }
.counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5mm; }
.counts div { background: #1B2A4A; color: #fff; border-radius: 3mm; padding: 3.5mm 6mm; text-align: center; }
.counts b { display: block; font-family: 'Barlow Condensed', sans-serif; font-size: 30pt; line-height: 1; color: #E3B04B; }
.counts span { font-size: 10.5pt; }
.form { background: #FFF3DA; border-radius: 3mm; padding: 4mm 5mm; margin-top: 3mm; }
.form .w { display: inline-block; border: .4mm solid #C9B07A; border-radius: 2mm; padding: 1mm 2.5mm; margin: 1mm 1.5mm 1mm 0; font-size: 11pt; font-weight: 700; color: #1B2A4A; }
.form .lbl { font-family: 'Barlow Condensed', sans-serif; font-size: 9pt; letter-spacing: .08em; color: #8A1C1C; margin: 1mm 0; }
.form .lbl .ta { letter-spacing: 0; }
"""

FIT = """<script>
(function () {
  function fit() {
    // a couplet keeps its two lines whole: a line wider than its column makes the couplet smaller; in a .uniform block
    // every couplet takes the size of the one that had to shrink most, so that the rows read alike
    var ratio = function (p) {
      var avail = p.clientWidth, widest = 0;
      for (var i = 0; i < p.children.length; i++) widest = Math.max(widest, p.children[i].scrollWidth);
      return (avail && widest > avail) ? avail / widest * 0.985 : 1;
    };
    document.querySelectorAll('.couplet').forEach(function (p) {
      var r = ratio(p);
      if (r < 1) p.style.fontSize = (parseFloat(getComputedStyle(p).fontSize) * r) + 'px';
    });
    document.querySelectorAll('.uniform').forEach(function (box) {
      var ps = box.querySelectorAll('.couplet'), min = 1e9;
      ps.forEach(function (p) { min = Math.min(min, parseFloat(getComputedStyle(p).fontSize)); });
      ps.forEach(function (p) { p.style.fontSize = min + 'px'; });
    });
    document.querySelectorAll('.fitw').forEach(function (el) {
      var size = parseFloat(getComputedStyle(el).fontSize), n = 0;
      while (el.scrollWidth > el.clientWidth + 1 && n++ < 30) { size *= 0.95; el.style.fontSize = size + 'px'; }
    });
    // the sizes are in points: what does not fit the page is zoomed down as a whole
    var page = document.querySelector('.page'), body = document.querySelector('.body'), s = parseFloat(body.style.zoom || '1'), n = 0;
    // what overflows its own box (the columns of the chart, the rows) is hidden behind the footer: those boxes are measured too
    var fills = document.querySelectorAll('.fill, .col');
    var over = function () {
      if (page.scrollHeight > page.clientHeight + 1 || body.scrollHeight > body.clientHeight + 1) return true;
      for (var i = 0; i < fills.length; i++) if (fills[i].scrollHeight > fills[i].clientHeight + 1) return true;
      return false;
    };
    while (body && over() && s > 0.55 && n++ < 40) { s *= 0.98; body.style.zoom = s; }
    document.documentElement.setAttribute('data-fit', 'done');
    document.documentElement.setAttribute('data-measure', page.scrollHeight + '/' + page.clientHeight + '/' + s.toFixed(3) + '/' + (document.fonts ? document.fonts.status : '-'));
  }
  // the web fonts first (with font-display block the fallback metrics would be measured), then twice more for late ones
  var faces = ['700 20pt "Noto Serif Tamil"', '500 20pt "Noto Serif Tamil"', '600 12pt "Barlow Condensed"', '700 12pt "Barlow Condensed"'];
  var start = function () { fit(); setTimeout(fit, 1500); setTimeout(fit, 3500); };
  if (document.fonts && document.fonts.load) Promise.all(faces.map(function (f) { return document.fonts.load(f, "அக"); })).then(start, start);
  else start();
})();
</script>"""


def shell(lang, body_html, title, page_class=""):
    tag = INTERFACE_TAG.get(lang) or K.lang_tag(stream_of(lang))
    direction = "rtl" if rtl_interface(lang) else "ltr"
    return f"""<!doctype html><html lang="{tag}" dir="{direction}"><head><meta charset="utf-8"><title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.gstatic.com"><link rel="stylesheet" href="{GOOGLE}">
<style>:root {{ --f-lang: {font_of(lang)}; }}{CSS}</style></head><body>
<div class="page {page_class}"><div class="body" style="display:flex;flex-direction:column;gap:5mm;flex:1;min-height:0">{body_html}</div></div>{FIT}</body></html>"""


def top():
    return (f'<div class="top"><div class="l"><img src="{LOGOS["goi"]}" alt=""><img src="{LOGOS["moe"]}" alt=""></div>'
            f'<div class="r"><img class="cict" src="{LOGOS["cict"]}" alt=""><img class="kts" src="{LOGOS["kts"]}" alt=""></div></div>')


def foot(cat, qr_url, credit=False):
    with APP.app_context():
        qr = qr_data_uri(qr_url)
    org = f'<div class="org"><b>{esc(cat["site.name"])}</b> · {esc(cat["site.theme"])}<br>{esc(cat["site.ministry"])}<br>{esc(cat["site.organiser"])}'
    if credit:
        org += f'<br><span class="credit">{esc(cat["kural.credit"])}</span>'
    org += "</div>"
    return f'<div class="foot">{org}<div class="qr"><div class="url">kts.cict.in</div><img src="{qr}" alt=""></div></div>'


def clean(line):
    """A translation as a poster prints it: without the editors' marks that some streams of the corpus still carry
    (footnote numbers glued to words or standing alone, [^n] markers, asterisks, long bracketed quotations, a space before a comma)."""
    line = re.sub(r"\[\^\d+\]", "", line)
    line = line.replace("*", "")
    line = re.sub(r"(?<=[^\W\d_]|[ऀ-෿])\d{1,2}(?=[\s,;:.।॥’'\"]|$)", "", line)   # 'जीवानां1,' 'धनमिति15'
    line = re.sub(r"(?:(?<=\s)|^)\d{1,2}(?=\s*(?:[^\W\d]|[‘'\"“]))", "", line)  # '6सन्तोषार्थं' '… 7 तेषां' '1‘दुष्करत्वेन'
    line = re.sub(r"\s\d{1,2}(?=\s|[,;:.।॥]|$)", "", line)                   # '… 2 …' 'सविद्याः 4।'
    line = re.sub(r"\s*[\(\[][^\)\]]{60,}[\)\]]", "", line)                    # an editor's quotation in brackets
    line = re.sub(r"\s+([,;:.।॥])", r"\1", line)
    return " ".join(line.split())


def translation(k, lang):
    return [clean(x) for x in K.lines(k, stream_of(lang)) if clean(x)]


def couplet_html(k, lang, size_class=""):
    ta = K.lines(k, "ta")
    out = f'<p class="couplet ta {size_class}" lang="ta"><span>{esc(ta[0])}</span><span>{esc(ta[1])}</span></p>'
    if lang == "ta":
        tac = (k.get("tr", {}).get("tac") or [""])[0]
        if tac:
            out += f'<div class="tr ta" lang="ta">{esc(tac)}</div>'
    else:
        ln = translation(k, lang)
        if ln:
            cls = "tr rtl" if rtl_stream(lang) else "tr ltr"
            out += f'<div class="{cls}" lang="{K.lang_tag(stream_of(lang))}">{"<br>".join(esc(x) for x in ln)}</div>'
    return out


def chapter_cite(k, lang):
    return (f'<span class="ta" lang="ta">குறள் {k["n"]} · {esc(k["chapter_name"])}</span> · '
            f'<span class="en">{esc(k["chapter_name_en"])}</span>')


DATES = {"{hei_end}": "21 Oct 2026", "{camp_from}": "15 Oct 2026", "{camp_to}": "21 Oct 2026", "{reg_end}": "22 Oct 2026",
         "{verify_end}": "24 Oct 2026", "{questions}": "50", "{minutes}": "30", "{email}": "kts@cict.in", "{phone}": "044-22540125"}


def filled(text):
    """The text escaped, its date and number placeholders filled in; a date keeps its order in a right-to-left line (bdi)."""
    out = esc(text)
    for key, value in DATES.items():
        out = out.replace(esc(key), f'<bdi dir="ltr">{esc(value)}</bdi>')
    return out


def ltr_numbers(text):
    """Escaped text in which the dates and amounts keep their order in a right-to-left line: '₹10,000', '15–21 Oct 2026'."""
    out = esc(text)
    return re.sub(r"(₹\s?[\d,]+|\d{1,2}(?:[–-]\d{1,2})? \w{3} \d{4}|\d{1,2} \w{3,9} \d{4})", r'<bdi dir="ltr">\1</bdi>', out)


def poster1(lang, cat):
    k = K.kural(391)
    steps = [(cat["home.step_exam"], f'{cat["guide.date_assess"]} · 15–21 Oct 2026'),
             (cat["home.step_merit"], cat["home.step_merit_sub"]),
             (cat["home.step_orient"], cat["home.step_orient_sub"]),
             (cat["home.step_present"], cat["home.step_present_sub"])]
    step_html = "".join(f'<div class="step"><span class="n">{i}</span><b class="fitw">{esc(t)}</b><small>{ltr_numbers(s)}</small></div>'
                        for i, (t, s) in enumerate(steps, 1))
    # how a student takes part: the six steps of the guide, as their titles
    how = "".join(f'<div class="how"><span class="n">{i}</span><span>{filled(cat[f"guide.s{i}_t"])}</span></div>' for i in range(1, 7))
    body = (top() +
            f'<div><div class="kicker">{esc(cat["home.kicker"])}</div>'
            f'<h1 class="big">{esc(cat["site.tagline"])}</h1>'
            f'<div class="sub"><span class="ta" lang="ta"><b>திருக்குறள் பயில்வோம்</b></span> · <span lang="hi" style="font-family:\'Nirmala UI\'">तिरुक्कुरल अभ्यास करें</span> · <span class="en">Thirukkural Payilvom</span></div></div>'
            f'<div class="rule"></div>'
            f'<div class="lead">{esc(cat["home.hero_sub"])}</div>'
            f'<div class="card">{couplet_html(k, lang)}<div class="cite">{chapter_cite(k, lang)}</div></div>'
            f'<div class="steps">{step_html}</div>'
            f'<div class="band"><div><div class="lbl">{esc(cat["guide.date_assess"])}</div><div class="val">15 – 21 October 2026</div></div>'
            f'<div><div class="lbl">{esc(cat["site.name"])}</div><div class="val">28 Nov – 12 Dec 2026 · <span class="en">Varanasi</span> · <span class="ta" lang="ta">வாரணாசி</span></div></div></div>'
            f'<div class="stipend"><b>₹10,000</b><span>{ltr_numbers(cat["home.stipend"])}</span></div>'
            f'<div><div class="kicker">{esc(cat["guide.title"])}</div><div class="hows">{how}</div></div>'
            + foot(cat, BASE + "/how-to-take-part"))
    return body


def poster2(lang, cat):
    ch = K.chapter(40)
    rows = "".join(f'<div class="row"><div class="no">{k["n"]}</div><div>{couplet_html(k, lang)}</div></div>' for k in ch["kurals"])
    body = (top() +
            f'<div><div class="kicker">{esc(cat["site.name"])} · {esc(cat["site.theme"])}</div>'
            f'<h1>{esc(cat["post.p2"])}</h1>'
            f'<div class="sub"><span class="ta" lang="ta"><b>அதிகாரம் 40 · கல்வி</b></span> · <span class="en">Chapter 40 · Learning (Kalvi)</span></div></div>'
            f'<div class="rule"></div><div class="rows uniform">{rows}</div>'
            + foot(cat, BASE + "/thirukkural?ch=40", credit=True))
    return body


def poster3(lang, cat):
    items = []
    for n in TWELVE:
        k = K.kural(n)
        items.append(f'<div class="row"><div class="no">{n}</div><div><div class="ch"><span class="ta" lang="ta">{esc(k["chapter_name"])}</span> · {esc(k["chapter_name_en"])}</div>'
                     f'{couplet_html(k, lang)}</div></div>')
    body = (top() +
            f'<div><div class="kicker">{esc(cat["site.name"])} · {esc(cat["site.theme"])}</div>'
            f'<h1>{esc(cat["post.p3"])}</h1>'
            f'<div class="sub"><span class="ta" lang="ta"><b>திருக்குறள்</b></span> · <span class="en">Thirukkural · Thiruvalluvar</span></div></div>'
            f'<div class="rule"></div><div class="two">{"".join(items)}</div>'
            + foot(cat, BASE + "/thirukkural-108", credit=True))
    return body


def poster4(lang, cat):
    pals = K.corpus()["meta"]["pals"]
    chapters = {c["adhigaram"]: c for c in K.chapters()}

    def chapter_list(nums):
        return "<ol>" + "".join(f'<li><i>{n}</i><span><span class="ta" lang="ta">{esc(chapters[n]["name"])}</span> <span class="en">· {esc(chapters[n]["nameEn"])}</span></span></li>'
                                for n in nums) + "</ol>"

    def iyal_block(iyal):
        return f'<h4><span class="ta" lang="ta">{esc(iyal["name"])}</span> · {esc(iyal["nameEn"])}</h4>{chapter_list(iyal["chapters"])}'

    p1, p2, p3 = pals[0], pals[1], pals[2]
    col1 = f'<div class="col"><h3><span class="ta" lang="ta">{esc(p1["name"])}</span> <span class="en">· {esc(p1["nameEn"])}</span></h3>' + "".join(iyal_block(i) for i in p1["iyals"]) + "</div>"
    col2 = f'<div class="col"><h3><span class="ta" lang="ta">{esc(p2["name"])}</span> <span class="en">· {esc(p2["nameEn"])}</span></h3>' + iyal_block(p2["iyals"][0]) + "</div>"
    col3 = '<div class="col"><h3 style="visibility:hidden">·</h3>' + "".join(iyal_block(i) for i in p2["iyals"][1:]) + "</div>"
    k = K.kural(391)
    w1, w2 = K.lines(k, "ta")
    gloss = [(k.get("tr", {}).get("tac") or [""])[0]] if lang == "ta" else translation(k, lang)
    form = (f'<div class="form"><div class="lbl"><span class="ta" lang="ta">ஒரு குறள்</span> · one couplet · 7 feet (<span class="ta" lang="ta">சீர்</span>): 4 + 3</div>'
            + "".join(f'<span class="w ta" lang="ta">{esc(w)}</span>' for w in w1.split()) + '<div class="lbl">+</div>'
            + "".join(f'<span class="w ta" lang="ta">{esc(w)}</span>' for w in w2.split())
            + f'<div class="tr {"rtl" if rtl_stream(lang) else "ltr"}" lang="{K.lang_tag(stream_of(lang))}" style="font-size:9.5pt;margin-top:2mm">{esc(" / ".join(gloss))}</div></div>')
    col4 = f'<div class="col"><h3><span class="ta" lang="ta">{esc(p3["name"])}</span> <span class="en">· {esc(p3["nameEn"])}</span></h3>' + "".join(iyal_block(i) for i in p3["iyals"]) + form + "</div>"
    # the chart is Tamil and English throughout (the chapter names are): so are the labels of the counts
    counts = ('<div class="counts"><div><b>3</b><span><span class="ta" lang="ta">பால்</span> · sections</span></div>'
              '<div><b>133</b><span><span class="ta" lang="ta">அதிகாரம்</span> · chapters</span></div>'
              '<div><b>1,330</b><span><span class="ta" lang="ta">குறள்</span> · couplets</span></div></div>')
    body = (top() +
            f'<div><div class="kicker">{esc(cat["site.name"])} · {esc(cat["site.theme"])}</div>'
            f'<h1>{esc(cat["post.p4"])}</h1>'
            f'<div class="sub"><span class="ta" lang="ta"><b>திருக்குறள்</b></span> · <span class="en">Thirukkural · Thiruvalluvar</span></div></div>'
            f'<div class="rule"></div>{counts}<div class="glance fill">{col1}{col2}{col3}{col4}</div>'
            + foot(cat, BASE + "/thirukkural", credit=True))
    return body


POSTERS = {1: ("site.tagline", poster1), 2: ("post.p2", poster2), 3: ("post.p3", poster3), 4: ("post.p4", poster4)}


# One headless Edge for the whole run, driven over its DevTools protocol (1.2.71): on 14 October 2026 Edge on CICT's PC
# stopped writing files for --print-to-pdf and --screenshot, and it kept a cache of pages even across fresh profiles,
# so the cache is switched off before each page is opened.
_EDGE = {}


def _call(method, **params):
    e = _EDGE
    e["n"] += 1
    e["ws"].send(json.dumps({"id": e["n"], "method": method, "params": params}))
    while True:
        msg = json.loads(e["ws"].recv())
        if msg.get("id") == e["n"]:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})


def _close():
    proc, prof = _EDGE.get("proc"), _EDGE.get("prof")
    if proc:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(.5)
    if prof:
        shutil.rmtree(prof, ignore_errors=True)


def _edge():
    if "ws" in _EDGE:
        return
    import atexit
    import urllib.request

    import websocket
    port = 9361
    OUT.mkdir(parents=True, exist_ok=True)
    prof = tempfile.mkdtemp(prefix="edgepdf-", dir=OUT)
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio", f"--remote-debugging-port={port}",
                             f"--user-data-dir={prof}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _EDGE.update(proc=proc, prof=prof, n=0)
    atexit.register(_close)
    tabs = None
    for _ in range(150):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
            break
        except OSError:
            time.sleep(.2)
    page = next(t for t in tabs if t["type"] == "page")
    _EDGE["ws"] = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=180, suppress_origin=True)
    _call("Network.enable")
    _call("Network.setCacheDisabled", cacheDisabled=True)


def to_pdf(html_path, pdf_path):
    _edge()
    _call("Page.navigate", url=html_path.resolve().as_uri())
    # the page loads its fonts and fits its text at 0, 1.5 and 3.5 seconds
    for _ in range(100):
        if _call("Runtime.evaluate", expression="document.readyState", returnByValue=True)["result"].get("value") == "complete":
            break
        time.sleep(.1)
    time.sleep(4.5)
    data = _call("Page.printToPDF", printBackground=True, preferCSSPageSize=True, marginTop=0, marginBottom=0, marginLeft=0,
                 marginRight=0, displayHeaderFooter=False)["data"]
    Path(pdf_path).write_bytes(base64.b64decode(data))
    doc = fitz.open(pdf_path)
    page = doc[0]
    # one page, A3, every word inside the frame (6 mm = 17 pt from the edges)
    problems = []
    if doc.page_count != 1:
        problems.append(f"{doc.page_count} pages")
    r = page.rect
    if abs(r.width - 841.9) > 2 or abs(r.height - 1190.6) > 2:
        problems.append(f"size {r.width:.0f}x{r.height:.0f}")
    words = page.get_text("words")
    inner = fitz.Rect(r.x0 + 17, r.y0 + 17, r.x1 - 17, r.y1 - 17)
    outside = [w[4] for w in words if not inner.contains(fitz.Rect(w[:4]))]
    if outside:
        problems.append(f"{len(outside)} word(s) at the edge: {' '.join(outside[:5])}")
    return doc, problems, len(words)


def build(lang, out_dir):
    cat = catalogue(lang)
    made = []
    for n, (title_key, fn) in POSTERS.items():
        name = f"KTS5-poster-{n}-{lang}"
        h = out_dir / "html" / f"{name}.html"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(shell(lang, fn(lang, cat), cat[title_key], f"p{n}"), encoding="utf-8")
        pdf = out_dir / f"{name}.pdf"
        doc, problems, nwords = to_pdf(h, pdf)
        doc.save(out_dir / f"{name}.tmp.pdf", garbage=4, deflate=True)
        doc.close()
        shutil.move(out_dir / f"{name}.tmp.pdf", pdf)
        first = fitz.open(pdf)[0]
        zoom = 360 / first.rect.width
        (out_dir / "thumbs").mkdir(exist_ok=True)
        first.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(out_dir / "thumbs" / f"{name}.jpg", jpg_quality=80)
        made.append({"n": n, "file": pdf.name, "kb": pdf.stat().st_size // 1024, "words": nwords, "problems": problems})
        print(f"{name}: {pdf.stat().st_size // 1024} KB, {nwords} words" + (f"  PROBLEMS: {problems}" if problems else ""))
    return made


if __name__ == "__main__":
    langs = sys.argv[1:] or ["en"]
    if langs == ["all"]:
        langs = list(K.ORIENTATION_LANGS)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for lang in langs:
        report[lang] = build(lang, OUT)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = {l: [m for m in ms if m["problems"]] for l, ms in report.items()}
    bad = {l: v for l, v in bad.items() if v}
    print("languages", len(report), "with problems", len(bad), sum(m["kb"] for ms in report.values() for m in ms), "KB in all")
    # into the portal, with their thumbnails
    (STATIC / "thumbs").mkdir(parents=True, exist_ok=True)
    for lang, made in report.items():
        for m in made:
            shutil.copy2(OUT / m["file"], STATIC / m["file"])
            thumb = m["file"].replace(".pdf", ".jpg")
            shutil.copy2(OUT / "thumbs" / thumb, STATIC / "thumbs" / thumb)
    print("copied into", STATIC)

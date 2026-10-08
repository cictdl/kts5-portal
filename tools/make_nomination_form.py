"""
The nomination form of KTS 5.0 (static/KTS5-nomination-form.pdf): one A4 page that the participating
institution fills in, signs and seals, and the nominated student uploads at registration.

    python tools/make_nomination_form.py

Drawn with PyMuPDF and the fonts of Windows (Cambria for the headings, Segoe UI for the text). The Tamil
and Hindi theme line goes through PyMuPDF's HTML layout (insert_htmlbox, with Latha and Mangal), which
shapes the script: drawn letter by letter, as insert_text does, the vowel signs of Tamil and Devanagari
come apart (திருக்குறள் lost its ு and the ோ of பயில்வோம் stood on a dotted circle). The logos are those of
the portal (static/img).
"""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "KTS5-nomination-form.pdf"
FONTS = Path(r"C:\Windows\Fonts")
INK = (0.11, 0.10, 0.09)
INDIGO = (0.12, 0.23, 0.37)
KUMKUM = (0.70, 0.15, 0.12)
DIM = (0.36, 0.33, 0.31)
RULE = (0.70, 0.68, 0.65)


def checked(page):
    """page.insert_textbox draws nothing, silently, when the text does not fit its box: here it stops instead."""
    plain = page.insert_textbox

    def insert_textbox(rect, text, **kw):
        left = plain(rect, text, **kw)
        assert left >= 0, f"the text does not fit its box {rect}: {text[:60]}"
        return left
    page.insert_textbox = insert_textbox
    return page


def main():
    doc = fitz.open()
    page = checked(doc.new_page(width=595, height=842))  # A4
    page.insert_font(fontname="head", fontfile=str(FONTS / "cambriab.ttf"))
    page.insert_font(fontname="text", fontfile=str(FONTS / "segoeui.ttf"))
    page.insert_font(fontname="bold", fontfile=str(FONTS / "segoeuib.ttf"))
    sh = page.new_shape()

    # tricolour band
    for i, colour in enumerate(((0.91, 0.47, 0.10), (1, 1, 1), (0.11, 0.50, 0.29))):
        sh.draw_rect(fitz.Rect(0, i * 4, 595, i * 4 + 4))
        sh.finish(fill=colour, color=None)
    sh.commit()

    # letterhead
    page.insert_image(fitz.Rect(40, 26, 92, 78), filename=str(ROOT / "static" / "img" / "logos" / "goi.png"), keep_proportion=True)
    page.insert_image(fitz.Rect(503, 24, 555, 76), filename=str(ROOT / "static" / "img" / "cict-logo.png"), keep_proportion=True)
    page.insert_textbox(fitz.Rect(100, 20, 495, 36), "Ministry of Education, Government of India", fontname="text", fontsize=9.5,
                        color=DIM, align=1)
    page.insert_textbox(fitz.Rect(100, 34, 495, 62), "Kashi Tamil Sangamam 5.0", fontname="head", fontsize=17, color=INDIGO, align=1)
    css = ("@font-face { font-family: ta; src: url(latha.ttf); } @font-face { font-family: dv; src: url(mangal.ttf); } "
           "body { margin: 0; font-size: 9.5pt; color: #b3261f; text-align: center; } "
           ".ta { font-family: ta; } .dv { font-family: dv; } .en { font-family: sans-serif; }")
    page.insert_htmlbox(fitz.Rect(100, 61, 495, 77),
                        '<p><span class="ta">திருக்குறள் பயில்வோம்</span> <span class="en">· Thirukkural Payilvom ·</span> '
                        '<span class="dv">तिरुक्कुरल अभ्यास करें</span></p>', css=css, archive=fitz.Archive(str(FONTS)))
    page.insert_textbox(fitz.Rect(100, 76, 495, 94), "Central Institute of Classical Tamil (CICT), Chennai · www.kts.cict.in",
                        fontname="text", fontsize=8.5, color=DIM, align=1)
    page.draw_line((40, 98), (555, 98), color=INDIGO, width=1.2)

    page.insert_textbox(fitz.Rect(40, 108, 555, 130), "NOMINATION FORM", fontname="head", fontsize=15, color=INDIGO, align=1)
    page.insert_textbox(fitz.Rect(40, 128, 555, 156),
                        "Nomination of a student and a Faculty Supervisor/Guide by the participating higher educational institution "
                        "for the Students' Engagement Programme of Kashi Tamil Sangamam 5.0 (10 October – 15 November 2026)",
                        fontname="text", fontsize=9, color=DIM, align=1)

    def section(y, title):
        page.draw_rect(fitz.Rect(40, y, 555, y + 16), color=None, fill=(0.90, 0.93, 0.96))
        page.insert_text((46, y + 12), title, fontname="bold", fontsize=9.5, color=INDIGO)
        return y + 22

    def line(y, label, width=515, x=40):
        page.insert_text((x, y + 10), label, fontname="text", fontsize=9, color=INK)
        page.draw_line((x + 150, y + 12), (x + width, y + 12), color=RULE, width=0.6)
        return y + 20

    def pair(y, label1, label2):
        page.insert_text((40, y + 10), label1, fontname="text", fontsize=9, color=INK)
        page.draw_line((150, y + 12), (295, y + 12), color=RULE, width=0.6)
        page.insert_text((305, y + 10), label2, fontname="text", fontsize=9, color=INK)
        page.draw_line((415, y + 12), (555, y + 12), color=RULE, width=0.6)
        return y + 20

    y = section(164, "A. Participating institution")
    y = line(y, "Name of the institution")
    y = pair(y, "District / city", "State / UT")
    y = pair(y, "Type of institution", "AISHE code")
    y = line(y, "State/UT Nodal Higher Educational Institution")
    y = pair(y, "Institutional Coordinator", "Mobile / e-mail")

    y = section(y + 6, "B. Nominated student")
    y = line(y, "Full name (as in college records)")
    y = pair(y, "Date of birth", "Gender")
    y = pair(y, "Programme and year of study", "Roll / register number")
    y = pair(y, "Mobile number", "E-mail")
    y = line(y, "Language chosen for the test and orientation")

    y = section(y + 6, "C. Faculty Supervisor/Guide")
    y = line(y, "Name")
    y = pair(y, "Designation / department", "Mobile number")
    y = line(y, "E-mail")

    y = section(y + 6, "D. Endorsement by the Head of the Institution")
    page.insert_textbox(fitz.Rect(40, y, 555, y + 60),
                        "The student named above is a bona fide student of this institution and is nominated, with the Faculty "
                        "Supervisor/Guide named above, for the Students' Engagement Programme of Kashi Tamil Sangamam 5.0. The "
                        "institution will facilitate the online qualifying examination, the orientation, the research paper and the "
                        "one-hour presentation on the Thirukkural, and will submit the institutional report in the prescribed format.",
                        fontname="text", fontsize=8.8, color=INK, align=3)
    y += 62
    y = pair(y, "Name of the Head of the Institution", "Designation")
    y = pair(y, "Place", "Date")
    page.insert_text((40, y + 10), "Signature", fontname="text", fontsize=9, color=INK)
    page.draw_line((110, y + 30), (280, y + 30), color=RULE, width=0.6)
    page.draw_rect(fitz.Rect(330, y - 4, 440, y + 46), color=RULE, width=0.6, dashes="[3 3] 0")
    page.insert_textbox(fitz.Rect(330, y + 14, 440, y + 30), "Seal of the institution", fontname="text", fontsize=8, color=DIM, align=1)
    y += 56

    page.draw_line((40, y), (555, y), color=RULE, width=0.6)
    page.insert_textbox(fitz.Rect(40, y + 4, 555, y + 40),
                        "How to use this form: fill it in, have it signed and sealed by the Director, Registrar, Principal or Head of the "
                        "Institution, scan it as PDF, JPG or PNG (up to 4 MB), and upload it in step 6 of the registration at "
                        "https://kts.cict.in/register before 16 October 2026. The institution keeps the original.",
                        fontname="text", fontsize=8.2, color=DIM, align=3)
    page.insert_textbox(fitz.Rect(40, 812, 555, 826),
                        "KTS 5.0 · Thirukkural Payilvom · Central Institute of Classical Tamil, an autonomous Institution under the "
                        "Ministry of Education, Government of India", fontname="text", fontsize=7.5, color=DIM, align=1)
    doc.set_metadata({"title": "KTS 5.0 Nomination Form", "author": "Central Institute of Classical Tamil",
                      "subject": "Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom: nomination of a student and a Faculty Supervisor/Guide"})
    doc.subset_fonts()
    doc.save(str(OUT), garbage=4, deflate=True)
    print(OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()

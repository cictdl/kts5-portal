"""
A sample letter from the Nodal Institution to its Participating Institutions (version 1.2.137), as a Word file, in any of the
23 languages of the portal: /nodal-institutions/letter.docx?state=<State/UT of Annexure-I>&lang=<code>, offered on the page of
the Nodal Institutions and in Console > Nodal officers. The texts are the interface strings nl.* (data/i18n); the dates are
those of the settings, written with the month names of the language; the infographic is a picture made for each language by
tools/build_letter_art.py (static/img/letter/<code>.png); the Nodal Officer's name, designation, e-mail and phone come from the
account, as the public pages show them, or stay as blanks to fill in.

The file is written here as Office Open XML directly - the server has no library for Word: document.xml with paragraphs,
runs, one table and two pictures, the right-to-left settings for Urdu and Kashmiri, and the complex-script font for the
Indian scripts.
"""
import io
import zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

from flask import current_app

from . import heis as HEI
from .db import DEFAULT_SETTINGS, get_setting
from .i18n import LANG_INFO, offered, text

PORTAL = "kts.cict.in"
EMU_CM, TW_CM = 360000, 567
INDIGO, SAFFRON, DIM = "1C3F94", "E07B0F", "555555"


# ---- the words and the dates ---------------------------------------------------------------------------------------------------

def _day(key, get):
    try:
        return date.fromisoformat((get(key) or DEFAULT_SETTINGS.get(key, ""))[:10])
    except (TypeError, ValueError):
        return None


def day_text(d, lang, year=True):
    """19 November 2026, with the month in the language of the letter (month.11); '…' without a day."""
    if not d:
        return "…"
    return f"{d.day} {text(f'month.{d.month}', lang)}" + (f" {d.year}" if year else "")


def span_text(a, b, lang):
    """28 November – 12 December 2026, or 15 December 2026 – 14 January 2027."""
    if not a or not b:
        return "…"
    return f"{day_text(a, lang, a.year != b.year)} – {day_text(b, lang)}"


def values(state, lang, officer=None, get=None):
    """The placeholders of the texts nl.*: the State/UT, its Nodal Institution and Officer, the number, the dates, the addresses."""
    get = get or get_setting
    row = HEI.row_of(state) or {"state": state, "name": "", "allocation": 0}
    reg_end, verify_end = _day("reg.end", get), _day("verify.end", get)
    guide = ""
    try:
        from .public import guide_videos
        guide = next((f"youtu.be/{v['youtube']}" for v in guide_videos() if v["n"] == 2), "")
    except Exception:  # noqa: BLE001 - the letter stands without the video
        guide = ""
    officer = officer or {}
    return {
        "state": HEI.label_of(state, lang), "hei": row["name"], "number": str(int(row.get("allocation") or 0)),
        "name": officer.get("name") or text("nl.ph_name", lang), "designation": officer.get("designation") or text("nl.ph_designation", lang),
        "email": officer.get("email") or text("nl.ph_email", lang), "phone": officer.get("phone") or text("nl.ph_phone", lang),
        "portal": PORTAL, "guide": guide or f"{PORTAL}/nodal-institutions",
        "contact_email": (get("contact.email") or "").strip() or "office@cict.in", "contact_phone": (get("contact.phone") or "").strip() or "",
        "camp_to": day_text(_day("camp.to", get), lang), "reg_end": day_text(reg_end, lang),
        "verify_span": span_text(reg_end + timedelta(days=1) if reg_end else None, verify_end, lang),
        "engagement": span_text(_day("internship.start", get), _day("papers.due", get), lang),
        "orientation_by": day_text(_day("orientation.by", get), lang), "papers_due": day_text(_day("papers.due", get), lang),
        "kts_start": day_text(_day("kts.start", get), lang), "kts_end": day_text(_day("kts.end", get), lang),
        "kts_dates": span_text(_day("kts.start", get), _day("kts.end", get), lang),
    }


def fill(key, lang, v):
    out = text(key, lang)
    for k, value in v.items():
        out = out.replace("{" + k + "}", value)
    return out


# ---- the Word file -----------------------------------------------------------------------------------------------------------

class _Doc:
    """Paragraphs, a table and pictures as WordprocessingML; the properties the letter needs and no more."""

    def __init__(self, lang):
        self.lang = lang
        self.rtl = LANG_INFO.get(lang, {}).get("dir") == "rtl"
        self.cs_font = "Segoe UI" if self.rtl else ("Calibri" if lang == "en" else "Nirmala UI")
        self.parts = []
        self.media = []   # (name, bytes)

    def rpr(self, bold=False, size=21, colour=None, italic=False):
        x = (f'<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="{self.cs_font}" w:eastAsia="{self.cs_font}"/>'
             + ("<w:b/><w:bCs/>" if bold else "") + ("<w:i/><w:iCs/>" if italic else "")
             + (f'<w:color w:val="{colour}"/>' if colour else "") + f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
             + ("<w:rtl/>" if self.rtl else ""))
        return f"<w:rPr>{x}</w:rPr>"

    def run(self, s, **kw):
        """A run; a tab character becomes a tab, a newline a line break."""
        out = []
        for i, line in enumerate(s.split("\n")):
            if i:
                out.append("<w:br/>")
            for j, piece in enumerate(line.split("\t")):
                if j:
                    out.append("<w:tab/>")
                if piece:
                    out.append(f'<w:t xml:space="preserve">{escape(piece)}</w:t>')
        return f"<w:r>{self.rpr(**kw)}{''.join(out)}</w:r>"

    def p(self, runs, align=None, before=0, after=4, indent=0, hanging=0, keep=False, page_break=False, tabs=(), line=259):
        pr = []
        if page_break:
            pr.append("<w:pageBreakBefore/>")
        if keep:
            pr.append("<w:keepNext/>")
        if self.rtl:
            pr.append("<w:bidi/>")
        pr.append(f'<w:spacing w:before="{int(before * 20)}" w:after="{int(after * 20)}" w:line="{line}" w:lineRule="auto"/>')
        if indent or hanging:
            pr.append(f'<w:ind w:left="{int(indent * TW_CM)}"' + (f' w:hanging="{int(hanging * TW_CM)}"' if hanging else "") + "/>")
        if tabs:
            pr.append("<w:tabs>" + "".join(f'<w:tab w:val="left" w:pos="{int(t * TW_CM)}"/>' for t in tabs) + "</w:tabs>")
        if align:
            pr.append(f'<w:jc w:val="{align}"/>')
        self.parts.append(f"<w:p><w:pPr>{''.join(pr)}</w:pPr>{''.join(runs)}</w:p>")

    def rule(self):
        self.parts.append(f'<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" w:color="{SAFFRON}"/></w:pBdr>'
                          f'<w:spacing w:before="0" w:after="120"/></w:pPr></w:p>')

    def picture(self, data, width_cm, height_cm, name):
        rid = f"rId{10 + len(self.media)}"
        self.media.append((name, data, rid))
        cx, cy = int(width_cm * EMU_CM), int(height_cm * EMU_CM)
        n = len(self.media)
        return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
                f'<wp:docPr id="{n}" name="{name}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                f'<pic:nvPicPr><pic:cNvPr id="{n}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
                f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')

    def table(self, rows, widths_cm, borders=True, header=False):
        grid = "".join(f'<w:gridCol w:w="{int(w * TW_CM)}"/>' for w in widths_cm)
        b = ("<w:tblBorders>" + "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
                                        for side in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders>"
             if borders else "<w:tblBorders>" + "".join(f'<w:{side} w:val="nil"/>' for side in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders>")
        pr = (f'<w:tblPr><w:tblW w:w="{int(sum(widths_cm) * TW_CM)}" w:type="dxa"/>' + ("<w:bidiVisual/>" if self.rtl else "") + b
              + '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>')
        body = []
        for i, cells in enumerate(rows):
            tcs = []
            for w, cell in zip(widths_cm, cells):
                # a cell holds a list of paragraphs, each a list of runs, or ready XML
                content = cell if isinstance(cell, str) else "".join(
                    f"<w:p><w:pPr>{'<w:bidi/>' if self.rtl else ''}<w:spacing w:before=\"0\" w:after=\"0\"/></w:pPr>{''.join(runs)}</w:p>" for runs in cell)
                tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="{int(w * TW_CM)}" w:type="dxa"/></w:tcPr>{content}</w:tc>')
            body.append("<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if header and i == 0 else "") + "".join(tcs) + "</w:tr>")
        self.parts.append(f"<w:tbl>{pr}<w:tblGrid>{grid}</w:tblGrid>{''.join(body)}</w:tbl>")

    def cell(self, runs, align=None, after=0):
        """A paragraph for a table cell, as XML."""
        return (f"<w:p><w:pPr>{'<w:bidi/>' if self.rtl else ''}<w:spacing w:before=\"0\" w:after=\"{int(after * 20)}\"/>"
                + (f'<w:jc w:val="{align}"/>' if align else "") + f"</w:pPr>{''.join(runs)}</w:p>")

    def bytes(self):
        ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
              'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
              'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
              'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
        sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="1191" w:bottom="794" w:left="1191" '
                'w:header="567" w:footer="567" w:gutter="0"/>' + ("<w:bidi/>" if self.rtl else "") + "</w:sectPr>")
        document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>{"".join(self.parts)}{sect}</w:body></w:document>')
        styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr>'
                  f'<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="{self.cs_font}" w:eastAsia="{self.cs_font}"/>'
                  '<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-IN"/></w:rPr></w:rPrDefault>'
                  '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
                          for name, _data, rid in self.media) + "</Relationships>")
        root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                     '</Relationships>')
        types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '</Types>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", types)
            z.writestr("_rels/.rels", root_rels)
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/_rels/document.xml.rels", rels)
            for name, data, _rid in self.media:
                z.writestr(f"word/media/{name}", data)
        return buf.getvalue()


def _png_size(data):
    """(width, height) of a PNG from its header."""
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def art_path(lang):
    """The infographic of the language, or the English one while the language has none."""
    folder = current_app.static_folder
    for code in (lang, "en"):
        p = f"{folder}/img/letter/{code}.png"
        try:
            with open(p, "rb") as f:
                return p, f.read()
        except OSError:
            continue
    return None, b""


def letter_docx(state, lang, officer=None):
    """The letter as the bytes of a .docx."""
    lang = lang if offered(lang) else "en"
    v = values(state, lang, officer)
    d = _Doc(lang)
    t = lambda key: fill(key, lang, v)  # noqa: E731

    # the letterhead: the Nodal Institution and its officer; the KTS 5.0 lock-up
    lockup = ""
    try:
        with open(f"{current_app.static_folder}/img/kts5-lockup.png", "rb") as f:
            data = f.read()
        w, h = _png_size(data)
        lockup = d.picture(data, 4.4, 4.4 * h / w, "lockup.png")
    except OSError:
        pass
    left = (d.cell([d.run(v["hei"].upper(), bold=True, size=28, colour=INDIGO)])
            + d.cell([d.run(t("nl.head_role"), size=19, colour=DIM)])
            + d.cell([d.run(t("nl.head_officer"), size=18, colour=DIM)]))
    right = d.cell([lockup] if lockup else [d.run("")], align="right")
    d.table([[left, right]], [12.2, 4.6], borders=False)
    d.rule()
    d.p([d.run(t("nl.ref")), d.run("\t" + t("nl.date"))], after=8, tabs=(12.4,))
    d.p([d.run(t("nl.to"))], after=0)
    d.p([d.run(t("nl.to_head"))], after=0)
    d.p([d.run(t("nl.to_list"))], after=8)
    d.p([d.run(t("nl.subject"), bold=True)], after=4)
    d.p([d.run(t("nl.reference"))], after=8)
    d.p([d.run(t("nl.salutation"))], after=6)

    def numbered(label, lead_key, body_key, indent=0.9):
        runs = [d.run(label + "\t")]
        if lead_key:
            runs.append(d.run(t(lead_key) + " ", bold=True))
        if body_key:
            runs.append(d.run(t(body_key)))
        d.p(runs, indent=indent, hanging=indent, tabs=(indent,), after=4)

    def bullet(key, indent=0.9):
        d.p([d.run("•\t"), d.run(t(key))], indent=indent, hanging=0.45, tabs=(indent,), after=3)

    numbered("1.", None, "nl.p1")
    numbered("2.", None, "nl.p2")
    numbered("3.", "nl.p3_t", "nl.p3")
    for n, label in enumerate(("(i)", "(ii)", "(iii)", "(iv)"), 1):
        numbered(label, f"nl.s{n}_t", f"nl.s{n}", indent=1.3)

    # page 2: the infographic, the engagement, the stipend, the resources
    _path, art = art_path(lang)
    if art:
        w, h = _png_size(art)
        d.p([d.picture(art, 16.8, 16.8 * h / w, "art.png")], align="center", after=2, page_break=True)
        d.p([d.run(t("nl.caption"), size=18, italic=True, colour=DIM)], align="center", after=6)
    else:
        d.p([d.run("")], page_break=True)
    numbered("4.", "nl.p4_t", None)
    for n in range(1, 6):
        bullet(f"nl.b{n}")
    numbered("5.", "nl.p5_t", "nl.p5")
    numbered("6.", "nl.p6_t", "nl.p6")

    # page 3: the campus, help, at a glance, the closing
    d.p([d.run("7.\t"), d.run(t("nl.p7_t") + " ", bold=True), d.run(t("nl.p7"))], indent=0.9, hanging=0.9, tabs=(0.9,), after=4, page_break=True)
    numbered("8.", "nl.p8_t", "nl.p8")
    d.p([d.run(t("nl.glance_t"), bold=True, size=23, colour=INDIGO)], before=8, after=3, keep=True)
    by = lambda s: text("nl.by", lang).replace("{date}", s)  # noqa: E731
    rows = [(by(v["camp_to"]), "nl.g1"), (v["reg_end"], "nl.g2"), (v["verify_span"], "nl.g3"), (v["kts_start"], "nl.g4"),
            (v["kts_end"], "nl.g5"), (by(v["orientation_by"]), "nl.g6"), (v["engagement"], "nl.g7"), (v["papers_due"], "nl.g8")]
    table = [[[[d.run(text("nl.col_when", lang), bold=True, size=19, colour=INDIGO)]], [[d.run(text("nl.col_what", lang), bold=True, size=19, colour=INDIGO)]]]]
    table += [[[[d.run(when, bold=True, size=19)]], [[d.run(t(key), size=19)]]] for when, key in rows]
    d.table(table, [5.2, 11.6], header=True)
    d.p([d.run(t("nl.request"))], before=10, after=10)
    d.p([d.run(t("nl.closing"))], after=30)
    for i, line in enumerate((v["name"], t("nl.sign_post"), v["designation"], v["hei"], f"{v['email']} · {v['phone']}")):
        d.p([d.run(line, bold=(i == 0), size=21 if i == 0 else 19)], after=0)
    d.p([d.run(t("nl.encl"), size=19)], before=10, after=0)
    d.p([d.run(t("nl.copy"), size=19)], before=4, after=0)
    return d.bytes()


def filename(state, lang):
    slug = "".join(ch if ch.isalnum() else "-" for ch in state.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"KTS5-letter-{slug}-{lang}.docx"

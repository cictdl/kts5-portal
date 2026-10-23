"""
Add a translation of the study book "Thirukkural Payilvom" (the syllabus of the institution-level assessment, 1.2.98) to
the portal: the PDF goes to static/syllabus/KTS5-Thirukkural-Payilvom-<lang>.pdf, the thumbnail of its cover to
static/syllabus/thumbs/, and a line to data/syllabus.json; the page /syllabus then offers it. Needs PyMuPDF and Pillow.

    python tools/add_syllabus.py LANG BOOK.pdf "Name of the translator"
"""
import json
import shutil
import sys
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kts.kural import ORIENTATION_LANGS  # noqa: E402

lang, src, translator = sys.argv[1], Path(sys.argv[2]), (sys.argv[3] if len(sys.argv) > 3 else "")
assert lang in ORIENTATION_LANGS, f"{lang} is not a language of the portal"
folder = ROOT / "static" / "syllabus"
name = f"KTS5-Thirukkural-Payilvom-{lang}"
shutil.copyfile(src, folder / f"{name}.pdf")
doc = fitz.open(folder / f"{name}.pdf")
page = doc[0]
zoom = 360 / page.rect.width
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(folder / "thumbs" / f"{name}.jpg", quality=85, optimize=True)
data_file = ROOT / "data" / "syllabus.json"
rows = [r for r in json.loads(data_file.read_text(encoding="utf-8")) if r["lang"] != lang]
rows.append({"lang": lang, "pages": len(doc), "translator": translator})
order = {"ta": -1, **{code: i for i, code in enumerate(ORIENTATION_LANGS)}}
rows.sort(key=lambda r: order[r["lang"]])
data_file.write_text("[\n" + ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n", encoding="utf-8")
print(name, len(doc), "pages,", (folder / f"{name}.pdf").stat().st_size // 1024, "KB")

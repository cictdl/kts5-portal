"""
Build the KTS 5.0 logo assets from the official artwork in tools/logo-src/:

  kts-logo-src.png            Kashi Tamil Sangamam logo (circle + trilingual wordmark, white background)
  thiruvalluvar-gold-src.png  golden Thiruvalluvar on a maroon oval (transparent background)

Outputs (static/img/):
  kts-logo.png            the full KTS logo with a transparent background (masthead, print headers)
  kts-mark.png            the circle alone on a square canvas (favicon, console, exam header)
  thiruvalluvar-gold.png  the Thirukkural emblem, trimmed
  favicon.png             64x64 mark
  apple-touch-icon.png    180x180 mark on cream
  kts5-lockup.png / .svg  logo + "Kashi Tamil Sangamam 5.0" + theme line + institute line (letterheads, press)

    python tools/make_logo.py
"""
import base64
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "logo-src"
OUT = ROOT / "static" / "img"
FONTS = Path("C:/Windows/Fonts")
INDIGO = (31, 58, 95, 255)
KUMKUM = (179, 38, 30, 255)
SAFFRON = (224, 123, 26, 255)
DIM = (87, 83, 78, 255)
CREAM = (250, 248, 244, 255)
THEME = "Thirukkural Payilvom – Thirukkural Abhyas Karen"
ORG = "Central Institute of Classical Tamil, Chennai  ·  Ministry of Education, Government of India"


def font(name, size):
    for candidate in (name, "calibri.ttf"):
        try:
            return ImageFont.truetype(str(FONTS / candidate), size)
        except OSError:
            continue
    return ImageFont.load_default()


def knock_out_white(im, tol=16):
    """Make the white background transparent by flood-filling from the edges, so white inside the artwork stays."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    queue = deque()

    def is_bg(x, y):
        r, g, b, a = px[x, y]
        return a == 0 or (r >= 255 - tol and g >= 255 - tol and b >= 255 - tol)

    for x in range(w):
        for y in (0, h - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        r, g, b, a = px[x, y]
        px[x, y] = (r, g, b, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and is_bg(nx, ny):
                seen[ny * w + nx] = 1
                queue.append((nx, ny))
    return im


def trimmed(im):
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def squared(im, size, pad=0.04):
    """Fit an RGBA image into a square transparent canvas."""
    inner = int(size * (1 - 2 * pad))
    scale = min(inner / im.width, inner / im.height)
    resized = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    return canvas


def circle_only(logo):
    """The circular device without the wordmark: content above the first blank row band."""
    w, h = logo.size
    alpha = logo.getchannel("A")
    rows = [alpha.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
    # first gap after at least 40% of the height = end of the circle
    end = h
    for y in range(int(h * 0.4), h):
        if not rows[y]:
            end = y
            break
    return trimmed(logo.crop((0, 0, w, end)))


def lockup_png(logo):
    f1, f2, f3 = font("cambriab.ttf", 104), font("cambriab.ttf", 50), font("calibri.ttf", 36)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    line1 = "Kashi Tamil Sangamam 5.0"
    logo_h = 440
    logo_s = logo.resize((round(logo.width * logo_h / logo.height), logo_h), Image.LANCZOS)
    x = logo_s.width + 60
    w = int(x + max(probe.textlength(line1, font=f1), probe.textlength(THEME, font=f2), probe.textlength(ORG, font=f3)) + 40)
    canvas = Image.new("RGBA", (w, 512), (0, 0, 0, 0))
    canvas.paste(logo_s, (0, 36), logo_s)
    d = ImageDraw.Draw(canvas)
    d.text((x, 96), line1, font=f1, fill=INDIGO)
    d.text((x, 236), THEME, font=f2, fill=KUMKUM)
    d.line((x, 326, w - 40, 326), fill=SAFFRON, width=5)
    d.text((x, 348), ORG, font=f3, fill=DIM)
    return canvas


def lockup_svg(logo_png):
    data = base64.b64encode(logo_png.read_bytes()).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1780" height="512" viewBox="0 0 1780 512">'
        "<title>Kashi Tamil Sangamam 5.0 · Thirukkural Payilvom – Thirukkural Abhyas Karen</title>"
        f'<image href="data:image/png;base64,{data}" x="0" y="36" width="405" height="440"/>'
        '<text x="465" y="180" font-family="Cambria, Georgia, serif" font-weight="700" font-size="100" fill="#1f3a5f">Kashi Tamil Sangamam 5.0</text>'
        '<text x="465" y="272" font-family="Cambria, Georgia, serif" font-weight="700" font-size="50" fill="#b3261e">'
        f"{THEME}</text>"
        '<rect x="465" y="326" width="1275" height="5" fill="#e07b1a"/>'
        f'<text x="465" y="382" font-family="Calibri, \'Segoe UI\', sans-serif" font-size="36" fill="#57534e">{ORG}</text>'
        "</svg>"
    )


def main():
    logo = trimmed(knock_out_white(Image.open(SRC / "kts-logo-src.png")))
    logo.save(OUT / "kts-logo.png")
    mark = squared(circle_only(logo), 512)
    mark.save(OUT / "kts-mark.png")
    mark.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.png")
    touch = Image.new("RGBA", (180, 180), CREAM)
    m = mark.resize((156, 156), Image.LANCZOS)
    touch.paste(m, (12, 12), m)
    touch.convert("RGB").save(OUT / "apple-touch-icon.png")
    valluvar = trimmed(Image.open(SRC / "thiruvalluvar-gold-src.png").convert("RGBA"))
    valluvar.save(OUT / "thiruvalluvar-gold.png")
    lockup_png(logo).save(OUT / "kts5-lockup.png")
    (OUT / "kts5-lockup.svg").write_text(lockup_svg(OUT / "kts-logo.png"), encoding="utf-8")
    print(f"kts-logo.png {logo.size}, kts-mark.png {mark.size}, thiruvalluvar-gold.png {valluvar.size}, favicon, touch icon, kts5-lockup.png/.svg")


if __name__ == "__main__":
    main()

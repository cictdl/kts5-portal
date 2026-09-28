"""
Build the KTS 5.0 image assets from the originals in tools/logo-src/:

  kts-logo-src.png          Kashi Tamil Sangamam logo (circle + trilingual wordmark, white background)
  thiruvalluvar-src.jpg     painting of Thiruvalluvar
  moe-src.png               Ministry of Education
  goi-src.webp              Government of India
  bhu-src.png               Banaras Hindu University
  iitm-src.jpg              IIT Madras (white background)
  bbs-src.png               Bharatiya Bhasha Samiti (white background)
  pm-thirukkural-src.jpg    the Prime Minister presenting the Thirukkural in Russian translation

Outputs (static/img/):
  kts-logo.png              the full KTS logo, transparent background (masthead, print headers)
  kts-mark.png              the circle alone on a square canvas (favicon, console, exam header)
  favicon.png, apple-touch-icon.png
  thiruvalluvar.jpg         the painting, full figure (About page; corners rounded in CSS)
  thiruvalluvar-bust.jpg    head and shoulders, square (Kural of the Day card; shown as a circle in CSS)
  logos/<code>.png          partner logos named after the agency code (moe, cict, iitm, bhu, bbs) plus goi
  pm-thirukkural.jpg        the photograph, web size
  kts5-lockup.png / .svg    logo + "Kashi Tamil Sangamam 5.0" + theme line + institute line

    python tools/make_logo.py
"""
import base64
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "logo-src"
OUT = ROOT / "static" / "img"
LOGOS = OUT / "logos"
FONTS = Path("C:/Windows/Fonts")
INDIGO = (31, 58, 95, 255)
KUMKUM = (179, 38, 30, 255)
SAFFRON = (224, 123, 26, 255)
DIM = (87, 83, 78, 255)
CREAM = (250, 248, 244, 255)
THEME = "Thirukkural Payilvom – Thirukkural Abhyas Karen"
ORG = "Central Institute of Classical Tamil, Chennai  ·  Ministry of Education, Government of India"

# Framing of the Thiruvalluvar painting, as fractions of its width/height.
PORTRAIT_BOX = (0.035, 0.10, 0.965, 0.945)      # full seated figure, excludes the corner mark of the source file
BUST_CENTRE = (0.510, 0.375)                   # centre of the face
BUST_RADIUS = 0.285                            # as a fraction of the width


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


def fit_height(im, height):
    if im.height <= height:
        return im
    return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)


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
    end = h
    for y in range(int(h * 0.4), h):
        if not rows[y]:
            end = y
            break
    return trimmed(logo.crop((0, 0, w, end)))


def save_png(im, path, colours=256):
    """Palette PNG with alpha: a fraction of the size of a true-colour PNG, visually the same for flat logo artwork."""
    im = im.convert("RGBA")
    try:
        im.quantize(colors=colours, method=Image.Quantize.FASTOCTREE).save(path, "PNG", optimize=True)
    except (ValueError, OSError):
        im.save(path, "PNG", optimize=True)


def save_jpeg(im, path, quality=86):
    im.convert("RGB").save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def crop_fraction(im, box):
    w, h = im.size
    return im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))


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


def lockup_svg(logo_png, logo_size):
    data = base64.b64encode(logo_png.read_bytes()).decode("ascii")
    lw = round(logo_size[0] * 440 / logo_size[1])
    x = lw + 60
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{x + 1315}" height="512" viewBox="0 0 {x + 1315} 512">'
        "<title>Kashi Tamil Sangamam 5.0 · Thirukkural Payilvom – Thirukkural Abhyas Karen</title>"
        f'<image href="data:image/png;base64,{data}" x="0" y="36" width="{lw}" height="440"/>'
        f'<text x="{x}" y="180" font-family="Cambria, Georgia, serif" font-weight="700" font-size="100" fill="#1f3a5f">Kashi Tamil Sangamam 5.0</text>'
        f'<text x="{x}" y="272" font-family="Cambria, Georgia, serif" font-weight="700" font-size="50" fill="#b3261e">{THEME}</text>'
        f'<rect x="{x}" y="326" width="1275" height="5" fill="#e07b1a"/>'
        f'<text x="{x}" y="382" font-family="Calibri, \'Segoe UI\', sans-serif" font-size="36" fill="#57534e">{ORG}</text>'
        "</svg>"
    )


def main():
    LOGOS.mkdir(parents=True, exist_ok=True)
    report = []

    # ---- Kashi Tamil Sangamam logo --------------------------------------
    full = trimmed(knock_out_white(Image.open(SRC / "kts-logo-src.png")))
    logo = fit_height(full, 520)
    save_png(logo, OUT / "kts-logo.png")
    mark = squared(circle_only(full), 512)
    save_png(mark, OUT / "kts-mark.png")
    mark.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.png")
    touch = Image.new("RGBA", (180, 180), CREAM)
    m = mark.resize((156, 156), Image.LANCZOS)
    touch.paste(m, (12, 12), m)
    touch.convert("RGB").save(OUT / "apple-touch-icon.png")
    report.append(f"kts-logo.png {logo.size}, kts-mark.png {mark.size}")

    # ---- Thiruvalluvar --------------------------------------------------
    painting = Image.open(SRC / "thiruvalluvar-src.jpg").convert("RGB")
    portrait = crop_fraction(painting, PORTRAIT_BOX)
    portrait = portrait.resize((640, round(portrait.height * 640 / portrait.width)), Image.LANCZOS)
    save_jpeg(portrait, OUT / "thiruvalluvar.jpg")
    w, h = painting.size
    cx, cy, r = BUST_CENTRE[0] * w, BUST_CENTRE[1] * h, BUST_RADIUS * w
    bust = painting.crop((round(cx - r), round(cy - r), round(cx + r), round(cy + r))).resize((400, 400), Image.LANCZOS)
    save_jpeg(bust, OUT / "thiruvalluvar-bust.jpg")
    report.append(f"thiruvalluvar.jpg {portrait.size}, thiruvalluvar-bust.jpg {bust.size}")

    # ---- partner logos (file name = agency code, lower case) -------------
    partners = [
        ("moe", "moe-src.png", 0, 220),
        ("goi", "goi-src.webp", 0, 220),
        ("bhu", "bhu-src.png", 0, 363),
        ("iitm", "iitm-src.jpg", 30, 400),
        ("bbs", "bbs-src.png", 40, 53),
    ]
    for code, name, tol, height in partners:
        im = Image.open(SRC / name).convert("RGBA")
        if tol:
            im = knock_out_white(im, tol=tol)
        im = fit_height(trimmed(im), height)
        save_png(im, LOGOS / f"{code}.png")
        report.append(f"logos/{code}.png {im.size}")
    cict = Image.open(OUT / "cict-logo.png").convert("RGBA")
    save_png(cict, LOGOS / "cict.png")
    report.append(f"logos/cict.png {cict.size}")

    # ---- photograph -----------------------------------------------------
    photo = Image.open(SRC / "pm-thirukkural-src.jpg").convert("RGB")
    if photo.width > 1100:
        photo = photo.resize((1100, round(photo.height * 1100 / photo.width)), Image.LANCZOS)
    save_jpeg(photo, OUT / "pm-thirukkural.jpg")
    report.append(f"pm-thirukkural.jpg {photo.size}")

    # ---- lockups --------------------------------------------------------
    lockup_png(logo).save(OUT / "kts5-lockup.png", optimize=True)
    (OUT / "kts5-lockup.svg").write_text(lockup_svg(OUT / "kts-logo.png", logo.size), encoding="utf-8")
    report.append("kts5-lockup.png/.svg")
    print("\n".join(report))


if __name__ == "__main__":
    main()

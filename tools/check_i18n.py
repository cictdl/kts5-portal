"""
Check the interface translations in data/i18n/.

    python tools/check_i18n.py            # every language
    python tools/check_i18n.py bn te ur   # some languages
    python tools/check_i18n.py --dir <folder> bn te   # files of another folder; its en.json is the source

ERRORS (exit code 1): invalid JSON, missing or unknown keys, empty values,
text in the wrong script, left in English.
WARNINGS: numbers of the English source that do not appear in the translation,
translations much longer than the source (buttons and labels must stay short).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

I18N = Path(__file__).resolve().parent.parent / "data" / "i18n"

DEVANAGARI = [(0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x1CD0, 0x1CFF)]
SCRIPTS = {
    "as": [(0x0980, 0x09FF)], "bn": [(0x0980, 0x09FF)], "mni": [(0x0980, 0x09FF)],
    "brx": DEVANAGARI, "doi": DEVANAGARI, "hi": DEVANAGARI, "kok": DEVANAGARI, "mai": DEVANAGARI,
    "mr": DEVANAGARI, "ne": DEVANAGARI, "sa": DEVANAGARI, "sd": DEVANAGARI,
    "gu": [(0x0A80, 0x0AFF)], "pa": [(0x0A00, 0x0A7F)], "or": [(0x0B00, 0x0B7F)], "ta": [(0x0B80, 0x0BFF)],
    "te": [(0x0C00, 0x0C7F)], "kn": [(0x0C80, 0x0CFF)], "ml": [(0x0D00, 0x0D7F)],
    "sat": [(0x1C50, 0x1C7F)],
    "ur": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "ks": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
}
# Tokens that legitimately stay in Latin letters.
KEEP = {"kts", "cict", "aishe", "ugc", "aicte", "cbse", "kvs", "jnv", "nvs", "iit", "nit", "iiser", "iiit", "obc", "sc", "st",
        "ews", "pin", "pdf", "jpg", "png", "csv", "kb", "mb", "whatsapp", "youtube", "excel", "cc", "by", "c", "m", "phil",
        "ph", "d", "ist", "mcq", "qr", "nhai", "aai", "bhu", "bbs", "irctc", "dr", "mu", "email", "otp", "id", "app", "url"}


def letters(text):
    return [ch for ch in text if unicodedata.category(ch).startswith("L")]


def in_ranges(ch, ranges):
    cp = ord(ch)
    return any(a <= cp <= b for a, b in ranges)


def latin_words(text):
    return [w for w in re.findall(r"[A-Za-z]+", text) if w.lower() not in KEEP]


def check(code, en, folder=None):
    path = Path(folder or I18N) / f"{code}.json"
    errors, warnings = [], []
    if not path.exists():
        return [f"{path.name} does not exist"], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"invalid JSON: {exc}"], []
    if not isinstance(data, dict):
        return ["the file must contain one JSON object"], []
    missing = [k for k in en if k not in data]
    extra = [k for k in data if k not in en]
    if missing:
        errors.append(f"{len(missing)} missing key(s): " + ", ".join(missing[:12]) + (" …" if len(missing) > 12 else ""))
    if extra:
        errors.append(f"{len(extra)} unknown key(s): " + ", ".join(extra[:12]))
    ranges = SCRIPTS.get(code)
    for key, source in en.items():
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}: empty")
            continue
        if ranges:
            ls = letters(value)
            own = [ch for ch in ls if in_ranges(ch, ranges)]
            stray = latin_words(value)
            source_words = latin_words(source)
            if source_words and ls and not own:
                errors.append(f"{key}: not translated ({value[:50]!r})")
            elif ls and own and len(own) / len(ls) < 0.5 and len(stray) > 2:
                errors.append(f"{key}: mostly Latin letters, {len(stray)} English word(s): {' '.join(stray[:6])}")
            other = [ch for ch in ls if not in_ranges(ch, ranges) and not ("A" <= ch.upper() <= "Z")
                     and unicodedata.name(ch, "").split(" ")[0] not in ("LATIN", "MODIFIER")]
            if own and len(other) > max(3, len(ls) * 0.25):
                names = sorted({unicodedata.name(ch, "?").split(" ")[0] for ch in other})
                errors.append(f"{key}: letters from another script ({', '.join(names)})")
        for number in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", source):
            if number not in value:
                warnings.append(f"{key}: the number {number} of the source is not in the translation")
        if len(source) <= 24 and len(value) > 3.2 * len(source) + 12:
            warnings.append(f"{key}: long for a label ({len(value)} characters for {len(source)} in English)")
    return errors, warnings


def main():
    args = sys.argv[1:]
    folder = I18N
    if "--dir" in args:
        at = args.index("--dir")
        folder = Path(args[at + 1])
        del args[at:at + 2]
    en = json.loads((folder / "en.json").read_text(encoding="utf-8"))
    codes = args or sorted(p.stem for p in folder.glob("*.json") if p.stem != "en")
    failed = 0
    for code in codes:
        errors, warnings = check(code, en, folder)
        state = "OK" if not errors else "FAILED"
        print(f"[{code}] {state}: {len(errors)} error(s), {len(warnings)} warning(s)")
        for e in errors[:40]:
            print("   ERROR  ", e)
        for w in warnings[:25]:
            print("   warning", w)
        if len(warnings) > 25:
            print(f"   … {len(warnings) - 25} more warning(s)")
        failed += bool(errors)
    print(f"source: {len(en)} keys; checked {len(codes)} language(s); {failed} with errors")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""
Repair of the Kashmiri stream in the Perso-Arabic script (tr.ksn) of the Thirukkural corpus.

As received from the Thirukkural app, the entry of couplet 93 is a second version of couplet 92,
and every later entry stands one couplet too late: entry n + 1 holds the translation of couplet n,
up to entry 1330. The translation of couplet 1330 itself is not in the data.

Found on 28 Sep 2026 while the Kashmiri interface was prepared, and confirmed with words that
occur in few couplets: "moon" is in couplets 782, 957, 1116-1119, 1146 and 1210 of the English and
in entries 783, 958, 1117-1120, 1147 and 1211 of this stream; "crow" 481 and 527 against 482 and
528; "tiger" 273 and 599 against 274 and 600.

    python tools/fix_ksn_alignment.py            # report only
    python tools/fix_ksn_alignment.py --write    # move entries 94..1330 up by one couplet

The second version of couplet 92 that is taken out is kept in data/kurals/ksn-repair.json, which
also marks the repair as done: running it again changes nothing. Couplet 1330 is left without a
Kashmiri text in this script until CICT supplies it; the portal then shows the English.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "kurals"
MARK = DATA / "ksn-repair.json"
STREAM = "ksn"
FIRST, LAST = 93, 1330


def load():
    chapters = []
    for i in range(1, 134):
        path = DATA / f"{i:03d}.json"
        chapters.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return chapters


def main():
    if MARK.exists():
        print("already repaired:", MARK.name)
        return
    chapters = load()
    kurals = {k["n"]: k for _, ch in chapters for k in ch["kurals"]}
    old = {n: kurals[n]["tr"].get(STREAM) for n in kurals}
    if not old[LAST] or not old[FIRST]:
        sys.exit("the stream does not look like the data this repair was written for; nothing changed")
    print(f"couplet {FIRST - 1}:", " / ".join(old[FIRST - 1]))
    print(f"entry {FIRST} (second version of {FIRST - 1}, taken out):", " / ".join(old[FIRST]))
    print(f"entry {FIRST + 1} (becomes couplet {FIRST}):", " / ".join(old[FIRST + 1]))
    print(f"entry {LAST} (becomes couplet {LAST - 1}):", " / ".join(old[LAST]))
    if "--write" not in sys.argv:
        print("report only; add --write to repair")
        return
    for n in range(FIRST, LAST):
        kurals[n]["tr"][STREAM] = old[n + 1]
    del kurals[LAST]["tr"][STREAM]
    for path, ch in chapters:
        if ch["end"] >= FIRST:
            path.write_text(json.dumps(ch, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    MARK.write_text(json.dumps({
        "stream": STREAM,
        "repaired": "entries 94 to 1330 moved to couplets 93 to 1329",
        "without_text": [LAST],
        "taken_out": {"entry": FIRST, "second_version_of": FIRST - 1, "text": old[FIRST]},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("repaired; couplet", LAST, "has no text in this stream")


if __name__ == "__main__":
    main()

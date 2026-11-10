"""
Repair of the Kashmiri stream in the Perso-Arabic script (tr.ksn) of the Thirukkural corpus.

Step 1 (28 Sep 2026). As received from the Thirukkural app, the entry of couplet 93 is a second
version of couplet 92, and every later entry stands one couplet too late: entry n + 1 holds the
translation of couplet n, up to entry 1330. The translation of couplet 1330 itself is not in the
data. Found while the Kashmiri interface was prepared, and confirmed with words that occur in few
couplets: "moon" is in couplets 782, 957, 1116-1119, 1146 and 1210 of the English and in entries
783, 958, 1117-1120, 1147 and 1211 of this stream; "crow" 481 and 527 against 482 and 528;
"tiger" 273 and 599 against 274 and 600.

Step 2 (10 Nov 2026, portal 1.2.170). From couplet 224 to 252 the data received was in place: it
has no translation of couplet 224, and two versions of couplet 252 (entries 252 and 253). Step 1
therefore put couplets 225 to 252 one place too early: entry n held the translation of couplet
n + 1 for n = 224 to 251, and entries 251 and 252 were the two versions of couplet 252. Found by
the reviewer of CICT's Kashmiri study book, whose garland is right at 226, 231 and 241 where the
portal was not; confirmed couplet by couplet against the English (entry 224: the ascetic who bears
hunger and the one who relieves it, couplet 225; entry 249: the strong over the weak, 250; entries
251 and 252: the thriftless and the flesh-eater, both 252). Every other pair of neighbouring
entries that are alike was read too; none of them closes such a run. Step 2 moves the entries 224
to 250 to couplets 225 to 251, keeps the version of couplet 252 that the portal showed, and leaves
couplet 224 without a text in this script until CICT supplies it.

    python tools/fix_ksn_alignment.py            # report only
    python tools/fix_ksn_alignment.py --write    # the steps not yet done

data/kurals/ksn-repair.json records each step and what it took out, and marks it as done: running
it again changes nothing. Where a couplet has no Kashmiri text in this script (224 and 1330), the
portal shows the English.
"""
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "kurals"
MARK = DATA / "ksn-repair.json"
STREAM = "ksn"
FIRST, LAST = 93, 1330          # step 1: entries 94..1330 to couplets 93..1329
LOW, HIGH = 224, 252            # step 2: entries 224..250 to couplets 225..251; 224 without a text


def load():
    chapters = []
    for i in range(1, 134):
        path = DATA / f"{i:03d}.json"
        chapters.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return chapters


def save(chapters, first, last):
    for path, ch in chapters:
        if ch["start"] <= last and ch["end"] >= first:
            path.write_bytes(json.dumps(ch, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def write_mark(mark):
    MARK.write_bytes((json.dumps(mark, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def step1(write):
    chapters = load()
    kurals = {k["n"]: k for _, ch in chapters for k in ch["kurals"]}
    old = {n: kurals[n]["tr"].get(STREAM) for n in kurals}
    if not old[LAST] or not old[FIRST]:
        sys.exit("the stream does not look like the data step 1 was written for; nothing changed")
    print(f"couplet {FIRST - 1}:", " / ".join(old[FIRST - 1]))
    print(f"entry {FIRST} (second version of {FIRST - 1}, taken out):", " / ".join(old[FIRST]))
    print(f"entry {FIRST + 1} (becomes couplet {FIRST}):", " / ".join(old[FIRST + 1]))
    print(f"entry {LAST} (becomes couplet {LAST - 1}):", " / ".join(old[LAST]))
    if not write:
        return None
    for n in range(FIRST, LAST):
        kurals[n]["tr"][STREAM] = old[n + 1]
    del kurals[LAST]["tr"][STREAM]
    save(chapters, FIRST, LAST)
    mark = {
        "stream": STREAM,
        "repaired": "entries 94 to 1330 moved to couplets 93 to 1329",
        "without_text": [LAST],
        "taken_out": {"entry": FIRST, "second_version_of": FIRST - 1, "text": old[FIRST]},
    }
    write_mark(mark)
    print("step 1 done; couplet", LAST, "has no text in this stream")
    return mark


def step2(mark, write):
    chapters = load()
    kurals = {k["n"]: k for _, ch in chapters for k in ch["kurals"]}
    old = {n: kurals[n]["tr"].get(STREAM) for n in range(LOW, HIGH + 1)}
    alike = SequenceMatcher(None, " ".join(old[HIGH - 1] or []), " ".join(old[HIGH] or [])).ratio()
    if not all(old.values()) or alike < 0.6:
        sys.exit("the stream does not look like the data step 2 was written for; nothing changed")
    print(f"entry {LOW} (becomes couplet {LOW + 1}; couplet {LOW} is left without a text):", " / ".join(old[LOW]))
    print(f"entry {HIGH - 2} (becomes couplet {HIGH - 1}):", " / ".join(old[HIGH - 2]))
    print(f"entry {HIGH - 1} (second version of {HIGH}, taken out; {alike:.2f} alike):", " / ".join(old[HIGH - 1]))
    print(f"entry {HIGH} (stays):", " / ".join(old[HIGH]))
    if not write:
        return
    for n in range(HIGH - 1, LOW, -1):
        kurals[n]["tr"][STREAM] = old[n - 1]
    del kurals[LOW]["tr"][STREAM]
    save(chapters, LOW, HIGH)
    mark["second"] = {
        "date": "2026-11-10",
        "repaired": "entries 224 to 250 moved to couplets 225 to 251",
        "without_text": [LOW],
        "taken_out": {"entry": HIGH - 1, "second_version_of": HIGH, "text": old[HIGH - 1]},
    }
    write_mark(mark)
    print("step 2 done; couplet", LOW, "has no text in this stream")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # the Kashmiri text on any console
    write = "--write" in sys.argv
    if MARK.exists():
        mark = json.loads(MARK.read_text(encoding="utf-8"))
        print("step 1 already done:", mark["repaired"])
    else:
        mark = step1(write)
        if mark is None:
            print("report only; add --write to repair")
            return
    if "second" in mark:
        print("step 2 already done:", mark["second"]["repaired"])
        return
    step2(mark, write)
    if not write:
        print("report only; add --write to repair")


if __name__ == "__main__":
    main()

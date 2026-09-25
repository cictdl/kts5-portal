"""
Command-line management for the KTS 5.0 portal.

    python manage.py init-db
    python manage.py create-user --email x@cict.in --name "Name" --role admin [--agency CICT]
    python manage.py gen-questions --langs en,hi,ta --count 60
    python manage.py seed-demo [--applications 80]
    python manage.py run-selection --select 1000 --wait 300
    python manage.py export-applications out.xlsx
"""
import argparse
import io
import random
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Vendored dependencies (Plesk package): lib/ next to this file is used when present,
# so the portal runs with only python.exe installed on the server.
_LIB = Path(__file__).resolve().parent / "lib"
if _LIB.is_dir():
    sys.path.insert(0, str(_LIB))

from werkzeug.security import generate_password_hash  # noqa: E402

from kts import create_app  # noqa: E402
from kts import kural as K  # noqa: E402
from kts.db import execute, executemany, query, set_setting, utcnow  # noqa: E402
from kts.utils import college_key, make_app_no, xlsx_bytes  # noqa: E402

app = create_app()


def cmd_init_db(_args):
    print("Database initialised at", app.config["DATABASE"])


def cmd_create_user(args):
    with app.app_context():
        agency_id = None
        if args.agency:
            row = query("SELECT id FROM agencies WHERE code = ?", (args.agency.upper(),), one=True)
            if row is None:
                sys.exit(f"No agency with code {args.agency}")
            agency_id = row["id"]
        password = args.password or ("Kts5-" + secrets.token_urlsafe(6))
        execute("INSERT INTO users(email, name, password_hash, role, agency_id, active, must_change_password, created_at) VALUES(?,?,?,?,?,1,?,?)",
                (args.email.lower(), args.name, generate_password_hash(password), args.role, agency_id, 0 if args.password else 1, utcnow()))
        print(f"Created {args.role} {args.email} · password: {password}")


def cmd_gen_questions(args):
    langs = ["ta"] + K.ORIENTATION_LANGS if args.langs == "all" else args.langs.split(",")
    with app.app_context():
        total = 0
        for lang in langs:
            rows = K.generate_questions(lang, args.count, seed=f"{lang}-{args.seed}")
            executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                        [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"], r["kural_no"], r["difficulty"], utcnow()) for r in rows])
            total += len(rows)
            print(f"{lang}: {len(rows)} questions")
        print("total", total)


FIRST = ["Aarav", "Ananya", "Arjun", "Bhavya", "Chirag", "Deepa", "Farhan", "Gauri", "Harsh", "Ishita", "Jaya", "Kabir", "Lakshmi",
         "Meera", "Nikhil", "Om", "Pooja", "Rahul", "Sneha", "Tarun", "Uma", "Vikram", "Zara", "Yash", "Riya", "Sanjay", "Tanvi", "Neha"]
LAST = ["Sharma", "Patel", "Reddy", "Das", "Nair", "Singh", "Kumar", "Bose", "Mishra", "Joshi", "Rao", "Iyer", "Gowda", "Khan", "Yadav", "Deshmukh", "Sen", "Pillai", "Mehta", "Choudhary"]
COLLEGES = ["Government Arts College", "St. Xavier's College", "National Institute of Technology", "Regional Engineering College", "Presidency College",
            "Government Degree College", "Christ College", "Sri Venkateswara College", "Fergusson College", "Ravenshaw College", "Loyola College",
            "Miranda House", "Hindu College", "Gargi College", "Maharaja's College", "Sacred Heart College", "Model Degree College"]


def cmd_seed_demo(args):
    import json
    from PIL import Image, ImageDraw
    rng = random.Random(args.seed)
    with app.app_context():
        states = json.loads((app.config["DATA_DIR"] / "states.json").read_text(encoding="utf-8"))
        all_states = states["states"] + states["union_territories"]
        now = utcnow()
        # ---- notices / resources / events / tasks ----
        if not query("SELECT 1 FROM notices LIMIT 1", one=True):
            for title, body, cat, pinned in [
                ("Call for applications: Kashi Tamil Sangamam 5.0 – Thirukkural Payilvom",
                 "The Central Institute of Classical Tamil invites applications from students enrolled in colleges and universities across India for KTS 5.0. One thousand student delegates, one per institution, will be selected through an online test and will take part in a ten-lecture orientation on the Thirukkural in their own language.\n\nRegister on this portal before the closing date. Keep your application number safe.", "registration", 1),
                ("Online selection test: date and pattern", "The online test will be held on the date announced on the Examination page. It has 25 objective questions drawn from the Thirukkural study material, four marks each, no negative marking, thirty minutes.", "examination", 0),
                ("Orientation lecture series in 21 languages", "The ten-part academic lecture series is being dubbed and subtitled with the Central Institute of Indian Languages. Language-wise session dates will be published after the merit list.", "orientation", 0),
            ]:
                execute("INSERT INTO notices(title, body, category, lang, pinned, published, created_at, updated_at) VALUES(?,?,?,?,?,1,?,?)",
                        (title, body, cat, "en", pinned, now, now))
        if not query("SELECT 1 FROM resources LIMIT 1", one=True):
            for title, desc, cat, lang, url, featured in [
                ("Thirukkural Multilingual App (22 languages)", "CICT's free, offline, ad-free app: all 1,330 couplets with translations into the 22 scheduled languages, two Tamil commentaries, English prose, word-level grammar and metre.", "app", "", "https://cictdl.github.io/index.html/kural-app/", 1),
                ("Thirukkural Ground-Truth Corpus (palm-leaf manuscripts)", "Line-level transcriptions of the Thirukkural from CICT's palm-leaf manuscript collection with PAGE-XML and IIIF images.", "corpus", "", "https://www.digitalarchives.cict.in/#ground-truth", 1),
                ("CICT Digital Archives", "Manuscript specimens, publications and the grammar layer of classical Tamil texts.", "link", "", "https://www.digitalarchives.cict.in/", 0),
                ("Thirukkural: an introduction (English)", "Study material for the online test: structure of the text, the three sections, the metre and the life of Thiruvalluvar.", "study", "en", "https://cictdl.github.io/index.html/kural-app/", 1),
                ("तिरुक्कुरल: परिचय (हिन्दी)", "ऑनलाइन परीक्षा के लिए अध्ययन सामग्री: ग्रंथ की संरचना, तीन खंड, छंद और तिरुवल्लुवर।", "study", "hi", "https://cictdl.github.io/index.html/kural-app/", 0),
                ("Kural Kattam – daily Tamil crossword", "A Dinamalar-style daily crossword built from the Thirukkural.", "app", "ta", "https://cictdl.github.io/kural-kattam/", 0),
            ]:
                execute("INSERT INTO resources(title, description, category, lang, url, published, featured, created_at, updated_at) VALUES(?,?,?,?,?,1,?,?,?)",
                        (title, desc, cat, lang, url, featured, now, now))
        if not query("SELECT 1 FROM events LIMIT 1", one=True):
            base = date.today()
            cict = query("SELECT id FROM agencies WHERE code = 'CICT'", one=True)["id"]
            bhu = query("SELECT id FROM agencies WHERE code = 'BHU'", one=True)["id"]
            evs = [("Registration closes", "registration", "", (base + timedelta(days=40)).isoformat() + "T23:59", "Online", cict),
                   ("Online selection test", "examination", "", (base + timedelta(days=55)).isoformat() + "T11:00", "Online", cict),
                   ("Merit list announcement", "general", "", (base + timedelta(days=65)).isoformat() + "T17:00", "This portal", cict),
                   ("National Conference on the Thirukkural", "conference", "", (base + timedelta(days=120)).isoformat() + "T10:00", "Banaras Hindu University, Varanasi", bhu)]
            for i, lang in enumerate(["hi", "bn", "te", "mr", "kn", "ml"]):
                evs.append((f"Orientation session 1 · {K.lang_info(lang)['name']}", "orientation", lang, (base + timedelta(days=75 + i)).isoformat() + "T18:00", "Online (link on the candidate portal)", cict))
            for title, kind, lang, starts, venue, ag in evs:
                execute("INSERT INTO events(title, kind, lang, starts_at, venue, agency_id, published, created_at, updated_at) VALUES(?,?,?,?,?,?,1,?,?)",
                        (title, kind, lang, starts, venue, ag, now, now))
        if not query("SELECT 1 FROM tasks LIMIT 1", one=True):
            ag = {r["code"]: r["id"] for r in query("SELECT id, code FROM agencies")}
            tasks = [
                ("Circulate the call for applications to all universities", "publicity", ag["UGC"], "in_progress", "high", 10),
                ("Circular to AICTE-approved institutions", "publicity", ag["AICTE"], "open", "normal", 12),
                ("Dub the ten orientation lectures into 21 languages", "orientation", ag["CIIL"], "in_progress", "urgent", 45),
                ("Finalise the question bank in every language", "exam", ag["CICT"], "in_progress", "urgent", 30),
                ("Couplet display slots on station information systems", "displays", ag["IRCTC"], "open", "normal", 60),
                ("Airport signage locations and formats", "displays", ag["AAI"], "blocked", "normal", 60),
                ("Toll plaza display boards", "displays", ag["NHAI"], "open", "low", 90),
                ("Daily Kural 200-day calendar to schools", "schools", ag["CBSE"], "open", "normal", 50),
                ("Printed charts for Kendriya and Navodaya Vidyalayas", "schools", ag["KVS"], "open", "normal", 70),
                ("National Conference venue and dates", "conference", ag["BHU"], "in_progress", "high", 40),
                ("Cultural troupes for KTS venues", "logistics", ag["MOC"], "open", "normal", 80),
                ("Portal go-live sign-off", "portal", ag["CICT"], "done", "high", -5),
            ]
            for title, ws, agency_id, status, prio, due in tasks:
                execute("INSERT INTO tasks(title, workstream, agency_id, status, priority, due_date, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (title, ws, agency_id, status, prio, (date.today() + timedelta(days=due)).isoformat(), now, now))
        # ---- applications ----
        photos = Path(app.config["UPLOAD_DIR"]) / "photos"
        ids = Path(app.config["UPLOAD_DIR"]) / "idproofs"
        photos.mkdir(parents=True, exist_ok=True)
        ids.mkdir(parents=True, exist_ok=True)
        existing = query("SELECT COUNT(*) AS n FROM applications", one=True)["n"]
        made = 0
        for i in range(args.applications):
            n = existing + i + 1
            first, last = rng.choice(FIRST), rng.choice(LAST)
            state = rng.choice(all_states)
            college = f"{rng.choice(COLLEGES)}, {state}"
            lang = rng.choice(K.ORIENTATION_LANGS[:8] + ["hi", "hi", "en", "bn", "te", "mr"])
            mobile = "9" + "".join(rng.choice("0123456789") for _ in range(9))
            email = f"{first}.{last}{n}@example.edu".lower()
            dob = date(rng.randint(1999, 2007), rng.randint(1, 12), rng.randint(1, 28)).isoformat()
            img = Image.new("RGB", (240, 300), (rng.randint(60, 200), rng.randint(60, 200), rng.randint(60, 200)))
            ImageDraw.Draw(img).text((20, 140), f"{first}\n{last}", fill=(255, 255, 255))
            pfile = f"demo-{secrets.token_hex(4)}.jpg"
            img.save(photos / pfile, "JPEG", quality=70)
            ifile = f"demo-{secrets.token_hex(4)}.png"
            Image.new("RGB", (400, 260), (235, 230, 220)).save(ids / ifile, "PNG")
            created = (date.today() - timedelta(days=rng.randint(0, 25))).isoformat() + "T10:00:00+00:00"
            status = rng.choice(["submitted", "verified", "verified", "verified", "rejected"])
            row_id = execute(
                "INSERT INTO applications(full_name, gender, dob, category, mobile, email, state, district, college_name, college_key, aishe_code, college_type, college_state, "
                "university, course_level, discipline, year_of_study, mother_tongue, pref_lang, photo_path, idproof_path, status, ip, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"{first} {last}", rng.choice("MF"), dob, rng.choice(states["categories"]), mobile, email, state, "", college,
                 college_key(college, state, ""), "", rng.choice(states["college_types"]), state, "", rng.choice(states["course_levels"]),
                 rng.choice(["B.A.", "B.Sc.", "B.Com.", "B.Tech", "M.A.", "BBA"]), rng.choice(states["years"]), lang if lang != "en" else "hi", lang,
                 f"photos/{pfile}", f"idproofs/{ifile}", status, "127.0.0.1", created, created))
            execute("UPDATE applications SET app_no = ? WHERE id = ?", (make_app_no(row_id), row_id))
            if status == "verified" and rng.random() < 0.7:
                score = rng.choice([40, 48, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100])
                taken = rng.randint(600, 1800)
                execute("INSERT INTO exam_sessions(application_id, lang, paper_json, answers_json, started_at, deadline_at, submitted_at, status, score, correct_count, time_taken_sec) "
                        "VALUES(?,?,'[]','{}',?,?,?,'submitted',?,?,?)",
                        (row_id, lang, created, created, created, score, score // 4, taken))
                execute("UPDATE applications SET exam_score = ? WHERE id = ?", (score, row_id))
            made += 1
        print(f"Seeded {made} demo applications (plus notices, resources, events and tasks where empty).")


def cmd_run_selection(args):
    from kts.admin import run_selection
    with app.app_context():
        with app.test_request_context():
            run_id, ranked, runners = run_selection(args.select, args.wait, None)
            set_setting("merit.select_count", str(args.select))
            set_setting("merit.wait_count", str(args.wait))
            print(f"Run {run_id}: {ranked} institutions ranked, {runners} runners-up")


def cmd_export(args):
    with app.app_context():
        rows = query("SELECT app_no, status, full_name, email, mobile, college_name, college_state, pref_lang, exam_score, exam_rank, created_at FROM applications ORDER BY id")
        data = xlsx_bytes(["App No", "Status", "Name", "Email", "Mobile", "Institution", "State", "Language", "Score", "Rank", "Submitted"], [tuple(r) for r in rows])
        Path(args.out).write_bytes(data)
        print(f"Wrote {len(rows)} rows to {args.out}")


def main():
    p = argparse.ArgumentParser(description="KTS 5.0 portal management")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    c = sub.add_parser("create-user")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", default="admin", choices=["superadmin", "admin", "verifier", "content", "agency", "viewer"])
    c.add_argument("--agency", help="agency code for the agency role")
    c.add_argument("--password", help="set a fixed password (otherwise a temporary one is printed)")
    c.set_defaults(fn=cmd_create_user)
    g = sub.add_parser("gen-questions")
    g.add_argument("--langs", default="en,hi,ta", help="comma-separated codes or 'all'")
    g.add_argument("--count", type=int, default=60)
    g.add_argument("--seed", default="kts5")
    g.set_defaults(fn=cmd_gen_questions)
    s = sub.add_parser("seed-demo")
    s.add_argument("--applications", type=int, default=80)
    s.add_argument("--seed", type=int, default=5)
    s.set_defaults(fn=cmd_seed_demo)
    r = sub.add_parser("run-selection")
    r.add_argument("--select", type=int, default=1000)
    r.add_argument("--wait", type=int, default=300)
    r.set_defaults(fn=cmd_run_selection)
    e = sub.add_parser("export-applications")
    e.add_argument("out")
    e.set_defaults(fn=cmd_export)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

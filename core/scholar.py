"""Scholar mode / Study 2.0 — GCSE tutor, Exam Hall, topic tracker, revision timetable, school timetable.

Exam Hall: ORION writes an exam-style paper (or you photograph a real one + its mark scheme), you answer by
typing or photographing your work, and it marks each question against a mark scheme like an examiner.
Every result is remembered: topics turn red/amber/green, missed questions come back a week later, and
the revision timetable aims at the weak spots.
"""
import base64
import datetime as dt
import io
import json
import os
import re
import threading
import time
import uuid

from .paths import DATA_DIR
from .tools import CTX, tool

PATH = os.path.join(DATA_DIR, "scholar.json")
_lock = threading.RLock()
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
GRADE_GUIDE = [(90, 9), (80, 8), (70, 7), (60, 6), (50, 5), (40, 4), (30, 3), (20, 2), (10, 1)]


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    for k, v in (("subjects", []), ("topics", {}), ("papers", []), ("mistakes", []), ("timetable", {}), ("lessons", [])):
        d.setdefault(k, v)
    return d


def _save(d):
    from .safeio import write_json
    with _lock:
        write_json(PATH, d)


def _quick(system, user, tier="smart"):
    brain = CTX.get("brain")
    if not brain:
        raise RuntimeError("brain not ready")
    out = brain.quick(system, user, tier=tier, max_steps=1) or ""
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}


def _subject(name, d=None):
    d = d or _load()
    low = (name or "").lower().strip()
    for s in d["subjects"]:
        if s["name"].lower() == low or low in s["name"].lower():
            return s
    return None


def grade_for(pct):
    for p, g in GRADE_GUIDE:
        if pct >= p:
            return g
    return "U"


# ------------------------------------------------------------------ subjects + topics
def add_subject(name, board="", target=""):
    with _lock:
        d = _load()
        s = _subject(name, d)
        if not s:
            s = {"name": name.strip().title()[:40], "board": "", "target": ""}
            d["subjects"].append(s)
        if board:
            s["board"] = board.strip().upper()[:20]
        if target:
            s["target"] = str(target)[:3]
        _save(d)
    return s


def gen_topics(subject):
    s = _subject(subject) or add_subject(subject)
    data = _quick("You list GCSE specification topics. Reply JSON only: {\"topics\":[\"...\"]} — 15-35 short topic names "
                  "covering the whole course in teaching order.",
                  f"GCSE {s['name']}" + (f" ({s['board']} specification)" if s.get("board") else " (most common UK spec)"))
    topics = [str(t)[:60] for t in data.get("topics", []) if t][:40]
    with _lock:
        d = _load()
        cur = d["topics"].setdefault(s["name"], {})
        for t in topics:
            cur.setdefault(t, {"r": "grey", "score": None, "seen": None})
        _save(d)
    return topics


def rate_topic(subject, topic, rating=None, score=None):
    with _lock:
        d = _load()
        s = _subject(subject, d) or add_subject(subject)
        tps = d["topics"].setdefault(s["name"], {})
        key = next((k for k in tps if k.lower() == topic.lower() or topic.lower() in k.lower()), topic.strip()[:60])
        t = tps.setdefault(key, {"r": "grey", "score": None, "seen": None})
        if score is not None:          # blend new evidence with old
            t["score"] = round(score if t["score"] is None else t["score"] * 0.4 + score * 0.6)
            t["r"] = "green" if t["score"] >= 70 else "amber" if t["score"] >= 40 else "red"
        if rating:
            t["r"] = {"r": "red", "a": "amber", "g": "green"}.get(rating[0].lower(), rating)
        t["seen"] = time.strftime("%Y-%m-%d")
        _save(d)
        return key, t


def weakest_topics(n=5):
    d = _load()
    rank = {"red": 0, "grey": 1, "amber": 2, "green": 3}
    out = []
    for subj, tps in d["topics"].items():
        for name, t in tps.items():
            out.append((rank.get(t["r"], 1), t.get("score") or 0, subj, name))
    out.sort()
    return [f"{s} — {t}" for _, _, s, t in out[:n]]


def overview():
    d = _load()
    subs = []
    for s in d["subjects"]:
        tps = d["topics"].get(s["name"], {})
        counts = {c: sum(1 for t in tps.values() if t["r"] == c) for c in ("red", "amber", "green", "grey")}
        papers = [p for p in d["papers"] if p["subject"] == s["name"] and p.get("marked")]
        subs.append({**s, "counts": counts, "topics": tps, "papers": len(papers),
                     "trend": [{"date": p["date"], "pct": p["pct"], "grade": p["grade"]} for p in papers[-10:]],
                     "latest": papers[-1]["grade"] if papers else None})
    due = [m for m in d["mistakes"] if m.get("due", "") <= time.strftime("%Y-%m-%d") and not m.get("done")]
    return {"subjects": subs, "papers": [{k: v for k, v in p.items() if k not in ("questions", "answers")}
                                         for p in reversed(d["papers"][-30:])],
            "mistakes_due": len(due), "weak": weakest_topics(6), "timetable": d["timetable"],
            "lessons": d["lessons"][-10:]}


# ------------------------------------------------------------------ Exam Hall
def make_paper(subject, topics="", marks=30, minutes=None):
    s = _subject(subject) or add_subject(subject)
    marks = max(10, min(int(marks or 30), 80))
    weak = [w.split(" — ", 1)[1] for w in weakest_topics(10) if w.startswith(s["name"] + " —")]
    focus = topics or (", ".join(weak[:4]) if weak else "a spread of the whole course")
    data = _quick(
        "You are a GCSE examiner writing an exam-style practice paper. Use real exam command words and realistic "
        "mark allocations (1-6 marks; include at least one longer 4-6 mark question). Give a precise examiner mark "
        "scheme for each question (marking points, accept/reject notes, levels for extended answers). Reply JSON only: "
        '{"title":"...","questions":[{"n":1,"q":"question text","marks":2,"topic":"topic name","scheme":"mark scheme"}]}',
        f"Subject: GCSE {s['name']}{' (' + s['board'] + ')' if s.get('board') else ''}. Topics: {focus}. "
        f"Total marks about {marks}. Student target grade: {s.get('target') or 'unknown'}.")
    qs = [q for q in data.get("questions", []) if q.get("q")]
    if not qs:
        raise RuntimeError("Couldn't write the paper — try again.")
    total = sum(int(q.get("marks", 1)) for q in qs)
    p = {"id": uuid.uuid4().hex[:6], "subject": s["name"], "title": data.get("title") or f"{s['name']} practice paper",
         "questions": qs, "total": total, "minutes": int(minutes or round(total * 1.2)), "date": time.strftime("%Y-%m-%d"),
         "source": "orion", "marked": False}
    with _lock:
        d = _load()
        d["papers"].append(p)
        _save(d)
    return p


def add_real_paper(subject, question_images, scheme_images=None, title=""):
    """A real past paper: ORION reads the questions (and mark scheme) from photos/PDF pages."""
    from PIL import Image
    from .vision import ask_image
    s = _subject(subject) or add_subject(subject)
    qtext = []
    for img in question_images:
        t, _, _ = ask_image(Image.open(img) if isinstance(img, str) else img,
                            "Transcribe every exam question on this page exactly, with question numbers and the marks "
                            "in brackets. Text only.")
        qtext.append(t)
    stext = []
    for img in scheme_images or []:
        t, _, _ = ask_image(Image.open(img) if isinstance(img, str) else img,
                            "Transcribe this mark scheme page exactly (question numbers, marking points, marks).")
        stext.append(t)
    data = _quick("Turn these transcribed exam pages into JSON only: "
                  '{"questions":[{"n":"1a","q":"...","marks":2,"topic":"best guess topic","scheme":"marking points or empty"}]}',
                  "QUESTIONS:\n" + "\n".join(qtext) + ("\n\nMARK SCHEME:\n" + "\n".join(stext) if stext else ""))
    qs = data.get("questions", [])
    p = {"id": uuid.uuid4().hex[:6], "subject": s["name"], "title": title or f"{s['name']} past paper",
         "questions": qs, "total": sum(int(q.get("marks", 1)) for q in qs), "minutes": 0,
         "date": time.strftime("%Y-%m-%d"), "source": "real", "marked": False}
    with _lock:
        d = _load()
        d["papers"].append(p)
        _save(d)
    return p


def get_paper(pid):
    return next((p for p in _load()["papers"] if p["id"] == pid), None)


def _read_photo(b64_or_path):
    from PIL import Image
    if isinstance(b64_or_path, str) and os.path.exists(b64_or_path):
        return Image.open(b64_or_path)
    raw = base64.b64decode(b64_or_path.split(",", 1)[-1])
    return Image.open(io.BytesIO(raw))


def mark_paper(pid, answers=None, photos=None, minutes_taken=None):
    """answers: {n: text}. photos: list of base64 images/paths of handwritten work (read with vision first)."""
    p = get_paper(pid)
    if not p:
        raise RuntimeError("No such paper.")
    answers = {str(k): v for k, v in (answers or {}).items()}
    if photos:
        from .vision import ask_image
        handwritten = []
        for ph in photos:
            t, _, _ = ask_image(_read_photo(ph), "Transcribe this student's handwritten exam answers exactly, keeping "
                                                 "question numbers. Describe any diagrams/graphs briefly in [brackets].")
            handwritten.append(t)
        answers["_photos"] = "\n".join(handwritten)
    qs = "\n\n".join(f"Q{q['n']} [{q.get('marks', 1)} marks] (topic: {q.get('topic', '')})\n{q['q']}\n"
                     f"MARK SCHEME: {q.get('scheme') or '(write a fair examiner scheme yourself)'}" for q in p["questions"])
    ans = "\n\n".join(f"Q{k}: {v}" for k, v in answers.items() if k != "_photos")
    if answers.get("_photos"):
        ans += "\n\nHANDWRITTEN ANSWERS (transcribed):\n" + answers["_photos"]
    data = _quick(
        "You are a strict but fair GCSE examiner. Mark each answer against its mark scheme exactly as an examiner "
        "would: award marks for creditworthy points, explain every lost mark briefly, and give the ideal full-mark "
        "answer. Unanswered = 0. Reply JSON only: "
        '{"results":[{"n":1,"got":1,"of":2,"why":"what earned/lost marks","ideal":"full-mark answer","topic":"..."}],'
        '"summary":"2-3 sentences of overall feedback and the top thing to fix"}',
        f"Subject: GCSE {p['subject']}\n\nPAPER:\n{qs}\n\nSTUDENT ANSWERS:\n{ans or '(none)'}")
    res = data.get("results", [])
    got = sum(float(r.get("got", 0)) for r in res)
    total = sum(float(r.get("of", 0)) for r in res) or p["total"] or 1
    pct = round(got / total * 100)
    with _lock:
        d = _load()
        for x in d["papers"]:
            if x["id"] == pid:
                x.update(marked=True, answers=answers, results=res, got=got, of=total, pct=pct, grade=grade_for(pct),
                         summary=data.get("summary", ""), minutes_taken=minutes_taken, marked_at=time.strftime("%Y-%m-%d"))
        _save(d)
    # remember: topic scores + questions to retry next week
    by_topic = {}
    for r in res:
        t = r.get("topic") or next((q.get("topic") for q in p["questions"] if str(q["n"]) == str(r.get("n"))), "")
        if t:
            g, o = by_topic.get(t, (0, 0))
            by_topic[t] = (g + float(r.get("got", 0)), o + float(r.get("of", 0)))
        if float(r.get("got", 0)) < float(r.get("of", 0)):
            q = next((q for q in p["questions"] if str(q["n"]) == str(r.get("n"))), None)
            if q:
                with _lock:
                    d = _load()
                    d["mistakes"].append({"id": uuid.uuid4().hex[:6], "subject": p["subject"], "q": q["q"],
                                          "marks": q.get("marks", 1), "scheme": q.get("scheme", ""), "topic": t,
                                          "ideal": r.get("ideal", ""),
                                          "due": (dt.date.today() + dt.timedelta(days=7)).isoformat(), "done": False})
                    d["mistakes"] = d["mistakes"][-400:]
                    _save(d)
    for t, (g, o) in by_topic.items():
        if o:
            rate_topic(p["subject"], t, score=g / o * 100)
    return get_paper(pid)


def mistakes_due(n=10):
    today = time.strftime("%Y-%m-%d")
    return [m for m in _load()["mistakes"] if not m.get("done") and m.get("due", "") <= today][:n]


def mistake_done(mid, correct=True):
    with _lock:
        d = _load()
        for m in d["mistakes"]:
            if m["id"] == mid:
                if correct:
                    m["done"] = True
                else:
                    m["due"] = (dt.date.today() + dt.timedelta(days=3)).isoformat()
        _save(d)


# ------------------------------------------------------------------ timetables
def timetable_for(date):
    day = DAYS[date.weekday()]
    return _load()["timetable"].get(day, [])


def set_timetable(day, lessons):
    with _lock:
        d = _load()
        key = next((x for x in DAYS if x.startswith(day.lower().strip()[:3])), day.lower().strip())
        d["timetable"][key] = [str(x).strip()[:30] for x in lessons if str(x).strip()][:10]
        _save(d)


def revision_plan(days=14, weekday_minutes=60, weekend_minutes=120, start_hour=17):
    """Fills free evening slots with revision sessions aimed at red/amber topics (most urgent exams first)."""
    from .schedule import add_event, free_slots
    from .study import overview as study_overview
    weak = weakest_topics(40)
    if not weak:
        d = _load()
        weak = [f"{s['name']} — mixed revision" for s in d["subjects"]] or ["Mixed revision"]
    exams = study_overview().get("exams", [])
    if exams:                     # subjects with sooner exams first
        order = {e["subject"].split()[0].lower(): e["days"] for e in exams}
        weak.sort(key=lambda w: order.get(w.split(" — ")[0].split()[0].lower(), 999))
    made, i = [], 0
    today = dt.date.today()
    for k in range(1, days + 1):
        day = today + dt.timedelta(days=k)
        mins = weekend_minutes if day.weekday() >= 5 else weekday_minutes
        slots = free_slots(day, start_hour if day.weekday() < 5 else 10, 21)
        need = mins
        for sl in slots:
            if need <= 0:
                break
            a, b = sl if isinstance(sl, (list, tuple)) else (sl.get("from"), sl.get("to"))
            a = a if isinstance(a, dt.datetime) else dt.datetime.fromisoformat(f"{day} {a}")
            b = b if isinstance(b, dt.datetime) else dt.datetime.fromisoformat(f"{day} {b}")
            while need > 0 and (b - a).total_seconds() >= 25 * 60:
                length = min(45, need)
                topic = weak[i % len(weak)]
                i += 1
                add_event(f"📚 Revise: {topic}", a.strftime("%Y-%m-%d %H:%M"), length, "none", 5, True, "",
                          "REVISION")
                made.append(f"{a:%a %d %b %H:%M} {topic}")
                a += dt.timedelta(minutes=length + 10)
                need -= length
    return made


# ------------------------------------------------------------------ tutor
def tutor_log(topic, understood, note=""):
    with _lock:
        d = _load()
        d["lessons"].append({"t": time.strftime("%Y-%m-%d %H:%M"), "topic": topic[:80], "ok": bool(understood),
                             "note": note[:200]})
        d["lessons"] = d["lessons"][-300:]
        _save(d)


# ------------------------------------------------------------------ AI tools
@tool("Add or update a GCSE subject (exam board and target grade optional).",
      {"subject": ("string", "e.g. Biology", True), "board": ("string", "AQA, Edexcel, OCR, WJEC… (optional)", False),
       "target": ("string", "Target grade 1-9 (optional)", False)})
def subject_add(subject, board="", target=""):
    s = add_subject(subject, board, target)
    threading.Thread(target=lambda: gen_topics(s["name"]), daemon=True).start()
    return f"Added GCSE {s['name']}{' (' + s['board'] + ')' if s['board'] else ''}. I'm building its topic list now."


@tool("TUTOR: start teaching a topic. Switches to Scholar mode. Then teach step by step, asking a check question after "
      "each part, re-explaining differently if they get it wrong. Log the outcome with tutor_progress.",
      {"topic": ("string", "e.g. 'covalent bonding'", True), "subject": ("string", "Subject", False)})
def tutor_start(topic, subject=""):
    if CTX.get("set_theme") and CTX.get("config", {}).get("theme") != "scholar":
        CTX["set_theme"]("scholar")
    d = _load()
    past = [l for l in d["lessons"] if topic.lower()[:12] in l["topic"].lower()][-3:]
    hist = "; ".join(f"{l['t'][:10]}: {'got it' if l['ok'] else 'struggled'} {l['note']}" for l in past)
    weak = ", ".join(weakest_topics(5))
    return (f"Tutoring '{topic}'. Start with 1-2 quick questions to find what they already know, then teach in small "
            f"steps with a check question after each. Previous lessons on this: {hist or 'none'}. Their weak topics: "
            f"{weak or 'unknown'}. Use the holographic card tool show_card for diagrams/key words if helpful.")


@tool("Log how a tutoring lesson went (so ORION remembers).",
      {"topic": ("string", "Topic", True), "understood": ("boolean", "Did they get it?", True),
       "subject": ("string", "Subject", False), "note": ("string", "What to revisit", False)})
def tutor_progress(topic, understood, subject="", note=""):
    tutor_log(topic, understood, note)
    if subject:
        rate_topic(subject, topic, score=80 if understood else 35)
    return "Logged."


@tool("EXAM HALL: write an exam-style practice paper (opens in the Study page to sit and get marked).",
      {"subject": ("string", "Subject", True), "topics": ("string", "Topics to focus on (blank = weakest)", False),
       "marks": ("integer", "Total marks (default 30)", False)})
def exam_paper(subject, topics="", marks=30):
    p = make_paper(subject, topics, marks)
    emit = CTX.get("emit")
    if emit:
        emit("exam_ready", id=p["id"], title=p["title"])
    return f"Paper ready: {p['title']} — {len(p['questions'])} questions, {p['total']} marks, {p['minutes']} minutes. It's open in Study › Exam Hall."


@tool("Rate how confident the user is with a topic (red/amber/green).",
      {"subject": ("string", "Subject", True), "topic": ("string", "Topic", True), "rating": ("string", "red | amber | green", True)})
def topic_rate(subject, topic, rating):
    k, t = rate_topic(subject, topic, rating)
    return f"{k} marked {t['r']}."


@tool("Build a REVISION TIMETABLE into the schedule for the next N days, aimed at weak topics and the soonest exams.",
      {"days": ("integer", "How many days (default 14)", False),
       "weekday_minutes": ("integer", "Minutes per school day (default 60)", False),
       "weekend_minutes": ("integer", "Minutes per weekend day (default 120)", False)})
def revision_plan_tool(days=14, weekday_minutes=60, weekend_minutes=120):
    made = revision_plan(int(days or 14), int(weekday_minutes or 60), int(weekend_minutes or 120))
    return f"Added {len(made)} revision sessions:\n" + "\n".join(made[:20]) if made else "No free slots found."


@tool("Set the user's school TIMETABLE for a weekday.",
      {"day": ("string", "monday…friday", True), "lessons": ("array", "Lessons in order, e.g. ['Maths','English']", True)})
def timetable_set(day, lessons):
    set_timetable(day, lessons)
    return f"Saved {day.title()}'s timetable."


@tool("Scholar overview: subjects, red topics, latest grades, mistakes to retry.")
def scholar_status():
    o = overview()
    lines = [f"{s['name']}{' (' + s['board'] + ')' if s.get('board') else ''}: latest grade {s['latest'] or '—'}, "
             f"{s['counts']['red']} red / {s['counts']['amber']} amber / {s['counts']['green']} green topics"
             for s in o["subjects"]]
    lines.append(f"Weakest: {', '.join(o['weak']) or '—'}. Mistakes to retry: {o['mistakes_due']}.")
    return "\n".join(lines)

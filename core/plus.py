"""ORION 4.2 extras: grade predictor, essay & maths marking, photo → flashcards, Money/Gaming Wrapped,
job price calculator and the bedtime nudge."""
import datetime as dt
import json
import re
import threading
import time

from .tools import CTX, tool


def _brain_json(system, user, tier="smart"):
    brain = CTX.get("brain")
    if not brain:
        raise RuntimeError("brain not ready")
    out = brain.quick(system, user, tier=tier, max_steps=1) or ""
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("the brain didn't answer properly — try again")
    return json.loads(m.group(0))


# ------------------------------------------------------------------ grade predictor
def predict_grades():
    """Predicted grade per subject from Exam Hall papers (recent ones count more) and topic confidence."""
    from .scholar import overview, grade_for
    o = overview()
    out = []
    for s in o["subjects"]:
        tr = s.get("trend") or []
        c = s.get("counts", {})
        if not tr and not sum(c.values()):
            out.append({"subject": s["name"], "board": s.get("board", ""), "target": s.get("target", ""), "grade": "?",
                        "pct": 0, "basis": "no data yet — sit an Exam Hall paper or rate some topics", "trend": 0,
                        "next_grade_at": None, "gap": 0, "focus": []})
            continue
        total_t = sum(c.values()) or 1
        conf = (c.get("green", 0) * 1.0 + c.get("amber", 0) * 0.55 + c.get("red", 0) * 0.15 + c.get("grey", 0) * 0.4) / total_t
        if tr:
            w = [0.5 ** (len(tr) - 1 - i) for i in range(len(tr))]
            pct = sum(p["pct"] * wi for p, wi in zip(tr, w)) / sum(w)
            pct = pct * 0.8 + conf * 100 * 0.2
            basis = f"{len(tr)} paper{'s' if len(tr) != 1 else ''} + topics"
            trend = (tr[-1]["pct"] - tr[0]["pct"]) if len(tr) > 1 else 0
        else:
            pct = conf * 100 * 0.85
            basis = "topic confidence only — sit a paper for a real prediction"
            trend = 0
        g = grade_for(pct)
        nxt = None
        for p in range(int(pct) + 1, 101):
            if grade_for(p) != g:
                nxt = p
                break
        reds = [t for t, v in (s.get("topics") or {}).items() if v.get("r") == "red"][:3]
        out.append({"subject": s["name"], "board": s.get("board", ""), "target": s.get("target", ""),
                    "grade": g, "pct": round(pct), "basis": basis, "trend": round(trend),
                    "next_grade_at": nxt, "gap": (nxt - round(pct)) if nxt else 0, "focus": reds})
    return out


@tool("GRADE PREDICTOR: predicted GCSE grade per subject (from Exam Hall papers and topic confidence) and what would "
      "push each one up a grade.")
def grade_predict():
    g = predict_grades()
    if not g:
        return "No subjects yet — add them in Study › Subjects (subject_add)."
    lines = []
    for x in g:
        up = f" · {x['gap']}% more for the next grade" if x["gap"] else ""
        foc = f" · focus: {', '.join(x['focus'])}" if x["focus"] else ""
        lines.append(f"{x['subject']}: grade {x['grade']} ({x['pct']}%, {x['basis']}){up}{foc}")
    from .holo import emit_card
    emit_card("chart", "Predicted grades", points=[[x["subject"][:20], float(x["grade"]) if x["grade"].isdigit() else 0] for x in g])
    return "\n".join(lines)


# ------------------------------------------------------------------ essay + maths marking
def mark_writing(text, question="", subject="English Literature", board="", marks=None):
    system = ("You are an experienced UK GCSE examiner and a kind, direct tutor for a Year 11 student. Mark the answer "
              "against the real assessment objectives for that subject/board (e.g. AQA English Lit AO1-AO4). Be honest. "
              'Reply JSON only: {"mark":int,"out_of":int,"grade":"1-9","summary":"2 sentences","strengths":["..."],'
              '"fixes":["specific, actionable fix", "..."],"model_paragraph":"one improved paragraph in the student\'s '
              'voice","ao":{"AO1":"short comment"}}')
    user = (f"Subject: {subject}\nBoard: {board or 'unknown (assume AQA)'}\nQuestion: {question or '(not given)'}\n"
            f"Marks available: {marks or 'typical for this question'}\n\nStudent answer:\n{text[:12000]}")
    r = _brain_json(system, user)
    r["subject"], r["question"] = subject, question
    return r


@tool("MARK the user's essay / long answer like a GCSE examiner (English, History etc.): mark, grade, strengths, "
      "exact fixes and a model paragraph.",
      {"text": ("string", "The student's answer", True), "question": ("string", "The exam question", False),
       "subject": ("string", "Subject", False), "board": ("string", "Exam board", False)})
def essay_mark(text, question="", subject="English Literature", board=""):
    r = mark_writing(text, question, subject, board)
    from .holo import emit_card
    emit_card("points", f"{subject}: {r.get('mark')}/{r.get('out_of')} · grade {r.get('grade')}",
              items=[f"✓ {s}" for s in r.get("strengths", [])[:3]] + [f"→ {f}" for f in r.get("fixes", [])[:4]])
    return json.dumps(r)[:4000]


def check_working(question="", working="", photo=None):
    if photo:
        from .scholar import _read_photo
        from .vision import ask_image
        working, _, _ = ask_image(_read_photo(photo), "Transcribe this student's maths/science working exactly, line by "
                                                      "line, numbering each line. Include the question if it's visible.")
    system = ("You are a GCSE maths/science tutor. Check the student's working line by line. Find the FIRST line that "
              "goes wrong (if any). Be encouraging and precise. Reply JSON only: "
              '{"correct":bool,"wrong_line":"the exact line or empty","why":"what went wrong",'
              '"fix":"how to do that step","answer":"correct final answer","marks_estimate":"e.g. 3/5 (method marks)"}')
    r = _brain_json(system, f"Question: {question or '(see working)'}\n\nWorking:\n{working[:8000]}")
    r["working"] = working
    return r


@tool("CHECK MATHS/SCIENCE WORKING: finds the exact line where it went wrong and how to fix it.",
      {"working": ("string", "The working (typed)", True), "question": ("string", "The question", False)})
def working_check(working, question=""):
    return json.dumps(check_working(question, working))[:3000]


# ------------------------------------------------------------------ photo → flashcards
def cards_from_photo(photos, deck="", count=12):
    from .scholar import _read_photo
    from .study import add_deck, make_cards
    from .vision import ask_image
    text = []
    for ph in photos[:6]:
        t, _, _ = ask_image(_read_photo(ph), "Transcribe all the text on this page of notes/textbook exactly. Describe "
                                             "diagrams briefly in [brackets].")
        text.append(t)
    notes = "\n\n".join(text)
    topic = deck or _brain_json("Name the topic of these revision notes in 2-5 words. JSON only: {\"topic\":\"...\"}",
                                notes[:3000], tier="fast").get("topic", "My notes")
    cards = make_cards(topic, notes, count)
    total = add_deck(topic, cards)
    return {"deck": topic, "added": len(cards), "total": total, "cards": cards[:5]}


# ------------------------------------------------------------------ wrapped
def money_wrapped(days=7):
    from .money import goals, per_hour
    from .ventures import earnings
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    prev = (dt.date.today() - dt.timedelta(days=days * 2)).isoformat()
    e = earnings()
    now = [x for x in e if x["date"] >= since]
    before = [x for x in e if prev <= x["date"] < since]
    tot, tot_prev = round(sum(x["amount"] for x in now), 2), round(sum(x["amount"] for x in before), 2)
    by = {}
    for x in now:
        by[x["venture"]] = round(by.get(x["venture"], 0) + x["amount"], 2)
    best = max(now, key=lambda x: x["amount"], default=None)
    ph = per_hour()
    return {"days": days, "total": tot, "previous": tot_prev, "change": round(tot - tot_prev, 2),
            "by_venture": sorted(by.items(), key=lambda kv: -kv[1]), "best": best,
            "per_hour": ph[:3], "goals": [{"name": g["name"], "pct": g["pct"], "per_week": g["per_week"]} for g in goals()]}


@tool("MONEY WRAPPED: this week's (or N days') money summary — total vs last week, best earner, £/hour, goals.",
      {"days": ("integer", "Days to look back (default 7)", False)})
def money_wrap(days=7):
    w = money_wrapped(int(days or 7))
    arrow = "▲" if w["change"] >= 0 else "▼"
    lines = [f"£{w['total']:.2f} in the last {w['days']} days ({arrow} £{abs(w['change']):.2f} vs before)"]
    if w["best"]:
        lines.append(f"Best: £{w['best']['amount']:.2f} from {w['best']['venture']} ({w['best'].get('note', '')})")
    for v, rate, hrs in w["per_hour"]:
        lines.append(f"{v}: £{rate}/hour over {hrs}h")
    for g in w["goals"]:
        lines.append(f"Goal {g['name']}: {g['pct']}% · need £{g['per_week']}/week")
    from .holo import emit_card
    emit_card("points", "Money Wrapped", items=lines)
    return "\n".join(lines)


def gaming_wrapped(days=7):
    from .gaming import game_stats
    s = game_stats(days)
    prev = game_stats(days * 2)
    prev_mins = prev["total_mins"] - s["total_mins"]
    top = s["by_game"][0] if s["by_game"] else None
    best_day = max(s["daily"], key=lambda d: d["mins"], default=None)
    return {"hours": round(s["total_mins"] / 60, 1), "prev_hours": round(prev_mins / 60, 1), "sessions": s["sessions"],
            "top": top, "longest": s["longest"], "best_day": best_day, "by_game": s["by_game"][:5]}


@tool("GAMING WRAPPED: hours this week vs last, top game, longest session, best day.",
      {"days": ("integer", "Days (default 7)", False)})
def gaming_wrap(days=7):
    w = gaming_wrapped(int(days or 7))
    lines = [f"{w['hours']}h across {w['sessions']} sessions (last time {w['prev_hours']}h)"]
    if w["top"]:
        lines.append(f"Most played: {w['top'][0]} — {round(w['top'][1] / 60, 1)}h")
    lines.append(f"Longest session: {w['longest']} min")
    if w["best_day"] and w["best_day"]["mins"]:
        lines.append(f"Biggest day: {w['best_day']['day']} ({round(w['best_day']['mins'] / 60, 1)}h)")
    from .holo import emit_card
    emit_card("chart", "Gaming Wrapped", points=[[g[:18], round(m / 60, 1)] for g, m in w["by_game"]])
    return "\n".join(lines)


# ------------------------------------------------------------------ price calculator
KINDS = {"discord bot": (2.5, 6), "website": (4, 12), "automation": (3, 8), "roblox script": (2, 5),
         "minecraft plugin": (2, 6), "video edit": (1, 3), "logo": (1, 3), "app": (8, 25), "other": (2, 6)}


def price_job(kind="other", hours=None, client="small business", rush=False, extras=""):
    from .money import per_hour
    k = next((x for x in KINDS if x in (kind or "").lower()), "other")
    lo_h, hi_h = KINDS[k]
    hrs = float(hours) if hours else (lo_h + hi_h) / 2
    rates = [r for _, r, _ in per_hour() if r]
    base = max(12.0, min(35.0, (sum(rates) / len(rates)) if rates else 15.0))   # a fair student rate
    mult = {"friend": 0.6, "individual": 0.85, "small business": 1.0, "company": 1.4}.get((client or "").lower(), 1.0)
    if rush:
        mult *= 1.3
    price = hrs * base * mult
    return {"kind": k, "hours": round(hrs, 1), "rate": round(base, 2), "client": client,
            "low": int(round(price * 0.85 / 5) * 5) or 5, "price": int(round(price / 5) * 5) or 5,
            "high": int(round(price * 1.25 / 5) * 5) or 10, "deposit": int(round(price * 0.3 / 5) * 5) or 5,
            "note": "Quote the middle price, take the deposit up front, and set a clear number of revisions (2)."}


@tool("PRICE CALCULATOR (CEO): what to charge for a job so the user doesn't undercharge.",
      {"kind": ("string", "discord bot | website | automation | roblox script | minecraft plugin | video edit | logo | app | other", True),
       "hours": ("number", "Estimated hours (optional)", False),
       "client": ("string", "friend | individual | small business | company", False),
       "rush": ("boolean", "Needed fast?", False)})
def price_calc(kind, hours=None, client="small business", rush=False):
    p = price_job(kind, hours, client, rush)
    from .holo import emit_card
    emit_card("points", f"Quote · {p['kind']}", items=[f"Charge £{p['price']} (range £{p['low']}–£{p['high']})",
                                                    f"≈{p['hours']}h at £{p['rate']}/h for a {p['client']}",
                                                    f"Deposit up front: £{p['deposit']}", p["note"]])
    return json.dumps(p)


# ------------------------------------------------------------------ bedtime nudge (PC goes off ~20:30)
class Bedtime:
    def __init__(self, cfg, say, toast, sync):
        self.cfg, self.say, self.toast, self.sync = cfg, say, toast, sync
        self.done_day = ""
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        from .daily import day_cfg
        from .jobs import idle_seconds
        while True:
            time.sleep(45)
            try:
                if not self.cfg.get("bedtime_nudge", True):
                    continue
                d = day_cfg(self.cfg)
                off = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(d.get("pc_off", "20:30")))
                now = dt.datetime.now()
                today = now.strftime("%Y-%m-%d")
                if self.done_day == today or not (off - dt.timedelta(minutes=10) <= now < off):
                    continue
                self.done_day = today
                g = CTX.get("gaming")
                if idle_seconds() > 600:
                    continue                      # not at the PC — nothing to nudge
                title = self.cfg.get("user_title", "sir")
                msg = (f"Ten minutes till the PC usually goes off, {title}. I'll save everything and sync your phone now."
                       if not (g and g.active) else f"Ten minutes till lights out, {title} — good time to finish this match.")
                self.toast(msg)
                self.say(msg)
                self.sync()
            except Exception:
                pass

"""ORION 6 brain upgrades.

- Plan cards: for multi-step jobs ORION shows a live holographic checklist and ticks each step off as it goes.
- Total recall: every conversation is archived on this PC (data/chat_archive.jsonl), so ORION can look back
  weeks or months ("what did I say about my mock exams?") instead of only the last 60 messages.
- Context: ORION knows what day it is in your week (school day? weekend? holiday?) and what's next on your plan.
"""
import datetime as dt
import json
import os
import re
import threading
import time

from .paths import DATA_DIR
from .tools import CTX, tool

ARCHIVE = os.path.join(DATA_DIR, "chat_archive.jsonl")
MAX_LINES = 40000
_lock = threading.Lock()
STOP = set("a an the and or but is are was were be to of in on at for with my me i you it that this what did do does "
           "how when where who about from have has had can could would should will just like so".split())


def _emit(kind, **d):
    e = CTX.get("emit")
    if e:
        e(kind, **d)


# ------------------------------------------------------------------ missions
MISSION = {"title": "", "steps": [], "done": [], "note": "", "t": 0}


@tool("PLAN CARD: for any job you do right now with 3+ steps, call this FIRST with a short title and the steps (3-8, a few words each). "
      "A live checklist appears beside you. Then call plan_tick after finishing each step. (For long background jobs use mission_start instead.)",
      {"title": ("string", "Mission name, e.g. 'Revision plan for mocks'", True),
       "steps": ("array", "The steps, in order", True)})
def plan_show(title, steps):
    steps = [str(s)[:80] for s in (steps or [])][:8]
    MISSION.update(title=str(title)[:60], steps=steps, done=[False] * len(steps), note="", t=time.time())
    _emit("mission", **MISSION)
    return f"Plan card shown with {len(steps)} steps. Tick each one with plan_tick as you finish it."


@tool("Tick off a plan-card step (1-based number) when it's done; optional short note of the result.",
      {"step": ("integer", "Step number that is now complete", True), "note": ("string", "Short result", False)})
def plan_tick(step, note=""):
    i = int(step) - 1
    if not MISSION["steps"]:
        return "No plan card showing."
    if 0 <= i < len(MISSION["steps"]):
        MISSION["done"][i] = True
    MISSION["note"] = str(note)[:120]
    _emit("mission", **MISSION)
    left = MISSION["done"].count(False)
    return "All steps done." if not left else f"{left} step(s) left."


# ------------------------------------------------------------------ total recall
def archive(role, content, device=""):
    if not content or content.startswith("[") and role == "user":
        return
    line = json.dumps({"t": time.time(), "r": role, "c": content[:4000], "d": device}, ensure_ascii=False)
    with _lock:
        try:
            with open(ARCHIVE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if os.path.getsize(ARCHIVE) > 25_000_000:            # keep it tidy: drop the oldest half
                with open(ARCHIVE, encoding="utf-8") as f:
                    rows = f.readlines()
                with open(ARCHIVE, "w", encoding="utf-8") as f:
                    f.writelines(rows[-MAX_LINES // 2:])
        except Exception:
            pass


def _words(s):
    return [w for w in re.findall(r"[a-z0-9']+", s.lower()) if w not in STOP and len(w) > 2]


def search(query, limit=8, days=None):
    q = _words(query)
    if not q or not os.path.exists(ARCHIVE):
        return []
    since = time.time() - days * 86400 if days else 0
    rows = []
    with _lock:
        with open(ARCHIVE, encoding="utf-8") as f:
            for ln in f:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
    scored = []
    for i, r in enumerate(rows):
        if r["t"] < since:
            continue
        ws = _words(r["c"])
        if not ws:
            continue
        hit = sum(1 for w in q if any(x.startswith(w[:5]) for x in ws))
        if hit:
            scored.append((hit / len(q) + (0.15 if r["r"] == "user" else 0) + r["t"] / 1e11, i))
    scored.sort(reverse=True)
    out, used = [], set()
    for _, i in scored:
        if i in used:
            continue
        used.update({i - 1, i, i + 1})
        ctx = [rows[j] for j in (i - 1, i, i + 1) if 0 <= j < len(rows)]
        out.append({"when": dt.datetime.fromtimestamp(rows[i]["t"]).strftime("%a %d %b %Y %H:%M"),
                    "turns": [{"who": "you" if c["r"] == "user" else "ORION", "text": c["c"][:400]} for c in ctx]})
        if len(out) >= limit:
            break
    return out


@tool("RECALL: search every past conversation with the user (weeks/months back, all devices) for what was said about "
      "something. Use for 'what did I say about…', 'remember when…', 'what was that thing…', 'when did I…'.",
      {"query": ("string", "What to look for", True), "days": ("integer", "Only the last N days (optional)", False)})
def recall(query, days=0):
    hits = search(query, 6, days or None)
    if not hits:
        return "Nothing in the archive about that."
    return "\n\n".join(f"[{h['when']}]\n" + "\n".join(f"{t['who']}: {t['text']}" for t in h["turns"]) for h in hits)


def stats():
    if not os.path.exists(ARCHIVE):
        return {"turns": 0, "since": None}
    n, first = 0, None
    with open(ARCHIVE, encoding="utf-8") as f:
        for ln in f:
            n += 1
            if first is None:
                try:
                    first = json.loads(ln)["t"]
                except Exception:
                    pass
    return {"turns": n, "since": dt.datetime.fromtimestamp(first).strftime("%d %b %Y") if first else None}


# ------------------------------------------------------------------ situational context for the system prompt
def situation():
    now = dt.datetime.now()
    bits = []
    wd = now.weekday()
    if wd >= 5:
        bits.append("It's the weekend.")
    elif 8 <= now.hour < 15 or (now.hour == 15 and now.minute < 10):
        bits.append("It's a school day and he's probably at school right now (finishes 15:10).")
    elif now.hour >= 15:
        bits.append("It's a school day evening.")
    if now.hour >= 23 or now.hour < 5:
        bits.append("It's late — keep it short and nudge towards sleep if it fits.")
    try:
        from .schedule import upcoming
        up = upcoming(1)[:2]
        if up:
            bits.append("Next on his plan: " + "; ".join(f"{o['title']} at {o['at']:%H:%M}" for o in up) + ".")
    except Exception:
        pass
    try:
        from .life import homework
        hw = [h for h in homework() if not h.get("done") and h["days"] <= 2]
        if hw:
            bits.append("Homework due soon: " + ", ".join(f"{h['subject']} ({h['days']}d)" for h in hw[:3]) + ".")
    except Exception:
        pass
    return " ".join(bits)


# ------------------------------------------------------------------ instant acknowledgements (feels much faster)
QUIET_TOOLS = {"get_time", "remember", "show_card", "close_popups", "plan_tick", "set_theme", "ambient", "habit",
               "open_app", "open_website", "note_add", "media", "volume", "weather"}
ACKS = {
    "web_search": ["Let me look that up, {t}.", "Checking now, {t}.", "One moment, {t}, searching."],
    "fetch_page": ["Reading up on it, {t}."],
    "browser_open": ["Opening it up now, {t}."],
    "plan_show": ["Right away, {t}.", "On it, {t}."],
    "project_create": ["Starting on it now, {t}. This may take a moment.", "Building it now, {t}."],
    "code_write": ["Writing it now, {t}."],
    "local_intel": ["Scanning the area, {t}."],
    "threat_scan_tool": ["Running a full scan, {t}."],
    "recall": ["Let me think back, {t}.", "Searching my memory, {t}."],
    "skill_use": ["On it, {t}."],
    "queue_job": ["I'll get that going, {t}."],
    "mission_start": ["Mission accepted, {t}."],
}
DEFAULT_ACKS = ["One moment, {t}.", "On it, {t}.", "Right away, {t}."]


def ack_for(tool_name, title="sir"):
    if tool_name in QUIET_TOOLS:
        return None
    import random
    return random.choice(ACKS.get(tool_name, DEFAULT_ACKS)).format(t=title)


def all_acks(title="sir"):
    return sorted({p.format(t=title) for v in list(ACKS.values()) + [DEFAULT_ACKS] for p in v})

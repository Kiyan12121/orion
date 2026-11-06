"""Daily learning: ORION notices what you ask for a lot and turns it into instant shortcuts.

- Every request is logged (text + time) to data/usage.json.
- Shortcuts ("when I say gaming setup, open Discord and Spotify and turn on gaming mode") live in
  data/shortcuts.json and are expanded before the AI even sees the message.
- Each night ORION looks for things you asked 3+ times recently and suggests making them shortcuts.
"""
import json
import os
import re
import threading
import time
from collections import Counter

from .paths import DATA_DIR
from .tools import CTX, tool

USAGE = os.path.join(DATA_DIR, "requests_log.json")      # was usage.json — clashed with the provider token counter


def _usage():
    u = _load(USAGE, None)
    if u is None:                                            # one-time migration from the old shared file
        old = _load(os.path.join(DATA_DIR, "usage.json"), [])
        u = old if isinstance(old, list) else []
    return [x for x in u if isinstance(x, dict) and "t" in x] if isinstance(u, list) else []
SHORTS = os.path.join(DATA_DIR, "shortcuts.json")
_lock = threading.Lock()


def _load(p, d):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _save(p, v):
    from .safeio import write_json
    write_json(p, v, indent=1)


def norm(t):
    t = re.sub(r"^(hey |ok |okay )?(orion|jarvis)[, ]*", "", (t or "").lower().strip())
    t = re.sub(r"\b(please|pls|plz|can you|could you|would you|for me|now|right now)\b", " ", t)
    return re.sub(r"[^\w' ]+", " ", re.sub(r"\s+", " ", t)).strip()


def log_request(text, tier=None):
    if not text or text.startswith("["):
        return
    with _lock:
        u = _usage()
        u.append({"t": time.time(), "text": text[:300], "tier": tier,
                  "hour": time.localtime().tm_hour, "wd": time.localtime().tm_wday})
        _save(USAGE, u[-3000:])


# ------------------------------------------------------------------ shortcuts
def shortcuts():
    return _load(SHORTS, [])


def add_shortcut(phrase, does):
    phrase, does = norm(phrase), (does or "").strip()
    if not phrase or not does:
        return False
    with _lock:
        s = [x for x in shortcuts() if x["phrase"] != phrase]
        s.append({"phrase": phrase, "does": does, "uses": 0, "made": time.strftime("%Y-%m-%d")})
        _save(SHORTS, s)
    return True


def remove_shortcut(phrase):
    phrase = norm(phrase)
    with _lock:
        s = shortcuts()
        keep = [x for x in s if x["phrase"] != phrase]
        _save(SHORTS, keep)
        return len(s) != len(keep)


def expand(text):
    """If the message IS a shortcut phrase, return what it stands for."""
    n = norm(text)
    for x in shortcuts():
        if n == x["phrase"]:
            with _lock:
                s = shortcuts()
                for y in s:
                    if y["phrase"] == x["phrase"]:
                        y["uses"] = y.get("uses", 0) + 1
                _save(SHORTS, s)
            return x["does"]
    return None


# ------------------------------------------------------------------ noticing patterns
def suggestions(days=14, min_count=3):
    since = time.time() - days * 86400
    have = {x["phrase"] for x in shortcuts()}
    c = Counter(norm(x["text"]) for x in _usage() if x["t"] > since)
    out = []
    for phrase, n in c.most_common(40):
        if n < min_count or not phrase or phrase in have or len(phrase) < 6 or len(phrase) > 120:
            continue
        out.append({"phrase": phrase, "count": n})
    return out[:8]


def habits():
    """When you usually do things — used for the dashboard and smarter suggestions."""
    u = _usage()
    if not u:
        return {"total": 0}
    hours = Counter(x["hour"] for x in u)
    week = [x for x in u if x["t"] > time.time() - 7 * 86400]
    tiers = Counter(x.get("tier") or "?" for x in week)
    return {"total": len(u), "this_week": len(week), "busiest_hour": hours.most_common(1)[0][0],
            "by_hour": [hours.get(h, 0) for h in range(24)], "tiers": dict(tiers)}


def nightly_digest():
    s = suggestions()
    if not s:
        return None
    top = s[0]
    return (f"I noticed you've asked \"{top['phrase']}\" {top['count']} times recently. "
            "Open the Brain page to turn it into an instant shortcut.")


# ------------------------------------------------------------------ AI tools
@tool("Create a SHORTCUT: when the user says a phrase, ORION does something (one or more steps). Use for "
      "'when I say X, do Y', 'make that a shortcut', 'every time I say…'.",
      {"phrase": ("string", "What the user will say", True),
       "does": ("string", "Full instructions for what ORION should do", True)})
def shortcut_add(phrase, does):
    return f"Shortcut saved: \"{norm(phrase)}\"." if add_shortcut(phrase, does) else "ERROR: need a phrase and an action."


@tool("List the user's shortcuts.")
def shortcut_list():
    s = shortcuts()
    return "\n".join(f"\"{x['phrase']}\" → {x['does']}" for x in s) or "No shortcuts yet."


@tool("Delete a shortcut.", {"phrase": ("string", "The shortcut phrase", True)})
def shortcut_remove(phrase):
    return "Shortcut removed." if remove_shortcut(phrase) else "No shortcut with that phrase."


@tool("Start a MISSION: a big multi-step job ORION does on its own in the background (research, build, write, "
      "make videos…) and saves everything to a mission folder with a report. Use for 'research X then make Y', "
      "'go and…', 'mission:'.",
      {"goal": ("string", "The full goal, with every step the user mentioned", True),
       "heavy": ("boolean", "Wait until the PC is idle", False)})
def mission_start(goal, heavy=False):
    q = CTX.get("jobs")
    if not q:
        return "Job queue isn't running."
    slug = re.sub(r"[^\w]+", "-", goal.lower())[:40].strip("-") or "mission"
    folder = os.path.join(os.path.expanduser("~"), "Documents", "ORION Missions", time.strftime("%Y-%m-%d ") + slug)
    text = (f"[MISSION] {goal}\n\nSave every file you make into this folder (create it): {folder}\n"
            "Work through it step by step with update_plan. When finished, write REPORT.md in that folder "
            "summarising what you did, what's in the folder and anything you couldn't do.")
    j = q.add(text, source="mission", title="🚀 " + goal[:70], autopilot=True, heavy=bool(heavy))
    return f"Mission launched (ticket {j['id']}). Everything will be saved to Documents › ORION Missions. I'll ring you when it's done."

"""Study mode for GCSEs: flashcards with spaced repetition, voice quizzes, focus sessions that block
games and distracting sites, revision stats and exam countdowns. Saved to data/study.json."""
import json
import os
import random
import re
import threading
import time

from .paths import DATA_DIR
from .tools import CTX, tool

PATH = os.path.join(DATA_DIR, "study.json")
_lock = threading.RLock()
BOX_DAYS = [0, 1, 3, 7, 14, 30]           # Leitner boxes: how long until a card comes back
DEFAULT_BLOCK = ["RobloxPlayerBeta.exe", "RobloxPlayer.exe", "steam.exe", "EpicGamesLauncher.exe",
                 "FortniteClient-Win64-Shipping.exe", "Minecraft.Windows.exe", "javaw.exe", "VALORANT-Win64-Shipping.exe",
                 "cs2.exe", "RocketLeague.exe", "GTA5.exe", "FiveM.exe"]
DISTRACT = re.compile(r"youtube|tiktok|netflix|twitch|instagram|snapchat|reddit|disney\+|prime video|x\.com|twitter",
                      re.I)


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("decks", {})
    d.setdefault("log", {})        # "YYYY-MM-DD": minutes focused
    d.setdefault("exams", [])
    return d


def _save(d):
    with _lock:
        from .safeio import write_json
        write_json(PATH, d, indent=1)


def _deck_name(name, d):
    if name in d["decks"]:
        return name
    low = (name or "").lower().strip()
    for k in d["decks"]:
        if low and (low in k.lower() or k.lower() in low):
            return k
    return None


# ------------------------------------------------------------------ flashcards
def make_cards(topic, source="", count=12):
    brain = CTX.get("brain")
    if not brain:
        raise RuntimeError("brain not ready")
    count = max(4, min(int(count or 12), 30))
    system = ("You make GCSE-level revision flashcards for a UK Year 11 student. Short, exam-focused questions with "
              "precise answers (one line, max ~25 words). Cover key facts, definitions, formulas and common exam "
              f'traps. Reply with JSON only: {{"cards":[{{"q":"...","a":"..."}}]}} with exactly {count} cards.')
    user = f"Topic: {topic}\n" + (f"\nUse these notes:\n{source[:9000]}" if source else "")
    out = brain.quick(system, user, tier="smart", max_steps=1)
    m = re.search(r"\{.*\}", out or "", re.S)
    cards = json.loads(m.group(0)).get("cards", []) if m else []
    return [{"q": str(c["q"])[:300], "a": str(c["a"])[:400]} for c in cards if c.get("q") and c.get("a")]


def add_deck(name, cards):
    with _lock:
        d = _load()
        deck = d["decks"].setdefault(name, [])
        have = {c["q"].lower() for c in deck}
        for c in cards:
            if c["q"].lower() not in have:
                deck.append({"q": c["q"], "a": c["a"], "box": 0, "due": 0, "right": 0, "wrong": 0})
        _save(d)
        return len(deck)


def due_cards(name=None, limit=20):
    d = _load()
    now = time.time()
    names = [name] if name else list(d["decks"])
    out = []
    for n in names:
        for i, c in enumerate(d["decks"].get(n, [])):
            if c.get("due", 0) <= now:
                out.append({"deck": n, "i": i, **c})
    random.shuffle(out)
    return out[:limit]


def mark(deck, i, correct):
    with _lock:
        d = _load()
        c = d["decks"][deck][int(i)]
        c["box"] = min(c.get("box", 0) + 1, len(BOX_DAYS) - 1) if correct else 0
        c["due"] = time.time() + BOX_DAYS[c["box"]] * 86400 + (0 if c["box"] else 600)
        c["right" if correct else "wrong"] = c.get("right" if correct else "wrong", 0) + 1
        _save(d)


def overview():
    d = _load()
    now = time.time()
    decks = []
    for n, cards in d["decks"].items():
        mastered = sum(1 for c in cards if c.get("box", 0) >= 4)
        decks.append({"name": n, "cards": len(cards), "due": sum(1 for c in cards if c.get("due", 0) <= now),
                      "mastered": mastered})
    today = time.strftime("%Y-%m-%d")
    streak, day = 0, time.time()
    while d["log"].get(time.strftime("%Y-%m-%d", time.localtime(day)), 0) > 0:
        streak += 1
        day -= 86400
    week = [d["log"].get(time.strftime("%Y-%m-%d", time.localtime(time.time() - k * 86400)), 0) for k in range(6, -1, -1)]
    exams = []
    for e in sorted(d["exams"], key=lambda e: e["date"]):
        try:
            days = int((time.mktime(time.strptime(e["date"], "%Y-%m-%d")) - time.time()) // 86400) + 1
        except Exception:
            continue
        if days >= 0:
            exams.append({**e, "days": days})
    return {"decks": decks, "today": d["log"].get(today, 0), "streak": streak, "week": week, "exams": exams,
            "focus": FOCUS.status()}


# ------------------------------------------------------------------ focus sessions
class Focus:
    """Pomodoro-style focus: blocks games, nudges you off distracting sites, logs minutes."""

    def __init__(self):
        self.until = 0
        self.subject = ""
        self.phase = "off"         # off | work | break
        self.started = 0
        self.cycles = 0
        self.work_min, self.break_min = 25, 5
        self._stop = threading.Event()
        self._last_nudge = 0

    def status(self):
        left = max(0, int(self.until - time.time())) if self.phase != "off" else 0
        return {"phase": self.phase, "subject": self.subject, "left": left, "cycles": self.cycles,
                "work": self.work_min, "brk": self.break_min}

    def start(self, minutes=25, subject="", break_min=5, total=None):
        self.stop(log=False)
        self._stop = threading.Event()
        self.work_min, self.break_min = max(5, int(minutes)), max(1, int(break_min))
        self.subject, self.cycles = subject, 0
        self.total_until = time.time() + int(total) * 60 if total else None
        self._phase("work")
        threading.Thread(target=self._loop, args=(self._stop,), daemon=True).start()

    def _phase(self, ph):
        self.phase = ph
        self.started = time.time()
        self.until = time.time() + (self.work_min if ph == "work" else self.break_min) * 60
        emit = CTX.get("emit")
        if emit:
            emit("focus", **self.status())

    def stop(self, log=True):
        if self.phase == "work" and log:
            self._log((time.time() - self.started) / 60)
        self._stop.set()
        self.phase = "off"
        emit = CTX.get("emit")
        if emit:
            emit("focus", **self.status())

    def _log(self, minutes):
        if minutes < 1:
            return
        with _lock:
            d = _load()
            k = time.strftime("%Y-%m-%d")
            d["log"][k] = round(d["log"].get(k, 0) + minutes)
            _save(d)

    def _say(self, text):
        n = CTX.get("notify")
        if n:
            n(text, True)

    def _loop(self, stop):
        title = CTX.get("config", {}).get("user_title", "sir")
        while not stop.wait(5):
            if self.phase == "work":
                self._enforce(title)
            if time.time() >= self.until:
                if self.phase == "work":
                    self._log(self.work_min)
                    self.cycles += 1
                    if self.total_until and time.time() >= self.total_until:
                        self.phase = "off"
                        self._say(f"Session complete, {title}. {self.cycles} rounds of {self.subject or 'revision'} — well done.")
                        CTX.get("emit") and CTX["emit"]("focus", **self.status())
                        return
                    self._phase("break")
                    self._say(f"Round {self.cycles} done, {title}. Take {self.break_min} minutes.")
                else:
                    self._phase("work")
                    self._say(f"Break's over, {title}. Back to {self.subject or 'it'}.")

    def _enforce(self, title):
        try:
            import psutil
            block = {b.lower() for b in CTX.get("config", {}).get("study", {}).get("block", DEFAULT_BLOCK)}
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() in block:
                    p.kill()
                    self._say(f"Not now, {title} — that's blocked until your focus round ends.")
        except Exception:
            pass
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = u.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(512)
            u.GetWindowTextW(hwnd, buf, 512)
            if DISTRACT.search(buf.value) and time.time() - self._last_nudge > 60:
                self._last_nudge = time.time()
                u.ShowWindow(hwnd, 6)          # minimise it
                self._say(f"Eyes on the work, {title}. That can wait for the break.")
        except Exception:
            pass


FOCUS = Focus()


# ------------------------------------------------------------------ AI tools
@tool("Make revision FLASHCARDS on a topic (optionally from notes in a file) and save them as a deck.",
      {"topic": ("string", "e.g. 'GCSE Biology cell division' or 'Macbeth themes'", True),
       "file": ("string", "Optional path to notes (.txt/.md) to make cards from", False),
       "count": ("integer", "How many cards (default 12)", False)})
def study_make_flashcards(topic, file="", count=12):
    src = ""
    if file:
        p = os.path.expandvars(os.path.expanduser(file.strip('"')))
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                src = f.read()
    cards = make_cards(topic, src, count)
    if not cards:
        return "ERROR: couldn't make cards — try again."
    total = add_deck(topic.strip()[:60], cards)
    return f"Made {len(cards)} flashcards in the '{topic.strip()[:60]}' deck ({total} total). Open Study to revise, or say 'quiz me'."


@tool("QUIZ the user out loud: get the next flashcard due. Ask them the question (don't reveal the answer), wait "
      "for their reply, judge it fairly, then call study_mark.",
      {"deck": ("string", "Deck name (blank = any deck)", False)})
def study_quiz(deck=""):
    d = _load()
    name = _deck_name(deck, d) if deck else None
    cards = due_cards(name, 1)
    if not cards:
        return "No cards are due — they're all learned for now." if d["decks"] else "No flashcards yet — make some first."
    c = cards[0]
    return (f"DECK: {c['deck']} | CARD: {c['i']}\nASK: {c['q']}\n(EXPECTED ANSWER — don't say it until they've "
            f"answered: {c['a']})")


@tool("Record whether the user got a quiz card right.",
      {"deck": ("string", "Deck name", True), "card": ("integer", "Card number from study_quiz", True),
       "correct": ("boolean", "Did they get it right?", True)})
def study_mark(deck, card, correct):
    d = _load()
    name = _deck_name(deck, d)
    if not name:
        return "ERROR: no such deck."
    mark(name, card, bool(correct))
    return "Marked. Ask if they want another (call study_quiz again)."


@tool("Start a FOCUS session (revision/homework): blocks games, nudges off YouTube/TikTok, Pomodoro breaks.",
      {"minutes": ("integer", "Work minutes per round (default 25)", False),
       "subject": ("string", "What they're studying", False),
       "total_minutes": ("integer", "Whole session length, e.g. 120 (blank = until stopped)", False)})
def focus_start(minutes=25, subject="", total_minutes=None):
    FOCUS.start(minutes or 25, subject or "", 5, total_minutes)
    return f"Focus on: {minutes or 25}-minute rounds with 5-minute breaks. Games are blocked until it ends."


@tool("Stop the focus session.")
def focus_stop():
    FOCUS.stop()
    return "Focus session ended."


@tool("Add an EXAM date so ORION counts down and plans revision.",
      {"subject": ("string", "e.g. 'Maths Paper 1'", True), "date": ("string", "YYYY-MM-DD", True)})
def exam_add(subject, date):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date.strip()):
        return "ERROR: date must be YYYY-MM-DD."
    with _lock:
        d = _load()
        d["exams"] = [e for e in d["exams"] if e["subject"].lower() != subject.lower()] + [{"subject": subject, "date": date.strip()}]
        _save(d)
    return f"Exam added: {subject} on {date}."


@tool("Revision stats: minutes studied, streak, decks, exam countdowns.")
def study_stats():
    o = overview()
    lines = [f"Today: {o['today']} min · streak {o['streak']} day(s) · this week {sum(o['week'])} min"]
    lines += [f"Deck {x['name']}: {x['cards']} cards, {x['due']} due, {x['mastered']} mastered" for x in o["decks"]]
    lines += [f"Exam {e['subject']}: {e['days']} day(s) ({e['date']})" for e in o["exams"][:6]]
    return "\n".join(lines)

"""ORION's own schedule: events, repeats, reminders, availability, busy (do-not-disturb) blocks
and a daily briefing. Saved in data/schedule.json (synced across devices in a later update)."""
import datetime as dt
import json
import os
import threading
import time
import uuid

from .paths import DATA_DIR
from .tools import CTX, tool

PATH = os.path.join(DATA_DIR, "schedule.json")
_lock = threading.Lock()
FMT = "%Y-%m-%d %H:%M"


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": [], "fired": [], "briefed": ""}


def _save(d):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


def _parse(s):
    s = str(s).strip().replace("T", " ")
    for fmt, n in ((FMT, 16), ("%Y-%m-%d", 10)):
        try:
            return dt.datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    raise ValueError(f"Couldn't read the time '{s}'. Use YYYY-MM-DD HH:MM.")


def occurrences(start, end, events=None):
    """All event occurrences between two datetimes, sorted."""
    events = _load()["events"] if events is None else events
    out = []
    for e in events:
        first = _parse(e["start"])
        dur = dt.timedelta(minutes=int(e.get("duration", 60)))
        rep = e.get("repeat", "none")
        if rep == "none":
            cands = [first]
        else:
            cands = []
            day = max(first.date(), (start - dur).date())
            while day <= end.date():
                t = dt.datetime.combine(day, first.time())
                ok = (rep == "daily" or (rep == "weekdays" and day.weekday() < 5)
                      or (rep == "weekly" and day.weekday() == first.weekday()))
                if ok and t >= first:
                    cands.append(t)
                day += dt.timedelta(days=1)
        for t in cands:
            if t + dur > start and t < end:
                out.append({**e, "at": t, "until": t + dur})
    return sorted(out, key=lambda o: o["at"])


def _fmt_occ(o, today=None):
    today = today or dt.date.today()
    d = o["at"].date()
    day = "today" if d == today else "tomorrow" if d == today + dt.timedelta(days=1) else o["at"].strftime("%a %d %b")
    tags = []
    if o.get("with"):
        tags.append(f"with {o['with']}")
    if o.get("busy"):
        tags.append("busy")
    if o.get("repeat", "none") != "none":
        tags.append(o["repeat"])
    return (f"{day} {o['at'].strftime('%H:%M')}-{o['until'].strftime('%H:%M')} {o['title']}"
            + (f" ({', '.join(tags)})" if tags else "") + f" [id {o['id']}]")


def add_event(title, start, duration=60, repeat="none", remind=10, busy=False, with_who="", notes=""):
    t = _parse(start)
    if repeat not in ("none", "daily", "weekdays", "weekly"):
        repeat = "none"
    e = {"id": uuid.uuid4().hex[:6], "title": title.strip()[:80], "start": t.strftime(FMT),
         "duration": int(duration or 60), "repeat": repeat, "remind": int(remind if remind is not None else 10),
         "busy": bool(busy), "with": (with_who or "").strip()[:40], "notes": (notes or "")[:200]}
    with _lock:
        d = _load()
        d["events"].append(e)
        _save(d)
    CTX.get("emit", lambda *a, **k: None)("schedule_changed")
    return e


def remove_event(key):
    key = str(key).lower().strip()
    with _lock:
        d = _load()
        keep = [e for e in d["events"] if e["id"] != key and key not in e["title"].lower()]
        gone = [e["id"] for e in d["events"] if e not in keep]
        n = len(gone)
        d["events"] = keep
        d["removed"] = (d.get("removed", []) + gone)[-500:]      # so sync doesn't bring them back
        _save(d)
    CTX.get("emit", lambda *a, **k: None)("schedule_changed")
    return n


def busy_now():
    now = dt.datetime.now()
    for o in occurrences(now, now + dt.timedelta(seconds=1)):
        if o.get("busy"):
            return o
    return None


def upcoming(days=7):
    now = dt.datetime.now()
    return occurrences(now, now + dt.timedelta(days=days))


def free_slots(day, start_hour=8, end_hour=23):
    d0 = dt.datetime.combine(day, dt.time(int(start_hour)))
    d1 = dt.datetime.combine(day, dt.time(min(int(end_hour), 23), 59))
    now = dt.datetime.now()
    if d0 < now < d1:
        d0 = now.replace(second=0, microsecond=0)
    slots, cur = [], d0
    for o in occurrences(d0, d1):
        if o["at"] > cur + dt.timedelta(minutes=29):
            slots.append((cur, o["at"]))
        cur = max(cur, o["until"])
    if d1 > cur + dt.timedelta(minutes=29):
        slots.append((cur, d1))
    return slots


def briefing_text(title="sir"):
    today = dt.date.today()
    occ = [o for o in upcoming(1) if o["at"].date() == today]
    hr = dt.datetime.now().hour
    greet = "Good morning" if hr < 12 else "Good afternoon" if hr < 18 else "Good evening"
    if not occ:
        return f"{greet}, {title}. Your schedule is clear today."
    items = ", ".join(f"{o['title']} at {o['at'].strftime('%H:%M')}" + (f" with {o['with']}" if o.get("with") else "")
                      for o in occ[:6])
    return f"{greet}, {title}. Today: {items}."


# ------------------------------------------------------------------ AI tools
@tool("Add an event/booking/reminder to ORION's schedule. Work out the exact date from 'today' in the system "
      "prompt. Mark busy=true for things like revision, school or work (ORION goes into do-not-disturb).",
      {"title": ("string", "What it is, e.g. 'Gaming with Sam'", True),
       "start": ("string", "Start as 'YYYY-MM-DD HH:MM' (24h)", True),
       "duration_minutes": ("integer", "Length in minutes (default 60)", False),
       "repeat": ("string", "none, daily, weekdays or weekly", False),
       "remind_minutes": ("integer", "Remind this many minutes before (default 10, 0 = at start)", False),
       "busy": ("boolean", "True = user is busy / do-not-disturb during it", False),
       "with_who": ("string", "Who it's with, if anyone", False)})
def schedule_add(title, start, duration_minutes=60, repeat="none", remind_minutes=10, busy=False, with_who=""):
    clash = occurrences(_parse(start), _parse(start) + dt.timedelta(minutes=int(duration_minutes or 60)))
    e = add_event(title, start, duration_minutes, repeat, remind_minutes, busy, with_who)
    msg = f"Booked: {e['title']} at {e['start']}" + (f" ({repeat})" if repeat and repeat != "none" else "")
    if clash:
        msg += f". Note: it overlaps with {', '.join(c['title'] for c in clash[:3])}."
    return msg


@tool("List upcoming schedule events.", {"days": ("integer", "How many days ahead (default 7)", False)})
def schedule_list(days=7):
    occ = upcoming(int(days or 7))
    return "\n".join(_fmt_occ(o) for o in occ[:40]) or "Nothing scheduled."


@tool("Remove a schedule event by its id or part of its title.", {"event": ("string", "Event id or title", True)})
def schedule_remove(event):
    n = remove_event(event)
    return f"Removed {n} event(s)." if n else "No matching event."


@tool("Check when the user is free on a day (returns free time slots).",
      {"date": ("string", "YYYY-MM-DD", True),
       "from_hour": ("integer", "Earliest hour (default 8)", False), "to_hour": ("integer", "Latest hour (default 23)", False)})
def check_availability(date, from_hour=8, to_hour=23):
    day = _parse(date).date()
    slots = free_slots(day, from_hour or 8, to_hour or 23)
    if not slots:
        return f"Fully booked on {day:%a %d %b}."
    return f"Free on {day:%a %d %b}: " + ", ".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in slots)


# ------------------------------------------------------------------ background reminders + briefing
class Scheduler:
    def __init__(self, cfg, notify, is_quiet=lambda: False):
        self.cfg = cfg
        self.notify = notify          # notify(text, important)
        self.is_quiet = is_quiet
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(8)
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(20)

    def tick(self):
        now = dt.datetime.now()
        with _lock:
            d = _load()
            fired = set(d.get("fired", []))
            changed = False
            for o in occurrences(now - dt.timedelta(minutes=2), now + dt.timedelta(hours=3), d["events"]):
                key = f"{o['id']}@{o['at']:%Y%m%d%H%M}"
                if key in fired:
                    continue
                remind_at = o["at"] - dt.timedelta(minutes=int(o.get("remind", 10)))
                if remind_at <= now <= o["at"] + dt.timedelta(minutes=2):
                    mins = int((o["at"] - now).total_seconds() // 60)
                    when = "now" if mins <= 0 else f"in {mins} minute{'s' if mins != 1 else ''}"
                    who = f" with {o['with']}" if o.get("with") else ""
                    self.notify(f"Reminder, {self.cfg.get('user_title', 'sir')}: {o['title']}{who} {when}.", True)
                    fired.add(key)
                    if str(o.get("notes", "")).startswith("PARTY:") and CTX.get("party_reminder"):
                        threading.Thread(target=CTX["party_reminder"], args=(o, when), daemon=True).start()
                    changed = True
            bt = self.cfg.get("briefing_time", "07:30")
            today = now.strftime("%Y-%m-%d")
            if self.cfg.get("daily_briefing", True) and d.get("briefed") != today and now.strftime("%H:%M") >= bt:
                d["briefed"] = today
                changed = True
                self.notify(briefing_text(self.cfg.get("user_title", "sir")), False)
            if changed:
                d["fired"] = sorted(fired)[-300:]
                _save(d)

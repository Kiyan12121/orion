"""Kiyan's day: school times, the evening recap, tomorrow's plan, and the 'morning pack' the phone uses to run
the wake-up routine while the PC is off."""
import datetime as dt
import json
import os
import time

from .paths import DATA_DIR
from .tools import CTX, tool

PACK = os.path.join(DATA_DIR, "morning_pack.json")
DEFAULT_DAY = {"wake": "08:00", "school_start": "08:40", "school_end": "15:10", "pc_off": "20:30",
               "school_days": [0, 1, 2, 3, 4], "holiday": False}


def day_cfg(cfg=None):
    cfg = cfg or CTX.get("config", {})
    d = cfg.setdefault("day", {})
    for k, v in DEFAULT_DAY.items():
        d.setdefault(k, v)
    return d


def is_school_day(date=None, cfg=None):
    d = day_cfg(cfg)
    date = date or dt.date.today()
    return not d.get("holiday") and date.weekday() in d.get("school_days", [0, 1, 2, 3, 4])


def at_school_now(cfg=None):
    d = day_cfg(cfg)
    if not is_school_day(cfg=cfg):
        return False
    now = time.strftime("%H:%M")
    return d["school_start"] <= now < d["school_end"]


def recap_today():
    """A few lines about today: revision, money, screen time, gaming."""
    out = []
    try:
        from .study import overview
        o = overview()
        if o["today"]:
            out.append(f"• 📚 Revised {o['today']} min today (streak {o['streak']} day(s)).")
    except Exception:
        pass
    try:
        from .ventures import earnings
        today = time.strftime("%Y-%m-%d")
        made = sum(x["amount"] for x in earnings() if x["date"] == today)
        if made:
            out.append(f"• 💷 Earned £{made:.2f} today.")
    except Exception:
        pass
    try:
        from .life import screen_day
        rows = screen_day()
        if rows:
            tot = sum(m for _, m in rows)
            out.append(f"• 🖥 Screen time {tot // 60}h {tot % 60}m — mostly {rows[0][0]}.")
    except Exception:
        pass
    try:
        from .gaming import game_stats
        g = game_stats(1)
        if g["total_mins"]:
            out.append(f"• 🎮 Gamed {g['total_mins']} min today.")
    except Exception:
        pass
    return out


def tomorrow_plan():
    out = []
    tom = dt.date.today() + dt.timedelta(days=1)
    try:
        from .schedule import occurrences
        start = dt.datetime.combine(tom, dt.time(0, 0))
        ev = occurrences(start, start + dt.timedelta(days=1))
        if ev:
            out.append("• 📅 Tomorrow: " + "; ".join(f"{o['at']:%H:%M} {o['title']}" for o in ev[:5]))
    except Exception:
        pass
    try:
        from .life import homework
        due = [h for h in homework() if not h.get("done") and h["days"] <= 1]
        if due:
            out.append("• 📝 Due by tomorrow: " + "; ".join(f"{h['subject']} — {h['task']}" for h in due[:5]))
    except Exception:
        pass
    try:
        from .scholar import timetable_for
        lessons = timetable_for(tom)
        if lessons:
            out.append("• 🏫 Lessons: " + ", ".join(lessons[:7]))
    except Exception:
        pass
    if is_school_day(tom):
        d = day_cfg()
        out.append(f"• ⏰ School day tomorrow — up at {d['wake']}, at the bike shed by {d['school_start']}.")
    return out


def morning_pack(cfg=None):
    """Saved for the phone: it runs tomorrow's wake-up call with the PC switched off."""
    tom = dt.date.today() + dt.timedelta(days=1)
    pack = {"date": tom.isoformat(), "school_day": is_school_day(tom, cfg), "day": day_cfg(cfg),
            "lines": tomorrow_plan(), "made": time.time()}
    try:
        from .life import homework
        pack["homework"] = [h for h in homework() if not h.get("done") and h["days"] <= 2][:6]
    except Exception:
        pack["homework"] = []
    try:
        from .study import overview
        o = overview()
        pack["exam"] = o["exams"][0] if o["exams"] else None
        pack["streak"] = o["streak"]
    except Exception:
        pass
    try:                                   # tomorrow's weather, so the phone can say it with the PC off
        from .life import forecast
        w = forecast("")
        t = (w.get("days") or [{}, {}])[1] if len(w.get("days") or []) > 1 else {}
        pack["weather"] = {"temp": t.get("max"), "rain": t.get("rain"), "sky": t.get("sky")}
    except Exception:
        pass
    try:
        from .scholar import weakest_topics
        pack["weak"] = weakest_topics(3)
    except Exception:
        pack["weak"] = []
    from .safeio import write_json
    write_json(PACK, pack, indent=1)
    return pack


def load_pack():
    try:
        with open(PACK, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return morning_pack()


@tool("Set the user's daily routine times (wake, school start/end, when the PC goes off) or mark holidays.",
      {"wake": ("string", "HH:MM", False), "school_start": ("string", "HH:MM", False),
       "school_end": ("string", "HH:MM", False), "pc_off": ("string", "HH:MM", False),
       "holiday": ("boolean", "True during school holidays", False)})
def set_routine(wake="", school_start="", school_end="", pc_off="", holiday=None):
    d = day_cfg()
    for k, v in (("wake", wake), ("school_start", school_start), ("school_end", school_end), ("pc_off", pc_off)):
        if v:
            d[k] = v
    if holiday is not None:
        d["holiday"] = bool(holiday)
    from . import config as config_mod
    config_mod.save(CTX["config"])
    return "Routine updated: " + ", ".join(f"{k} {v}" for k, v in d.items() if k != "school_days")

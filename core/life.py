"""Everyday helpers: homework tracker, weather, news, notes, clipboard history, screen time, file finder,
and ready-made scene shortcuts ("goodnight", "study time", "gaming time")."""
import datetime as dt
import html
import json
import os
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from .paths import DATA_DIR
from .tools import CTX, tool

HW = os.path.join(DATA_DIR, "homework.json")
NOTES = os.path.join(DATA_DIR, "notes.json")
CLIPS = os.path.join(DATA_DIR, "clipboard.json")
SCREEN = os.path.join(DATA_DIR, "screentime.json")
_lock = threading.RLock()
UA = {"User-Agent": "ORION/3 (personal assistant)"}


def _load(p, d):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _save(p, v):
    with _lock:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(v, f, indent=1)
        os.replace(tmp, p)


def _id():
    import uuid
    return uuid.uuid4().hex[:6]


# ======================================================================== homework
def _due(s):
    s = (s or "").strip().lower()
    today = dt.date.today()
    if not s:
        return (today + dt.timedelta(days=7)).isoformat()
    if s in ("today", "tonight"):
        return today.isoformat()
    if s == "tomorrow":
        return (today + dt.timedelta(days=1)).isoformat()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, d in enumerate(days):
        if d in s:
            ahead = (i - today.weekday()) % 7 or 7
            return (today + dt.timedelta(days=ahead)).isoformat()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.search(r"in (\d+) days?", s)
    if m:
        return (today + dt.timedelta(days=int(m.group(1)))).isoformat()
    return (today + dt.timedelta(days=7)).isoformat()


def homework():
    hw = _load(HW, [])
    today = dt.date.today()
    for h in hw:
        try:
            h["days"] = (dt.date.fromisoformat(h["due"]) - today).days
        except Exception:
            h["days"] = 99
    return sorted(hw, key=lambda h: (h.get("done", False), h["due"]))


def hw_add(subject, task, due=""):
    hw = _load(HW, [])
    h = {"id": _id(), "subject": subject.strip()[:40] or "General", "task": task.strip()[:200],
         "due": _due(due), "done": False, "added": time.strftime("%Y-%m-%d")}
    hw.append(h)
    _save(HW, hw)
    return h


def hw_set(hid, done=True):
    hw = _load(HW, [])
    for h in hw:
        if h["id"] == hid:
            h["done"] = bool(done)
    _save(HW, [h for h in hw if not (h.get("done") and h.get("due", "") < (dt.date.today() - dt.timedelta(days=14)).isoformat())])


def hw_remove(hid):
    _save(HW, [h for h in _load(HW, []) if h["id"] != hid])


def hw_summary():
    due = [h for h in homework() if not h.get("done") and h["days"] <= 2]
    if not due:
        return ""
    return "Homework due: " + "; ".join(f"{h['subject']} — {h['task']} ({'overdue' if h['days'] < 0 else 'today' if h['days'] == 0 else 'tomorrow' if h['days'] == 1 else 'in 2 days'})" for h in due[:5])


@tool("Add HOMEWORK to the tracker (ORION reminds the user before it's due).",
      {"subject": ("string", "e.g. Maths", True), "task": ("string", "What to do", True),
       "due": ("string", "When it's due: 'tomorrow', 'friday', 'in 3 days' or YYYY-MM-DD", False)})
def homework_add(subject, task, due=""):
    h = hw_add(subject, task, due)
    return f"Added {h['subject']} homework, due {h['due']}."


@tool("List homework that isn't done yet.")
def homework_list():
    hw = [h for h in homework() if not h.get("done")]
    return "\n".join(f"[{h['id']}] {h['subject']}: {h['task']} — due {h['due']} ({h['days']} day(s))" for h in hw) or "No homework — nice."


@tool("Mark homework as done (by id or a word from it).", {"which": ("string", "Id or keyword", True)})
def homework_done(which):
    w = which.lower().strip()
    for h in homework():
        if not h.get("done") and (h["id"] == w or w in (h["subject"] + " " + h["task"]).lower()):
            hw_set(h["id"], True)
            return f"Ticked off: {h['subject']} — {h['task']}."
    return "Couldn't find that homework."


# ======================================================================== weather + news
_geo_cache = {}
CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy", 51: "light drizzle",
         53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
         67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "showers",
         81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorms",
         96: "thunderstorms with hail", 99: "thunderstorms with hail"}


def _geo(place):
    place = place or CTX.get("config", {}).get("home_place", "Leicester")
    if place in _geo_cache:
        return _geo_cache[place]
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": place.split(",")[0], "count": 1},
                     headers=UA, timeout=10).json()
    if not r.get("results"):
        raise RuntimeError(f"Couldn't find {place}.")
    g = r["results"][0]
    _geo_cache[place] = (g["latitude"], g["longitude"], g["name"])
    return _geo_cache[place]


def forecast(place=""):
    lat, lon, name = _geo(place)
    r = requests.get("https://api.open-meteo.com/v1/forecast", headers=UA, timeout=10, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunset",
        "hourly": "precipitation_probability"}).json()
    c, d = r["current"], r["daily"]
    hours = r.get("hourly", {})
    rain_soon = None
    now = dt.datetime.now().strftime("%Y-%m-%dT%H")
    for t, p in zip(hours.get("time", []), hours.get("precipitation_probability", [])):
        if t >= now and p is not None and p >= 50:
            rain_soon = t[11:16]
            break
    return {"place": name, "temp": round(c["temperature_2m"]), "feels": round(c["apparent_temperature"]),
            "sky": CODES.get(c["weather_code"], "mixed"), "wind": round(c["wind_speed_10m"]), "code": c["weather_code"],
            "rain_at": rain_soon,
            "days": [{"date": d["time"][i], "max": round(d["temperature_2m_max"][i]), "min": round(d["temperature_2m_min"][i]),
                      "sky": CODES.get(d["weather_code"][i], "mixed"), "rain": d["precipitation_probability_max"][i],
                      "code": d["weather_code"][i]} for i in range(len(d["time"]))],
            "sunset": d["sunset"][0][11:16]}


@tool("WEATHER now and the next few days (free, no key). Use for 'do I need a coat/umbrella', 'what's it like out'.",
      {"place": ("string", "Town/city (blank = home)", False)})
def weather(place=""):
    w = forecast(place)
    t = w["days"][1] if len(w["days"]) > 1 else None
    out = (f"{w['place']}: {w['temp']}°C (feels {w['feels']}°), {w['sky']}, wind {w['wind']} km/h. "
           f"Today {w['days'][0]['min']}–{w['days'][0]['max']}°, {w['days'][0]['rain']}% chance of rain.")
    if w["rain_at"]:
        out += f" Rain likely from about {w['rain_at']}."
    if t:
        out += f" Tomorrow {t['sky']}, {t['min']}–{t['max']}°, {t['rain']}% rain."
    return out + f" Sunset {w['sunset']}."


FEEDS = {"top": "https://feeds.bbci.co.uk/news/rss.xml", "uk": "https://feeds.bbci.co.uk/news/uk/rss.xml",
         "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml", "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
         "sport": "https://feeds.bbci.co.uk/sport/rss.xml", "football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
         "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
         "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
         "gaming": "https://feeds.bbci.co.uk/news/technology/rss.xml",
         "leicester": "https://feeds.bbci.co.uk/news/england/leicester/rss.xml"}


def headlines(topic="top", n=6):
    url = FEEDS.get((topic or "top").lower().strip(), FEEDS["top"])
    root = ET.fromstring(requests.get(url, headers=UA, timeout=10).content)
    out = []
    for it in root.iter("item"):
        out.append({"title": html.unescape(it.findtext("title") or ""), "link": it.findtext("link") or "",
                    "desc": html.unescape(it.findtext("description") or "")})
        if len(out) >= n:
            break
    return out


@tool("NEWS headlines from the BBC. topics: top, uk, world, tech, science, business, sport, football, leicester.",
      {"topic": ("string", "Topic (default top)", False)})
def news(topic="top"):
    h = headlines(topic, 6)
    return "\n".join(f"• {x['title']} — {x['desc'][:120]}" for x in h) or "No headlines right now."


# ======================================================================== notes
def notes():
    return _load(NOTES, [])


def note_add_raw(text, tag=""):
    n = notes()
    x = {"id": _id(), "text": text.strip()[:2000], "tag": (tag or "").strip()[:20], "t": time.strftime("%Y-%m-%d %H:%M")}
    n.append(x)
    _save(NOTES, n[-500:])
    return x


def note_remove(nid):
    _save(NOTES, [x for x in notes() if x["id"] != nid])


@tool("Save a quick NOTE or idea (e.g. 'note: video idea — Hatchlands speedrun'). Optional tag like idea, todo, video.",
      {"text": ("string", "The note", True), "tag": ("string", "Optional tag", False)})
def note_add(text, tag=""):
    note_add_raw(text, tag)
    return "Noted."


@tool("Find saved notes (blank = latest).", {"search": ("string", "Words to look for", False)})
def notes_find(search=""):
    s = (search or "").lower()
    hits = [x for x in notes() if not s or s in (x["text"] + " " + x["tag"]).lower()][-15:]
    return "\n".join(f"[{x['t']}] {('#' + x['tag'] + ' ') if x['tag'] else ''}{x['text']}" for x in reversed(hits)) or "No notes found."


# ======================================================================== clipboard history
SECRETISH = re.compile(r"(gsk_|sk-|ghp_|github_pat_|AIza|xox[bp]-|-----BEGIN|password|\b\d{12,19}\b)", re.I)


class ClipWatch:
    """Remembers the last 60 things you copied (skips anything that looks like a password or key)."""

    def __init__(self):
        self.last = None
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            import pyperclip
        except Exception:
            return
        while True:
            try:
                t = pyperclip.paste()
                if t and t != self.last and len(t) < 20000:
                    self.last = t
                    if not SECRETISH.search(t) and t.strip():
                        h = [x for x in _load(CLIPS, []) if x["text"] != t]
                        h.append({"text": t, "t": time.strftime("%Y-%m-%d %H:%M")})
                        _save(CLIPS, h[-60:])
            except Exception:
                pass
            time.sleep(1.5)


def clip_history():
    return list(reversed(_load(CLIPS, [])))


@tool("Clipboard HISTORY: find something the user copied earlier, and optionally put it back on the clipboard.",
      {"search": ("string", "Words to look for (blank = latest)", False),
       "restore": ("integer", "Number of the item to copy back (from the list)", False)})
def clipboard_history(search="", restore=None):
    s = (search or "").lower()
    items = [x for x in clip_history() if not s or s in x["text"].lower()][:12]
    if restore:
        i = int(restore) - 1
        if 0 <= i < len(items):
            import pyperclip
            pyperclip.copy(items[i]["text"])
            return "Copied back to your clipboard."
    return "\n".join(f"{i + 1}. [{x['t'][11:]}] {x['text'][:140]!r}" for i, x in enumerate(items)) or "Nothing copied yet."


# ======================================================================== screen time
NICE = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "discord.exe": "Discord",
        "spotify.exe": "Spotify", "robloxplayerbeta.exe": "Roblox", "robloxstudiobeta.exe": "Roblox Studio",
        "code.exe": "VS Code", "explorer.exe": "File Explorer", "root.exe": "Root", "javaw.exe": "Minecraft",
        "minecraft.windows.exe": "Minecraft", "steam.exe": "Steam", "obs64.exe": "OBS", "winword.exe": "Word",
        "powerpnt.exe": "PowerPoint", "excel.exe": "Excel", "python.exe": "Python", "pythonw.exe": "ORION",
        "msedgewebview2.exe": "ORION", "notepad.exe": "Notepad", "vlc.exe": "VLC"}
SITES = re.compile(r"(youtube|tiktok|netflix|twitch|instagram|reddit|roblox|chatgpt|claude|github|bbc|wikipedia|"
                   r"seneca|bbc bitesize|google docs|sparx|kerboodle|quizlet|amazon|ebay|vinted|spotify)", re.I)


class ScreenTime:
    """Every 20 s: which app (and which big site) is in front, while you're actually at the PC."""

    def __init__(self):
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def _front():
        import ctypes
        import psutil
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(512)
        u.GetWindowTextW(hwnd, buf, 512)
        exe = psutil.Process(pid.value).name().lower()
        name = NICE.get(exe, exe.replace(".exe", "").capitalize())
        if exe in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"):
            m = SITES.search(buf.value or "")
            if m:
                name = m.group(1).title().replace("Youtube", "YouTube").replace("Tiktok", "TikTok")
        return name

    def _loop(self):
        from .jobs import idle_seconds
        while True:
            time.sleep(20)
            try:
                if os.name != "nt" or idle_seconds() > 120:
                    continue
                name = self._front()
                d = _load(SCREEN, {})
                day = d.setdefault(time.strftime("%Y-%m-%d"), {})
                day[name] = day.get(name, 0) + 20
                if len(d) > 60:
                    for k in sorted(d)[:-60]:
                        d.pop(k)
                _save(SCREEN, d)
            except Exception:
                pass


def screen_day(day=None):
    d = _load(SCREEN, {}).get(day or time.strftime("%Y-%m-%d"), {})
    return sorted(((k, round(v / 60)) for k, v in d.items() if v >= 60), key=lambda kv: -kv[1])


def screen_week():
    d = _load(SCREEN, {})
    out = []
    for k in range(6, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - k * 86400))
        out.append({"day": day[5:], "mins": round(sum(d.get(day, {}).values()) / 60)})
    return out


@tool("SCREEN TIME: how long the user spent in each app/site today (or another day YYYY-MM-DD).",
      {"day": ("string", "YYYY-MM-DD (blank = today)", False)})
def screen_time(day=""):
    rows = screen_day(day or None)
    if not rows:
        return "No screen time recorded yet for that day."
    tot = sum(m for _, m in rows)
    return f"Total {tot // 60}h {tot % 60}m. " + ", ".join(f"{k} {m // 60}h{m % 60:02d}m" if m >= 60 else f"{k} {m}m" for k, m in rows[:10])


# ======================================================================== file finder
@tool("FIND FILES on the PC by name (searches Desktop, Documents, Downloads, Pictures, Videos, Music, OneDrive).",
      {"name": ("string", "Part of the file name, e.g. 'macbeth essay' or '.mp4'", True),
       "open_it": ("boolean", "Open the best match", False)})
def find_files(name, open_it=False):
    home = os.path.expanduser("~")
    roots = [os.path.join(home, x) for x in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
    roots += [os.path.join(home, x) for x in os.listdir(home) if x.lower().startswith("onedrive")]
    words = [w for w in re.split(r"[\s_\-]+", name.lower()) if w]
    hits, t0 = [], time.time()
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith((".", "$")) and d.lower() not in ("node_modules", "__pycache__", "appdata")]
            for f in fn:
                low = f.lower()
                if all(w in low for w in words):
                    p = os.path.join(dp, f)
                    try:
                        hits.append((os.path.getmtime(p), p))
                    except Exception:
                        pass
            if time.time() - t0 > 12:
                break
    hits.sort(reverse=True)
    if not hits:
        return f"No files matching '{name}'."
    if open_it:
        os.startfile(hits[0][1])
    return ("Opened the newest match.\n" if open_it else "") + "\n".join(
        f"{time.strftime('%d %b', time.localtime(m))}  {p}" for m, p in hits[:15])


# ======================================================================== scene shortcuts
SCENES = [
    ("goodnight", "Say goodnight, mute the PC volume, tell me what's on tomorrow and any homework due, then lock the PC."),
    ("good morning", "Give me the weather, today's schedule, homework due and anything that happened overnight."),
    ("study time", "Start a 25-minute focus session and close any games. Tell me which homework is due soonest."),
    ("gaming time", "Turn on gaming mode and open Discord."),
    ("what did i miss", "Summarise new Root DMs, finished jobs and notifications since I was last here."),
]


def install_scenes(cfg):
    """Adds the ready-made scenes once (you can edit or delete them on the Brain page)."""
    if cfg.get("_scenes_v1"):
        return
    try:
        from . import learning
        have = {x["phrase"] for x in learning.shortcuts()}
        for p, d in SCENES:
            if p not in have:
                learning.add_shortcut(p, d)
        cfg["_scenes_v1"] = True
    except Exception:
        pass


@tool("DICTATION mode: everything the user says gets typed into the window they're using, until they say "
      "'stop dictation'. Use for 'type what I say', 'dictate'.", {"on": ("boolean", "True = start, False = stop", True)})
def dictation(on=True):
    f = CTX.get("dictate")
    if not f:
        return "Dictation isn't available."
    f(bool(on))
    return "Dictation on — click where you want the words to go." if on else "Dictation off."


@tool("VOICE MEMO: record the user talking (as long as they like) and save it as a note. Use for 'take a memo', "
      "'record a voice note', 'let me brain-dump'.")
def voice_memo():
    f = CTX.get("listen_memo")
    if not f:
        return "Voice memos aren't available."
    text = f()
    return f"Saved your memo ({len(text.split())} words): {text[:300]}" if text else "I didn't hear anything, so nothing was saved."

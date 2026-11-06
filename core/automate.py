"""Automations — "WHEN this happens, THEN do that". Runs in the background, checks every few seconds.

Triggers:  app_open / app_close (e.g. Fortnite) · game_start / game_end · away (idle N min) · back (returned after N min)
           time (HH:MM, daily/weekdays/weekends) · sunset · sunrise · rain_soon · cpu_high · ram_high · disk_low
           battery_low · new_download (file type) · revision_due (none done today, after a time)
Actions:   say (ORION speaks) · notify (phone + PC) · do (ORION carries out an instruction, via the job queue)
           open_app · theme (switch mode) · routine (run a Night Shift routine) · gaming_mode on/off · focus (start a session)
Every automation has a cooldown so it can't spam. Same safety rules as everything else ORION does.
"""
import datetime as dt
import json
import os
import threading
import time
import uuid

import psutil

from .paths import DATA_DIR
from .safeio import write_json
from .tools import CTX, tool

PATH = os.path.join(DATA_DIR, "automations.json")
TRIGGERS = {
    "app_open": "When I open an app", "app_close": "When I close an app", "game_start": "When I start gaming",
    "game_end": "When I stop gaming", "away": "When I've been away for N min", "back": "When I come back after N min away",
    "time": "At a time", "sunset": "At sunset", "sunrise": "At sunrise", "rain_soon": "When rain is coming (within the hour)",
    "cpu_high": "When the CPU is maxed out", "ram_high": "When memory is nearly full", "disk_low": "When disk space is low",
    "battery_low": "When the laptop battery is low", "new_download": "When a new file lands in Downloads",
    "no_revision": "If I haven't revised by a time",
}
ACTIONS = {"say": "ORION says…", "notify": "Message my phone", "do": "ORION does…", "open_app": "Open an app",
           "theme": "Switch mode", "routine": "Run a Night Shift routine", "gaming": "Gaming mode on/off", "focus": "Start a focus session"}
PRESETS = [
    {"name": "Game time", "trigger": {"type": "game_start"}, "action": {"type": "say", "value": "Gaming mode engaged, sir. I'll hold your messages."}},
    {"name": "Good game", "trigger": {"type": "game_end"}, "action": {"type": "do", "value": "Tell me in one line how long I just played and what homework is due next."}},
    {"name": "Welcome home", "trigger": {"type": "back", "value": 120}, "action": {"type": "do", "value": "Give me a 3-line catch-up: anything new, what's due, what's next on my plan."}},
    {"name": "Revision nudge", "trigger": {"type": "no_revision", "value": "19:30"}, "action": {"type": "notify", "value": "No revision yet today, sir — 25 minutes now and you're done."}},
    {"name": "Rain warning", "trigger": {"type": "rain_soon"}, "action": {"type": "notify", "value": "☔ Rain within the hour — take a coat (or wait it out)."}},
    {"name": "Sunset lights", "trigger": {"type": "sunset"}, "action": {"type": "theme", "value": "standby"}},
    {"name": "Low disk clean-up", "trigger": {"type": "disk_low", "value": 15}, "action": {"type": "routine", "value": "clear_temp"}},
    {"name": "Battery saver", "trigger": {"type": "battery_low", "value": 20}, "action": {"type": "say", "value": "Battery's under 20 percent, sir. Might be time for the charger."}},
    {"name": "Sort new PDFs", "trigger": {"type": "new_download", "value": ".pdf"}, "action": {"type": "do", "value": "A new PDF just downloaded — tell me its name and ask if it's homework I should add."}},
    {"name": "Discord with Spotify", "trigger": {"type": "app_open", "value": "discord"}, "action": {"type": "open_app", "value": "Spotify"}},
    {"name": "Bedtime wind-down", "trigger": {"type": "time", "value": "22:30", "days": "weekdays"}, "action": {"type": "say", "value": "It's half ten on a school night, sir. Time to start winding down."}},
    {"name": "PC struggling", "trigger": {"type": "cpu_high"}, "action": {"type": "notify", "value": "Your PC's CPU has been maxed out for over a minute — something's hogging it."}},
]
_lock = threading.Lock()


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save(rules):
    with _lock:
        write_json(PATH, rules)


def describe(r):
    t, a = r["trigger"], r["action"]
    tv = t.get("value")
    when = {"app_open": f"I open {tv}", "app_close": f"I close {tv}", "game_start": "I start a game", "game_end": "I stop gaming",
            "away": f"I've been away {tv or 30} min", "back": f"I'm back after {tv or 60}+ min away",
            "time": f"it's {tv} ({t.get('days', 'daily')})", "sunset": "the sun sets", "sunrise": "the sun rises",
            "rain_soon": "rain is coming", "cpu_high": "the CPU is maxed out", "ram_high": "memory is nearly full",
            "disk_low": f"disk space drops under {tv or 15} GB", "battery_low": f"battery drops under {tv or 20}%",
            "new_download": f"a new {tv or 'file'} downloads", "no_revision": f"I haven't revised by {tv or '19:30'}"}.get(t["type"], t["type"])
    then = {"say": f"say “{a.get('value', '')}”", "notify": "message my phone", "do": f"do: {a.get('value', '')}",
            "open_app": f"open {a.get('value', '')}", "theme": f"switch to {a.get('value', '')} mode",
            "routine": f"run {a.get('value', '')}", "gaming": f"gaming mode {a.get('value', 'on')}",
            "focus": f"start a {a.get('value', 25)}-min focus session"}.get(a["type"], a["type"])
    return f"When {when} → {then}"


def add(name, trigger, action, cooldown=None):
    if trigger.get("type") not in TRIGGERS or action.get("type") not in ACTIONS:
        raise ValueError("Unknown trigger or action.")
    rules = load()
    r = {"id": "a" + uuid.uuid4().hex[:6], "name": (name or "").strip()[:50] or TRIGGERS[trigger["type"]], "trigger": trigger,
         "action": action, "on": True, "cooldown": int(cooldown or (720 if trigger["type"] in ("time", "sunset", "sunrise", "no_revision") else 20)),
         "last": 0, "runs": 0, "created": time.time()}
    rules.append(r)
    save(rules)
    return r


class Engine:
    TICK = 5

    def __init__(self, cfg, emit, run_action):
        self.cfg, self.emit, self.run_action = cfg, emit, run_action
        self.procs = set()
        self.away_since = None
        self.was_gaming = False
        self.cpu_hot_since = None
        self.downloads = None
        self.away_fired = set()
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ signals
    def _procs(self):
        out = set()
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info["name"] or "").lower()
                if n:
                    out.add(n.removesuffix(".exe"))
            except Exception:
                continue
        return out

    def _downloads(self):
        d = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            return {e.name for e in os.scandir(d) if e.is_file() and not e.name.endswith((".crdownload", ".part", ".tmp"))}
        except Exception:
            return set()

    def _loop(self):
        time.sleep(20)
        self.procs = self._procs()
        self.downloads = self._downloads()
        while True:
            try:
                if self.cfg.get("automations_on", True):
                    self.tick()
            except Exception:
                pass
            time.sleep(self.TICK)

    def tick(self):
        rules = [r for r in load() if r.get("on", True)]
        if not rules:
            return
        types = {r["trigger"]["type"] for r in rules}
        ev = {}
        if types & {"app_open", "app_close"}:
            now = self._procs()
            ev["opened"], ev["closed"] = now - self.procs, self.procs - now
            self.procs = now
        if types & {"away", "back"}:
            from .jobs import idle_seconds
            idle = idle_seconds()
            ev["idle_min"] = idle / 60
            if idle > 120 and self.away_since is None:
                self.away_since = time.time() - idle
            if idle < 30 and self.away_since:
                ev["back_after"] = (time.time() - self.away_since) / 60
                self.away_since = None
        g = CTX.get("gaming")
        gaming = bool(g and g.active)
        ev["game_start"], ev["game_end"] = gaming and not self.was_gaming, self.was_gaming and not gaming
        self.was_gaming = gaming
        if "cpu_high" in types:
            c = psutil.cpu_percent(interval=None)
            self.cpu_hot_since = (self.cpu_hot_since or time.time()) if c > 92 else None
            ev["cpu_hot"] = bool(self.cpu_hot_since and time.time() - self.cpu_hot_since > 60)
        if "new_download" in types:
            now = self._downloads()
            ev["new_files"] = list(now - (self.downloads or now))
            self.downloads = now
        now = dt.datetime.now()
        hm = now.strftime("%H:%M")
        for r in rules:
            try:
                ctx = self._match(r, ev, now, hm)
            except Exception:
                ctx = None
            if ctx is None:
                continue
            if time.time() - r.get("last", 0) < r.get("cooldown", 20) * 60:
                continue
            self._fire(r, ctx)

    def _match(self, r, ev, now, hm):
        t = r["trigger"]
        ty, v = t["type"], t.get("value")
        if ty == "app_open":
            hit = [p for p in ev.get("opened", ()) if str(v).lower().replace(" ", "") in p.replace(" ", "")]
            return {"app": hit[0]} if hit else None
        if ty == "app_close":
            hit = [p for p in ev.get("closed", ()) if str(v).lower().replace(" ", "") in p.replace(" ", "")]
            return {"app": hit[0]} if hit else None
        if ty == "game_start":
            return {} if ev.get("game_start") else None
        if ty == "game_end":
            return {} if ev.get("game_end") else None
        if ty == "away":
            idle = ev.get("idle_min", 0)
            if idle < 1:
                self.away_fired.discard(r["id"])
                return None
            if idle >= float(v or 30) and r["id"] not in self.away_fired:
                self.away_fired.add(r["id"])
                return {"mins": round(idle)}
            return None
        if ty == "back":
            b = ev.get("back_after")
            return {"mins": round(b)} if b and b >= float(v or 60) else None
        days = t.get("days", "daily")
        if days == "weekdays" and now.weekday() >= 5 or days == "weekends" and now.weekday() < 5:
            return None
        if ty == "time":
            return {} if hm == (v or "") else None
        if ty in ("sunset", "sunrise"):
            from .localintel import _sun_times, home
            h = CTX.setdefault("_auto_home", home())
            rise, sset = _sun_times(h["lat"], h["lon"])
            return {} if hm == (sset if ty == "sunset" else rise) else None
        if ty == "rain_soon":
            if now.minute % 10:                         # only check the forecast every 10 minutes
                return None
            from .life import forecast
            w = forecast("")
            if w.get("rain_at"):
                rh, rm = map(int, w["rain_at"].split(":"))
                mins = (rh * 60 + rm) - (now.hour * 60 + now.minute)
                return {"at": w["rain_at"]} if 0 <= mins <= 60 else None
            return None
        if ty == "cpu_high":
            return {} if ev.get("cpu_hot") else None
        if ty == "ram_high":
            return {} if psutil.virtual_memory().percent >= float(v or 92) else None
        if ty == "disk_low":
            return {} if psutil.disk_usage(os.path.abspath(os.sep)).free / 2**30 < float(v or 15) else None
        if ty == "battery_low":
            b = psutil.sensors_battery()
            return {"pct": round(b.percent)} if b and not b.power_plugged and b.percent < float(v or 20) else None
        if ty == "new_download":
            ext = (v or "").lower().strip()
            hit = [f for f in ev.get("new_files", []) if not ext or f.lower().endswith(ext if ext.startswith(".") else "." + ext)]
            return {"file": hit[0]} if hit else None
        if ty == "no_revision":
            if hm != (v or "19:30"):
                return None
            from .study import overview
            return {} if overview().get("today", 0) == 0 else None
        return None

    def _set(self, rid, **kw):
        rules = load()
        for x in rules:
            if x["id"] == rid:
                x.update(kw)
        save(rules)

    def _fire(self, r, ctx):
        self._set(r["id"], last=time.time(), runs=r.get("runs", 0) + 1)
        self.emit("toast", level="info", text=f"⚡ {r['name']}")
        self.emit("automation", id=r["id"], name=r["name"])
        try:
            self.run_action(r, ctx)
        except Exception as e:
            self.emit("toast", level="warn", text=f"Automation '{r['name']}' failed: {e}")


# ------------------------------------------------------------------ tools for the brain
@tool("AUTOMATION: create a 'when X happens, do Y' rule that runs by itself. trigger: app_open, app_close, game_start, game_end, "
      "away, back, time, sunset, sunrise, rain_soon, cpu_high, ram_high, disk_low, battery_low, new_download, no_revision. "
      "trigger_value: app name / minutes / HH:MM / GB / % / file extension. action: say, notify, do, open_app, theme, routine, "
      "gaming, focus. action_value: what to say / instruction to do / app / mode / routine / on|off / minutes. "
      "e.g. 'when I open Fortnite turn on gaming mode', 'if I haven't revised by 7:30 nag me'.",
      {"name": ("string", "Short name", False), "trigger": ("string", "Trigger type", True),
       "trigger_value": ("string", "Value for the trigger", False), "days": ("string", "daily | weekdays | weekends (time triggers)", False),
       "action": ("string", "Action type", True), "action_value": ("string", "Value for the action", False)})
def automation_add(trigger, action, name="", trigger_value="", days="daily", action_value=""):
    t = {"type": trigger}
    if trigger_value:
        t["value"] = float(trigger_value) if trigger in ("away", "back", "disk_low", "battery_low", "ram_high") else trigger_value
    if trigger in ("time", "no_revision", "sunset", "sunrise"):
        t["days"] = days if days in ("daily", "weekdays", "weekends") else "daily"
    try:
        r = add(name, t, {"type": action, "value": action_value})
    except ValueError as e:
        return f"ERROR: {e}"
    CTX.get("emit") and CTX["emit"]("automations_changed")
    return "Automation saved: " + describe(r)


@tool("List the user's automations (when→then rules).")
def automation_list():
    rs = load()
    return "\n".join(f"{'✓' if r.get('on', True) else '✗'} {r['name']}: {describe(r)} (ran {r.get('runs', 0)}×)" for r in rs) or "No automations yet."


@tool("Delete or turn off an automation by name.",
      {"name": ("string", "Automation name", True), "delete": ("boolean", "Delete instead of switching off", False)})
def automation_remove(name, delete=True):
    rs = load()
    hit = [r for r in rs if r["name"].lower() == name.lower() or r["id"] == name]
    if not hit:
        return "No automation with that name."
    if delete:
        rs = [r for r in rs if r not in hit]
    else:
        for r in hit:
            r["on"] = False
    save(rs)
    CTX.get("emit") and CTX["emit"]("automations_changed")
    return f"{'Deleted' if delete else 'Switched off'}: {hit[0]['name']}"

"""Automations — "WHEN this happens, THEN do that". Runs in the background, checks every few seconds.

Triggers:  app_open / app_close (e.g. Fortnite) · game_start / game_end · away (idle N min) · back (returned after N min)
           time (HH:MM, daily/weekdays/weekends) · sunset · sunrise · rain_soon · cpu_high · ram_high · disk_low
           battery_low · new_download (file type) · revision_due (none done today, after a time)
Actions:   say (ORION speaks) · notify (phone + PC) · do (ORION carries out an instruction, via the job queue)
           open_app · theme (switch mode) · routine (run a Night Shift routine) · gaming_mode on/off · focus (start a session)
Every automation has a cooldown so it can't spam. Same safety rules as everything else ORION does.

7.0: business & money triggers (money in, goal hit, spending over budget, quiet leads, deal won, weekly), streams
(going live, stream ended, follower milestones), website down, new file in any folder, PC start-up; more actions
(webhook — e.g. a Discord channel, open a website, CEO report, draft follow-ups, back up ORION, add a note, log a
reminder); up to 3 steps per rule; "only between" times/days; and an AI budget so automations never burn your credits —
most automations use no AI at all, and the ones that do stop for the day once the budget's spent.
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
    # ORION OS
    "os_start": "When ORION OS starts", "unlock": "When I unlock ORION", "wifi_join": "When I join a Wi-Fi network",
    "offline": "When the internet drops", "online": "When the internet comes back",
    "charger_in": "When I plug the charger in", "charger_out": "When I unplug the charger",
    # 7.0
    "pc_start": "When ORION starts up", "weekly": "Every week (day + time)",
    "money_in": "When I log money earned", "goal_hit": "When I hit a money goal", "spend_over": "When this month's spending passes £X",
    "lead_quiet": "When a lead goes quiet", "deal_won": "When a deal is won",
    "stream_start": "When I go live", "stream_end": "When my stream ends", "followers": "When I pass a follower milestone",
    "site_down": "When a website goes down", "file_in": "When a new file lands in a folder",
}
NO_AI = {"say", "notify", "open_app", "open_url", "theme", "gaming", "focus", "webhook", "report", "backup", "note", "remind",
         "volume", "lock", "power", "sky", "stream_recap"}
AI_ACTIONS = {"do", "followups"}
OS_ONLY = {"os_start", "unlock", "wifi_join", "volume", "lock", "power", "sky"}
ACTIONS = {"say": "ORION says…", "notify": "Message my phone", "do": "ORION does…", "open_app": "Open an app",
           "theme": "Switch mode", "routine": "Run a Night Shift routine", "gaming": "Gaming mode on/off", "focus": "Start a focus session",
           "volume": "Set the volume (ORION OS)", "lock": "Lock the screen (ORION OS)",
           "power": "Shut down / restart / sleep, with a 60-second warning (ORION OS)", "sky": "Change the sky (ORION OS)",
           "open_url": "Open a website", "webhook": "Post to a webhook (e.g. Discord)", "report": "Send me the CEO report",
           "followups": "Draft follow-ups for quiet leads (uses AI)", "backup": "Back up ORION's memory & settings",
           "note": "Add a note", "remind": "Remind me later (minutes)", "stream_recap": "Send my last stream recap"}
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
    {"name": "Bedtime shutdown", "os": True, "trigger": {"type": "time", "value": "23:30", "days": "weekdays"}, "action": {"type": "power", "value": "shutdown"}},
    {"name": "Welcome back brief", "os": True, "trigger": {"type": "unlock"}, "cooldown": 240, "action": {"type": "do", "value": "Welcome me back in 3 short lines: anything new, what's due next, and what's next on my plan."}},
    {"name": "Quiet nights", "os": True, "trigger": {"type": "time", "value": "22:00"}, "action": {"type": "volume", "value": "30"}},
    {"name": "Aurora after dark", "os": True, "trigger": {"type": "sunset"}, "action": {"type": "sky", "value": "aurora"}},
    {"name": "Night sky at sunrise", "os": True, "trigger": {"type": "sunrise"}, "action": {"type": "sky", "value": "night"}},
    {"name": "Internet's down", "os": True, "trigger": {"type": "offline"}, "action": {"type": "say", "value": "We've lost the internet, sir. I'll keep going offline where I can."}},
    {"name": "Lock when I leave", "os": True, "trigger": {"type": "away", "value": 5}, "action": {"type": "lock"}},
    # 7.0 — business, money, streams
    {"name": "Monday money brief", "trigger": {"type": "weekly", "value": "mon 08:15"}, "action": {"type": "report"}},
    {"name": "Quiet lead nudge", "trigger": {"type": "lead_quiet"}, "cooldown": 1440, "action": {"type": "notify", "value": "A lead's gone quiet — open Money to send a follow-up."}},
    {"name": "Deal won!", "trigger": {"type": "deal_won"}, "action": {"type": "say", "value": "Deal won, sir. Well done — I've updated the numbers."}},
    {"name": "Goal smashed", "trigger": {"type": "goal_hit"}, "action": {"type": "notify", "value": "🎯 You've hit a money goal! Time to set the next one."}},
    {"name": "Spending alert", "trigger": {"type": "spend_over", "value": 30}, "cooldown": 10080, "action": {"type": "notify", "value": "You've spent over £30 on your ventures this month — worth a quick check."}},
    {"name": "Live = game mode", "trigger": {"type": "stream_start"}, "action": {"type": "gaming", "value": "on"}, "then": [{"type": "say", "value": "You're live, sir. Messages held, go get them."}]},
    {"name": "Stream recap", "trigger": {"type": "stream_end"}, "action": {"type": "stream_recap"}},
    {"name": "Follower milestone", "trigger": {"type": "followers"}, "action": {"type": "say", "value": "New follower milestone, sir. Congratulations."}},
    {"name": "Website down", "trigger": {"type": "site_down", "value": "https://"}, "cooldown": 60, "action": {"type": "notify", "value": "Your website just went down."}},
    {"name": "Weekly backup", "trigger": {"type": "weekly", "value": "sun 20:00"}, "action": {"type": "backup"}},
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
            "new_download": f"a new {tv or 'file'} downloads", "no_revision": f"I haven't revised by {tv or '19:30'}",
            "os_start": "ORION OS starts", "unlock": "I unlock ORION", "wifi_join": f"I join {tv or 'a Wi-Fi network'}",
            "offline": "the internet drops", "online": "the internet comes back", "charger_in": "I plug the charger in",
            "charger_out": "I unplug the charger", "pc_start": "ORION starts up", "weekly": f"it's {tv or 'mon 09:00'} each week",
            "money_in": "I log money earned", "goal_hit": "I hit a money goal", "spend_over": f"spending passes £{tv or 30} this month",
            "lead_quiet": "a lead goes quiet", "deal_won": "a deal is won", "stream_start": "I go live", "stream_end": "my stream ends",
            "followers": "I pass a follower milestone", "site_down": f"{tv or 'my website'} goes down",
            "file_in": f"a new file lands in {tv or 'a folder'}"}.get(t["type"], t["type"])
    def act(a):
        return {"say": f"say “{a.get('value', '')}”", "notify": "message my phone", "do": f"do: {a.get('value', '')}",
            "open_app": f"open {a.get('value', '')}", "theme": f"switch to {a.get('value', '')} mode",
            "routine": f"run {a.get('value', '')}", "gaming": f"gaming mode {a.get('value', 'on')}",
            "focus": f"start a {a.get('value', 25)}-min focus session", "volume": f"set the volume to {a.get('value', 30)}%",
            "lock": "lock the screen", "power": {'restart': 'restart', 'sleep': 'put to sleep'}.get(a.get('value'), 'shut down') + ' the PC (60-second warning)',
            "sky": f"switch the sky to {a.get('value', 'night')}", "open_url": f"open {a.get('value', '')}",
            "webhook": "post to my webhook", "report": "send me the CEO report", "followups": "draft follow-ups",
            "backup": "back up ORION", "note": f"note “{a.get('value', '')}”", "remind": f"remind me in {a.get('value', 30)} min",
            "stream_recap": "send my stream recap"}.get(a["type"], a["type"])
    then = " → ".join(act(x) for x in [a] + list(r.get("then") or []))
    only = r.get("only") or {}
    extra = ""
    if only.get("from") and only.get("to"):
        extra += f" (only {only['from']}–{only['to']}"
        extra += f", {only['days']})" if only.get("days") and only["days"] != "daily" else ")"
    elif only.get("days") and only["days"] != "daily":
        extra += f" (only {only['days']})"
    return f"When {when} → {then}{extra}"


# ------------------------------------------------------------------ AI budget (so automations never eat your credits)
BUDGET = os.path.join(DATA_DIR, "ai_budget.json")


def budget_state(cfg):
    b = {}
    try:
        with open(BUDGET, encoding="utf-8") as f:
            b = json.load(f)
    except Exception:
        pass
    today = dt.date.today().isoformat()
    if b.get("date") != today:
        b = {"date": today, "used": 0}
    return {"date": today, "used": b.get("used", 0), "limit": int(cfg.get("ai_budget_auto", 15))}


def budget_take(cfg):
    """True if an automation may use AI now (and counts it)."""
    st = budget_state(cfg)
    if st["limit"] <= 0 or st["used"] >= st["limit"]:
        return False
    with _lock:
        write_json(BUDGET, {"date": st["date"], "used": st["used"] + 1})
    return True


def uses_ai(r):
    return any(x.get("type") in AI_ACTIONS for x in [r["action"]] + list(r.get("then") or []))


def add(name, trigger, action, cooldown=None, then=None, only=None):
    cooldown = cooldown or {"pc_start": 1, "money_in": 1, "deal_won": 1, "goal_hit": 1440, "stream_start": 1, "stream_end": 1,
                            "followers": 1, "lead_quiet": 1440, "spend_over": 10080, "site_down": 60, "file_in": 1, "weekly": 1440,
                            "os_start": 1, "unlock": 1, "wifi_join": 5, "offline": 10, "online": 10, "charger_in": 2,
                            "charger_out": 2}.get(trigger.get("type"))
    then = [x for x in (then or []) if x and x.get("type") in ACTIONS][:2]
    if trigger.get("type") not in TRIGGERS or action.get("type") not in ACTIONS:
        raise ValueError("Unknown trigger or action.")
    for x in [action] + then:
        if x["type"] in ("webhook", "open_url") and not str(x.get("value", "")).startswith("https://"):
            raise ValueError("Webhooks and websites need a full https:// address.")
    rules = load()
    r = {"id": "a" + uuid.uuid4().hex[:6], "name": (name or "").strip()[:50] or TRIGGERS[trigger["type"]], "trigger": trigger,
         "action": action, "on": True, "cooldown": int(cooldown or (720 if trigger["type"] in ("time", "sunset", "sunrise", "no_revision") else 20)),
         "last": 0, "runs": 0, "created": time.time(), "then": then, "only": only or {}}
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
        self.signals = []
        self.net = None
        self.ssid = None
        self.plugged = None
        self.net_checked = 0
        self.snap = {}                # money/CRM state between ticks
        self.sites = {}
        self.folders = {}
        self.slow_t = 0
        CTX["automate"] = self
        self.signal("pc_start")
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ signals
    def signal(self, kind, **ctx):
        """Events from elsewhere in ORION: os_start, unlock, pc_start, money_in, stream_start/end, followers…"""
        self.signals.append((kind, ctx))

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
        sigs, self.signals = self.signals, []
        sig = {k for k, _ in sigs}
        sigctx = {k: c for k, c in sigs}
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
        ev["signals"], ev["sigctx"] = sig, sigctx
        if types & {"goal_hit", "spend_over", "lead_quiet", "deal_won", "site_down"} and time.time() - self.slow_t > 60:
            self.slow_t = time.time()
            self._business(types, ev)
        if "file_in" in types:
            for r in rules:
                if r["trigger"]["type"] == "file_in":
                    d = os.path.expanduser(str(r["trigger"].get("value") or "~/Downloads"))
                    try:
                        now_f = {f for f in os.listdir(d) if not f.endswith((".crdownload", ".part", ".tmp"))}
                    except Exception:
                        continue
                    old = self.folders.get(d)
                    self.folders[d] = now_f
                    if old is not None and now_f - old:
                        ev.setdefault("folder_new", {})[d] = sorted(now_f - old)
        if types & {"offline", "online"} and time.time() - self.net_checked > 15:
            from .oslinux import online
            self.net_checked = time.time()
            n = online()
            ev["went_offline"], ev["went_online"] = self.net is True and not n, self.net is False and n
            self.net = n
        if "wifi_join" in types:
            from .oslinux import wifi_ssid
            w = wifi_ssid()
            ev["joined"] = w if w and w != self.ssid else None
            self.ssid = w
        if types & {"charger_in", "charger_out"}:
            b = psutil.sensors_battery()
            p = b.power_plugged if b else None
            ev["plug_in"], ev["plug_out"] = self.plugged is False and p is True, self.plugged is True and p is False
            self.plugged = p
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
        if ty in ("os_start", "unlock"):
            return {} if ty in ev.get("signals", ()) else None
        if ty == "wifi_join":
            j = ev.get("joined")
            return {"network": j} if j and (not v or str(v).lower() in j.lower()) else None
        if ty in ("offline", "online"):
            return {} if ev.get("went_" + ty) else None
        if ty in ("charger_in", "charger_out"):
            return {} if ev.get("plug_in" if ty == "charger_in" else "plug_out") else None
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
        if ty in ("pc_start", "money_in", "stream_start", "stream_end", "followers"):
            return dict(ev.get("sigctx", {}).get(ty) or {}) if ty in ev.get("signals", ()) else None
        if ty == "weekly":
            day, _, at = str(v or "mon 09:00").lower().partition(" ")
            return {} if now.strftime("%a").lower().startswith(day[:3]) and hm == (at or "09:00") else None
        if ty == "goal_hit":
            return {"goal": ev["goal_hit"]} if ev.get("goal_hit") else None
        if ty == "spend_over":
            sp = ev.get("spent_month")
            return {"spent": sp} if sp is not None and sp >= float(v or 30) else None
        if ty == "lead_quiet":
            return {"lead": ev["quiet_new"]} if ev.get("quiet_new") else None
        if ty == "deal_won":
            return {"client": ev["won_new"]} if ev.get("won_new") else None
        if ty == "site_down":
            return {"site": v} if ev.get("down", {}).get(v) else None
        if ty == "file_in":
            d = os.path.expanduser(str(v or "~/Downloads"))
            new = ev.get("folder_new", {}).get(d)
            return {"file": new[0]} if new else None
        if ty == "no_revision":
            if hm != (v or "19:30"):
                return None
            from .study import overview
            return {} if overview().get("today", 0) == 0 else None
        return None

    def _business(self, types, ev):
        """Money, CRM and website checks (once a minute, all free — no AI)."""
        if types & {"goal_hit"}:
            try:
                from .money import goals
                done = {g["name"] for g in goals() if g.get("pct", 0) >= 100}
                old = self.snap.get("goals")
                self.snap["goals"] = done
                if old is not None and done - old:
                    ev["goal_hit"] = sorted(done - old)[0]
            except Exception:
                pass
        if "spend_over" in types:
            try:
                from .ceo import expenses
                m = dt.date.today().strftime("%Y-%m")
                ev["spent_month"] = round(sum(x["amount"] for x in expenses() if x["date"].startswith(m)), 2)
            except Exception:
                pass
        if types & {"lead_quiet", "deal_won"}:
            try:
                from .money import crm, crm_followups
                quiet = {x["name"] for x in crm_followups()}
                won = {x["name"] for x in crm() if x["stage"] == "won"}
                oq, ow = self.snap.get("quiet"), self.snap.get("won")
                self.snap["quiet"], self.snap["won"] = quiet, won
                if oq is not None and quiet - oq:
                    ev["quiet_new"] = sorted(quiet - oq)[0]
                if ow is not None and won - ow:
                    ev["won_new"] = sorted(won - ow)[0]
            except Exception:
                pass
        if "site_down" in types:
            import requests
            ev["down"] = {}
            for r in load():
                u = r["trigger"].get("value")
                if r["trigger"]["type"] != "site_down" or not str(u or "").startswith("http") or len(str(u)) < 12:
                    continue
                if time.time() - self.sites.get(u, {}).get("t", 0) < 300:
                    continue
                try:
                    code = requests.get(u, timeout=12, headers={"User-Agent": "ORION uptime check"}).status_code
                    up = code < 500
                except Exception:
                    up = False
                prev = self.sites.get(u, {}).get("up", True)
                self.sites[u] = {"t": time.time(), "up": up}
                ev["down"][u] = prev and not up

    def _set(self, rid, **kw):
        rules = load()
        for x in rules:
            if x["id"] == rid:
                x.update(kw)
        save(rules)

    def _fire(self, r, ctx):
        only = r.get("only") or {}
        now = dt.datetime.now()
        if only.get("days") == "weekdays" and now.weekday() >= 5 or only.get("days") == "weekends" and now.weekday() < 5:
            return
        if only.get("from") and only.get("to"):
            hm = now.strftime("%H:%M")
            f, t = only["from"], only["to"]
            if not (f <= hm < t if f <= t else (hm >= f or hm < t)):
                return
        if uses_ai(r) and not ctx.get("test") and not budget_take(self.cfg):
            self._set(r["id"], last=time.time())
            self.emit("toast", level="warn", text=f"⚡ {r['name']} skipped — today's AI budget for automations is used up (saving your credits).")
            return
        self._set(r["id"], last=time.time(), runs=r.get("runs", 0) + 1)
        self.emit("toast", level="info", text=f"⚡ {r['name']}")
        self.emit("automation", id=r["id"], name=r["name"])
        try:
            self.run_action(r, ctx)
        except Exception as e:
            self.emit("toast", level="warn", text=f"Automation '{r['name']}' failed: {e}")


# ------------------------------------------------------------------ tools for the brain
@tool("AUTOMATION: create a 'when X happens, do Y' rule that runs by itself. trigger: app_open, app_close, game_start, game_end, "
      "away, back, time, sunset, sunrise, rain_soon, cpu_high, ram_high, disk_low, battery_low, new_download, no_revision, "
      "pc_start, weekly (value 'mon 08:00'), money_in, goal_hit, spend_over (value £), lead_quiet, deal_won, stream_start, stream_end, "
      "followers, site_down (value https URL), file_in (value folder), "
      "and on ORION OS: os_start, unlock, wifi_join, offline, online, charger_in, charger_out. "
      "trigger_value: app name / minutes / HH:MM / GB / % / file extension / Wi-Fi name. action: say, notify, do, open_app, theme, "
      "routine, gaming, focus, open_url, webhook (https URL, e.g. a Discord webhook), report, followups, backup, note, remind (minutes), "
      "stream_recap, and on ORION OS: volume, lock, power, sky. Prefer actions that need no AI (say/notify/report) — only 'do' and "
      "'followups' use AI credits. action_value: what to say / instruction to do / app / "
      "mode / routine / on|off / minutes / volume % / shutdown|restart|sleep / night|aurora|dawn|deep. "
      "e.g. 'when I open Fortnite turn on gaming mode', 'if I haven't revised by 7:30 nag me'.",
      {"name": ("string", "Short name", False), "trigger": ("string", "Trigger type", True),
       "then": ("string", "Optional second step as 'action: value' (e.g. 'say: you're live')", False),
       "only_between": ("string", "Optional time window 'HH:MM-HH:MM'", False),
       "trigger_value": ("string", "Value for the trigger", False), "days": ("string", "daily | weekdays | weekends (time triggers)", False),
       "action": ("string", "Action type", True), "action_value": ("string", "Value for the action", False)})
def automation_add(trigger, action, name="", trigger_value="", days="daily", action_value="", then="", only_between=""):
    t = {"type": trigger}
    if trigger_value:
        t["value"] = float(trigger_value) if trigger in ("away", "back", "disk_low", "battery_low", "ram_high", "spend_over") else trigger_value
    if trigger in ("time", "no_revision", "sunset", "sunrise"):
        t["days"] = days if days in ("daily", "weekdays", "weekends") else "daily"
    try:
        th = []
        if then and ":" in then:
            k, _, val = then.partition(":")
            th = [{"type": k.strip(), "value": val.strip()}]
        only = {}
        if only_between and "-" in only_between:
            f_, _, t_ = only_between.partition("-")
            only = {"from": f_.strip()[:5], "to": t_.strip()[:5]}
        r = add(name, t, {"type": action, "value": action_value}, then=th, only=only)
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


@tool("How much of today's AI budget automations have used (they stop using AI once it's spent, to save credits).")
def automation_budget():
    st = budget_state(CTX.get("config") or {})
    return f"Automations have used {st['used']} of {st['limit']} AI runs today. Most automations use no AI at all."

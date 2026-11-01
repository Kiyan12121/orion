"""Gaming Mode: spots a game starting, boosts performance, keeps ORION quiet, holds non-urgent
notifications until you're done, and gives you a push-to-talk hotkey that works inside games."""
import glob
import json
import os
import platform
import re
import subprocess
import threading
import time

from .paths import DATA_DIR
from .tools import CTX, REGISTRY, tool

STATS = os.path.join(DATA_DIR, "gamestats.json")
CLIPS = os.path.join(os.path.expanduser("~"), "Videos", "ORION Clips")
BUF = os.path.join(DATA_DIR, "clipbuffer")
# background stuff that's safe to slow down while you play (restored afterwards)
BACKGROUND = ["OneDrive.exe", "SearchIndexer.exe", "MsMpEngSvc.exe", "Teams.exe", "ms-teams.exe", "msedge.exe",
              "chrome.exe", "Spotify.exe", "EpicWebHelper.exe", "steamwebhelper.exe", "GoogleDriveFS.exe",
              "Dropbox.exe", "AdobeUpdateService.exe", "CompPkgSrv.exe"]


def _stats():
    try:
        with open(STATS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sessions": []}


def record_session(game, start, mins):
    if mins < 2:
        return
    s = _stats()
    s["sessions"].append({"game": game, "start": start, "mins": mins, "day": time.strftime("%Y-%m-%d", time.localtime(start))})
    s["sessions"] = s["sessions"][-2000:]
    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


def game_stats(days=7):
    s = _stats()["sessions"]
    since = time.time() - days * 86400
    recent = [x for x in s if x["start"] > since]
    per = {}
    for x in recent:
        per[x["game"]] = per.get(x["game"], 0) + x["mins"]
    daily = []
    for k in range(days - 1, -1, -1):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - k * 86400))
        daily.append({"day": d[5:], "mins": sum(x["mins"] for x in s if x["day"] == d)})
    return {"total_mins": sum(per.values()), "sessions": len(recent), "by_game": sorted(per.items(), key=lambda kv: -kv[1]),
            "daily": daily, "longest": max((x["mins"] for x in recent), default=0),
            "all_time_hours": round(sum(x["mins"] for x in s) / 60, 1)}


def nice_name(exe):
    n = (exe or "game").replace(".exe", "").replace("PlayerBeta", "").replace("-Win64-Shipping", "")
    return {"Roblox": "Roblox", "Minecraft.Windows": "Minecraft", "javaw": "Minecraft (Java)", "cs2": "CS2",
            "FortniteClient": "Fortnite", "VALORANT": "Valorant", "GTA5": "GTA V"}.get(n, n)

IS_WIN = platform.system() == "Windows"
FLAGS = 0x08000000 if IS_WIN else 0
HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"   # Windows "High performance" plan

try:
    import psutil
except Exception:
    psutil = None


def _ps(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, creationflags=FLAGS, timeout=10).stdout
    except Exception:
        return ""


class GamingMode:
    def __init__(self, cfg, emit, notify, brain):
        self.cfg = cfg
        self.emit = emit
        self.notify = notify            # notify(text, important)
        self.brain = brain
        self.active = False
        self.game = None
        self.manual = False
        self.held = []
        self.prev_plan = None
        self.started = 0
        self.nudged = 0
        self.lowered = []
        self.buffer = None
        CTX["party_reminder"] = self.party_reminder
        CTX["gaming"] = self
        threading.Thread(target=self._watch, daemon=True).start()

    @property
    def g(self):
        return self.cfg.setdefault("gaming", {})

    def _running_game(self):
        if psutil is None:
            return None
        games = {x.lower() for x in self.g.get("games", [])}
        for p in psutil.process_iter(["name"]):
            n = (p.info["name"] or "").lower()
            if n in games:
                return p.info["name"]
        return None

    def _watch(self):
        while True:
            try:
                if self.g.get("auto", True):
                    game = self._running_game()
                    if game and not self.active:
                        self.enter(game)
                    elif not game and self.active and not self.manual:
                        self.exit()
                if self.active:
                    self._break_nudge()
                    self._doctor()
            except Exception:
                pass
            time.sleep(5)

    def enter(self, game="manual", manual=False):
        if self.active:
            return
        self.active, self.game, self.manual, self.started = True, game, manual, time.time()
        self.held = []
        boosted = []
        if IS_WIN and self.g.get("high_performance", True):
            m = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27})", _ps("powercfg /getactivescheme"), re.I)
            self.prev_plan = m.group(1) if m else None
            if self.prev_plan and self.prev_plan.lower() != HIGH_PERF:
                _ps(f"powercfg /setactive {HIGH_PERF}")
                boosted.append("high-performance power")
        closed = []
        if psutil:
            targets = {x.lower() for x in self.g.get("close_apps", [])}
            for p in psutil.process_iter(["name"]):
                n = (p.info["name"] or "").lower()
                if n in targets:
                    try:
                        p.terminate()
                        closed.append(p.info["name"])
                    except Exception:
                        pass
        if closed:
            boosted.append(f"closed {', '.join(sorted(set(closed)))}")
        if self.g.get("boost", True):
            n = self._boost(game)
            if n:
                boosted.append(f"slowed {n} background app(s)")
        self.session_clips, self.doctor_notes = 0, []
        prof = self.g.get("profiles", {}).get(nice_name(game), {})
        if prof:
            threading.Thread(target=self._apply_profile, args=(prof,), daemon=True).start()
            boosted.append(f"{nice_name(game)} profile")
        if self.g.get("clip_buffer", False) and not CTX.get("lite"):
            self._start_buffer()
        self.brain.force_cloud = True          # keep the CPU free for the game
        self.prev_theme = self.cfg.get("theme", "standby")
        if self.g.get("stealth_while_gaming", True) and self.prev_theme != "stealth" and CTX.get("set_theme"):
            CTX["set_theme"]("stealth")
        name = game.replace(".exe", "").replace("PlayerBeta", "")
        self.emit("gaming", on=True, game=name)
        self.emit("toast", level="info", text=f"Gaming Mode: {name}" + (f" — {', '.join(boosted)}" if boosted else ""))

    def exit(self):
        if not self.active:
            return
        self.active, self.manual = False, False
        if IS_WIN and self.prev_plan and self.prev_plan.lower() != HIGH_PERF:
            _ps(f"powercfg /setactive {self.prev_plan}")
        self.brain.force_cloud = False
        prev = getattr(self, "prev_theme", None)
        if prev and prev != "stealth" and self.cfg.get("theme") == "stealth" and CTX.get("set_theme"):
            CTX["set_theme"](prev)
        self.emit("gaming", on=False, game=None)
        mins = int((time.time() - self.started) // 60)
        self._unboost()
        self._stop_buffer()
        if self.game and self.game != "manual":
            record_session(nice_name(self.game), self.started, mins)
        self.nudged = 0
        title = self.cfg.get("user_title", "sir")
        bits = [f"Well played, {title}. {mins // 60}h {mins % 60}m of {nice_name(self.game)}" if mins >= 60
                else f"Well played, {title}. {mins} minutes of {nice_name(self.game)}"]
        clips = getattr(self, "session_clips", 0)
        if clips:
            bits.append(f"{clips} clip{'s' if clips != 1 else ''} saved")
        if self.held:
            bits.append(f"while you played: {'; '.join(self.held[:6])}")
        else:
            bits.append("nothing needed your attention")
        if getattr(self, "doctor_notes", None):
            bits.append("performance: " + "; ".join(self.doctor_notes[:2]))
        self.notify(". ".join(bits) + ".", bool(self.held))
        CTX.get("emit", lambda *a, **k: None)("gaming_wrap", text=". ".join(bits))
        self.held = []

    def hold(self, text):
        """Called for non-urgent notifications while gaming."""
        self.held.append(text)

    # -------------------------------------------------- 3.0: break reminders, booster, clips, parties
    def _break_nudge(self):
        every = int(self.g.get("break_every_min", 120) or 0)
        if not every:
            return
        played = (time.time() - self.started) / 60
        if played >= every * (self.nudged + 1):
            self.nudged += 1
            h = played / 60
            self.notify(f"You've been on {nice_name(self.game)} for {h:.1f} hours, {self.cfg.get('user_title', 'sir')}. "
                        "Might be worth a stretch and some water.", True)

    def _apply_profile(self, prof):
        """Per-game profile: open/close apps when this game starts."""
        run = CTX.get("toolbox_run")
        for app in prof.get("open", []):
            try:
                run and run("open_app", {"name": app})
            except Exception:
                pass
        if psutil:
            close = {x.lower() for x in prof.get("close", [])}
            for p in psutil.process_iter(["name"]):
                try:
                    if (p.info["name"] or "").lower() in close:
                        p.terminate()
                except Exception:
                    pass

    def _doctor(self):
        """Performance doctor: if the PC is struggling mid-game, find the culprit and calm it down."""
        if not psutil or time.time() - getattr(self, "_doc_t", 0) < 60:
            return
        self._doc_t = time.time()
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            if cpu < 92 and ram < 90:
                self._hot = 0
                return
            self._hot = getattr(self, "_hot", 0) + 1
            if self._hot < 2:
                return
            game = (self.game or "").lower()
            hogs = []
            for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
                n = (p.info["name"] or "").lower()
                if n and n != game and n not in ("system idle process", "system", "pythonw.exe", "python.exe"):
                    hogs.append((p.info["cpu_percent"] or 0, p.info["memory_percent"] or 0, p))
            hogs.sort(key=lambda h: -(h[0] if cpu >= 92 else h[1]))
            if hogs:
                c, m, p = hogs[0]
                try:
                    p.nice(psutil.IDLE_PRIORITY_CLASS)
                    self.lowered.append(p.pid)
                except Exception:
                    pass
                note = (f"{p.info['name']} was eating {'CPU' if cpu >= 92 else 'RAM'} "
                        f"({c:.0f}% CPU, {m:.0f}% RAM) — I've turned it right down")
                self.doctor_notes.append(note)
                self.hold("⚙ " + note)
                self._hot = 0
        except Exception:
            pass

    def _boost(self, game):
        """Game gets high priority; known background apps drop to below-normal (restored on exit)."""
        if not (psutil and IS_WIN):
            return 0
        self.lowered = []
        bg = {x.lower() for x in self.g.get("background", BACKGROUND)}
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info["name"] or "").lower()
                if game and n == game.lower():
                    p.nice(psutil.HIGH_PRIORITY_CLASS)
                elif n in bg:
                    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    self.lowered.append(p.pid)
            except Exception:
                pass
        return len(self.lowered)

    def _unboost(self):
        for pid in self.lowered:
            try:
                psutil.Process(pid).nice(psutil.NORMAL_PRIORITY_CLASS)
            except Exception:
                pass
        self.lowered = []

    def _start_buffer(self):
        """Rolling recording of the last ~60s (light settings) so 'clip that' works without Game Bar."""
        try:
            from .video import ffmpeg as _ffmpeg
            ff = _ffmpeg()
        except Exception:
            ff = None
        if not ff:
            return
        os.makedirs(BUF, exist_ok=True)
        for f in glob.glob(os.path.join(BUF, "*.ts")):
            try:
                os.remove(f)
            except Exception:
                pass
        cmd = [ff, "-loglevel", "error", "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
               "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
               "-f", "segment", "-segment_time", "10", "-segment_wrap", "7", "-reset_timestamps", "1",
               os.path.join(BUF, "seg%d.ts")]
        try:
            self.buffer = subprocess.Popen(cmd, creationflags=FLAGS, stdin=subprocess.PIPE)
        except Exception:
            self.buffer = None

    def _stop_buffer(self):
        if self.buffer:
            try:
                self.buffer.communicate(b"q", timeout=5)
            except Exception:
                try:
                    self.buffer.kill()
                except Exception:
                    pass
            self.buffer = None

    def clip(self, seconds=30):
        os.makedirs(CLIPS, exist_ok=True)
        out = os.path.join(CLIPS, f"{nice_name(self.game or 'clip')} {time.strftime('%Y-%m-%d %H-%M-%S')}.mp4")
        segs = sorted(glob.glob(os.path.join(BUF, "seg*.ts")), key=os.path.getmtime)
        if self.buffer and segs:
            from .video import ffmpeg as _ffmpeg
            need = max(1, min(len(segs), int(seconds // 10) + 1))
            # the newest segment is still being written; include it (ffmpeg copes) for the freshest moment
            pick = segs[-need:]
            lst = os.path.join(BUF, "list.txt")
            with open(lst, "w", encoding="utf-8") as f:
                f.write("".join(f"file '{p}'\n" for p in pick))
            r = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                                "-c", "copy", out], capture_output=True, creationflags=FLAGS, timeout=60)
            if r.returncode == 0 and os.path.exists(out):
                self.session_clips = getattr(self, "session_clips", 0) + 1
                return f"Clipped the last ~{need * 10}s → {out}"
        # fall back to Windows Game Bar's "record that" (Win+Alt+G) — needs background recording on
        try:
            import pyautogui
            pyautogui.hotkey("win", "alt", "g")
            return ("Asked Windows Game Bar to save the last 30 seconds (it lands in Videos\\Captures). If nothing "
                    "saves, turn on ORION's own clip buffer in the Gaming page.")
        except Exception as e:
            return f"ERROR: couldn't clip ({e})."

    def party_reminder(self, o, when):
        """Party booked with friends: DM each of them when the reminder fires."""
        friends = [x.strip() for x in str(o.get("notes", ""))[6:].split(",") if x.strip()]
        send = REGISTRY.get("root_send_message", {}).get("fn")
        if not send:
            return
        for f in friends[:8]:
            try:
                send(f, f"Hey {f}, {o['title']} is starting {when}! Hop on 🎮 — sent by {self.cfg.get('owner_name', 'Kiyan')}'s assistant")
            except Exception:
                pass


@tool("Turn Gaming Mode on or off manually (it also switches on automatically when a game starts).",
      {"on": ("boolean", "True = on, False = off", True)})
def gaming_mode(on):
    gm = CTX.get("gaming")
    if not gm:
        return "Gaming Mode isn't available."
    if on:
        gm.enter("manual", manual=True)
        return "Gaming Mode on."
    gm.exit()
    return "Gaming Mode off."


@tool("Set up a per-game PROFILE: apps to open and close automatically when a game starts.",
      {"game": ("string", "Game name, e.g. Roblox", True), "open": ("array", "Apps to open, e.g. ['Discord']", False),
       "close": ("array", "Processes to close, e.g. ['chrome.exe']", False)})
def game_profile(game, open=None, close=None):
    gm = CTX.get("gaming")
    if not gm:
        return "Gaming Mode isn't available."
    prof = gm.g.setdefault("profiles", {}).setdefault(nice_name(game) if game.endswith(".exe") else game.strip().title(), {})
    if open is not None:
        prof["open"] = list(open)
    if close is not None:
        prof["close"] = list(close)
    from . import config as config_mod
    config_mod.save(gm.cfg)
    return f"{game.title()} profile: opens {', '.join(prof.get('open', [])) or 'nothing'}, closes {', '.join(prof.get('close', [])) or 'nothing'}."


class Controller:
    """Hold the controller's View/Back button for half a second to talk to ORION (XInput pads)."""

    def __init__(self, cfg, talk):
        self.cfg, self.talk = cfg, talk
        if IS_WIN:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        import ctypes

        class GP(ctypes.Structure):
            _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

        class ST(ctypes.Structure):
            _fields_ = [("packet", ctypes.c_uint), ("pad", GP)]
        try:
            x = ctypes.windll.xinput1_4
        except Exception:
            try:
                x = ctypes.windll.xinput9_1_0
            except Exception:
                return
        BACK = 0x0020
        held = 0.0
        while True:
            if not self.cfg.get("gaming", {}).get("controller_talk", True):
                time.sleep(2)
                continue
            st = ST()
            pressed = False
            for i in range(4):
                if x.XInputGetState(i, ctypes.byref(st)) == 0 and st.pad.buttons & BACK:
                    pressed = True
                    break
            held = held + 0.05 if pressed else 0.0
            if 0.5 <= held < 0.55:
                threading.Thread(target=self.talk, daemon=True).start()
            time.sleep(0.05)


@tool("CLIP THAT: save the last ~30 seconds of gameplay/screen as a video clip.",
      {"seconds": ("integer", "How many seconds back (10-60)", False)})
def clip_that(seconds=30):
    gm = CTX.get("gaming")
    if not gm:
        return "Gaming Mode isn't available."
    return gm.clip(max(10, min(int(seconds or 30), 60)))


@tool("Gaming stats: hours played per game, sessions, daily time this week.",
      {"days": ("integer", "How many days back (default 7)", False)})
def gaming_stats(days=7):
    s = game_stats(int(days or 7))
    if not s["sessions"]:
        return "No games recorded yet."
    games = ", ".join(f"{g} {m // 60}h{m % 60:02d}m" for g, m in s["by_game"])
    return (f"Last {days} days: {s['total_mins'] // 60}h {s['total_mins'] % 60}m over {s['sessions']} sessions "
            f"(longest {s['longest']} min). By game: {games}. All time: {s['all_time_hours']} h.")


@tool("PARTY PLANNER: book a gaming session with friends — adds it to the schedule and DMs each friend on Root "
      "now, then pings them again when it's about to start.",
      {"game": ("string", "What you're playing", True),
       "start": ("string", "When, as 'YYYY-MM-DD HH:MM' (work it out from today)", True),
       "friends": ("array", "Root names of the friends to invite", True),
       "minutes": ("integer", "How long (default 120)", False)}, dangerous=True)
def party_plan(game, start, friends, minutes=120):
    from .schedule import add_event, _parse
    friends = [f.strip() for f in (friends or []) if f.strip()][:8]
    if not friends:
        return "ERROR: who's invited?"
    e = add_event(f"🎮 {game} party", start, int(minutes or 120), "none", 10, False, ", ".join(friends)[:40],
                  "PARTY:" + ",".join(friends))
    when = _parse(start).strftime("%A at %H:%M")
    owner = CTX.get("config", {}).get("owner_name", "Kiyan")
    send = REGISTRY.get("root_send_message", {}).get("fn")
    sent = []
    for f in friends:
        try:
            r = send(f, f"Hey {f}! {owner}'s booked {game} for {when} — you in? 🎮 (sent by {owner}'s assistant)")
            sent.append(f if not str(r).startswith("ERROR") else f"{f} (failed)")
        except Exception:
            sent.append(f"{f} (failed)")
    return f"Booked {game} for {when} (event {e['id']}). Invited: {', '.join(sent)}. I'll remind everyone 10 min before."


class Hotkey:
    """Global push-to-talk: press once to start listening, press again to send. Works in games."""

    def __init__(self, combo, start, stop):
        self.ok = False
        self.on = False
        try:
            import keyboard
            keyboard.add_hotkey(combo, self._toggle, suppress=False)
            self.ok = True
        except Exception:
            pass
        self.start, self.stop = start, stop

    def _toggle(self):
        threading.Thread(target=self.start, daemon=True).start()     # start() toggles: listen / send now

"""Night Shift: things ORION does on its own, on a schedule.

Built-in routines (plain code, no AI, safe):
  tidy_downloads  — sorts old files in Downloads into Downloads/Sorted/<type> (moves, never deletes)
  clear_temp      — removes Windows temp files older than 3 days
  backup          — zips ORION's projects, skills and memory into Documents/ORION Backups (keeps last 7)
  health          — disk space, RAM, biggest folders, uptime → report
  updates         — checks for a new ORION version
  content         — new videos in your Videos folder → auto-cut + 3 Shorts + titles
  coding_queue    — runs anything you queued for overnight

Custom routines: any instruction + time + days, e.g. "every weekday at 07:00: summarise my Root DMs".
Morning report: what happened overnight, pushed to your phone.
"""
import datetime as dt
import glob
import json
import os
import shutil
import threading
import time
import uuid
import zipfile

from .paths import APP_DIR, DATA_DIR, PROJECTS_DIR, SKILLS_DIR
from .tools import CTX, tool

STATE = os.path.join(DATA_DIR, "routines_state.json")
VIDEO_EXT = (".mp4", ".mkv", ".mov", ".webm")
TYPES = {"Images": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"),
         "Videos": VIDEO_EXT + (".avi", ".flv"), "Audio": (".mp3", ".wav", ".ogg", ".m4a", ".flac"),
         "Documents": (".pdf", ".docx", ".doc", ".txt", ".pptx", ".xlsx", ".csv", ".md", ".odt"),
         "Installers": (".exe", ".msi"), "Archives": (".zip", ".rar", ".7z", ".tar", ".gz"),
         "Code": (".py", ".js", ".lua", ".json", ".html", ".css", ".bat", ".ps1", ".jar")}

BUILTIN = {
    "tidy_downloads": {"name": "Tidy Downloads", "time": "02:00", "days": "daily", "heavy": False,
                       "desc": "Sorts files older than 7 days into Downloads\\Sorted\\<type>. Moves, never deletes."},
    "clear_temp":     {"name": "Clear temp junk", "time": "02:05", "days": "daily", "heavy": False,
                       "desc": "Removes Windows temp files older than 3 days to free space."},
    "backup":         {"name": "Back up ORION", "time": "02:10", "days": "daily", "heavy": False,
                       "desc": "Zips your projects, skills and memory into Documents\\ORION Backups (keeps 7)."},
    "health":         {"name": "PC health check", "time": "02:15", "days": "daily", "heavy": False,
                       "desc": "Disk space, RAM, uptime and the biggest space-wasters."},
    "updates":        {"name": "Check for updates", "time": "02:20", "days": "daily", "heavy": False,
                       "desc": "Looks for a new ORION version on GitHub."},
    "content":        {"name": "Content: new videos → Shorts", "time": "03:00", "days": "daily", "heavy": True,
                       "desc": "Any new video in your Videos folder gets auto-cut, plus 3 captioned Shorts and titles."},
    "learn":          {"name": "Learn from the day", "time": "02:30", "days": "daily", "heavy": False,
                       "desc": "Pulls new facts about you from today's chats and spots things you ask a lot (→ shortcuts)."},
    "devqueue":       {"name": "Dev queue (Hatchlands etc.)", "time": "01:00", "days": "daily", "heavy": True,
                       "desc": "Works through your coding to-do list overnight and saves the scripts for review."},
    "report":         {"name": "Morning report", "time": "07:30", "days": "daily", "heavy": False,
                       "desc": "Sends your phone a summary of everything ORION did overnight."},
}
DEFAULT_ON = {"tidy_downloads", "clear_temp", "backup", "health", "updates", "report", "learn", "devqueue"}
DAYS = {"daily": [0, 1, 2, 3, 4, 5, 6], "weekdays": [0, 1, 2, 3, 4], "weekends": [5, 6]}


def _state():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_run": {}, "videos_seen": [], "last_report": 0, "results": {}}


def _save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


def _days(d):
    if isinstance(d, list):
        return d
    return DAYS.get(d, DAYS["daily"])


def _size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# ------------------------------------------------------------------ built-in jobs (plain code)
def tidy_downloads(days_old=7):
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(dl):
        return "No Downloads folder."
    cutoff = time.time() - days_old * 86400
    moved = {}
    for name in os.listdir(dl):
        p = os.path.join(dl, name)
        if not os.path.isfile(p) or os.path.getmtime(p) > cutoff or name.lower().endswith((".crdownload", ".part", ".tmp")):
            continue
        ext = os.path.splitext(name)[1].lower()
        folder = next((k for k, v in TYPES.items() if ext in v), "Other")
        dest_dir = os.path.join(dl, "Sorted", folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name)
        i = 1
        while os.path.exists(dest):
            b, e = os.path.splitext(name)
            dest = os.path.join(dest_dir, f"{b} ({i}){e}")
            i += 1
        try:
            shutil.move(p, dest)
            moved[folder] = moved.get(folder, 0) + 1
        except Exception:
            pass
    if not moved:
        return "Downloads already tidy."
    return "Sorted " + ", ".join(f"{n} {k.lower()}" for k, n in moved.items()) + " into Downloads\\Sorted."


def clear_temp(days_old=3):
    tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if not tmp or not os.path.isdir(tmp) or "temp" not in tmp.lower():
        return "Temp folder not found."
    cutoff = time.time() - days_old * 86400
    freed = count = 0
    for root, dirs, files in os.walk(tmp, topdown=False):
        for f in files:
            p = os.path.join(root, f)
            try:
                if os.path.getmtime(p) < cutoff:
                    s = os.path.getsize(p)
                    os.remove(p)
                    freed += s
                    count += 1
            except Exception:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))      # only removes folders that are now empty
            except Exception:
                pass
    return f"Cleared {count} old temp files ({_size(freed)})."


def backup():
    dest_dir = os.path.join(os.path.expanduser("~"), "Documents", "ORION Backups")
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, dt.datetime.now().strftime("orion_%Y-%m-%d.zip"))
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, arc in ((PROJECTS_DIR, "projects"), (SKILLS_DIR, "skills")):
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".venv", "build", "dist")]
                for f in files:
                    p = os.path.join(root, f)
                    if os.path.getsize(p) < 50 * 2**20:
                        z.write(p, os.path.join(arc, os.path.relpath(p, base)))
                        n += 1
        for f in ("memory.json", "schedule.json", "jobs.json", "routines_state.json"):
            p = os.path.join(DATA_DIR, f)
            if os.path.exists(p):
                z.write(p, os.path.join("data", f))
                n += 1
        cfg = os.path.join(APP_DIR, "config.json")
        if os.path.exists(cfg):
            z.write(cfg, "config.json")
    old = sorted(glob.glob(os.path.join(dest_dir, "orion_*.zip")))[:-7]
    for o in old:
        try:
            os.remove(o)
        except Exception:
            pass
    return f"Backed up {n} files ({_size(os.path.getsize(out))}) to Documents\\ORION Backups."


def health():
    import psutil
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    vm = psutil.virtual_memory()
    up = dt.timedelta(seconds=int(time.time() - psutil.boot_time()))
    lines = [f"Disk {disk.percent:.0f}% full ({_size(disk.free)} free)", f"RAM {vm.percent:.0f}% in use",
             f"Uptime {up.days}d {up.seconds // 3600}h"]
    if up.days >= 5:
        lines.append("Tip: a restart would help — it's been on for days.")
    big = []
    home = os.path.expanduser("~")
    for d in ("Downloads", "Videos", "Desktop", "Documents"):
        p = os.path.join(home, d)
        total = 0
        for root, _, files in os.walk(p):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
        big.append((total, d))
    big.sort(reverse=True)
    lines.append("Biggest folders: " + ", ".join(f"{d} {_size(t)}" for t, d in big[:3]))
    if disk.percent > 90:
        lines.append("⚠ Disk is nearly full.")
    return " · ".join(lines)


def new_videos(state):
    vids = []
    for d in ("Videos",):
        for ext in VIDEO_EXT:
            vids += glob.glob(os.path.join(os.path.expanduser("~"), d, "**", "*" + ext), recursive=True)
    seen = set(state.get("videos_seen", []))
    fresh = [v for v in vids if v not in seen and not any(t in os.path.basename(v)
             for t in ("_cut", "_captioned", "_shorts", "clip"))
             and "_shorts" not in v and time.time() - os.path.getmtime(v) > 600]
    return sorted(fresh, key=os.path.getmtime)[-3:]


# ------------------------------------------------------------------ the engine
class NightShift:
    def __init__(self, cfg, jobs, notify, emit, updater=None):
        self.cfg = cfg
        self.jobs = jobs
        self.notify = notify
        self.emit = emit
        self.updater = updater
        CTX["night_shift"] = self
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def ns(self):
        n = self.cfg.setdefault("night_shift", {})
        n.setdefault("enabled", True)
        n.setdefault("idle_minutes", 10)
        n.setdefault("builtin", {k: {"on": k in DEFAULT_ON, "time": v["time"]} for k, v in BUILTIN.items()})
        for k, v in BUILTIN.items():
            n["builtin"].setdefault(k, {"on": k in DEFAULT_ON, "time": v["time"]})
        n.setdefault("custom", [])
        return n

    def listing(self):
        st = _state()
        out = []
        for k, v in BUILTIN.items():
            b = self.ns["builtin"][k]
            out.append({"id": k, "name": v["name"], "desc": v["desc"], "time": b["time"], "days": "daily",
                        "on": b["on"], "builtin": True, "last": st["last_run"].get(k),
                        "result": st.get("results", {}).get(k, "")})
        for c in self.ns["custom"]:
            out.append({**c, "builtin": False, "desc": c["prompt"], "last": st["last_run"].get(c["id"]),
                        "result": st.get("results", {}).get(c["id"], "")})
        return {"enabled": self.ns["enabled"], "idle_minutes": self.ns["idle_minutes"], "routines": out}

    def _loop(self):
        time.sleep(30)
        while True:
            try:
                if self.ns["enabled"]:
                    self.tick()
            except Exception:
                pass
            time.sleep(30)

    def _due(self, rid, hhmm, days, st):
        now = dt.datetime.now()
        if now.weekday() not in _days(days):
            return False
        try:
            h, m = map(int, hhmm.split(":"))
        except ValueError:
            return False
        due = now.replace(hour=h, minute=m, second=0, microsecond=0)
        last = st["last_run"].get(rid, 0)
        # run if we're past today's time and haven't run since (catches up if the PC was off/asleep at that time)
        return now >= due and last < due.timestamp() and now - due < dt.timedelta(hours=10)

    def tick(self):
        st = _state()
        for k, v in BUILTIN.items():
            b = self.ns["builtin"][k]
            if b["on"] and self._due(k, b["time"], "daily", st):
                st["last_run"][k] = time.time()
                _save_state(st)
                self.run_builtin(k)
        for c in self.ns["custom"]:
            if c.get("on", True) and self._due(c["id"], c["time"], c.get("days", "daily"), st):
                st["last_run"][c["id"]] = time.time()
                _save_state(st)
                self.jobs.add(c["prompt"], source="routine", title=f"⏰ {c['name']}", heavy=c.get("heavy", False),
                              notify=c.get("notify", True), routine=c["id"])

    def run_builtin(self, k):
        """Quick upkeep runs straight away in a thread; AI/heavy work goes through the job queue."""
        if CTX.get("lite") and k in ("content", "devqueue"):
            self._record(k, "Skipped — this machine is in Lite mode.")
            return
        if k == "content":
            st = _state()
            vids = new_videos(st)
            st["videos_seen"] = (st.get("videos_seen", []) + vids)[-500:]
            _save_state(st)
            for v in vids:
                self.jobs.add(f"For the video {v}: run video_autocut, then video_shorts with 3 shorts, then "
                              f"video_metadata. Report the output files.", source="routine",
                              title=f"🎬 Shorts from {os.path.basename(v)}", heavy=True)
            self._record(k, f"Queued {len(vids)} new video(s)." if vids else "No new videos.")
            return
        if k == "report":
            self.morning_report()
            return
        if k == "devqueue":
            try:
                from .ventures import queue_dev_tasks
                self._record(k, queue_dev_tasks(self.jobs))
            except Exception as e:
                self._record(k, f"Failed: {e}")
            return
        if k == "learn":
            def learn():
                res = []
                mem, brain = CTX.get("memory"), CTX.get("brain")
                if mem and brain and mem.history:
                    res.append(f"learned {mem.learn_from_chat(brain)} new fact(s)")
                from .learning import nightly_digest
                tip = nightly_digest()
                if tip:
                    res.append(tip)
                self._record(k, "; ".join(res) or "Nothing new.")
            threading.Thread(target=learn, daemon=True).start()
            return

        def run():
            fn = {"tidy_downloads": tidy_downloads, "clear_temp": clear_temp, "backup": backup, "health": health,
                  "updates": self._updates}[k]
            try:
                res = fn()
            except Exception as e:
                res = f"Failed: {e}"
            self._record(k, res)
        threading.Thread(target=run, daemon=True).start()

    def _updates(self):
        if not self.updater:
            return "Updater unavailable."
        u = self.updater.check()
        return f"Update {u['version']} available — open Devices to install." if u else "ORION is up to date."

    def _record(self, k, res):
        st = _state()
        st.setdefault("results", {})[k] = f"{time.strftime('%a %H:%M')}: {res}"
        st.setdefault("log", []).append({"t": time.time(), "id": k, "text": res})
        st["log"] = st["log"][-200:]
        _save_state(st)
        self.emit("routines_changed")

    def morning_report(self):
        st = _state()
        since = st.get("last_report", 0) or (time.time() - 86400)
        lines = []
        for e in st.get("log", []):
            if e["t"] > since and e["id"] != "report":
                lines.append(f"• {BUILTIN.get(e['id'], {}).get('name', e['id'])}: {e['text']}")
        for j in self.jobs.since(since):
            lines.append(f"• {'✅' if j['status'] == 'done' else '⚠️'} {j['title']}: {(j['result'] or '')[:140]}")
        try:
            from .study import overview
            o = overview()
            if o["exams"]:
                e = o["exams"][0]
                lines.append(f"• 📚 {e['subject']} in {e['days']} day(s). Revision streak: {o['streak']} day(s).")
        except Exception:
            pass
        try:
            from .schedule import briefing_text
            lines.append(briefing_text(self.cfg.get("user_title", "sir")))
        except Exception:
            pass
        st["last_report"] = time.time()
        _save_state(st)
        text = "Overnight:\n" + "\n".join(lines) if len(lines) > 1 else (lines[0] if lines else "Quiet night, nothing to report.")
        self._record("report", "Sent.")
        self.notify(text, "ORION morning report")
        return text

    # -------------------------------------------------- editing
    def set_builtin(self, k, on=None, hhmm=None):
        b = self.ns["builtin"][k]
        if on is not None:
            b["on"] = bool(on)
        if hhmm:
            b["time"] = hhmm
        self._persist()

    def add_custom(self, name, prompt, hhmm, days="daily", heavy=False):
        c = {"id": "c" + uuid.uuid4().hex[:6], "name": name.strip()[:60] or prompt[:40], "prompt": prompt.strip(),
             "time": hhmm, "days": days, "heavy": bool(heavy), "on": True, "notify": True}
        self.ns["custom"].append(c)
        self._persist()
        return c

    def remove_custom(self, cid):
        self.ns["custom"] = [c for c in self.ns["custom"] if c["id"] != cid and c["name"].lower() != str(cid).lower()]
        self._persist()

    def _persist(self):
        from . import config as config_mod
        config_mod.save(self.cfg)
        self.emit("routines_changed")


# ------------------------------------------------------------------ AI tools
@tool("Create a recurring routine: ORION will do this automatically at the given time (e.g. 'every weekday at "
      "07:00 summarise my Root DMs', 'every Sunday at 10:00 back up my projects and check disk space').",
      {"name": ("string", "Short name", True), "instruction": ("string", "What ORION should do each time", True),
       "time": ("string", "HH:MM 24h", True), "days": ("string", "daily, weekdays or weekends", False),
       "heavy": ("boolean", "Wait until the PC is idle (big jobs)", False)})
def routine_add(name, instruction, time, days="daily", heavy=False):
    ns = CTX.get("night_shift")
    if not ns:
        return "Night Shift isn't running."
    c = ns.add_custom(name, instruction, time, days if days in DAYS else "daily", heavy)
    return f"Routine '{c['name']}' set for {time} ({c['days']})."


@tool("List ORION's automatic routines (Night Shift).")
def routine_list():
    ns = CTX.get("night_shift")
    if not ns:
        return "Night Shift isn't running."
    return "\n".join(f"{'ON ' if r['on'] else 'off'} {r['time']} {r['name']}" + (f" — last: {r['result']}" if r["result"] else "")
                     for r in ns.listing()["routines"])


@tool("Run one Night Shift routine right now: tidy_downloads, clear_temp, backup, health, updates, content, report.",
      {"routine": ("string", "Routine id", True)})
def routine_run_now(routine):
    ns = CTX.get("night_shift")
    if not ns or routine not in BUILTIN:
        return "Unknown routine."
    ns.run_builtin(routine)
    return f"Running {BUILTIN[routine]['name']} now."

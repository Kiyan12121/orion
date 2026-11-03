"""Autonomous-mode screensaver: when you've been away (and ORION is working on its own), the window goes
full-screen with a holographic HUD — globe, clock, weather, telemetry and a live feed of what ORION is doing.
Move the mouse or press a key and it gets out of the way. Never shows while you're gaming or watching something."""
import os
import threading
import time

from .tools import CTX, tool


def _media_playing():
    """True if any app is making sound (a video/music) — don't cover it with a screensaver."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() in ("orion.exe", "pythonw.exe", "python.exe"):
                continue
            try:
                meter = s._ctl.QueryInterface(IAudioMeterInformation)
                if meter.GetPeakValue() > 0.01:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _fullscreen_app():
    """True if something else is full-screen in front (a game or film)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or "ORION" in win32gui.GetWindowText(hwnd):
            return False
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        return l <= 0 and t <= 0 and r >= sw and b >= sh and win32gui.GetClassName(hwnd) not in ("Progman", "WorkerW")
    except Exception:
        return False


class Saver:
    def __init__(self, cfg, emit, get_window):
        self.cfg, self.emit, self.get_window = cfg, emit, get_window
        self.on = False
        self.auto = False
        self.since = 0
        self._prev_fs = False
        self._prev_min = False
        CTX["saver"] = self
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def sc(self):
        s = self.cfg.setdefault("screensaver", {})
        s.setdefault("enabled", True)
        s.setdefault("idle_minutes", 0)            # 0 = same as autonomous mode (30 min)
        s.setdefault("only_autonomy", False)
        return s

    def _idle_needed(self):
        m = int(self.sc.get("idle_minutes") or 0) or int(self.cfg.get("autonomy", {}).get("idle_minutes", 30))
        return max(1, m) * 60

    def _loop(self):
        from .jobs import idle_seconds
        time.sleep(60)
        while True:
            time.sleep(4)
            try:
                idle = idle_seconds()
                if self.on:
                    if self.auto and idle < 3 and time.time() - self.since > 4:
                        self.hide()
                    continue
                if not self.sc.get("enabled", True) or idle < self._idle_needed():
                    continue
                if self.sc.get("only_autonomy") and not self.cfg.get("autonomy", {}).get("enabled", True):
                    continue
                g = CTX.get("gaming")
                if (g and g.active) or _media_playing() or _fullscreen_app():
                    continue
                self.show(auto=True)
            except Exception:
                pass

    def show(self, auto=False):
        if self.on:
            return
        self.on, self.auto, self.since = True, auto, time.time()
        w = self.get_window()
        self.emit("saver", on=True, auto=auto)
        if w:
            try:
                self._toggled = not bool(getattr(w, "fullscreen", False))
                w.restore()
                w.show()
                if self._toggled:
                    w.toggle_fullscreen()
                w.on_top = True
            except Exception:
                pass

    def hide(self):
        if not self.on:
            return
        self.on = False
        w = self.get_window()
        self.emit("saver", on=False)
        if w:
            try:
                w.on_top = False
                if getattr(self, "_toggled", False):
                    w.toggle_fullscreen()
                    self._toggled = False
            except Exception:
                pass


def saver_data():
    out = {"t": time.time()}
    try:
        from .autonomy import recent
        out["log"] = recent(8)
    except Exception:
        out["log"] = []
    try:
        from .life import forecast
        w = forecast("")
        out["weather"] = {"temp": w["temp"], "sky": w["sky"], "place": w["place"], "rain_at": w.get("rain_at"), "code": w.get("code", 0)}
    except Exception:
        out["weather"] = None
    try:
        from .schedule import upcoming
        out["next"] = [{"at": o["at"].strftime("%a %H:%M"), "title": o["title"]} for o in upcoming(2)[:3]]
    except Exception:
        out["next"] = []
    try:
        jobs = CTX.get("jobs")
        cur = jobs.current if jobs else None
        out["job"] = cur["title"] if cur else ""
        out["queued"] = sum(1 for j in (jobs.jobs if jobs else []) if j["status"] in ("queued", "waiting"))
    except Exception:
        out["job"], out["queued"] = "", 0
    try:
        from .ventures import earn_summary
        out["money"] = earn_summary()["this_month"]
    except Exception:
        out["money"] = None
    try:
        from .life import homework
        out["homework"] = sum(1 for h in homework() if not h.get("done"))
    except Exception:
        out["homework"] = 0
    try:
        a = CTX.get("autonomy")
        out["autonomy"] = bool(a and a.ac.get("enabled"))
    except Exception:
        out["autonomy"] = False
    return out


@tool("Show the holographic SCREENSAVER now (it also appears by itself when the user is away). Moving the mouse closes it.")
def screensaver_show():
    s = CTX.get("saver")
    if not s:
        return "Screensaver not ready."
    threading.Timer(1.5, lambda: s.show(auto=False)).start()
    return "Screensaver on — move the mouse to wake me."

"""Gaming Mode: spots a game starting, boosts performance, keeps ORION quiet, holds non-urgent
notifications until you're done, and gives you a push-to-talk hotkey that works inside games."""
import platform
import re
import subprocess
import threading
import time

from .tools import CTX, tool

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
        self.brain.force_cloud = True          # keep the CPU free for the game
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
        self.emit("gaming", on=False, game=None)
        mins = int((time.time() - self.started) // 60)
        title = self.cfg.get("user_title", "sir")
        if self.held:
            items = "; ".join(self.held[:6])
            self.notify(f"Welcome back, {title}. While you were playing ({mins} min): {items}", True)
        else:
            self.notify(f"Welcome back, {title}. Nothing needed your attention.", False)
        self.held = []

    def hold(self, text):
        """Called for non-urgent notifications while gaming."""
        self.held.append(text)


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
        self.on = not self.on
        threading.Thread(target=self.start if self.on else self.stop, daemon=True).start()

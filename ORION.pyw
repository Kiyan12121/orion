"""ORION — double-click to launch.  (.pyw = no console window)"""
import json
import re
import logging
import os
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:   # real pixel coordinates on scaled (125%/150%/175%) screens, so clicks land where they should
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
# let the interface play ORION's voice without needing a click first
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")

from core import config as config_mod                       # noqa: E402
from core import tools                                      # noqa: E402
from core import autopilot, coder, schedule, skills         # noqa: E402,F401  (registers their tools)
from core import browser, root, video, vision               # noqa: E402,F401
from core.jobs import Jobs                                  # noqa: E402
from core import phone, calls                               # noqa: E402
from core import health, learning, life, study, ventures    # noqa: E402
from core.link import Link                                  # noqa: E402
from core import daily                                      # noqa: E402,F401
from core import scholar                                    # noqa: E402
from core import money                                      # noqa: E402
from core import holo                                       # noqa: E402,F401
from core import plus                                       # noqa: E402
from core.autonomy import Autonomy                          # noqa: E402
from core import gaming as gaming_mod                        # noqa: E402
from core.routines import NightShift                        # noqa: E402
from core.devices import Push, Remote, Sync, Updater        # noqa: E402
from core.gaming import Controller, GamingMode, Hotkey      # noqa: E402
from core.listen import VoiceID, WakeListener, extras_status  # noqa: E402
from core.ears import END_CONVO, Ears              # noqa: E402
from core import ducking                                    # noqa: E402
from core.brain import Brain                                # noqa: E402
from core.memory import Memory                              # noqa: E402
from core.paths import LOG_PATH, UI_PATH                    # noqa: E402
from core.providers import Cancelled                        # noqa: E402
from core.voice import Recorder, SentenceStream, Speaker    # noqa: E402

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orion")

STOP_WORDS = {"stop", "cancel", "abort", "halt", "stop it", "nevermind", "never mind"}


def _ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / 2**30
    except Exception:
        return 8


class Api:
    """Everything here not starting with _ is callable from the interface's JavaScript."""

    def __init__(self):
        self._window = None
        self._cfg = config_mod.load()
        self._memory = Memory()
        self._busy = threading.Lock()
        self._cancel = threading.Event()
        self._pending = {}
        tools.CTX.update(memory=self._memory, config=self._cfg, notify=self._notify,
                         set_theme=self._set_theme, cancel=self._cancel,
                         emit=self._emit)
        skills.load_all()
        self._toolbox = tools.Toolbox(self._cfg, self._emit, self._confirm)
        self._brain = Brain(self._cfg, self._memory, self._toolbox, self._emit, self._context)
        self._speaker = Speaker(self._cfg, self._emit)
        self._recorder = Recorder()
        self._gaming = GamingMode(self._cfg, self._emit, self._notify, self._brain)
        tools.CTX["toolbox_run"] = lambda name, args: self._toolbox.run(name, args)
        tools.CTX["stop_all"] = self.stop
        self._scheduler = schedule.Scheduler(self._cfg, self._sched_notify)
        self._hotkey = Hotkey(self._cfg.get("hotkey", "ctrl+alt+space"), self._hk_start, self._hk_stop)
        tools.CTX["brain"] = self._brain
        tools.CTX["lite"] = self.lite_profile
        try:   # instant "clip that" hotkey, works inside games
            import keyboard
            keyboard.add_hotkey(self._cfg.setdefault("gaming", {}).get("clip_hotkey", "ctrl+alt+c"),
                                lambda: threading.Thread(target=self.clip_now, daemon=True).start())
        except Exception:
            pass
        self._push = Push(self._cfg)
        self._root = root.RootWatcher(self._cfg, self._notify, self._brain)
        self._remote = Remote(self._cfg, self)
        self._sync = Sync(self._cfg, self._emit)
        self._sync.start()
        self._updater = Updater(self._cfg, self._emit)
        self._updater.start()
        self._jobs = Jobs(self._cfg, self._run_job, lambda t, title=None: self._push.send(t, title), self._emit)
        self._jobs.on_finish = self._job_finished
        self._autonomy = Autonomy(self._cfg, self._jobs, self._emit)
        self._bedtime = plus.Bedtime(self._cfg, lambda t: self._speaker.say(t),
                                     lambda t: self._emit("toast", text="🌙 " + t),
                                     lambda: self._sync.enabled and threading.Thread(target=self._sync.sync_now, daemon=True).start())
        tools.CTX["sync"] = self._sync
        self._shift = NightShift(self._cfg, self._jobs, self._shift_notify, self._emit, self._updater)
        tools.CTX["push_phone"] = lambda t: self._push.send(t, "ORION", 5, "iphone")
        self._voice_id = VoiceID(self._cfg)
        self._link = Link(self._cfg, self._memory, self._emit)
        self._ears = Ears(self._cfg, self._emit, self._transcribe, self._voice_id)
        self._followup = False          # conversation mode: listen again after ORION answers you by voice
        self._voice_turn = False
        self._wake = WakeListener(self._cfg, self._wake_command, self._emit, self._voice_id,
                                  busy=lambda: self._ears.active or self._busy.locked() or self._speaking,
                                  listen_fn=lambda: self._listen_session("wake"))
        if self._cfg.get("remote", {}).get("enabled"):
            try:
                self._remote.start()
            except Exception as e:
                log.warning(str(e))
        if self._cfg.get("wake", {}).get("enabled") and not self.lite_profile:
            self._wake.start()
        threading.Thread(target=self._health_bg, daemon=True).start()
        Controller(self._cfg, self.mic_start)
        life.ClipWatch()
        life.ScreenTime()
        life.install_scenes(self._cfg)
        config_mod.save(self._cfg)
        self._dictating = False
        tools.CTX["dictate"] = self.dictate_set
        tools.CTX["listen_memo"] = self._memo

    @property
    def lite_profile(self):
        """Laptop lite mode: 4 GB machines skip the heavy extras (wake word, clip buffer, overnight video work)."""
        p = self._cfg.get("profile", "auto")
        return p == "lite" or (p == "auto" and _ram_gb() <= 6.5)

    def _health_bg(self):
        """Quietly check health a minute after start; flag the dock if something's broken."""
        time.sleep(60)
        try:
            bad = [c for c in health.run_checks(self) if c["state"] == "bad"]
            if bad:
                self._emit("health_badge", count=len(bad))
        except Exception:
            log.exception("health check failed")

    def health_get(self):
        return health.run_checks(self)

    def health_fix(self, fid):
        def run():
            try:
                msg = health.fix(self, fid)
            except Exception as e:
                msg = f"Fix failed: {e}"
            self._emit("health_fixed", id=fid, text=msg)
        threading.Thread(target=run, daemon=True).start()
        return True

    def backup_now(self):
        try:
            return health.backup_cloud(self._cfg)
        except Exception as e:
            return f"Backup failed: {e}"

    def restore_now(self):
        try:
            return health.restore_cloud(self._cfg)
        except Exception as e:
            return f"Restore failed: {e}"

    def profile_set(self, p):
        if p in ("auto", "full", "lite"):
            self._cfg["profile"] = p
            config_mod.save(self._cfg)
        return self.lite_profile

    # ---------------------------------------------------------------- plumbing
    def _emit(self, kind, **data):
        if kind == "card":
            self._cards = (getattr(self, "_cards", []) + [(time.time(), data.get("card"))])[-12:]
        elif kind == "live":
            self._live = {**data, "t": time.time()}
        mini = getattr(self, "_mini", None)
        if mini and kind in ("state", "speaking", "theme", "toast", "stream_end", "hearing"):
            try:
                mini.evaluate_js(f"window.ui && window.ui.event({json.dumps({'kind': kind, **data})})")
            except Exception:
                self._mini = None
        if not self._window:
            return
        try:
            self._window.evaluate_js(f"window.ui && window.ui.event({json.dumps({'kind': kind, **data})})")
        except Exception:
            log.exception("emit failed")

    def _confirm(self, text):
        cid = uuid.uuid4().hex
        ev = threading.Event()
        self._pending[cid] = {"event": ev, "ok": False}
        self._emit("confirm", id=cid, text=text)
        ev.wait(timeout=90)
        return self._pending.pop(cid, {}).get("ok", False)

    def _notify(self, text, important=True):
        """Proactive messages (timers, reminders, briefings). Non-urgent ones are held during
        Gaming Mode; busy (do-not-disturb) blocks keep it silent but still on screen."""
        g = getattr(self, "_gaming", None)
        if g and g.active and not important:
            g.hold(text)
            return
        self._emit("toast", level="info", text=text)
        self._emit("message", id=uuid.uuid4().hex[:8], role="assistant", text=text, tier="reflex")
        if important or not schedule.busy_now():
            self._speaker.say(text)
        if getattr(self, "_push", None):
            threading.Thread(target=self._push.send, args=(text,), daemon=True).start()

    def _context(self):
        bits = []
        b = schedule.busy_now()
        if b:
            bits.append(f"User is currently busy ({b['title']} until {b['until']:%H:%M}) — keep it brief.")
        g = getattr(self, "_gaming", None)
        if g and g.active:
            bits.append(f"GAMING MODE is on ({g.game}): user is mid-game — replies must be one short sentence.")
        r = getattr(self, "_root", None)
        if r and r.afk:
            bits.append("User is AFK; ORION is answering their Root DMs.")
        return " ".join(bits)

    def _run_job(self, j):
        src = {"phone": "📱", "routine": "⏰", "voice": "🗂", "auto": "🤖", "mission": "🚀"}.get(j["source"], "🗂")
        self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=f"{src} JOB: {j['title']}")
        t0 = time.time()
        out = self._process(j["text"], j.get("autopilot", True), speak=False)
        j["cards"] = [c for t, c in getattr(self, "_cards", []) if t >= t0 and c][:4]
        return out

    def _sched_notify(self, text, important=True):
        self._notify(text, important)
        if important:
            calls.maybe_call(self._cfg, "reminders", text, getattr(self, "_gaming", None))

    def _job_finished(self, j):
        if j["status"] in ("done", "failed") and calls.worth_calling(self._cfg, j):
            calls.maybe_call(self._cfg, "jobs", calls.job_reason(j), self._gaming)

    def _shift_notify(self, text, title=None):
        self._emit("toast", level="info", text=(title + ": " if title else "") + text.split("\n")[0][:140])
        self._push.send(text, title)
        if title == "ORION morning report":
            calls.maybe_call(self._cfg, "morning", "Here's your morning report. " + text[:250], self._gaming)

    def _wake_command(self, wav):
        prov = self._brain.groq_like
        if not prov:
            return
        try:
            text = prov.transcribe(wav)
        except Exception:
            return
        if text:
            self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=text)
            self.send(text)

    def _hk_start(self):
        if self._ears.active:
            self._ears.finish()
            return
        self.mic_start()
        self._emit("toast", level="info", text="Listening — just talk. I'll send it when you finish.")

    def _hk_stop(self):
        self._ears.finish()

    # ---------------------------------------------------------------- listening (core/ears.py)
    _speaking = False

    def _transcribe(self, wav, prompt=None):
        prov = self._brain.groq_like
        if not prov:
            raise RuntimeError("Voice input needs a Groq key (free) — add it in Settings.")
        return prov.transcribe(wav, prompt=prompt)

    def _listen_session(self, purpose="command", start_timeout=8.0):
        """Listen until the user has finished, then hand the text to the interface to send."""
        self._speaker.stop()
        self._emit("state", state="listening")
        self._emit("listening", on=True, purpose=purpose)
        text = ""
        v = self._cfg["voice"]
        if v.setdefault("duck", True):            # turn music / videos / games down while you talk
            ducking.duck(float(v.setdefault("duck_level", 0.12)))
        try:
            text = self._ears.listen(start_timeout=start_timeout, purpose=purpose)
        except Exception as e:
            self._emit("toast", level="warn", text=f"Couldn't hear that: {e}")
        finally:
            ducking.restore()
        self._emit("listening", on=False, purpose=purpose)
        self._emit("state", state="idle")
        if not text:
            if purpose == "followup":
                self._followup = False
            return ""
        if purpose == "followup" and END_CONVO.match(text):
            self._followup = False
            self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=text)
            self._speaker.say(f"Very good, {self._cfg.get('user_title', 'sir')}.")
            return ""
        self._voice_turn = True
        self._emit("heard", text=text)
        return text

    def _maybe_followup(self):
        """Conversation mode: after a spoken answer, listen for the follow-up (no wake word needed)."""
        if not (self._followup and self._cfg["voice"].get("conversation", True)):
            return
        if self._ears.active or self._busy.locked() or not self._speaker.idle or self._speaking:
            return
        self._followup = False
        threading.Thread(target=self._listen_session, args=("followup", 7.0), daemon=True).start()

    def voice_state(self, speaking):
        """Called by the interface when ORION's voice starts/stops playing."""
        self._speaking = bool(speaking)
        if speaking and self._cfg["voice"].get("barge_in") and not self._ears.active:
            threading.Thread(target=self._barge_watch, daemon=True).start()
        if not speaking:
            threading.Timer(0.35, self._maybe_followup).start()
        return True

    def _barge_watch(self):
        """Barge-in: start talking while ORION is speaking and it stops to listen."""
        if getattr(self, "_barging", False):
            return
        self._barging = True
        try:
            if self._ears.wait_for_voice(lambda: not self._speaking):
                self._speaker.stop()
                self._followup = False
                self._listen_session("command")
        finally:
            self._barging = False

    # ---------------------------------------------------------------- dictation + voice memos
    def dictate_set(self, on=True):
        """Dictation: everything you say gets typed into whatever window you're in. Say 'stop dictation' to end."""
        on = bool(on)
        if on == self._dictating:
            return on
        self._dictating = on
        if on:
            threading.Thread(target=self._dictate_loop, daemon=True).start()
        else:
            self._ears.finish()
        self._emit("dictation", on=on)
        return on

    def _dictate_loop(self):
        import pyautogui
        import pyperclip
        self._emit("toast", level="info", text="✍ Dictation on — click where you want the words to go. Say “stop dictation” to finish.")
        time.sleep(2.5)
        while self._dictating:
            v = self._cfg["voice"]
            if v.get("duck", True):
                ducking.duck(float(v.get("duck_level", 0.12)))
            try:
                text = self._ears.listen(start_timeout=45, purpose="dictate")
            except Exception as e:
                self._emit("toast", level="warn", text=str(e))
                break
            finally:
                ducking.restore()
            if not self._dictating:
                break
            if not text:
                continue
            if re.search(r"\b(stop|end|finish) (dictation|dictating|typing)\b", text, re.I):
                break
            text = re.sub(r"\s*\b(new line|newline)\b\s*", "\n", text, flags=re.I)
            text = re.sub(r"\s*\bnew paragraph\b\s*", "\n\n", text, flags=re.I)
            try:
                old = pyperclip.paste()
            except Exception:
                old = None
            pyperclip.copy(text + ("" if text.endswith("\n") else " "))
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.25)
            if old is not None:
                try:
                    pyperclip.copy(old)
                except Exception:
                    pass
            self._emit("hearing", text="✍ " + text)
        self._dictating = False
        self._emit("dictation", on=False)
        self._emit("toast", level="info", text="Dictation off.")

    def _memo(self):
        """Voice memo: record a long message (up to 5 min) and save it as a note."""
        self._speaker.stop()
        self._emit("toast", level="info", text="🎙 Recording your memo — talk as long as you like. Pause for a few seconds to finish.")
        v = self._cfg["voice"]
        old = v.get("patience", "normal")
        v["patience"] = "relaxed"
        if v.get("duck", True):
            ducking.duck(float(v.get("duck_level", 0.12)))
        self._emit("state", state="listening")
        try:
            text = self._ears.listen(start_timeout=10, purpose="memo")
        finally:
            v["patience"] = old
            ducking.restore()
            self._emit("state", state="thinking")
        if not text:
            return ""
        life.note_add_raw(text, "memo")
        return text

    def dictate_toggle(self):
        return self.dictate_set(not self._dictating)

    # ---------------------------------------------------------------- life page data
    _wx = (0, None)

    def life_get(self):
        if time.time() - self._wx[0] > 900 or not self._wx[1]:
            try:
                self._wx = (time.time(), life.forecast(self._cfg.get("home_place", "")))
            except Exception:
                pass
        return {"weather": self._wx[1], "homework": life.homework(), "notes": list(reversed(life.notes()))[:40],
                "clips": life.clip_history()[:20], "screen": life.screen_day(), "screen_week": life.screen_week(),
                "home_place": self._cfg.get("home_place", "Leicester"), "dictating": self._dictating}

    def life_action(self, b):
        a = b.get("action")
        if a == "hw_add":
            life.hw_add(b.get("subject", ""), b.get("task", ""), b.get("due", ""))
        elif a == "hw_done":
            life.hw_set(b.get("id"), b.get("done", True))
        elif a == "hw_del":
            life.hw_remove(b.get("id"))
        elif a == "note_add":
            life.note_add_raw(b.get("text", ""), b.get("tag", ""))
        elif a == "note_del":
            life.note_remove(b.get("id"))
        elif a == "clip_copy":
            import pyperclip
            pyperclip.copy(b.get("text", ""))
        elif a == "place":
            self._cfg["home_place"] = (b.get("place") or "Leicester").strip()[:60]
            config_mod.save(self._cfg)
            self._wx = (0, None)
        elif a == "news":
            try:
                return {"news": life.headlines(b.get("topic", "top"), 8)}
            except Exception as e:
                return {"news": [], "error": str(e)}
        return self.life_get()

    def voice_settings(self, b=None):
        v = self._cfg["voice"]
        self._ears.vc            # fills defaults
        if b:
            if b.get("patience") in ("quick", "normal", "relaxed"):
                v["patience"] = b["patience"]
            for k in ("conversation", "barge_in", "duck"):
                if k in b:
                    v[k] = bool(b[k])
            if "mic_sensitivity" in b:
                v["mic_sensitivity"] = max(0.4, min(2.0, float(b["mic_sensitivity"])))
            config_mod.save(self._cfg)
        v.setdefault("duck", True)
        return {k: v.get(k) for k in ("patience", "conversation", "barge_in", "mic_sensitivity", "max_talk_seconds", "duck")}

    def _set_theme(self, theme):
        self._cfg["theme"] = theme
        config_mod.save(self._cfg)
        self._emit("theme", theme=theme)

    # ---------------------------------------------------------------- startup
    def init(self):
        c = self._cfg
        vis = c.get("visuals", "auto")
        lite = vis == "lite" or (vis == "auto" and self.lite_profile)
        return {"custom_modes": c.get("custom_modes", {}), "owner": c.get("owner_name", ""), "name": c["assistant_name"], "title": c["user_title"], "version": config_mod.VERSION,
                "theme": c["theme"], "brain": c["brain"], "speak": c["voice"]["speak_replies"],
                "safe_mode": c["safe_mode"], "lite": lite, "skip_boot": c.get("skip_boot", False),
                "has_key": bool(self._brain.cloud), "mic": self._recorder.available,
                "neural": self._speaker.neural_ok, "hotkey": self._cfg.get("hotkey") if self._hotkey.ok else None,
                "gaming": self._gaming.active, "game": self._gaming.game,
                "afk": getattr(self, "_root", None) and self._root.afk,
                "afk_note": getattr(self, "_root", None) and self._root.afk_note,
                "history": self._memory.recent(16), "facts": len(self._memory.facts),
                "boot_checks": self._boot_checks()}

    def _boot_checks(self):
        """Real system checks shown during the boot-up sequence."""
        out = []
        try:
            b = self._brain.status()
            labels = b.get("cloud", {}).get("labels", [])
            out.append(["Neural core", " + ".join(labels[:3]) or "local only", bool(labels) or b.get("local", {}).get("ok")])
            out.append(["Local brain", b.get("local", {}).get("model") or "offline", bool(b.get("local", {}).get("ok"))])
        except Exception:
            out.append(["Neural core", "unknown", False])
        out.append(["Long-term memory", f"{len(self._memory.facts)} facts", True])
        out.append(["Voice", "neural" if self._speaker.neural_ok else "Windows voice", True])
        out.append(["Microphone", "ready" if self._recorder.available else "not found", bool(self._recorder.available)])
        try:
            out.append(["Phone link", "online" if self._cfg.get("remote", {}).get("enabled") else "off",
                        bool(self._cfg.get("remote", {}).get("enabled"))])
            out.append(["Cloud sync", self._sync.status or ("on" if self._sync.enabled else "off"), bool(self._sync.enabled)])
        except Exception:
            pass
        try:
            hw = [h for h in life.homework() if not h.get("done")]
            out.append(["Homework", f"{len(hw)} due" if hw else "all clear", True])
        except Exception:
            pass
        try:
            out.append(["Jobs", f"{sum(1 for j in self._jobs.jobs if j['status'] in ('queued', 'waiting'))} queued", True])
        except Exception:
            pass
        return out

    def status(self):
        return self._brain.status()

    def meters(self):
        return self._brain.meters()

    def stats(self):
        try:
            import psutil
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            net = psutil.net_io_counters()
            bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            return {"cpu": psutil.cpu_percent(), "ram": vm.percent,
                    "ram_used": round(vm.used / 2**30, 1), "ram_total": round(vm.total / 2**30, 1),
                    "disk": disk.percent, "disk_free": round(disk.free / 2**30),
                    "procs": len(psutil.pids()), "net": net.bytes_recv + net.bytes_sent,
                    "uptime": int(time.time() - psutil.boot_time()),
                    "battery": round(bat.percent) if bat else None,
                    "plugged": bool(bat.power_plugged) if bat else None}
        except Exception:
            return {}

    # ---------------------------------------------------------------- conversation
    def send(self, text, autopilot=False):
        text = (text or "").strip()
        if not text:
            return False
        if text.lower().strip(" .!") in STOP_WORDS:
            self.stop()
            return True
        voice, self._voice_turn = self._voice_turn, False
        threading.Thread(target=self._process_voice if voice else self._process, args=(text, autopilot),
                         daemon=True).start()
        return True

    def _process_voice(self, text, autopilot=False):
        out = self._process(text, autopilot)
        if out[1] != "none" and not autopilot:
            self._followup = True
            if not self._speaker.enabled:
                threading.Timer(0.3, self._maybe_followup).start()
            else:
                threading.Timer(1.5, self._maybe_followup).start()   # in case nothing was spoken
        return out

    def autopilot(self, goal):
        tools.CTX["plan"] = {"steps": [], "current": 0, "done": False, "note": ""}
        self._emit("plan", **tools.CTX["plan"])
        return self.send(goal, autopilot=True)

    def stop(self):
        self._cancel.set()
        tools.CTX["cancel"].set()
        self._speaker.stop()
        self._emit("stopped")
        return True

    def ask(self, text, source="phone"):
        """Used by the phone/laptop remote: runs the request and returns the reply."""
        text = (text or "").strip()
        if not text:
            return {"reply": "", "tier": None}
        if text.lower().strip(" .!") in STOP_WORDS:
            self.stop()
            return {"reply": "Stopped.", "tier": "reflex"}
        self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=("💻 " if source == "laptop" else "📱 ") + text)
        t0 = time.time()
        reply, tier, model = self._process(text, False, speak=False)
        cards = [c for t, c in getattr(self, "_cards", []) if t >= t0 and c]
        return {"reply": reply, "tier": tier, "model": model, "cards": cards}

    def _process(self, text, autopilot=False, speak=True):
        with self._busy:
            ev = threading.Event()               # a fresh stop button for every task — one click always works
            self._cancel = ev
            tools.CTX["cancel"] = ev
            mid = uuid.uuid4().hex[:8]
            self._emit("state", state="thinking")
            self._emit("stream_start", id=mid)
            buf, last = [], [time.time()]
            speech = SentenceStream(self._speaker.say if speak else (lambda *_: None))

            def flush():
                if buf:
                    self._emit("delta", id=mid, text="".join(buf))
                    buf.clear()
                last[0] = time.time()

            def on_delta(chunk):
                if ev.is_set():
                    raise Cancelled()
                buf.append(chunk)
                speech.feed(chunk)
                if time.time() - last[0] > 0.06:
                    flush()

            def think():
                tools.TL.ev = ev
                if self._link.enabled and self._link.online and not autopilot:
                    try:                       # laptop: hand it to the gaming PC — one brain, one conversation
                        self._emit("status", text="asking your gaming PC…")
                        out = self._link.ask(text)
                        on_delta(out[0])
                        threading.Thread(target=self._link.sync_history, daemon=True).start()
                        return out
                    except Cancelled:
                        raise
                    except Exception:
                        pass
                return self._brain.handle(text, on_delta, ev, autopilot)

            try:
                # the thinking runs on its own thread so Stop works INSTANTLY — even mid-reply or mid-tool
                box = {}

                def work():
                    try:
                        box["r"] = think()
                    except BaseException as e:
                        box["e"] = e
                th = threading.Thread(target=work, daemon=True)
                th.start()
                while th.is_alive() and not ev.wait(0.15):
                    pass
                if ev.is_set():
                    raise Cancelled()
                if "e" in box:
                    raise box["e"]
                reply, tier, model = box["r"]
                flush()
                self._emit("stream_end", id=mid, text=reply, tier=tier, model=model)
                if speak and not speech.flush():
                    self._speaker.say(reply)
                if autopilot:
                    self._push.send(f"Mission complete: {reply[:300]}", "ORION Autopilot")
            except Cancelled:
                buf.clear()
                self._speaker.stop()
                reply, tier, model = "Stopped.", "none", None
                self._emit("stream_end", id=mid, text=None, tier="none", model=None, stopped=True)
            except Exception as e:
                log.exception("handle failed")
                reply, tier, model = f"Something went wrong in my core: {e}", "none", None
                self._emit("stream_end", id=mid, text=reply, tier="none", model=None)
            self._emit("state", state="idle")
            return reply, tier, model

    def confirm_reply(self, cid, ok):
        p = self._pending.get(cid)
        if p:
            p["ok"] = bool(ok)
            p["event"].set()
        return True

    def audio_failed(self, text):
        """The interface couldn't play neural audio -> use the Windows voice instead."""
        threading.Thread(target=self._speaker.offline_say, args=(text,), daemon=True).start()
        return True

    # ---------------------------------------------------------------- voice in
    def mic_start(self):
        """Tap the mic: ORION listens until you've finished talking (tap again to send early)."""
        if self._ears.active:
            self._ears.finish()
            return True
        if not self._ears.available:
            self._emit("toast", level="warn", text="Microphone support isn't installed (sounddevice) — run 1_SETUP.bat.")
            return False
        if not self._brain.groq_like:
            self._emit("toast", level="warn", text="Voice input needs a Groq key (free) — add it in Settings.")
            return False
        self._followup = False
        threading.Thread(target=self._listen_session, daemon=True).start()
        return True

    def mic_level(self):
        return self._ears.level if self._ears.active else 0

    def mic_stop(self):
        self._ears.finish()
        return ""

    def mic_cancel(self):
        self._dictating = False
        self._ears.cancel()
        self._followup = False
        return True

    # ---------------------------------------------------------------- controls
    def set_brain(self, mode):
        if mode in ("auto", "cloud", "local"):
            self._cfg["brain"] = mode
            config_mod.save(self._cfg)
        return self._brain.status()

    def set_theme(self, theme):
        tools.set_theme(theme)
        return theme

    def mode_custom(self, b):
        """Make your own mode: name, colour, personality/job."""
        key = re.sub(r"[^a-z0-9]", "", (b.get("name") or "").lower())[:20]
        if key:
            self._cfg.setdefault("custom_modes", {})[key] = {"label": b.get("name", key).strip()[:24],
                                                            "colour": b.get("colour") or "#ff8bd1",
                                                            "persona": (b.get("persona") or "").strip()[:600],
                                                            "groups": ["life", "web", "browser", "memory"]}
            config_mod.save(self._cfg)
        return self._cfg.get("custom_modes", {})

    def toggle_speak(self):
        v = self._cfg["voice"]
        v["speak_replies"] = not v.get("speak_replies", True)
        config_mod.save(self._cfg)
        if not v["speak_replies"]:
            self._speaker.stop()
        return v["speak_replies"]

    def preview_voice(self, voice):
        self._speaker.stop()
        t = self._cfg["user_title"]
        self._speaker.say(f"Good evening, {t}. This is how I'll sound. All systems are at your disposal.",
                          voice=voice, force=True)
        return True

    def undo(self):
        r = self._toolbox.run("undo_last_change", {})
        self._emit("toast", level="info", text=r)
        return r

    def get_settings(self):
        c = self._cfg
        return {"name": c["assistant_name"], "title": c["user_title"], "owner": c.get("owner_name", ""),
                "local_vision": c["local"].get("vision_model", ""),
                "providers": [{"id": p["id"], "label": p["label"], "key": p.get("api_key", ""),
                               "key_url": p.get("key_url", "")} for p in c["providers"]],
                "local_model": c["local"]["model"], "speak": c["voice"]["speak_replies"],
                "engine": c["voice"]["engine"], "voice": c["voice"]["neural_voice"],
                "voices": config_mod.NEURAL_VOICES, "safe_mode": c["safe_mode"],
                "fullscreen": c["fullscreen"], "visuals": c["visuals"], "skip_boot": c.get("skip_boot", False),
                "auto_mode": c.get("auto_mode", True), "per_mode": c["voice"].get("per_mode", True),
                "custom_modes": c.get("custom_modes", {})}

    def save_settings(self, s):
        c = self._cfg
        c["assistant_name"] = (s.get("name") or "ORION").strip()[:24]
        c["user_title"] = (s.get("title") or "sir").strip()[:24]
        keys = s.get("keys") or {}
        for p in c["providers"]:
            if p["id"] in keys:
                p["api_key"] = (keys[p["id"]] or "").strip()
        if (s.get("local_model") or "").strip():
            c["local"]["model"] = s["local_model"].strip()
        c["local"]["vision_model"] = (s.get("local_vision") or "").strip()
        if (s.get("owner") or "").strip():
            c["owner_name"] = s["owner"].strip()[:30]
        v = c["voice"]
        v["speak_replies"] = bool(s.get("speak"))
        v["engine"] = s.get("engine") if s.get("engine") in ("neural", "offline") else "neural"
        v["neural_voice"] = s.get("voice") or v["neural_voice"]
        c["safe_mode"] = bool(s.get("safe_mode"))
        c["fullscreen"] = bool(s.get("fullscreen"))
        c["skip_boot"] = bool(s.get("skip_boot"))
        if "auto_mode" in s:
            c["auto_mode"] = bool(s["auto_mode"])
        if "per_mode" in s:
            v["per_mode"] = bool(s["per_mode"])
        c["visuals"] = s.get("visuals") if s.get("visuals") in ("auto", "full", "lite") else "auto"
        config_mod.save(c)
        self._brain.reload_providers()
        return self.init()

    # ---------------------------------------------------------------- schedule / skills / gaming panels
    def schedule_get(self, days=14):
        out = []
        for o in schedule.upcoming(int(days)):
            out.append({"id": o["id"], "title": o["title"], "date": o["at"].strftime("%Y-%m-%d"),
                        "day": o["at"].strftime("%a %d %b"), "time": o["at"].strftime("%H:%M"),
                        "until": o["until"].strftime("%H:%M"), "repeat": o.get("repeat", "none"),
                        "busy": o.get("busy", False), "with": o.get("with", "")})
        b = schedule.busy_now()
        return {"items": out, "busy": b["title"] if b else None}

    def schedule_week(self, start=None, days=7):
        import datetime as _dt
        d = _dt.date.fromisoformat(start) if start else _dt.date.today()
        from core import daily as _daily
        return {"events": schedule.week(d, int(days)), "start": d.isoformat(), "day": _daily.day_cfg(self._cfg),
                "timetable": scholar._load().get("timetable", {})}

    def schedule_move(self, eid, start, duration=None):
        return bool(schedule.move_event(eid, start, duration))

    def schedule_add(self, e):
        try:
            schedule.add_event(e.get("title") or "Event", f"{e.get('date')} {e.get('time') or '12:00'}",
                               int(e.get("duration") or 60), e.get("repeat") or "none", 10,
                               bool(e.get("busy")), e.get("with") or "")
            return True
        except Exception as ex:
            self._emit("toast", level="warn", text=str(ex))
            return False

    def schedule_remove(self, eid):
        schedule.remove_event(eid)
        return True

    def skills_get(self):
        return skills.all_skills()

    def skill_toggle(self, name, on):
        skills.set_enabled(name, on)
        return True

    def skill_remove(self, name):
        return skills.skill_delete(name)

    def gaming_toggle(self):
        if self._gaming.active:
            self._gaming.exit()
        else:
            self._gaming.enter("manual", manual=True)
        return self._gaming.active

    def plan_get(self):
        return tools.CTX.get("plan") or {"steps": [], "current": 0, "done": False, "note": ""}

    def projects_open(self):
        from core.paths import PROJECTS_DIR
        webbrowser.open(PROJECTS_DIR)
        return True

    # ---------------------------------------------------------------- Root panel
    def root_state(self):
        r = self._root
        return {"running": bool(root.root_window(launch=False)) if os.name == "nt" else False,
                "afk": r.afk, "note": r.afk_note, "status": r.status, "queue": len(r.queue),
                "settings": self._cfg.get("root", {}), "log": root.recent_log(40)}

    def root_check(self):
        def run():
            r = self._toolbox.run("root_check_messages", {})
            self._emit("toast", level="info", text="Root checked.")
            self._emit("root_text", text=r)
        threading.Thread(target=run, daemon=True).start()
        return True

    def root_afk(self, on, note=""):
        return tools.REGISTRY["root_afk"]["fn"](on=bool(on), note=note or "")

    def root_settings(self, s):
        rc = self._cfg.setdefault("root", {})
        for k in ("watch", "gaming_autoreply"):
            if k in s:
                rc[k] = bool(s[k])
        if s.get("gaming_reply") in ("instant", "queue"):
            rc["gaming_reply"] = s["gaming_reply"]
        if s.get("owner_name"):
            self._cfg["owner_name"] = s["owner_name"][:30]
        config_mod.save(self._cfg)
        return True

    # ---------------------------------------------------------------- Studio panel
    def studio_pick(self):
        import webview
        r = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=(
            "Videos (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.flv)", "All files (*.*)"))
        return r[0] if r else ""

    def studio_run(self, action, path):
        prompts = {"autocut": f"Use video_autocut on {path}", "captions": f"Use video_captions on {path}",
                   "shorts": f"Use video_shorts on {path} and make 3 shorts",
                   "metadata": f"Use video_metadata on {path}", "info": f"Use video_info on {path}"}
        if action not in prompts:
            return False
        tool = {"autocut": "video_autocut", "captions": "video_captions", "shorts": "video_shorts",
                "metadata": "video_metadata", "info": "video_info"}[action]

        def run():
            self._cancel.clear()
            self._emit("state", state="thinking")
            self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=f"🎬 {action}: {os.path.basename(path)}")
            res = self._toolbox.run(tool, {"path": path})
            self._emit("message", id=uuid.uuid4().hex[:8], role="assistant", text=res, tier="reflex")
            self._emit("studio_done", action=action, result=res)
            self._emit("state", state="idle")
            self._push.send(f"Studio {action} finished: {res[:200]}", "ORION Studio")
        threading.Thread(target=run, daemon=True).start()
        return True

    # ---------------------------------------------------------------- Devices panel
    def devices_info(self):
        ex = extras_status()
        return {"extras": {"python": ex["python"], "frozen": ex["frozen"], "wake_err": ex["wake"],
                           "vid_err": ex["voice_id"], "installing": getattr(self, "_installing", False)},"remote": self._remote.info(), "remote_enabled": self._cfg.get("remote", {}).get("enabled", False),
                "ntfy": self._push.topic, "sync": {"enabled": self._sync.enabled, "status": self._sync.status,
                                                   "token": bool(self._cfg.get("sync", {}).get("github_token"))},
                "update": self._updater.latest, "version": config_mod.VERSION,
                "repo": self._cfg.get("update", {}).get("repo", ""),
                "wake": {"available": self._wake.available, "enabled": self._cfg.get("wake", {}).get("enabled", False),
                         "running": self._wake.running, "error": self._wake.error,
                         "phrase": self._cfg.get("wake", {}).get("model", "hey_jarvis").replace("_", " ")},
                "voice_id": {"available": self._voice_id.available, "enrolled": self._voice_id.print is not None,
                             "enabled": self._cfg.get("voice_id", {}).get("enabled", False)}}

    def devices_action(self, action, value=None):
        c = self._cfg
        try:
            if action == "remote_on":
                c.setdefault("remote", {})["enabled"] = True
                self._remote.start()
            elif action == "remote_off":
                c.setdefault("remote", {})["enabled"] = False
                self._remote.stop()
            elif action == "new_pin":
                c["remote"]["pin"] = ""
                self._remote.ensure_pin()
            elif action == "push_on":
                self._push.enable()
                self._push.send("ORION push notifications are working, sir.", "ORION", 4, "white_check_mark")
            elif action == "push_off":
                c["notify"]["ntfy_topic"] = ""
            elif action == "push_test":
                self._push.send("Test notification from ORION.", "ORION", 4, "bell")
            elif action == "sync_token":
                c.setdefault("sync", {})["github_token"] = (value or "").strip()
                config_mod.save(c)
                if value:
                    self._sync.sync_now()
            elif action == "sync_now":
                self._sync.sync_now()
            elif action == "update_check":
                if not self._updater.check():
                    self._emit("toast", level="info", text=f"ORION {config_mod.VERSION} is up to date.")
            elif action == "update_install":
                threading.Thread(target=self._do_update, daemon=True).start()
            elif action == "install_extras":
                self._install_extras(bool(value))
            elif action == "wake_on":
                c.setdefault("wake", {})["enabled"] = True
                if not self._wake.start() and not self._wake.available:
                    raise RuntimeError("Wake word needs the voice extras — run 4_INSTALL_VOICE_EXTRAS.bat.")
            elif action == "wake_off":
                c.setdefault("wake", {})["enabled"] = False
                self._wake.stop()
            elif action == "voiceid_on":
                c.setdefault("voice_id", {})["enabled"] = True
            elif action == "voiceid_off":
                c.setdefault("voice_id", {})["enabled"] = False
            config_mod.save(c)
        except Exception as e:
            self._emit("toast", level="warn", text=str(e))
        return self.devices_info()

    def _do_update(self):
        def say(m):
            log.info("update: %s", m)
            self._emit("toast", level="info", text=m)
            self._emit("status", text=m)
        try:
            self._emit("state", state="thinking")
            self._updater.install(say)
            time.sleep(1.5)
            self.quit()
        except Exception as e:
            log.exception("update failed")
            self._emit("state", state="idle")
            self._emit("message", id=uuid.uuid4().hex[:8], role="system",
                       text=f"Update failed: {e}\n\nManual fix: download the ORION zip from "
                            f"github.com/Kiyan12121/orion/releases/latest, close ORION, unzip it over your "
                            f"ORION folder (Replace all), then open ORION from the Desktop shortcut.")

    def _install_extras(self, voice_id=False):
        """Installs the voice extras into the EXACT Python ORION is running on (fixes 'not installed'
        when the .bat used a different Python)."""
        import subprocess
        if extras_status()["frozen"]:
            raise RuntimeError("ORION.exe can't use the voice extras — launch from the Desktop shortcut.")
        py = sys.executable.replace("pythonw.exe", "python.exe")
        pkgs = [["openwakeword", "onnxruntime", "sounddevice"]]
        if voice_id:
            pkgs += [["torch", "--index-url", "https://download.pytorch.org/whl/cpu"],
                     ["webrtcvad-wheels", "librosa", "scipy"], ["resemblyzer", "--no-deps"]]

        def run():
            self._installing = True
            self._emit("toast", level="info", text="Installing voice extras… (a few minutes)")
            log_lines = []
            for p in pkgs:
                r = subprocess.run([py, "-m", "pip", "install", *p], capture_output=True, text=True,
                                   creationflags=0x08000000 if os.name == "nt" else 0)
                log_lines.append((r.stdout + r.stderr)[-1500:])
                if r.returncode != 0:
                    self._installing = False
                    log.error("extras install failed: %s", log_lines[-1])
                    self._emit("toast", level="warn", text=f"Install failed on {p[0]} — details in data/orion.log")
                    self._emit("devices_changed")
                    return
            try:
                import openwakeword
                openwakeword.utils.download_models([self._cfg.get("wake", {}).get("model", "hey_jarvis")])
            except Exception as e:
                log.warning("wake model download: %s", e)
            self._installing = False
            import importlib
            importlib.invalidate_caches()
            self._emit("toast", level="info", text="Voice extras installed ✓")
            self._emit("devices_changed")
        threading.Thread(target=run, daemon=True).start()

    def voice_enroll(self):
        """Records 3 short clips of the user's voice for Voice ID."""
        if not self._voice_id.available:
            self._emit("toast", level="warn", text="Voice ID needs the voice extras — run 4_INSTALL_VOICE_EXTRAS.bat.")
            return False

        def run():
            import numpy as np
            lines = ["ORION, open my schedule and tell me what's on today.",
                     "Turn the volume down and check my messages on Root.",
                     "This is my voice — only listen to me."]
            clips = []
            for i, line in enumerate(lines, 1):
                self._emit("enroll", step=i, line=line)
                time.sleep(1.2)
                self._recorder.start()
                time.sleep(4.5)
                wav = self._recorder.stop()
                if wav:
                    import io as _io
                    import wave as _wave
                    with _wave.open(_io.BytesIO(wav)) as w:
                        clips.append(np.frombuffer(w.readframes(w.getnframes()), dtype="int16"))
            try:
                self._voice_id.enroll(clips)
                self._cfg.setdefault("voice_id", {})["enabled"] = True
                config_mod.save(self._cfg)
                self._emit("enroll", step=0, line="Voice learned. I'll only respond to you now.")
            except Exception as e:
                self._emit("enroll", step=-1, line=str(e))
        threading.Thread(target=run, daemon=True).start()
        return True

    # ---------------------------------------------------------------- used by the phone remote
    def remote_state(self):
        b = schedule.busy_now()
        today = [o for o in schedule.upcoming(1) if o["at"].strftime("%Y-%m-%d") == time.strftime("%Y-%m-%d")]
        nxt = schedule.upcoming(7)[:1]
        return {"name": self._cfg["assistant_name"], "theme": self._cfg["theme"], "brain": self._cfg["brain"],
                "busy": self._busy.locked(), "gaming": self._gaming.active, "game": self._gaming.game,
                "afk": self._root.afk, "busy_now": b["title"] if b else None,
                "next": f"{nxt[0]['title']} · {nxt[0]['at']:%a %H:%M}" if nxt else None,
                "today": [{"time": o["at"].strftime("%H:%M"), "title": o["title"]} for o in today],
                "version": config_mod.VERSION, "title": self._cfg.get("user_title", "sir"),
                "jobs_active": sum(1 for j in self._jobs.jobs if j["status"] in ("queued", "running", "waiting")),
                "job_running": (self._jobs.current or {}).get("title"),
                "phone_actions": phone.take(),
                "stats": self.stats(), "root_unread": sum(1 for e in root.recent_log(20) if e["kind"] == "received")}

    def remote_action(self, action, value=None):
        if action == "stop":
            self.stop()
            return "Stopped."
        if action == "afk":
            return self.root_afk(not self._root.afk)
        if action == "gaming":
            return "Gaming Mode on." if self.gaming_toggle() else "Gaming Mode off."
        if action == "lock":
            return self._toolbox.run("lock_pc", {})
        if action == "theme" and value:
            return self.set_theme(value)
        simple = {"vol_up": ("media", {"action": "volume_up", "steps": 3}), "vol_down": ("media", {"action": "volume_down", "steps": 3}),
                  "mute": ("media", {"action": "mute"}), "play": ("media", {"action": "play_pause"}),
                  "next": ("media", {"action": "next"}), "prev": ("media", {"action": "previous"}),
                  "screenshot": ("save_screenshot", {}), "sleep": ("power", {"action": "sleep"}),
                  "restart": ("power", {"action": "restart"}), "shutdown": ("power", {"action": "shutdown"})}
        if action in simple:
            t, a = simple[action]
            return self._toolbox.run(t, a)
        if action == "open" and value:
            return self._toolbox.run("open_app", {"name": value})
        if action == "report":
            return self._shift.morning_report()
        if action == "routine" and value:
            self._shift.run_builtin(value)
            return f"Running {value}."
        return "Unknown action."

    def screen_jpeg(self):
        try:
            import io
            import pyautogui
            img = pyautogui.screenshot()
            img.thumbnail((1280, 1280))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=70)
            return buf.getvalue()
        except Exception:
            return None

    def remote_get(self, path):
        if path.startswith("/api/jobs/"):
            j = self._jobs.get(path.split("/")[3])
            if not j:
                raise KeyError(path)
            return j
        if path == "/api/jobs":
            return {"jobs": self._jobs.list(40)}
        if path == "/api/schedule":
            return self.schedule_get(14)
        if path.startswith("/api/week"):
            return self.schedule_week()
        if path == "/api/routines":
            return self._shift.listing()
        if path == "/api/root":
            return {"afk": self._root.afk, "note": self._root.afk_note, "log": root.recent_log(30)}
        if path == "/api/stats":
            return {**self.stats(), "meters": self._brain.meters()}
        if path == "/api/history":
            return {"turns": self._memory.recent_full(60), "device": "pc"}
        if path == "/api/wake":
            return {"actions": phone.wake(), "title": self._cfg.get("user_title", "sir")}
        if path == "/api/clip":
            try:
                import pyperclip
                return {"text": pyperclip.paste()[:20000]}
            except Exception:
                return {"text": ""}
        if path == "/api/calls":
            return calls.settings(self._cfg)
        if path == "/api/scholar":
            return self.scholar_get()
        if path.startswith("/api/scholar/paper/"):
            return self.scholar_paper(path.rsplit("/", 1)[1])
        if path == "/api/live":
            lv = getattr(self, "_live", None)
            return lv if lv and time.time() - lv["t"] < 120 else {"img": None}
        if path == "/api/morning":
            pk = daily.load_pack() or {}
            if pk.get("date", "") <= time.strftime("%Y-%m-%d"):
                pk = daily.morning_pack(self._cfg)
            return pk
        if path == "/api/autonomy":
            return self.autonomy_get()
        simple = {"/api/plus": self.plus_get, "/api/life": self.life_get, "/api/health": self.health_get, "/api/study": self.study_get, "/api/ventures": self.ventures_get,
                  "/api/gaming": self.gaming_get, "/api/brain": self.brain_get}
        if path.split("?")[0] in simple:
            return simple[path.split("?")[0]]()
        if path.startswith("/api/study/cards"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
            return {"cards": self.study_cards((q.get("deck") or [""])[0])}
        raise KeyError(path)

    def remote_post(self, path, body):
        if path == "/api/jobs":
            j = self._jobs.add(body.get("text", ""), source="phone", heavy=bool(body.get("heavy")),
                               autopilot=bool(body.get("autopilot", True)))
            return j
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            return {"ok": self._jobs.cancel(path.split("/")[3])}
        if path == "/api/jobs/clear":
            self._jobs.clear_done()
            return {"ok": True}
        if path == "/api/schedule":
            return {"ok": self.schedule_add(body)}
        if path == "/api/schedule/remove":
            return {"ok": self.schedule_remove(body.get("id"))}
        if path == "/api/routines":
            return self.routines_action(body)
        if path == "/api/call":
            return self.call_turn(body.get("text", ""), body.get("first", False))
        if path == "/api/tts":
            return {"audio": self._tts(body.get("text", ""))}
        if path == "/api/clip":
            try:
                import pyperclip
                pyperclip.copy(body.get("text", ""))
                self._emit("toast", level="info", text="📋 Clipboard received from your phone.")
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if path == "/api/calls":
            return self.calls_save(body)
        if path == "/api/study/mark":
            return {"ok": self.study_mark(body.get("deck"), int(body.get("i", 0)), body.get("ok"))}
        if path == "/api/study/make":
            return {"ok": self.study_make(body.get("topic", ""), body.get("notes", ""), int(body.get("count", 12)))}
        if path == "/api/study":
            return self.study_action(body)
        if path == "/api/ventures":
            return self.ventures_action(body)
        if path == "/api/brain":
            return self.brain_action(body)
        if path == "/api/gaming":
            return self.gaming_set(body)
        if path == "/api/clipnow":
            return {"result": self.clip_now()}
        if path == "/api/life":
            return self.life_action(body)
        if path == "/api/autonomy":
            return self.autonomy_set(body)
        if path == "/api/scholar":
            if body.get("action") in ("paper", "mark", "plan", "topics"):     # phone: wait for the result
                fn = {"paper": lambda: scholar.make_paper(body.get("subject", ""), body.get("topics", ""), body.get("marks", 30)),
                      "mark": lambda: scholar.mark_paper(body.get("id"), body.get("answers") or {}, body.get("photos") or [],
                                                         body.get("minutes")),
                      "plan": lambda: scholar.revision_plan(14, 60, 120),
                      "topics": lambda: scholar.gen_topics(body.get("name", ""))}[body["action"]]
                return {"result": fn()}
            return self.scholar_action(body)
        if path == "/api/plus":
            return self.plus_action(body)
        if path == "/api/history":
            n = self._memory.merge_turns(body.get("turns", []))
            if n:
                self._emit("history_merged", count=n)
            return {"turns": self._memory.recent_full(60), "merged": n}
        if path == "/api/health/fix":
            return {"ok": self.health_fix(body.get("id", ""))}
        raise KeyError(path)

    def file_drop(self, name, raw):
        """Phone -> PC file drop: saved to Downloads\\ORION Drop."""
        name = re.sub(r"[^\w.\- ]", "_", os.path.basename(name or "file"))[:120] or "file"
        folder = os.path.join(os.path.expanduser("~"), "Downloads", "ORION Drop")
        os.makedirs(folder, exist_ok=True)
        fp = os.path.join(folder, name)
        base, ext = os.path.splitext(fp)
        n = 1
        while os.path.exists(fp):
            fp = f"{base} ({n}){ext}"
            n += 1
        with open(fp, "wb") as f:
            f.write(raw)
        self._emit("toast", level="info", text=f"📁 {os.path.basename(fp)} arrived from your phone.")
        return {"ok": True, "path": fp}

    def link_get(self):
        return {**{k: v for k, v in self._link.lc.items() if k != "pin"}, "has_pin": bool(self._link.lc.get("pin")),
                "online": self._link.online, "device": __import__("core.memory", fromlist=["DEVICE"]).DEVICE}

    def link_set(self, b):
        lc = self._link.lc
        if "addr" in b:
            lc["addr"] = (b.get("addr") or "").strip()
        if b.get("pin"):
            lc["pin"] = str(b["pin"]).strip()
        if "enabled" in b:
            lc["enabled"] = bool(b["enabled"])
        config_mod.save(self._cfg)
        return self.link_get()

    def autonomy_get(self):
        from core import autonomy as amod
        a = self._autonomy.ac
        return {**a, "log": amod.recent(40), "day": daily.day_cfg(self._cfg)}

    def autonomy_set(self, b):
        a = self._autonomy.ac
        for k in ("enabled",):
            if k in b:
                a[k] = bool(b[k])
        for k in ("idle_minutes", "every_minutes", "tasks_per_run"):
            if k in b:
                a[k] = max(1, int(b[k]))
        if b.get("run_now"):
            self._autonomy.run(0, "you asked")
        d = daily.day_cfg(self._cfg)
        for k in ("wake", "school_start", "school_end", "pc_off"):
            if b.get(k):
                d[k] = b[k]
        if "holiday" in b:
            d["holiday"] = bool(b["holiday"])
        config_mod.save(self._cfg)
        return self.autonomy_get()

    def calls_get(self):
        return calls.settings(self._cfg)

    def calls_save(self, b):
        c = calls.settings(self._cfg)
        for k in ("jobs", "reminders", "morning", "dms", "not_while_gaming"):
            if k in b:
                c[k] = bool(b[k])
        for k in ("quiet_from", "quiet_to"):
            if re.match(r"^\d{2}:\d{2}$", str(b.get(k, ""))):
                c[k] = b[k]
        config_mod.save(self._cfg)
        return c

    def call_me(self, reason=""):
        phone.push("call", reason=reason)
        return True

    def ring_phone(self):
        phone.push("ring")
        return True

    # ---------------------------------------------------------------- phone call mode
    def _tts(self, text):
        """Natural voice (same as the PC's) as base64 mp3 for the phone."""
        if not text or not self._speaker.neural_ok:
            return None
        try:
            import asyncio
            import base64
            from core.modes import voice as mode_voice
            mv, rate, pitch = mode_voice(self._cfg.get("theme", "standby"), self._cfg)
            audio = asyncio.run(self._speaker._neural(text[:900], mv, rate, pitch))
            return base64.b64encode(audio).decode() if audio else None
        except Exception:
            return None

    def call_turn(self, text, first=False):
        title = self._cfg.get("user_title", "sir")
        if first:
            reason = text.strip()
            hr = time.localtime().tm_hour
            g = "Morning" if hr < 12 else "Afternoon" if hr < 18 else "Evening"
            reply = f"{g}, {title}. {reason}" if reason else f"{g}, {title}. What can I do for you?"
        else:
            self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=f"📞 {text}")
            reply, _tier, _model = self._process(
                "[PHONE CALL — the user is talking to you out loud on a voice call. Reply in 1-2 short spoken "
                "sentences, no lists, no markdown, no code.]\n" + text, False, speak=False)
        clean = re.sub(r"```.*?```", " ", reply, flags=re.S)
        clean = re.sub(r"[*_#`>]", "", clean)
        return {"reply": clean.strip(), "audio": self._tts(clean.strip())}

    # ---------------------------------------------------------------- Night Shift panel
    def jobs_get(self):
        return {"jobs": self._jobs.list(60)}

    def job_add(self, text, heavy=False):
        return self._jobs.add(text, source="pc", heavy=bool(heavy))

    def job_cancel(self, jid):
        return self._jobs.cancel(jid)

    def jobs_clear(self):
        self._jobs.clear_done()
        return True

    def routines_get(self):
        return self._shift.listing()

    def routines_action(self, b):
        a = b.get("action")
        if a == "toggle_builtin":
            self._shift.set_builtin(b["id"], on=b.get("on"))
        elif a == "time_builtin":
            self._shift.set_builtin(b["id"], hhmm=b.get("time"))
        elif a == "run":
            if b["id"] in __import__("core.routines", fromlist=["BUILTIN"]).BUILTIN:
                self._shift.run_builtin(b["id"])
            else:
                c = next((c for c in self._shift.ns["custom"] if c["id"] == b["id"]), None)
                if c:
                    self._jobs.add(c["prompt"], source="routine", title=f"⏰ {c['name']}", heavy=c.get("heavy", False))
        elif a == "add":
            self._shift.add_custom(b.get("name", ""), b.get("prompt", ""), b.get("time", "09:00"),
                                   b.get("days", "daily"), b.get("heavy", False))
        elif a == "remove":
            self._shift.remove_custom(b["id"])
        elif a == "toggle_custom":
            for c in self._shift.ns["custom"]:
                if c["id"] == b["id"]:
                    c["on"] = bool(b.get("on"))
            self._shift._persist()
        elif a == "settings":
            ns = self._shift.ns
            if "enabled" in b:
                ns["enabled"] = bool(b["enabled"])
            if b.get("idle_minutes"):
                ns["idle_minutes"] = max(1, int(b["idle_minutes"]))
            self._shift._persist()
        return self._shift.listing()

    def transcribe_bytes(self, raw):
        prov = self._brain.groq_like
        if not prov or not raw:
            return ""
        head = raw[:12]
        name, mime = ("speech.webm", "audio/webm")
        if head[:4] == b"OggS":
            name, mime = "speech.ogg", "audio/ogg"
        elif b"ftyp" in head:
            name, mime = "speech.m4a", "audio/mp4"
        elif head[:4] == b"RIFF":
            name, mime = "speech.wav", "audio/wav"
        try:
            return prov.transcribe(raw, name, mime, prompt=self._ears.vocab())
        except Exception:
            return ""

    def open_link(self, url):
        webbrowser.open(url)
        return True

    def memories(self):
        return [f["text"] for f in self._memory.facts]

    # ---------------------------------------------------------------- brain page (memory, shortcuts, habits)
    def brain_get(self):
        return {"facts": [{"i": i, "text": f["text"], "cat": f.get("cat", "fact"), "t": f.get("t", ""),
                           "src": f.get("src", "you")} for i, f in enumerate(self._memory.facts)],
                "shortcuts": learning.shortcuts(), "suggest": learning.suggestions(), "habits": learning.habits(),
                "local": self._brain.local.fast[0], "auto_learn": self._cfg.get("auto_learn", True)}

    def brain_action(self, b):
        a = b.get("action")
        if a == "fact_add":
            self._memory.add_fact(b.get("text", ""), b.get("cat", "fact"))
        elif a == "fact_del":
            self._memory.remove(int(b.get("i", -1)))
        elif a == "short_add":
            learning.add_shortcut(b.get("phrase", ""), b.get("does", ""))
        elif a == "short_del":
            learning.remove_shortcut(b.get("phrase", ""))
        elif a == "auto_learn":
            self._cfg["auto_learn"] = bool(b.get("on"))
            config_mod.save(self._cfg)
        elif a == "learn_now":
            threading.Thread(target=lambda: self._emit(
                "toast", level="info", text=f"🧠 Learned {self._memory.learn_from_chat(self._brain)} new thing(s).")).start()
        return self.brain_get()

    # ---------------------------------------------------------------- ventures + gaming pages
    def ventures_get(self):
        return {"dev": ventures.dev_sync(self._jobs), "earn": ventures.earn_summary(), "goals": money.goals(),
                "crm": money.crm(), "followups": [x["id"] for x in money.crm_followups()], "stages": money.STAGES,
                "ideas": list(reversed(money.ideas()))[:20], "per_hour": money.per_hour(),
                "content": self._shift.ns["builtin"].get("content", {}).get("on", False)}

    def ventures_action(self, b):
        a = b.get("action")
        if a == "dev_add":
            try:
                ventures.dev_add(b.get("task", ""), b.get("project") or "Projects")
            except ValueError as e:
                self._emit("toast", level="warn", text=str(e))
        elif a == "dev_del":
            ventures.dev_remove(b.get("id"))
        elif a == "dev_now":
            ventures.queue_dev_tasks(self._jobs, [b.get("id")])
        elif a == "earn_add":
            ventures.earn_add(b.get("venture", "Other"), float(b.get("amount") or 0), b.get("note", ""), b.get("date") or None)
        elif a == "earn_del":
            ventures.earn_remove(b.get("id"))
        elif a == "leads":
            self._toolbox.run("leads_find", {"business_type": b.get("type", ""), "area": b.get("area", ""),
                                             "offer": b.get("offer", "")})
        elif a == "content":
            self._shift.set_builtin("content", on=bool(b.get("on")))
        elif a == "goal":
            money.add_goal(b.get("name", "Goal"), float(b.get("target") or 0), b.get("by") or "2027-07-31", b.get("venture", ""))
        elif a == "goal_del":
            money._save(money.GOALS, [g for g in money._load(money.GOALS, []) if g["id"] != b.get("id")])
        elif a == "crm":
            money.crm_upsert(b.get("name", ""), b.get("stage", "lead"), note=b.get("note", ""), value=b.get("value"),
                             next=b.get("next", ""), next_date=b.get("next_date", ""))
        elif a == "crm_del":
            money._save(money.CRM, [x for x in money.crm() if x["id"] != b.get("id")])
        elif a == "idea":
            return self._bg(money.score_idea, "idea_scored", b.get("idea", ""))
        elif a == "hours":
            money.log_hours(b.get("venture", "Other"), int(b.get("minutes") or 0))
        elif a == "invoice":
            path, total, num = money.make_invoice(b.get("client", ""), b.get("items", []), int(b.get("due_days", 14)))
            try:
                os.startfile(path)
            except Exception:
                pass
            self._emit("toast", level="info", text=f"🧾 Invoice {num} — £{total:.2f}")
        elif a == "meeting":
            self._emit("message", id=uuid.uuid4().hex[:8], role="assistant", text=money.money_meeting_text(), tier="reflex")
        return self.ventures_get()

    def gaming_get(self):
        g = self._cfg.setdefault("gaming", {})
        live = {}
        if self._gaming.active:
            st = self.stats()
            live = {"cpu": st.get("cpu"), "ram": st.get("ram"), "mins": int((time.time() - self._gaming.started) // 60),
                    "clips": getattr(self._gaming, "session_clips", 0), "held": len(self._gaming.held),
                    "held_items": self._gaming.held[-5:], "doctor": getattr(self._gaming, "doctor_notes", [])[-3:]}
        return {**gaming_mod.game_stats(int(7)), "active": self._gaming.active, "live": live,
                "profiles": g.get("profiles", {}),
                "game": gaming_mod.nice_name(self._gaming.game) if self._gaming.active else None,
                "settings": {"auto": g.get("auto", True), "boost": g.get("boost", True),
                             "clip_buffer": g.get("clip_buffer", False), "break_every_min": g.get("break_every_min", 120),
                             "high_performance": g.get("high_performance", True),
                             "controller_talk": g.get("controller_talk", True),
                             "stealth_while_gaming": g.get("stealth_while_gaming", True)}}

    def gaming_set(self, b):
        g = self._cfg.setdefault("gaming", {})
        if "profile" in b:
            pr = b["profile"]
            g.setdefault("profiles", {})[pr["game"]] = {"open": pr.get("open", []), "close": pr.get("close", [])}
        if "profile_del" in b:
            g.setdefault("profiles", {}).pop(b["profile_del"], None)
        for k in ("auto", "boost", "clip_buffer", "high_performance", "controller_talk", "stealth_while_gaming"):
            if k in b:
                g[k] = bool(b[k])
        if "break_every_min" in b:
            g["break_every_min"] = max(0, int(b["break_every_min"] or 0))
        config_mod.save(self._cfg)
        return self.gaming_get()

    def clip_now(self):
        r = self._gaming.clip(30)
        self._emit("toast", level="info", text="🎬 " + r)
        return r

    # ---------------------------------------------------------------- scholar (Study 2.0)
    def scholar_get(self):
        o = scholar.overview()
        o["mistakes"] = scholar.mistakes_due(10)
        return o

    def scholar_paper(self, pid):
        return scholar.get_paper(pid)

    def _bg(self, fn, event, *a):
        def run():
            try:
                self._emit(event, ok=True, data=fn(*a))
            except Exception as e:
                self._emit(event, ok=False, error=str(e))
        threading.Thread(target=run, daemon=True).start()
        return True

    def scholar_action(self, b):
        a = b.get("action")
        if a == "subject":
            scholar.add_subject(b.get("name", ""), b.get("board", ""), b.get("target", ""))
            threading.Thread(target=scholar.gen_topics, args=(b.get("name", ""),), daemon=True).start()
        elif a == "subject_del":
            with scholar._lock:
                d = scholar._load()
                d["subjects"] = [x for x in d["subjects"] if x["name"] != b.get("name")]
                scholar._save(d)
        elif a == "topics":
            return self._bg(scholar.gen_topics, "scholar_topics", b.get("name", ""))
        elif a == "rate":
            scholar.rate_topic(b.get("subject", ""), b.get("topic", ""), b.get("rating", "amber"))
        elif a == "paper":
            return self._bg(scholar.make_paper, "exam_paper", b.get("subject", ""), b.get("topics", ""), b.get("marks", 30))
        elif a == "mark":
            return self._bg(scholar.mark_paper, "exam_marked", b.get("id"), b.get("answers") or {},
                            b.get("photos") or [], b.get("minutes"))
        elif a == "mistake":
            scholar.mistake_done(b.get("id"), bool(b.get("correct")))
        elif a == "timetable":
            scholar.set_timetable(b.get("day", ""), b.get("lessons", []))
        elif a == "plan":
            return self._bg(scholar.revision_plan, "revision_planned", int(b.get("days", 14)),
                            int(b.get("weekday", 60)), int(b.get("weekend", 120)))
        elif a == "tutor":
            self.send(f"Teach me {b.get('topic', '')}" + (f" ({b.get('subject')})" if b.get("subject") else ""))
        return self.scholar_get()

    # ---------------------------------------------------------------- study page
    def study_get(self):
        return study.overview()

    def study_cards(self, deck=""):
        return study.due_cards(deck or None, 30)

    def study_mark(self, deck, i, ok):
        study.mark(deck, i, bool(ok))
        return True

    def study_make(self, topic, notes="", count=12):
        def run():
            try:
                cards = study.make_cards(topic, notes, count)
                n = study.add_deck(topic.strip()[:60], cards)
                self._emit("study", ok=True, text=f"Made {len(cards)} cards — '{topic[:60]}' now has {n}.")
            except Exception as e:
                self._emit("study", ok=False, text=f"Couldn't make cards: {e}")
        threading.Thread(target=run, daemon=True).start()
        return True

    def study_action(self, b):
        a = b.get("action")
        if a == "focus":
            study.FOCUS.start(int(b.get("minutes", 25)), b.get("subject", ""), int(b.get("brk", 5)), b.get("total") or None)
        elif a == "unfocus":
            study.FOCUS.stop()
        elif a == "exam":
            study.exam_add(b.get("subject", ""), b.get("date", ""))
        elif a == "exam_del":
            with study._lock:
                d = study._load()
                d["exams"] = [e for e in d["exams"] if e["subject"] != b.get("subject")]
                study._save(d)
        elif a == "deck_del":
            with study._lock:
                d = study._load()
                d["decks"].pop(b.get("deck", ""), None)
                study._save(d)
        return study.overview()

    def clear_chat(self):
        self._memory.clear_history()
        return True

    def mini_toggle(self):
        """Mini mode: ORION shrinks to a small always-on-top orb in the corner (click it to talk)."""
        import webview
        if getattr(self, "_mini", None):
            try:
                self._mini.destroy()
            except Exception:
                pass
            self._mini = None
            if self._window:
                self._window.restore()
            return False
        x, y = 40, 40
        try:
            import ctypes
            x = ctypes.windll.user32.GetSystemMetrics(0) - 190
            y = ctypes.windll.user32.GetSystemMetrics(1) - 240
        except Exception:
            pass
        self._mini = webview.create_window("ORION mini", url=os.path.join(os.path.dirname(UI_PATH), "mini.html"),
                                           js_api=self, width=140, height=150, x=x, y=y, frameless=True,
                                           on_top=True, easy_drag=True, resizable=False, background_color="#02060b")
        if self._window:
            self._window.minimize()
        return True

    def toggle_fullscreen(self):
        if self._window:
            self._window.toggle_fullscreen()
        return True

    def minimize(self):
        if self._window:
            self._window.minimize()
        return True

    # ---------------------------------------------------------------- 4.2 extras (grades, marking, wrapped, quotes)
    def plus_get(self):
        out = {}
        for k, fn in (("grades", plus.predict_grades), ("money", plus.money_wrapped), ("gaming", plus.gaming_wrapped)):
            try:
                out[k] = fn()
            except Exception as e:
                out[k] = {"error": str(e)} if k != "grades" else []
        return out

    def plus_action(self, body):
        a = (body or {}).get("action", "")
        try:
            if a == "essay":
                r = plus.mark_writing(body.get("text", ""), body.get("question", ""), body.get("subject") or "English Literature",
                                      body.get("board", ""))
            elif a == "working":
                r = plus.check_working(body.get("question", ""), body.get("working", ""), (body.get("photos") or [None])[0])
            elif a == "photo_cards":
                r = plus.cards_from_photo(body.get("photos") or [], body.get("deck", ""), int(body.get("count") or 12))
            elif a == "price":
                r = plus.price_job(body.get("kind", "other"), body.get("hours") or None, body.get("client") or "small business",
                                   bool(body.get("rush")))
            else:
                return {"ok": False, "error": "unknown action"}
            return {"ok": True, "result": r}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def power_down(self):
        """Plays the power-down sequence (UI animation + voice), then quits."""
        self._emit("powerdown", title=self._cfg.get("user_title", "sir"))
        try:
            if self._cfg["voice"]["speak_replies"]:
                self._speaker.say(f"Powering down. Goodbye, {self._cfg.get('user_title', 'sir')}.")
        except Exception:
            pass
        threading.Timer(3.2, self.quit).start()
        return True

    # ---------------------------------------------------------------- holo browser windows (click to drive it yourself)
    def _bshot(self, delay=0.0):
        from core.browser import B
        import base64 as _b64

        def grab(p):
            if delay:
                p.wait_for_timeout(int(delay * 1000))
            return _b64.b64encode(p.screenshot(type="jpeg", quality=60)).decode(), p.url, p.title()
        img, url, title = B.call(grab, 30)
        return {"img": img, "url": url, "title": title}

    def browser_shot(self):
        try:
            return self._bshot()
        except Exception as e:
            return {"error": str(e)}

    def browser_click_at(self, fx, fy):
        from core.browser import B
        try:
            B.call(lambda p: p.mouse.click(float(fx) * p.viewport_size["width"], float(fy) * p.viewport_size["height"]), 20)
            return self._bshot(0.9)
        except Exception as e:
            return {"error": str(e)}

    def browser_scroll(self, dy):
        from core.browser import B
        try:
            B.call(lambda p: p.mouse.wheel(0, int(dy)), 15)
            return self._bshot(0.35)
        except Exception as e:
            return {"error": str(e)}

    def browser_go(self, text):
        from core.browser import B
        import urllib.parse as _u
        t = (text or "").strip()
        if not t:
            return {"error": "empty"}
        if t.lower() == "back":
            fn = lambda p: p.go_back(timeout=15000)
        else:
            url = t if "://" in t else (f"https://{t}" if "." in t and " " not in t else
                                         "https://duckduckgo.com/?q=" + _u.quote_plus(t))
            fn = lambda p: p.goto(url, timeout=20000, wait_until="domcontentloaded")
        try:
            B.call(fn, 30)
            return self._bshot(0.6)
        except Exception as e:
            return {"error": str(e)}

    def browser_type_text(self, text, enter=False):
        from core.browser import B
        try:
            def go(p):
                p.keyboard.type(str(text)[:2000], delay=8)
                if enter:
                    p.keyboard.press("Enter")
            B.call(go, 20)
            return self._bshot(0.8 if enter else 0.2)
        except Exception as e:
            return {"error": str(e)}

    def browser_show_real(self, url):
        import webbrowser
        if str(url).startswith("http"):
            webbrowser.open(url)
        return True

    def quit(self):
        self._speaker.stop()
        try:
            if self._sync.enabled:
                self._sync.sync_now()          # so the laptop/phone carry on from exactly here
        except Exception:
            pass
        if self._window:
            self._window.destroy()
        os._exit(0)


def _fatal(msg):
    log.error(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg[:1500] + f"\n\nFull log: {LOG_PATH}",
                                         "ORION failed to start", 0x10)
    except Exception:
        print(msg)


def main():
    try:
        import webview
    except ImportError:
        _fatal("pywebview isn't installed. Double-click 1_SETUP.bat first.")
        return
    api = Api()
    # warm up the app index in the background so the first "open X" is instant
    threading.Thread(target=tools._start_menu_index, daemon=True).start()
    window = webview.create_window(
        api._cfg.get("assistant_name", "ORION"), url=UI_PATH, js_api=api,
        fullscreen=api._cfg.get("fullscreen", True), width=1366, height=820,
        min_size=(900, 600), background_color="#03060c", text_select=True)
    api._window = window
    log.info("starting UI")
    webview.start(debug=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _fatal(traceback.format_exc())

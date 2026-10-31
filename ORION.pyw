"""ORION — double-click to launch.  (.pyw = no console window)"""
import json
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
from core.routines import NightShift                        # noqa: E402
from core.devices import Push, Remote, Sync, Updater        # noqa: E402
from core.gaming import GamingMode, Hotkey                  # noqa: E402
from core.listen import VoiceID, WakeListener, extras_status  # noqa: E402
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
                         open_claude=self._open_claude, set_theme=self._set_theme, cancel=self._cancel,
                         emit=self._emit)
        skills.load_all()
        self._toolbox = tools.Toolbox(self._cfg, self._emit, self._confirm)
        self._brain = Brain(self._cfg, self._memory, self._toolbox, self._emit, self._context)
        self._speaker = Speaker(self._cfg, self._emit)
        self._recorder = Recorder()
        self._gaming = GamingMode(self._cfg, self._emit, self._notify, self._brain)
        self._scheduler = schedule.Scheduler(self._cfg, self._notify)
        self._hotkey = Hotkey(self._cfg.get("hotkey", "ctrl+alt+space"), self._hk_start, self._hk_stop)
        tools.CTX["brain"] = self._brain
        self._push = Push(self._cfg)
        self._root = root.RootWatcher(self._cfg, self._notify, self._brain)
        self._remote = Remote(self._cfg, self)
        self._sync = Sync(self._cfg, self._emit)
        self._sync.start()
        self._updater = Updater(self._cfg, self._emit)
        self._updater.start()
        self._jobs = Jobs(self._cfg, self._run_job, lambda t, title=None: self._push.send(t, title), self._emit)
        self._shift = NightShift(self._cfg, self._jobs, self._shift_notify, self._emit, self._updater)
        self._voice_id = VoiceID(self._cfg)
        self._wake = WakeListener(self._cfg, self._wake_command, self._emit, self._voice_id,
                                  busy=lambda: self._recorder.recording or self._busy.locked())
        if self._cfg.get("remote", {}).get("enabled"):
            try:
                self._remote.start()
            except Exception as e:
                log.warning(str(e))
        if self._cfg.get("wake", {}).get("enabled"):
            self._wake.start()

    # ---------------------------------------------------------------- plumbing
    def _emit(self, kind, **data):
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
        src = {"phone": "📱", "routine": "⏰", "voice": "🗂"}.get(j["source"], "🗂")
        self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=f"{src} JOB: {j['title']}")
        return self._process(j["text"], j.get("autopilot", True), speak=False)

    def _shift_notify(self, text, title=None):
        self._emit("toast", level="info", text=(title + ": " if title else "") + text.split("\n")[0][:140])
        self._push.send(text, title)

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
        self.mic_start()
        self._emit("toast", level="info", text="Listening… press the hotkey again to send.")

    def _hk_stop(self):
        text = self.mic_stop()
        if text:
            self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=text)
            self.send(text)

    def _open_claude(self, question):
        try:
            import pyperclip
            pyperclip.copy(question)
        except Exception:
            pass
        base = self._cfg.get("claude_url", "https://claude.ai/new")
        webbrowser.open(f"{base}?q={urllib.parse.quote(question[:3000])}")
        self._emit("claude", text=question)

    def _set_theme(self, theme):
        self._cfg["theme"] = theme
        config_mod.save(self._cfg)
        self._emit("theme", theme=theme)

    # ---------------------------------------------------------------- startup
    def init(self):
        c = self._cfg
        vis = c.get("visuals", "auto")
        lite = vis == "lite" or (vis == "auto" and _ram_gb() <= 6.5)
        return {"name": c["assistant_name"], "title": c["user_title"], "version": config_mod.VERSION,
                "theme": c["theme"], "brain": c["brain"], "speak": c["voice"]["speak_replies"],
                "safe_mode": c["safe_mode"], "lite": lite, "skip_boot": c.get("skip_boot", False),
                "has_key": bool(self._brain.cloud), "mic": self._recorder.available,
                "neural": self._speaker.neural_ok, "hotkey": self._cfg.get("hotkey") if self._hotkey.ok else None,
                "gaming": self._gaming.active, "game": self._gaming.game,
                "afk": getattr(self, "_root", None) and self._root.afk,
                "afk_note": getattr(self, "_root", None) and self._root.afk_note,
                "history": self._memory.recent(16), "facts": len(self._memory.facts)}

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
        threading.Thread(target=self._process, args=(text, autopilot), daemon=True).start()
        return True

    def autopilot(self, goal):
        tools.CTX["plan"] = {"steps": [], "current": 0, "done": False, "note": ""}
        self._emit("plan", **tools.CTX["plan"])
        return self.send(goal, autopilot=True)

    def stop(self):
        self._cancel.set()
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
        self._emit("message", id=uuid.uuid4().hex[:8], role="user", text=f"📱 {text}")
        reply, tier, model = self._process(text, False, speak=False)
        return {"reply": reply, "tier": tier, "model": model}

    def _process(self, text, autopilot=False, speak=True):
        with self._busy:
            self._cancel.clear()
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
                buf.append(chunk)
                speech.feed(chunk)
                if time.time() - last[0] > 0.06:
                    flush()

            try:
                reply, tier, model = self._brain.handle(text, on_delta, self._cancel, autopilot)
                flush()
                self._emit("stream_end", id=mid, text=reply, tier=tier, model=model)
                if speak and not speech.flush():
                    self._speaker.say(reply)
                if autopilot:
                    self._push.send(f"Mission complete: {reply[:300]}", "ORION Autopilot")
            except Cancelled:
                flush()
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
        try:
            self._speaker.stop()
            self._recorder.start()
            self._emit("state", state="listening")
            return True
        except Exception as e:
            self._emit("toast", level="warn", text=str(e))
            return False

    def mic_level(self):
        return self._recorder.level() if self._recorder.recording else 0

    def mic_stop(self):
        wav = self._recorder.stop()
        self._emit("state", state="idle")
        if not wav:
            return ""
        prov = self._brain.groq_like
        if not prov:
            self._emit("toast", level="warn", text="Voice input needs a Groq key (free) — add it in Settings.")
            return ""
        self._emit("state", state="thinking")
        try:
            text = prov.transcribe(wav)
        except Exception as e:
            self._emit("state", state="idle")
            self._emit("toast", level="warn", text=f"Couldn't hear that: {e}")
            return ""
        self._emit("state", state="idle")
        return text

    # ---------------------------------------------------------------- controls
    def ask_claude(self, text=""):
        self._open_claude(text or "Hey Claude — I've got a question for you.")
        return True

    def set_brain(self, mode):
        if mode in ("auto", "cloud", "local"):
            self._cfg["brain"] = mode
            config_mod.save(self._cfg)
        return self._brain.status()

    def set_theme(self, theme):
        tools.set_theme(theme)
        return theme

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
                "fullscreen": c["fullscreen"], "visuals": c["visuals"], "skip_boot": c.get("skip_boot", False)}

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
                self._emit("toast", level="info", text="Installing update — ORION will restart…")
                self._updater.install()
                self.quit()
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
        if path == "/api/routines":
            return self._shift.listing()
        if path == "/api/root":
            return {"afk": self._root.afk, "note": self._root.afk_note, "log": root.recent_log(30)}
        if path == "/api/stats":
            return {**self.stats(), "meters": self._brain.meters()}
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
        raise KeyError(path)

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
            return prov.transcribe(raw, name, mime)
        except Exception:
            return ""

    def open_link(self, url):
        webbrowser.open(url)
        return True

    def memories(self):
        return [f["text"] for f in self._memory.facts]

    def clear_chat(self):
        self._memory.clear_history()
        return True

    def toggle_fullscreen(self):
        if self._window:
            self._window.toggle_fullscreen()
        return True

    def minimize(self):
        if self._window:
            self._window.minimize()
        return True

    def quit(self):
        self._speaker.stop()
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

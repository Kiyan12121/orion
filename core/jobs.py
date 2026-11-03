"""Job queue: work that keeps going in the background.

Anything sent from the phone, a routine, or "queue this" becomes a job with a ticket ID. Jobs are saved
to data/jobs.json, run one at a time on the PC, survive the phone app closing, and send a push
notification when finished. Heavy jobs can wait until the PC is idle (not gaming, no input for a while).
"""
import json
import os
import threading
import time
import uuid

from .paths import DATA_DIR
from .tools import CTX, tool

PATH = os.path.join(DATA_DIR, "jobs.json")
_lock = threading.RLock()


def idle_seconds():
    """Seconds since the last mouse/keyboard input (Windows)."""
    try:
        import ctypes

        class LII(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LII()
        lii.cbSize = ctypes.sizeof(LII)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
    except Exception:
        return 0.0


class Jobs:
    """runner(job) -> (reply, tier, model). notify(text, title)."""

    def __init__(self, cfg, runner, notify, emit):
        self.cfg = cfg
        self.runner = runner
        self.notify = notify
        self.emit = emit
        self.current = None
        self.on_finish = None          # hook: called with the job when it finishes (auto-calls)
        self.wake = threading.Event()
        self.jobs = self._load()
        for j in self.jobs:                       # anything "running" when ORION closed goes back in the queue
            if j["status"] == "running":
                j["status"] = "queued"
        self._save()
        CTX["jobs"] = self
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ storage
    def _load(self):
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self):
        with _lock:
            keep = [j for j in self.jobs if j["status"] in ("queued", "running", "waiting")]
            done = [j for j in self.jobs if j not in keep][-150:]
            self.jobs = done + keep
            from .safeio import write_json
            write_json(PATH, self.jobs, indent=1)

    def _changed(self, j=None):
        self._save()
        self.emit("jobs_changed", job=j)

    # ------------------------------------------------------------------ API
    def add(self, text, source="pc", title=None, autopilot=True, heavy=False, notify=True, routine=None):
        j = {"id": uuid.uuid4().hex[:8], "text": text.strip(), "title": (title or text.strip())[:80],
             "source": source, "status": "queued", "autopilot": bool(autopilot), "heavy": bool(heavy),
             "notify": bool(notify), "routine": routine, "created": time.time(), "started": None,
             "finished": None, "result": "", "tier": None, "note": ""}
        with _lock:
            self.jobs.append(j)
        self._changed(j)
        self.wake.set()
        return j

    def get(self, jid):
        return next((j for j in self.jobs if j["id"] == jid), None)

    def list(self, limit=40):
        order = {"running": 0, "waiting": 1, "queued": 2}
        active = sorted([j for j in self.jobs if j["status"] in order], key=lambda j: (order[j["status"]], j["created"]))
        done = sorted([j for j in self.jobs if j["status"] not in order], key=lambda j: -(j["finished"] or 0))
        return (active + done)[:limit]

    def cancel(self, jid):
        j = self.get(jid)
        if not j:
            return False
        if j["status"] == "running":
            CTX["cancel"].set()
            stop = CTX.get("stop_all")
            stop and stop()
        elif j["status"] in ("queued", "waiting"):
            j["status"] = "cancelled"
            j["finished"] = time.time()
            self._changed(j)
        return True

    def clear_done(self):
        with _lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("queued", "running", "waiting")]
        self._changed()

    def retry_later(self, jid, minutes=15):
        """Park a job until the AI allowance comes back."""
        j = self.get(jid)
        if j:
            j["retry_at"] = time.time() + minutes * 60
            j["status"], j["note"] = "waiting", "waiting for a brain to be free — retries automatically"
            self._changed(j)

    def since(self, ts):
        return [j for j in self.jobs if (j["finished"] or 0) > ts and j["status"] in ("done", "failed")]

    # ------------------------------------------------------------------ worker
    def _can_run_heavy(self):
        ns = self.cfg.get("night_shift", {})
        g = CTX.get("gaming")
        if g and g.active:
            return False, "waiting — you're gaming"
        need = int(ns.get("idle_minutes", 10)) * 60
        if idle_seconds() < need:
            return False, f"waiting — runs after {ns.get('idle_minutes', 10)} min of you being away"
        return True, ""

    def _next(self):
        for j in sorted(self.jobs, key=lambda x: x["created"]):
            if j["status"] not in ("queued", "waiting"):
                continue
            if j.get("retry_at") and j["retry_at"] > time.time():
                continue
            if j["heavy"]:
                ok, why = self._can_run_heavy()
                if not ok:
                    if j["status"] != "waiting" or j["note"] != why:
                        j["status"], j["note"] = "waiting", why
                        self._changed(j)
                    continue
            return j
        return None

    def _loop(self):
        CTX["job_thread"] = threading.get_ident()
        time.sleep(6)
        while True:
            j = self._next()
            if not j:
                self.wake.wait(20)
                self.wake.clear()
                continue
            self.current = j
            j.update(status="running", started=time.time(), note="working…")
            self._changed(j)
            try:
                reply, tier, model = self.runner(j)
                if (reply or "").startswith("Every brain I have is out") and j.get("tries", 0) < 12:
                    j["tries"] = j.get("tries", 0) + 1
                    self.current = None
                    self.retry_later(j["id"], 15 if j["tries"] < 4 else 60)
                    continue
                stopped = reply == "Stopped."
                j.update(status="cancelled" if stopped else "done", result=reply or "Done.", tier=tier,
                         note="" if not stopped else "cancelled")
            except Exception as e:
                j.update(status="failed", result=f"{type(e).__name__}: {e}", note="failed")
            j["finished"] = time.time()
            self.current = None
            self._changed(j)
            if j["notify"] and j["status"] in ("done", "failed"):
                icon = "✅" if j["status"] == "done" else "⚠️"
                self.notify(f"{icon} {j['title']}\n{(j['result'] or '')[:300]}",
                            "ORION job finished" if j["status"] == "done" else "ORION job failed")
                if self.on_finish:
                    try:
                        self.on_finish(j)
                    except Exception:
                        pass


# ------------------------------------------------------------------ AI tools
@tool("Queue a job to run in the BACKGROUND (the user gets a notification when it's done). Use when the user "
      "says 'queue', 'later', 'in the background', 'overnight', 'when I'm away', or for long jobs like building "
      "an app or editing videos. heavy=true makes it wait until the PC is idle and not gaming.",
      {"task": ("string", "Full instructions for the job", True),
       "heavy": ("boolean", "Wait until the PC is idle (videos, big builds)", False)})
def queue_job(task, heavy=False):
    q = CTX.get("jobs")
    if not q:
        return "Job queue isn't running."
    j = q.add(task, source="voice", heavy=bool(heavy))
    ahead = sum(1 for x in q.jobs if x["status"] in ("queued", "running", "waiting") and x is not j)
    return f"Queued (ticket {j['id']}). {ahead} job(s) ahead of it." + (" It'll wait until you're away." if heavy else "")


@tool("List background jobs and their status.")
def list_jobs():
    q = CTX.get("jobs")
    if not q:
        return "Job queue isn't running."
    rows = [f"[{j['id']}] {j['status'].upper()}: {j['title']}" + (f" — {j['result'][:120]}" if j["result"] else "")
            for j in q.list(15)]
    return "\n".join(rows) or "No jobs."

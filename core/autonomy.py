"""Autonomous mode: when Kiyan has been away for a while (30 min by default), ORION gets on with things by
itself — then messages or rings his phone if something matters. Everything it does is logged.

Freedom: full (Kiyan's choice) — but these hard limits always apply: never spend money, never delete the
user's files, never type passwords/payment details, always say it's the assistant when messaging friends,
and the safety blocklist still applies to every command.
"""
import json
import os
import threading
import time

from .paths import DATA_DIR
from .tools import CTX, tool

LOG = os.path.join(DATA_DIR, "autonomy.json")

RULES = """AUTONOMOUS MODE — the user has been away from the PC for {mins} minutes. You're working on your own.
Pick the {n} most useful things to do RIGHT NOW from the situation below, do them with your tools, then stop.
Good things to do: chase homework/exams (message the user a nudge if something's due soon), answer Root DMs as
the user's assistant (always say you're his assistant), research or draft things for his money projects (leads,
pitch ideas, price research) and save them as notes, make Shorts from new videos, tidy and organise, prepare
tomorrow (revision plan, kit, schedule clashes), learn useful facts about his projects.
HARD LIMITS: never spend money, buy or subscribe to anything; never delete the user's files; never type passwords
or payment details; never post publicly; never work on Hatchlands; don't repeat something from the recent log.
Use message_user for anything the user should know (urgent=true only if it truly can't wait — that rings his phone).
Finish with a 1-3 line report of what you did.

SITUATION:
{situation}

RECENT AUTONOMOUS LOG (don't repeat these):
{log}"""


def _load():
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(v):
    from .safeio import write_json
    write_json(LOG, v[-300:], indent=1)


def log_entry(text, kind="did"):
    d = _load()
    d.append({"t": time.time(), "when": time.strftime("%a %H:%M"), "kind": kind, "text": text[:600]})
    _save(d)
    emit = CTX.get("emit")
    if emit:
        emit("autonomy", entry=d[-1])


def recent(n=30):
    return list(reversed(_load()))[:n]


def situation():
    lines = [time.strftime("Now: %A %d %B, %H:%M.")]
    try:
        from .life import homework
        hw = [h for h in homework() if not h.get("done") and h["days"] <= 3]
        if hw:
            lines.append("Homework due soon: " + "; ".join(f"{h['subject']} {h['task']} (due {h['due']})" for h in hw))
    except Exception:
        pass
    try:
        from .study import overview
        o = overview()
        lines.append(f"Revision today: {o['today']} min, streak {o['streak']}." +
                     (f" Next exam: {o['exams'][0]['subject']} in {o['exams'][0]['days']} days." if o["exams"] else ""))
    except Exception:
        pass
    try:
        from .schedule import upcoming
        up = upcoming(2)[:4]
        if up:
            lines.append("Coming up: " + "; ".join(f"{o['at']:%a %H:%M} {o['title']}" for o in up))
    except Exception:
        pass
    try:
        from .root import recent_log
        dms = [e for e in recent_log(15) if e["kind"] == "received"]
        if dms:
            lines.append(f"Recent Root DMs: {len(dms)} (latest from {dms[-1].get('who', '?')}).")
    except Exception:
        pass
    try:
        from .ventures import dev_list, earn_summary
        todo = [t for t in dev_list() if t["status"] == "todo"]
        if todo:
            lines.append(f"Dev queue: {len(todo)} task(s) waiting.")
        lines.append(f"Money this month: £{earn_summary()['this_month']:.2f}.")
    except Exception:
        pass
    try:
        from .money import goals_text
        g = goals_text()
        if g:
            lines.append(g)
    except Exception:
        pass
    try:
        from .life import notes
        todo = [n["text"] for n in notes() if n.get("tag") in ("todo", "idea")][-5:]
        if todo:
            lines.append("Open ideas/todos in notes: " + " | ".join(t[:80] for t in todo))
    except Exception:
        pass
    return "\n".join(lines)


class Autonomy:
    def __init__(self, cfg, jobs, emit):
        self.cfg = cfg
        self.jobs = jobs
        self.emit = emit
        self.last_run = 0
        self.running_job = None
        CTX["autonomy"] = self
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def ac(self):
        a = self.cfg.setdefault("autonomy", {})
        a.setdefault("enabled", True)
        a.setdefault("idle_minutes", 30)
        a.setdefault("every_minutes", 45)
        a.setdefault("tasks_per_run", 3)
        a.setdefault("freedom", "full")
        return a

    def _loop(self):
        from .jobs import idle_seconds
        time.sleep(120)
        while True:
            try:
                a = self.ac
                g = CTX.get("gaming")
                idle = idle_seconds()
                busy = self.running_job and (self.jobs.get(self.running_job) or {}).get("status") in ("queued", "running")
                if (a["enabled"] and idle >= a["idle_minutes"] * 60 and not busy and not (g and g.active)
                        and time.time() - self.last_run >= a["every_minutes"] * 60):
                    self.run(int(idle // 60))
            except Exception:
                pass
            time.sleep(60)

    def run(self, mins=0, why="you were away"):
        self.last_run = time.time()
        log = "\n".join(f"- {e['when']}: {e['text'][:140]}" for e in recent(12)) or "(nothing yet)"
        prompt = "[AUTONOMOUS] " + RULES.format(mins=mins or self.ac["idle_minutes"], n=self.ac["tasks_per_run"],
                                                situation=situation(), log=log)
        j = self.jobs.add(prompt, source="auto", title="🤖 Autonomous check-in", autopilot=True, notify=False)
        self.running_job = j["id"]
        log_entry(f"Started a check-in ({why}).", "start")
        threading.Thread(target=self._watch, args=(j["id"],), daemon=True).start()
        return j

    def _watch(self, jid):
        while True:
            time.sleep(10)
            j = self.jobs.get(jid)
            if not j or j["status"] in ("done", "failed", "cancelled"):
                break
        if j and j.get("result"):
            log_entry(j["result"], "did" if j["status"] == "done" else "failed")


@tool("Send the user a message on their phone (and the PC). urgent=true rings their phone instead — only for things "
      "that truly can't wait.", {"text": ("string", "The message", True), "urgent": ("boolean", "Ring the phone", False)})
def message_user(text, urgent=False):
    from . import phone
    push = CTX.get("push_phone")
    if urgent:
        phone.push("call", reason=text[:300])
    else:
        phone.push("msg", text=text[:1000])
        if push:
            push("💬 " + text[:300])
    notify = CTX.get("notify")
    if notify:
        notify(text, False)
    log_entry(("📞 Rang you: " if urgent else "💬 Messaged you: ") + text, "message")
    return "Sent."


@tool("Autonomous mode on/off, or start a check-in right now.",
      {"action": ("string", "on | off | now", True), "idle_minutes": ("integer", "Minutes away before it starts", False)})
def autonomous_mode(action, idle_minutes=None):
    a = CTX.get("autonomy")
    if not a:
        return "Autonomous mode isn't available."
    if idle_minutes:
        a.ac["idle_minutes"] = max(5, int(idle_minutes))
    if action == "now":
        a.run(0, "you asked")
        return "Starting an autonomous check-in now."
    a.ac["enabled"] = action != "off"
    from . import config as config_mod
    config_mod.save(a.cfg)
    return f"Autonomous mode {'on' if a.ac['enabled'] else 'off'} — I'll start after {a.ac['idle_minutes']} min of you being away."

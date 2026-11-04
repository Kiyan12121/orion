"""ORION speaks up on its own: holographic pop-ups when something is worth knowing — an event starting soon,
homework due tomorrow, rain on the way, a job finished, what happened while you were away, a nudge when
YouTube has eaten the evening. Each thing pops up once; never while gaming or with the screensaver on."""
import datetime as dt
import threading
import time

from .tools import CTX


class Proactive:
    def __init__(self, cfg, emit):
        self.cfg, self.emit = cfg, emit
        self.seen = set()
        self.once = set()                 # milestones: once ever (per run), not once a day
        self.day = ""
        self.away_since = None
        self.last_card = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def _card(self, key, kind, title, sound=True, **data):
        if key in self.seen:
            return
        self.seen.add(key)
        self.last_card = time.time()
        try:
            from .holo import emit_card
            emit_card(kind, title, proactive=True, **data)
            if sound:
                self.emit("proactive", title=title)
        except Exception:
            pass

    def _quiet(self):
        g = CTX.get("gaming")
        s = CTX.get("saver")
        return (g and g.active) or (s and s.on) or not self.cfg.get("proactive", True)

    def _loop(self):
        from .jobs import idle_seconds
        time.sleep(25)
        first = True
        while True:
            try:
                today = time.strftime("%Y-%m-%d")
                if today != self.day:
                    self.day, self.seen = today, set()
                idle = idle_seconds()
                if idle > 20 * 60 and self.away_since is None:
                    self.away_since = time.time() - idle
                if not self._quiet() and idle < 60:
                    if self.away_since:
                        self._welcome_back(self.away_since)
                        self.away_since = None
                    if first:
                        self._briefing()
                        first = False
                    self._checks()
            except Exception:
                pass
            time.sleep(45)

    # ------------------------------------------------------------------ what's worth saying
    def _briefing(self):
        items = []
        try:
            from .life import forecast
            w = forecast("")
            items.append(f"{w['temp']}° {w['sky']}" + (f" · rain from {w['rain_at']}" if w.get("rain_at") else ""))
        except Exception:
            pass
        try:
            from .schedule import upcoming
            for o in upcoming(1)[:3]:
                items.append(f"{o['at']:%H:%M} {o['title']}")
        except Exception:
            pass
        try:
            from .life import homework
            hw = [h for h in homework() if not h.get("done") and h["days"] <= 2]
            if hw:
                items.append(f"Homework soon: {', '.join(h['subject'] for h in hw[:3])}")
        except Exception:
            pass
        if items:
            h = dt.datetime.now().hour
            self._card("brief", "points", ("Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening") +
                       f", {self.cfg.get('user_title', 'sir')}", items=items, icon="🌅" if h < 12 else "👋",
                       actions=[{"label": "Read it to me", "say": "give me a quick briefing out loud"}, {"label": "Dashboard", "page": "dash"}])

    def _welcome_back(self, since):
        mins = int((time.time() - since) / 60)
        items = []
        try:
            from .autonomy import recent
            done = [e for e in recent(20) if e.get("ts", 0) >= since or e.get("t", "") >= time.strftime("%Y-%m-%d %H:%M", time.localtime(since))]
            items += [f"🤖 {e['text'][:90]}" for e in done[-3:]]
        except Exception:
            pass
        try:
            jobs = CTX.get("jobs")
            fin = [j for j in (jobs.jobs if jobs else []) if (j.get("finished") or 0) >= since and j["status"] in ("done", "failed")]
            items += [f"{'✅' if j['status'] == 'done' else '⚠️'} {j['title'][:80]}" for j in fin[-3:]]
        except Exception:
            pass
        try:
            from .root import recent_log
            dms = [e for e in recent_log(30) if e["kind"] == "received" and e.get("t", "") >= time.strftime("%Y-%m-%d %H:%M", time.localtime(since))]
            if dms:
                items.append(f"✉ {len(dms)} DM(s) on Root — latest from {dms[-1].get('who', '?')}")
        except Exception:
            pass
        if items and mins >= 20:
            self._card(f"back-{int(since)}", "points", f"While you were away ({mins // 60}h {mins % 60}m)" if mins >= 60 else f"While you were away ({mins} min)",
                       items=items[:6], icon="🛰️", actions=[{"label": "Tell me more", "say": "what did you get done while I was away?"}])

    def _checks(self):
        now = dt.datetime.now()
        try:                                                     # starting soon
            from .schedule import upcoming
            for o in upcoming(1):
                mins = (o["at"] - now).total_seconds() / 60
                if 0 < mins <= 15:
                    self._card(f"ev-{o['title']}-{o['at']:%H%M}", "event", o["title"], icon="⏰", at=o["at"].strftime("%H:%M"),
                               ts=o["at"].timestamp(),
                               text=f"{o['at']:%H:%M} — {o['title']}" + (f"\n{o.get('notes', '')}" if o.get("notes") else ""),
                               actions=[{"label": "Snooze 10 min", "say": f"remind me about {o['title']} in 10 minutes"}, {"label": "Open plan", "page": "sched"}])
        except Exception:
            pass
        try:                                                     # homework due tomorrow (after school)
            if now.hour >= 16:
                from .life import homework
                due = [h for h in homework() if not h.get("done") and h["days"] == 1]
                if due:
                    self._card("hw-tomorrow", "checklist", "Due tomorrow", items=[f"{h['subject']} — {h['task']}" for h in due[:5]], icon="📝",
                               actions=[{"label": "Plan tonight", "say": "plan my homework for tonight around my schedule"}, {"label": "Open homework", "page": "study"}])
        except Exception:
            pass
        try:                                                     # rain coming
            if 7 <= now.hour <= 21:
                from .life import forecast
                w = forecast("")
                if w.get("rain_at"):
                    rh = int(w["rain_at"][:2])
                    if 0 <= rh - now.hour <= 2:
                        self._card(f"rain-{rh}", "weather", f"Rain around {w['rain_at']}", weather=w, actions=[{"label": "Full forecast", "say": "what's the weather for the rest of today?"}])
        except Exception:
            pass
        try:                                                     # too much YouTube/TikTok tonight
            if now.hour >= 18:
                from .life import screen_day
                for app, mins in screen_day()[:6]:
                    if app.lower() in ("youtube", "tiktok") and mins >= 90:
                        self._card(f"st-{app}", "text", f"{app}: {mins // 60}h {mins % 60}m today",
                                   text="Shall I start a 25-minute focus round?", icon="📵",
                                   actions=[{"label": "Focus 25", "say": "start a 25 minute focus session"}, {"label": "Not now", "page": ""}])
        except Exception:
            pass
        try:                                                     # money goal milestones
            from .money import goals
            for g in goals():
                top = max([m for m in (25, 50, 75, 100) if g["pct"] >= m], default=0)
                key = f"goal-{g['name']}"
                prev = next((int(k.split("@")[1]) for k in self.once if k.startswith(key + "@")), None)
                if prev is None:                                 # first look: remember, don't announce old progress
                    self.once.add(f"{key}@{top}")
                elif top > prev:
                    self.once.discard(f"{key}@{prev}")
                    self.once.add(f"{key}@{top}")
                    m = top
                    self._card(f"goal-{g['name']}-{m}", "ring", g["name"], value=g["pct"],
                                   text=f"£{g['got']:.0f} of £{g['target']:.0f} · £{g['per_week']}/week to go", sound=m == 100, icon="🎯",
                                   actions=[{"label": "CEO page", "page": "ventures"}])
        except Exception:
            pass

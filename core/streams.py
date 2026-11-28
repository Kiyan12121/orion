"""Streams 7.0 — TikTok stats and an automatic stream log.

- Profile stats: followers, likes and videos, read from your public TikTok profile a few times a day (no login, read-only),
  kept as a history so ORION can show growth by day/week/month.
- Stream sessions: when TikTok LIVE Studio (or OBS) is open for a while, ORION logs it as a stream automatically — start,
  end, length, and followers gained during it. Afterwards you can add the numbers from TikTok Studio / LIVE Center
  (peak viewers, gifts…) in one go, and ORION keeps the lot.
- Nothing here posts, follows, comments or changes anything on TikTok.
"""
import datetime as dt
import json
import os
import re
import threading
import time
import uuid

from .paths import DATA_DIR
from .safeio import write_json
from .tools import CTX, tool

STATS = os.path.join(DATA_DIR, "tiktok_stats.json")
SESS = os.path.join(DATA_DIR, "streams.json")
STUDIO_URL = "https://www.tiktok.com/tiktokstudio"
# processes that mean "streaming right now" (TikTok LIVE Studio, OBS, Streamlabs)
STREAM_APPS = ("tiktok live studio.exe", "tiktoklivestudio.exe", "live studio.exe", "obs64.exe", "streamlabs obs.exe", "streamlabs desktop.exe")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
_lock = threading.Lock()


def _load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _num(s):
    return int(re.sub(r"\D", "", str(s)) or 0)


# ------------------------------------------------------------------ profile stats
def fetch_profile(user):
    """Public profile numbers from tiktok.com/@user. Returns dict or raises."""
    import requests
    user = user.strip().lstrip("@")
    if not re.fullmatch(r"[\w.]{2,30}", user):
        raise ValueError("That doesn't look like a TikTok username.")
    r = requests.get(f"https://www.tiktok.com/@{user}", headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}, timeout=15)
    h = r.text
    out = {}
    for k, pat in (("followers", r'"followerCount":(\d+)'), ("following", r'"followingCount":(\d+)'),
                   ("likes", r'"heart(?:Count)?":(\d+)'), ("videos", r'"videoCount":(\d+)')):
        m = re.search(pat, h)
        if m:
            out[k] = int(m.group(1))
    if "followers" not in out:
        raise RuntimeError("TikTok didn't return your stats this time (it sometimes blocks automatic visits). I'll try again later.")
    m = re.search(r'"nickname":"([^"]{1,60})"', h)
    if m:
        out["name"] = m.group(1)
    return out


def history():
    return _load(STATS, [])


def snapshot(user, force=False):
    h = history()
    if h and not force and time.time() - h[-1]["t"] < 2.5 * 3600:
        return h[-1]
    s = fetch_profile(user)
    rec = {"t": int(time.time()), **{k: s.get(k) for k in ("followers", "following", "likes", "videos")}}
    with _lock:
        h = history()
        h.append(rec)
        write_json(STATS, h[-3000:])
    return rec


def add_manual(followers, likes=None):
    """When TikTok blocks the automatic read, you can type today's numbers."""
    rec = {"t": int(time.time()), "followers": int(followers), "likes": int(likes) if likes not in (None, "") else None, "manual": True}
    with _lock:
        h = history()
        h.append(rec)
        write_json(STATS, h[-3000:])
    return rec


def _at(h, secs_ago):
    t = time.time() - secs_ago
    best = None
    for x in h:
        if x["t"] <= t:
            best = x
    return best


# ------------------------------------------------------------------ stream sessions
def sessions():
    return _load(SESS, [])


def _save_sessions(s):
    with _lock:
        write_json(SESS, s[-1000:])


def session_update(sid, **kw):
    s = sessions()
    for x in s:
        if x["id"] == sid:
            for k in ("peak", "viewers", "gifts", "new_followers", "likes", "notes", "game"):
                if k in kw and kw[k] not in (None, ""):
                    x[k] = kw[k] if k in ("notes", "game") else _num(kw[k])
    _save_sessions(s)
    return True


def session_delete(sid):
    _save_sessions([x for x in sessions() if x["id"] != sid])


def overview():
    h = history()
    last = h[-1] if h else None
    def delta(secs):
        a = _at(h, secs)
        return (last["followers"] - a["followers"]) if last and a and a.get("followers") is not None else None
    # one point per day (last reading of the day) for the chart
    days = {}
    for x in h:
        if x.get("followers") is not None:
            days[dt.date.fromtimestamp(x["t"]).isoformat()] = x["followers"]
    series = sorted(days.items())[-60:]
    ss = sorted(sessions(), key=lambda x: x["start"], reverse=True)
    month = dt.date.today().strftime("%Y-%m")
    mon = [x for x in ss if dt.date.fromtimestamp(x["start"]).strftime("%Y-%m") == month and x.get("end")]
    done = [x for x in ss if x.get("end")]
    best = max(done, key=lambda x: (x.get("peak") or 0, x.get("gained") or 0), default=None)
    return {
        "user": (CTX.get("config") or {}).get("tiktok_user", ""),
        "last": last, "d1": delta(86400), "d7": delta(7 * 86400), "d30": delta(30 * 86400), "series": series,
        "live": next((x for x in ss if not x.get("end")), None),
        "sessions": ss[:15],
        "month": {"streams": len(mon), "hours": round(sum(x.get("mins", 0) for x in mon) / 60, 1),
                  "gained": sum(x.get("gained") or 0 for x in mon),
                  "avg_mins": round(sum(x.get("mins", 0) for x in mon) / len(mon)) if mon else 0},
        "best": best, "studio_url": STUDIO_URL, "auto": (CTX.get("config") or {}).get("streams_auto", True),
    }


def recap_text(x):
    title = (CTX.get("config") or {}).get("user_title", "sir")
    m = x.get("mins", 0)
    bits = [f"Stream wrapped, {title}: {m // 60}h {m % 60}m" if m >= 60 else f"Stream wrapped, {title}: {m} minutes"]
    if x.get("gained") is not None:
        bits.append(f"{x['gained']:+d} followers while you were live")
    if x.get("peak"):
        bits.append(f"peak {x['peak']} viewers")
    prev = [s for s in sessions() if s.get("end") and s["id"] != x["id"] and s.get("mins")]
    if prev:
        avg = sum(s["mins"] for s in prev[-10:]) / len(prev[-10:])
        if m > avg * 1.2:
            bits.append(f"longer than your usual {round(avg)} minutes")
    return ". ".join(bits) + "."


class Watcher:
    """Spots a stream starting/ending and keeps the follower history ticking over."""

    def __init__(self, cfg, emit, notify):
        self.cfg, self.emit, self.notify = cfg, emit, notify
        self.seen_since = None
        self.manual = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _streaming_app(self):
        try:
            from . import procs
            return procs.first(STREAM_APPS, max_age=15)
        except Exception:
            pass
        return None

    def _followers(self, force=False):
        u = self.cfg.get("tiktok_user")
        if not u:
            return None
        try:
            return snapshot(u, force=force).get("followers")
        except Exception:
            h = history()
            return h[-1]["followers"] if h else None

    def start(self, source="manual"):
        if any(not x.get("end") for x in sessions()):
            return False
        x = {"id": uuid.uuid4().hex[:8], "start": int(time.time()), "end": None, "source": source,
             "followers_before": self._followers(force=True), "game": self.cfg.get("stream_game", "Roblox Rivals")}
        _save_sessions(sessions() + [x])
        self.manual = source == "manual"
        self.emit("stream_live", on=True, session=x)
        a = CTX.get("automate")
        a and a.signal("stream_start")
        return True

    def stop(self):
        s = sessions()
        x = next((y for y in s if not y.get("end")), None)
        if not x:
            return None
        x["end"] = int(time.time())
        x["mins"] = max(1, round((x["end"] - x["start"]) / 60))
        after = self._followers(force=True)
        x["followers_after"] = after
        if after is not None and x.get("followers_before") is not None:
            x["gained"] = after - x["followers_before"]
        _save_sessions(s)
        self.manual = False
        self.seen_since = None
        if x["mins"] < 3:                       # opened the app by accident — don't keep it
            session_delete(x["id"])
            self.emit("stream_live", on=False, session=None)
            return None
        self.emit("stream_live", on=False, session=x)
        self.notify(recap_text(x) + " Add peak viewers and gifts from TikTok Studio on the Streams page.", important=False)
        a = CTX.get("automate")
        a and a.signal("stream_end", mins=x["mins"], gained=x.get("gained"))
        return x

    def _loop(self):
        time.sleep(30)
        last_snap = 0
        while True:
            try:
                if self.cfg.get("streams_auto", True):
                    app = self._streaming_app()
                    live = any(not x.get("end") for x in sessions())
                    if app and not live:
                        self.seen_since = self.seen_since or time.time()
                        if time.time() - self.seen_since > 120:      # open for 2 min = streaming
                            self.start(source=app)
                    elif not app and live and not self.manual:
                        self.stop()
                    elif not app:
                        self.seen_since = None
                if self.cfg.get("tiktok_user") and time.time() - last_snap > 3 * 3600:
                    last_snap = time.time()
                    try:
                        before = history()[-1]["followers"] if history() else None
                        rec = snapshot(self.cfg["tiktok_user"])
                        self._milestone(before, rec.get("followers"))
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(20)   # not slowed in game mode — you stream while gaming

    def _milestone(self, before, now):
        if before is None or now is None or now <= before:
            return
        for m in (100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000):
            if before < m <= now:
                self.notify(f"🎉 You just passed {m:,} TikTok followers, {self.cfg.get('user_title', 'sir')}!", important=True)
                a = CTX.get("automate")
                a and a.signal("followers", count=now, milestone=m)


# ------------------------------------------------------------------ tools for the brain
@tool("STREAMS: the user's TikTok stats (followers, likes, growth today/this week/this month) and their recent LIVE streams "
      "(length, followers gained, peak viewers, gifts). Use for 'how did my stream go', 'how many followers have I got', "
      "'how am I doing on TikTok'.")
def tiktok_stats():
    o = overview()
    lines = []
    if o["last"]:
        L = o["last"]
        lines.append(f"TikTok @{o['user'] or '?'}: {L.get('followers', 0):,} followers"
                     + (f", {L['likes']:,} likes" if L.get("likes") else "")
                     + (f", {L['videos']} videos" if L.get("videos") else ""))
        g = [f"{lbl} {v:+d}" for lbl, v in (("today", o["d1"]), ("this week", o["d7"]), ("this month", o["d30"])) if v is not None]
        if g:
            lines.append("Growth: " + ", ".join(g))
    else:
        lines.append("No TikTok stats yet — the user needs to set their @username on the Streams page.")
    if o["live"]:
        lines.append(f"LIVE right now (since {dt.datetime.fromtimestamp(o['live']['start']):%H:%M}).")
    m = o["month"]
    lines.append(f"This month: {m['streams']} streams, {m['hours']} hours live, {m['gained']:+d} followers during streams.")
    for x in o["sessions"][:5]:
        if not x.get("end"):
            continue
        d = dt.datetime.fromtimestamp(x["start"])
        bits = [f"{d:%a %d %b %H:%M}", f"{x.get('mins', 0)} min"]
        for k, lbl in (("gained", "followers"), ("peak", "peak viewers"), ("viewers", "viewers"), ("gifts", "gifts/diamonds")):
            if x.get(k) is not None:
                bits.append(f"{x[k]:+d} {lbl}" if k == "gained" else f"{x[k]} {lbl}")
        lines.append("• " + ", ".join(bits))
    return "\n".join(lines)


@tool("STREAMS: mark that the user has gone LIVE now (start=true) or finished (start=false). Normally automatic.",
      {"start": ("boolean", "true = going live, false = finished", True)})
def stream_mark(start=True):
    w = CTX.get("streams")
    if not w:
        return "Streams isn't running."
    if start:
        return "Stream started — I'm logging it." if w.start("manual") else "A stream is already being logged."
    x = w.stop()
    return recap_text(x) if x else "No stream was running."

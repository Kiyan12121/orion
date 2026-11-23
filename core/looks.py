"""The at-a-glance labels the Orion Core and Halo looks show around the core: next up, home time / weather, TikTok, money.
All free and local (weather comes from Open-Meteo, no key). Cached for 10 minutes so it costs nothing to show."""
import datetime as dt
import time

_cache = {"t": 0, "v": None}


def _when(at):
    today = dt.date.today()
    d = at.date()
    day = "Today" if d == today else "Tomorrow" if d == today + dt.timedelta(days=1) else at.strftime("%A")
    return f"{day} {at:%H:%M}"


def glance(cfg, force=False):
    if not force and _cache["v"] and time.time() - _cache["t"] < 600:
        return _cache["v"]
    out = []
    # ---- next up: the soonest of an exam or a calendar event
    nxt = None
    try:
        from .schedule import upcoming
        ev = upcoming(7)
        if ev:
            e = ev[0]
            nxt = {"k": "next", "label": "NEXT UP", "title": e["title"][:32], "sub": _when(e["at"])}
    except Exception:
        pass
    try:
        from .study import overview
        ex = overview().get("exams") or []
        if ex and (not nxt or ex[0]["days"] <= 2):
            e = ex[0]
            nxt = {"k": "next", "label": "NEXT UP", "title": f"{e.get('subject', 'Exam')} exam"[:32],
                   "sub": "today" if e["days"] == 0 else "tomorrow" if e["days"] == 1 else f"in {e['days']} days"}
    except Exception:
        pass
    out.append(nxt or {"k": "next", "label": "NEXT UP", "title": "Nothing booked", "sub": "Ask me to add something"})
    # ---- home time on school days, otherwise just the weather
    try:
        from .life import forecast
        from .daily import day_cfg, is_school_day
        w = forecast()
        end = day_cfg(cfg).get("school_end", "15:10")
        before_home = is_school_day(cfg=cfg) and time.strftime("%H:%M") < end
        if w.get("rain_at") and before_home and w["rain_at"] <= f"{int(end[:2]) + 1:02d}{end[2:]}":
            out.append({"k": "weather", "label": "HOME TIME", "title": f"Rain at {w['rain_at']}", "sub": "Bring a coat for the ride", "warn": True})
        elif w.get("rain_at"):
            out.append({"k": "weather", "label": "WEATHER", "title": f"Rain from {w['rain_at']}", "sub": f"{w['temp']}° now, {w['sky']}", "warn": True})
        else:
            out.append({"k": "weather", "label": "HOME TIME" if before_home else "WEATHER", "title": f"{w['temp']}° and {w['sky']}"[:32],
                        "sub": "Dry for the ride home" if before_home else f"Sunset {w['sunset']}"})
    except Exception:
        out.append({"k": "weather", "label": "WEATHER", "title": "Offline", "sub": "I'll check again shortly"})
    # ---- TikTok
    try:
        from .streams import overview as so
        o = so()
        if o["last"] and o["last"].get("followers") is not None:
            d = o["d7"] if o["d7"] is not None else o["d1"]
            last = next((x for x in o["sessions"] if x.get("end")), None)
            sub = (f"Last LIVE: {last['mins'] // 60}h {last['mins'] % 60}m" if last and last["mins"] >= 60
                   else f"Last LIVE: {last['mins']} min" if last else f"{o['last']['followers']:,} followers")
            out.append({"k": "tiktok", "label": "TIKTOK", "title": f"{d:+d} followers" if d else f"{o['last']['followers']:,} followers", "sub": sub})
        else:
            out.append({"k": "tiktok", "label": "TIKTOK", "title": "Add your @", "sub": "On the Streams page"})
    except Exception:
        pass
    # ---- money
    try:
        from .ceo import hq
        m = hq()["month"]
        out.append({"k": "money", "label": "MONEY", "title": f"£{m['profit']:.0f} profit",
                    "sub": f"On pace for £{m['pace']:.0f} this month" if m.get("pace") else f"£{m['in']:.0f} in this month"})
    except Exception:
        pass
    _cache.update(t=time.time(), v=out)
    return out

"""Local intel for Globe mode: a holographic map of your area with real data.

- Map: roads, buildings, water, railways, places and points of interest from OpenStreetMap (Overpass), cached a week.
- Crime: police.uk street-level crime within 1 mile of home (anonymised by the police: points are snapped to
  streets, never addresses). Latest month, the 6-month trend, categories, outcomes, top streets, and your
  neighbourhood team's priorities.
- Area: air quality + UV, sunrise/sunset, moon phase, aurora chance (NOAA Kp), Environment Agency flood warnings.
- Sky: aircraft overhead (OpenSky, anonymous).
- World: NASA EONET natural events (wildfires, storms, volcanoes, icebergs) for the globe.
All free, no keys."""
import datetime as dt
import json
import logging
import math
import os
import threading
import time

import requests

from .paths import DATA_DIR
from .safeio import write_json
from .tools import CTX, tool

log = logging.getLogger("orion")
UA = {"User-Agent": "ORION-personal-assistant (local intel)"}
POLICE = "https://data.police.uk/api"
CACHE = os.path.join(DATA_DIR, "localintel_cache.json")
_lock = threading.Lock()

CRIME_NAMES = {
    "anti-social-behaviour": "Anti-social behaviour", "bicycle-theft": "Bicycle theft", "burglary": "Burglary",
    "criminal-damage-arson": "Criminal damage & arson", "drugs": "Drugs", "other-theft": "Other theft",
    "possession-of-weapons": "Weapons possession", "public-order": "Public order", "robbery": "Robbery",
    "shoplifting": "Shoplifting", "theft-from-the-person": "Theft from the person", "vehicle-crime": "Vehicle crime",
    "violent-crime": "Violence & sexual offences", "other-crime": "Other crime"}


def _cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(c):
    with _lock:
        write_json(CACHE, c)


def place_name():
    cfg = CTX.get("config", {})
    p = (cfg.get("local_place") or "").strip()
    if not p:
        hp = (cfg.get("home_place") or "").strip()
        p = hp if hp and hp.lower() != "leicester" else "Desford"
    return p


def home():
    from .life import _geo
    lat, lon, name = _geo(place_name())
    return {"lat": lat, "lon": lon, "name": name}


# ------------------------------------------------------------------ the village boundary (so it's just YOUR area)
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")


def _overpass(q, timeout=90):
    last = None
    for ep in OVERPASS:
        try:
            r = requests.post(ep, data={"data": q}, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            log.warning("overpass %s: %s", ep, e)
    raise RuntimeError(f"OpenStreetMap unreachable: {last}")


def _stitch(ways):
    """Joins boundary way pieces into closed rings."""
    ways = [w[:] for w in ways if len(w) > 1]
    rings = []
    while ways:
        ring = ways.pop(0)
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, w in enumerate(ways):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                ways.pop(i)
                changed = True
                break
        rings.append(ring)
    return rings


def _simplify(ring, n=90):
    if len(ring) <= n:
        return ring
    step = len(ring) / n
    return [ring[int(i * step)] for i in range(n)] + [ring[0]]


def boundary(h=None):
    """The parish/village boundary polygon around home from OpenStreetMap (cached), or None."""
    h = h or home()
    c = _cache()
    key = f"bound:{h['name']}:{h['lat']:.3f},{h['lon']:.3f}"
    if c.get(key):
        return c[key]
    q = f"""[out:json][timeout:40];
is_in({h['lat']},{h['lon']})->.a;
rel(pivot.a)[boundary=administrative][admin_level~"^(8|9|10)$"];
out geom;"""
    try:
        d = _overpass(q, 60)
    except Exception:
        return None
    best = None
    for rel in d.get("elements", []):
        nm = rel.get("tags", {}).get("name", "")
        ways = [[[round(p["lat"], 5), round(p["lon"], 5)] for p in m.get("geometry", [])]
                for m in rel.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "")]
        rings = [r for r in _stitch(ways) if len(r) > 3]
        if not rings:
            continue
        ring = max(rings, key=len)
        score = (nm.lower() == h["name"].lower(), int(rel["tags"].get("admin_level", 0)))
        if best is None or score > best[0]:
            best = (score, {"name": nm, "ring": ring})
    out = best[1] if best else None
    if out:
        c[key] = out
        _save(c)
    return out


def _inside(pt, ring):
    y, x = pt
    ins = False
    for i in range(len(ring) - 1):
        y1, x1 = ring[i]
        y2, x2 = ring[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def _get(url, timeout=20, **params):
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ map (OpenStreetMap)
def local_map(h=None, force=False):
    h = h or home()
    c = _cache()
    key = f"map2:{h['lat']:.3f},{h['lon']:.3f}"
    hit = c.get(key)
    if hit and not force and time.time() - hit.get("ts", 0) < 7 * 86400:
        return hit["data"]
    la, lo = h["lat"], h["lon"]
    rad = 2600
    try:
        b = boundary(h)
        if b:
            cl = math.cos(math.radians(la))
            rad = int(min(5000, max(1500, max(math.hypot((p[0] - la) * 110540, (p[1] - lo) * 111320 * cl) for p in b["ring"]) + 250)))
    except Exception:
        pass
    q = f"""[out:json][timeout:90];
(
  way(around:{rad},{la},{lo})[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|footway|path|cycleway|bridleway)$"];
  way(around:{rad},{la},{lo})[building];
  way(around:{rad},{la},{lo})[natural=water];
  way(around:{rad},{la},{lo})[waterway];
  way(around:{rad},{la},{lo})[railway~"^(rail|disused|abandoned)$"];
  way(around:{rad},{la},{lo})[landuse~"^(forest|meadow|recreation_ground|cemetery)$"];
  way(around:{rad},{la},{lo})[leisure~"^(park|pitch|golf_course|playground)$"];
  node(around:{rad},{la},{lo})[amenity~"^(school|pub|cafe|restaurant|fast_food|pharmacy|doctors|place_of_worship|library|post_office|fuel|police|fire_station)$"];
  node(around:{rad},{la},{lo})[shop];
  node(around:9000,{la},{lo})[place~"^(town|village|hamlet)$"];
);
out geom qt;"""
    try:
        data = _overpass(q)
    except Exception:
        if hit:
            return hit["data"]
        raise RuntimeError("Couldn't reach OpenStreetMap right now.")
    out = {"roads": [], "buildings": [], "water": [], "rail": [], "green": [], "poi": [], "places": []}
    rnd = lambda v: round(v, 5)
    for e in data.get("elements", []):
        t = e.get("tags", {})
        if e["type"] == "node":
            p = [rnd(e["lat"]), rnd(e["lon"])]
            if t.get("place"):
                if t.get("name"):
                    out["places"].append({"p": p, "n": t["name"], "k": t["place"]})
            elif t.get("name"):
                out["poi"].append({"p": p, "n": t["name"], "k": t.get("amenity") or "shop:" + t.get("shop", "")})
            continue
        g = [[rnd(x["lat"]), rnd(x["lon"])] for x in e.get("geometry", []) if x]
        if len(g) < 2:
            continue
        if "building" in t:
            out["buildings"].append(g)
        elif "highway" in t:
            out["roads"].append({"g": g, "k": t["highway"], "n": t.get("name", "")})
        elif t.get("natural") == "water" or "waterway" in t:
            out["water"].append({"g": g, "area": t.get("natural") == "water"})
        elif "railway" in t:
            out["rail"].append(g)
        else:
            out["green"].append(g)
    c[key] = {"ts": time.time(), "data": out}
    _save(c)
    return out


# ------------------------------------------------------------------ crime (police.uk)
def _month_list(latest, n):
    y, m = map(int, latest.split("-")[:2])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _crimes(la, lo, month, c, poly=None):
    key = f"crime:{'poly' + str(len(poly)) if poly else ''}{la:.3f},{lo:.3f}:{month}"
    if key in c:                                  # past months never change
        return c[key]
    if poly:
        r = requests.post(f"{POLICE}/crimes-street/all-crime", headers=UA, timeout=30,
                          data={"poly": ":".join(f"{a},{b}" for a, b in poly), "date": month})
        r.raise_for_status()
        rows = r.json()
    else:
        rows = _get(f"{POLICE}/crimes-street/all-crime", lat=la, lng=lo, date=month, timeout=30)
    slim = [[round(float(r["location"]["latitude"]), 5), round(float(r["location"]["longitude"]), 5), r["category"],
             (r["location"].get("street") or {}).get("name", "").replace("On or near ", ""),
             (r.get("outcome_status") or {}).get("category", "")] for r in rows]
    c[key] = slim
    return slim


def crime(h=None, months=6):
    h = h or home()
    c = _cache()
    latest = _get(f"{POLICE}/crime-last-updated")["date"][:7]
    ms = _month_list(latest, months)
    b = boundary(h)
    poly = _simplify(b["ring"]) if b else None
    per = {}
    for m in ms:
        try:
            per[m] = _crimes(h["lat"], h["lon"], m, c, poly)
        except Exception as e:
            log.warning("police %s: %s", m, e)
    _save(c)
    cur = per.get(latest, [])
    by_cat, streets, outcomes = {}, {}, {}
    for la, lo, cat, st, oc in cur:
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if st:
            streets[st] = streets.get(st, 0) + 1
        outcomes[oc or "No outcome recorded yet"] = outcomes.get(oc or "No outcome recorded yet", 0) + 1
    trend = [{"m": m, "n": len(per[m]), "cats": {}} for m in reversed(ms) if m in per]
    for t in trend:
        for r in per[t["m"]]:
            t["cats"][r[2]] = t["cats"].get(r[2], 0) + 1
    six = [r for m in ms for r in per.get(m, [])]
    hood = {}
    try:
        loc = _get(f"{POLICE}/locate-neighbourhood", q=f"{h['lat']},{h['lon']}")
        f, n = loc["force"], loc["neighbourhood"]
        info = _get(f"{POLICE}/{f}/{n}")
        pri = _get(f"{POLICE}/{f}/{n}/priorities")
        import re
        clean = lambda s: re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()
        hood = {"force": f.replace("-", " ").title(), "name": info.get("name", n), "url": info.get("url_force", ""),
                "priorities": [clean(p.get("issue"))[:220] for p in pri[:4] if p.get("issue")]}
    except Exception as e:
        log.warning("police neighbourhood: %s", e)
    return {"month": latest, "radius": f"the {b['name']} boundary" if b else "1 mile", "area": b["name"] if b else "",
            "items": cur, "six": six, "total": len(cur),
            "by_cat": sorted(([k, CRIME_NAMES.get(k, k), v] for k, v in by_cat.items()), key=lambda x: -x[2]),
            "streets": sorted(streets.items(), key=lambda x: -x[1])[:6],
            "outcomes": sorted(outcomes.items(), key=lambda x: -x[1])[:5],
            "trend": trend, "names": CRIME_NAMES, "hood": hood}


# ------------------------------------------------------------------ area
def _sun_times(la, lo, day=None):
    day = day or dt.date.today()
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eq = 229.18 * (.000075 + .001868 * math.cos(g) - .032077 * math.sin(g) - .014615 * math.cos(2 * g) - .040849 * math.sin(2 * g))
    decl = .006918 - .399912 * math.cos(g) + .070257 * math.sin(g) - .006758 * math.cos(2 * g) + .000907 * math.sin(2 * g)
    lr = math.radians(la)
    cosh = (math.cos(math.radians(90.833)) / (math.cos(lr) * math.cos(decl))) - math.tan(lr) * math.tan(decl)
    if abs(cosh) > 1:
        return None, None
    ha = math.degrees(math.acos(cosh))
    off = dt.datetime.now().astimezone().utcoffset().total_seconds() / 60
    rise = 720 - 4 * (lo + ha) - eq + off
    sset = 720 - 4 * (lo - ha) - eq + off
    f = lambda m: f"{int(m // 60) % 24:02d}:{int(m % 60):02d}"
    return f(rise), f(sset)


def _moon():
    days = (time.time() - 947182440) / 86400          # known new moon 2000-01-06 18:14 UTC
    age = days % 29.530588853
    names = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous", "Full moon", "Waning gibbous",
             "Last quarter", "Waning crescent"]
    return {"age": round(age, 1), "name": names[int((age / 29.53) * 8 + .5) % 8],
            "lit": round((1 - math.cos(2 * math.pi * age / 29.53)) / 2 * 100)}


def area(h=None):
    h = h or home()
    out = {"home": h}
    out["sunrise"], out["sunset"] = _sun_times(h["lat"], h["lon"])
    out["moon"] = _moon()
    try:
        from .life import forecast
        w = forecast("")
        out["weather"] = {"temp": w["temp"], "sky": w["sky"], "rain_at": w.get("rain_at")}
    except Exception:
        pass
    try:
        a = _get("https://air-quality-api.open-meteo.com/v1/air-quality", latitude=h["lat"], longitude=h["lon"],
                 current="european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,uv_index,alder_pollen,birch_pollen,grass_pollen")["current"]
        aqi = a.get("european_aqi") or 0
        out["air"] = {"aqi": aqi, "label": "Good" if aqi <= 20 else "Fair" if aqi <= 40 else "Moderate" if aqi <= 60 else
                      "Poor" if aqi <= 80 else "Very poor", "pm25": a.get("pm2_5"), "no2": a.get("nitrogen_dioxide"),
                      "uv": a.get("uv_index"), "pollen": max([a.get(k) or 0 for k in ("alder_pollen", "birch_pollen", "grass_pollen")])}
    except Exception as e:
        log.warning("air: %s", e)
    try:
        k = _get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json")
        kp = float(k[-1].get("estimated_kp", k[-1].get("kp_index", 0)))
        out["kp"] = {"kp": round(kp, 1), "chance": "Good — look north tonight!" if kp >= 6 else "Possible on camera" if kp >= 5 else
                     "Unlikely" if kp >= 4 else "Very unlikely"}
    except Exception as e:
        log.warning("kp: %s", e)
    try:
        fl = _get("https://environment.data.gov.uk/flood-monitoring/id/floods", lat=h["lat"], long=h["lon"], dist=20)
        out["floods"] = [{"area": i.get("description", ""), "sev": i.get("severity", ""), "lvl": i.get("severityLevel", 4)}
                         for i in fl.get("items", [])][:6]
    except Exception as e:
        log.warning("floods: %s", e)
    return out


def flights(h=None, box=.45):
    h = h or home()
    try:
        r = _get("https://opensky-network.org/api/states/all", timeout=15, lamin=h["lat"] - box, lamax=h["lat"] + box,
                 lomin=h["lon"] - box * 1.6, lomax=h["lon"] + box * 1.6)
    except Exception as e:
        log.warning("opensky: %s", e)
        return []
    out = []
    for s in r.get("states") or []:
        if s[5] is None or s[6] is None or s[8]:
            continue
        out.append({"cs": (s[1] or "").strip() or s[0], "from": s[2], "lat": s[6], "lon": s[5],
                    "alt": round((s[13] or s[7] or 0) * 3.281), "kt": round((s[9] or 0) * 1.944), "hdg": s[10] or 0,
                    "vs": s[11] or 0})
    return sorted(out, key=lambda f: (f["lat"] - h["lat"]) ** 2 + (f["lon"] - h["lon"]) ** 2)[:40]


def world_events():
    try:
        r = _get("https://eonet.gsfc.nasa.gov/api/v3/events", status="open", days=20, limit=120)
    except Exception as e:
        log.warning("eonet: %s", e)
        return []
    out = []
    for ev in r.get("events", []):
        geo = ev.get("geometry") or []
        if not geo or geo[-1].get("type") != "Point":
            continue
        lon, lat = geo[-1]["coordinates"][:2]
        cat = (ev.get("categories") or [{}])[0].get("id", "")
        out.append({"t": ev.get("title", ""), "c": cat, "lat": lat, "lon": lon,
                    "track": [[g["coordinates"][1], g["coordinates"][0]] for g in geo[-12:] if g.get("type") == "Point"] if cat == "severeStorms" else []})
    return out


def local_all():
    h = home()
    out = {"home": h, "boundary": boundary(h)}
    jobs = {"crime": lambda: crime(h), "area": lambda: area(h), "flights": lambda: flights(h)}
    res = {}

    def run(k, fn):
        try:
            res[k] = fn()
        except Exception as e:
            res[k] = {"error": str(e)}
    ts = [threading.Thread(target=run, args=(k, fn)) for k, fn in jobs.items()]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    out.update(res)
    return out


# ------------------------------------------------------------------ tool
@tool("LOCAL INTEL: crime around home (police.uk, last month + 6-month trend, categories, top streets, neighbourhood "
      "priorities), plus air quality, aurora chance, flood warnings and planes overhead — and opens the holographic local "
      "map in Globe mode. Use for 'how much crime is there in Desford', 'is my area safe', 'what's going on round here', "
      "'planes overhead', 'any flood warnings'.")
def local_intel():
    CTX.get("emit") and CTX["emit"]("globe", target=None, local=True)
    try:
        c = crime()
    except Exception as e:
        return f"Opened the local map, but couldn't reach police.uk: {e}"
    trend = c["trend"]
    prev = trend[-2]["n"] if len(trend) > 1 else None
    top = ", ".join(f"{n.lower()} {v}" for _, n, v in c["by_cat"][:4])
    avg = round(sum(t["n"] for t in trend) / max(1, len(trend)))
    s = (f"{c['total']} crimes reported {'inside ' + c['area'] if c.get('area') else 'within a mile of ' + home()['name']} in {dt.datetime.strptime(c['month'], '%Y-%m'):%B %Y} "
         f"(police data runs about two months behind). Biggest: {top}. ")
    if prev is not None:
        s += f"That's {'up' if c['total'] > prev else 'down' if c['total'] < prev else 'level'} from {prev} the month before; 6-month average {avg}. "
    if c["streets"]:
        s += f"Most reports on or near {c['streets'][0][0]}. "
    if c["hood"].get("priorities"):
        s += f"Local police priority: {c['hood']['priorities'][0][:140]}"
    return s

"""Proper Iron Man moments: suit-up sequence, threat scan, 3D holograms, globe mode (battle reports live in gaming)."""
import os
import subprocess
import threading
import time

import psutil
import requests

from .tools import CTX, tool

IS_WIN = os.name == "nt"
FLAGS = 0x08000000 if IS_WIN else 0
UA = {"User-Agent": "ORION-assistant"}


def _emit(kind, **d):
    e = CTX.get("emit")
    if e:
        e(kind, **d)


def _ps(cmd, timeout=20):
    if not IS_WIN:
        return ""
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                              timeout=timeout, creationflags=FLAGS).stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ suit up
def status_report(cfg):
    t = cfg.get("user_title", "sir")
    bits = [f"All systems online, {t}."]
    try:
        from .life import forecast
        w = forecast("")
        bits.append(f"It's {w['temp']} degrees and {w['sky']} outside" + (f", rain from {w['rain_at']}." if w.get("rain_at") else "."))
    except Exception:
        pass
    try:
        from .schedule import upcoming
        up = upcoming(1)[:2]
        if up:
            bits.append("Next up: " + ", then ".join(f"{o['title']} at {o['at']:%H:%M}" for o in up) + ".")
    except Exception:
        pass
    try:
        from .life import homework
        hw = [h for h in homework() if not h.get("done") and h["days"] <= 2]
        if hw:
            bits.append(f"{len(hw)} piece{'s' if len(hw) != 1 else ''} of homework due soon.")
    except Exception:
        pass
    vm = psutil.virtual_memory()
    bits.append(f"Processor at {psutil.cpu_percent(interval=.3):.0f} percent, memory at {vm.percent:.0f}.")
    return " ".join(bits)


@tool("SUIT UP: the full Iron Man power-up sequence — cinematic HUD build, opens the user's suit-up apps, spoken status "
      "report. Use when the user says 'suit up', 'let's go', 'power up', 'jarvis wake up' etc.")
def suit_up():
    cfg = CTX.get("config", {})
    rep = status_report(cfg)
    _emit("suitup", report=rep, apps=cfg.get("suitup_apps", []))
    run = CTX.get("toolbox_run")

    def later():
        time.sleep(3.5)
        for app in cfg.get("suitup_apps", [])[:6]:
            try:
                run and run("open_app", {"name": app})
                time.sleep(.8)
            except Exception:
                pass
    threading.Thread(target=later, daemon=True).start()
    return rep


# ------------------------------------------------------------------ threat scan
def threat_scan():
    """Real checks, dramatic presentation. Returns [{name, status ok|warn|bad, detail}] + verdict."""
    out = []

    def add(name, status, detail):
        out.append({"name": name, "status": status, "detail": detail})

    cpu = psutil.cpu_percent(interval=1)
    vm = psutil.virtual_memory()
    add("Processor load", "ok" if cpu < 70 else "warn" if cpu < 90 else "bad", f"{cpu:.0f}% in use")
    add("Memory", "ok" if vm.percent < 80 else "warn" if vm.percent < 92 else "bad", f"{vm.used / 2**30:.1f} of {vm.total / 2**30:.0f} GB used")
    try:
        du = psutil.disk_usage(os.path.abspath(os.sep))
        free = du.free / 2**30
        add("System drive space", "ok" if free > 30 else "warn" if free > 10 else "bad", f"{free:.0f} GB free ({100 - du.percent:.0f}%)")
    except Exception:
        pass
    if IS_WIN:
        disk = _ps("Get-PhysicalDisk | Select-Object -ExpandProperty HealthStatus")
        if disk:
            bad = [d for d in disk.split() if d.lower() != "healthy"]
            add("Drive health (SMART)", "ok" if not bad else "bad", "all drives healthy" if not bad else f"{', '.join(bad)} reported")
        av = _ps("$s=Get-MpComputerStatus; \"$($s.AntivirusEnabled)|$($s.RealTimeProtectionEnabled)|$($s.AntivirusSignatureAge)\"")
        if "|" in av:
            en, rt, age = av.split("|")[:3]
            ok = en.strip() == "True" and rt.strip() == "True"
            add("Windows Defender", "ok" if ok and int(age or 0) <= 3 else "warn" if ok else "bad",
                ("protection on" if ok else "real-time protection OFF") + f" · definitions {age} day(s) old")
        fw = _ps("(Get-NetFirewallProfile | Where-Object {$_.Enabled -eq $false}).Name")
        add("Firewall", "ok" if not fw else "bad", "all profiles on" if not fw else f"OFF for: {fw.replace(chr(10), ', ')}")
    # suspicious places for programs to run from
    sus = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            exe = (p.info.get("exe") or "").lower()
            if exe and ("\\temp\\" in exe or "\\downloads\\" in exe or "/tmp/" in exe):
                sus.append(p.info["name"])
        except Exception:
            continue
    add("Programs running from Temp/Downloads", "ok" if not sus else "warn",
        "none" if not sus else ", ".join(sorted(set(sus))[:5]) + " — fine if you just installed something")
    try:
        listening = {}
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.ip not in ("127.0.0.1", "::1"):
                try:
                    name = psutil.Process(c.pid).name() if c.pid else "system"
                except Exception:
                    name = "?"
                listening.setdefault(name, set()).add(c.laddr.port)
        names = [n for n in listening if n.lower() not in ("system", "svchost.exe", "lsass.exe", "wininit.exe", "services.exe", "spoolsv.exe")]
        add("Open network ports", "ok" if len(names) <= 6 else "warn",
            f"{sum(len(v) for v in listening.values())} listening · " + (", ".join(sorted(names)[:6]) or "system only"))
    except Exception:
        pass
    try:
        from .pctools import startup_apps
        n = startup_apps().split(" apps start")[0]
        add("Startup apps", "ok" if not n.isdigit() or int(n) <= 8 else "warn", f"{n} start with Windows")
    except Exception:
        pass
    hogs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            hogs.append((p.info["memory_info"].rss, p.info["name"]))
        except Exception:
            continue
    hogs.sort(reverse=True)
    add("Biggest memory users", "ok", ", ".join(f"{n} {r / 2**20:.0f} MB" for r, n in hogs[:3]))
    up = time.time() - psutil.boot_time()
    add("Uptime", "ok" if up < 5 * 86400 else "warn", f"{up / 3600:.0f} hours" + (" — a restart would help" if up >= 5 * 86400 else ""))
    bad = sum(1 for o in out if o["status"] == "bad")
    warn = sum(1 for o in out if o["status"] == "warn")
    verdict = ("No threats detected. All systems nominal." if not bad and not warn else
               f"{warn} minor issue{'s' if warn != 1 else ''} found — nothing dangerous." if not bad else
               f"{bad} problem{'s' if bad != 1 else ''} need{'s' if bad == 1 else ''} attention.")
    return {"checks": out, "verdict": verdict, "bad": bad, "warn": warn}


@tool("THREAT SCAN: dramatic full-screen security & health scan of the PC (Defender, firewall, drive health, space, "
      "memory, odd programs, open ports, startup apps). Use for 'scan the system', 'run diagnostics', 'any threats?'.")
def threat_scan_tool():
    _emit("scan", start=True)
    return "Scan running on screen."


# ------------------------------------------------------------------ holograms
MODELS = ("earth", "planet", "atom", "molecule", "dna", "cell", "cube", "pyramid", "sphere", "torus", "cylinder",
          "cone", "heart", "brain", "rocket", "galaxy", "sun")


@tool("3D HOLOGRAM: show a rotating 3D wireframe hologram to explain something. model: earth, planet, atom, molecule, "
      "dna, cell, galaxy, sun, rocket, heart, brain, cube, pyramid, sphere, torus, cylinder, cone. detail: element name "
      "or symbol for atom (e.g. 'carbon'), formula for molecule (H2O, CO2, CH4, NH3, O2, N2, C2H5OH, NaCl).",
      {"model": ("string", "Which model", True), "label": ("string", "Caption", False),
       "detail": ("string", "Element / formula / extra", False)})
def hologram(model, label="", detail=""):
    m = (model or "sphere").lower().strip()
    if m not in MODELS:
        m = next((x for x in MODELS if x in m), "sphere")
    _emit("holo3d", model=m, label=(label or model)[:60], detail=(detail or "")[:30])
    return f"Hologram of {label or m} on screen."


# ------------------------------------------------------------------ globe
def geocode(place):
    from .life import _geo
    lat, lon, name = _geo(place)
    return {"lat": lat, "lon": lon, "name": name}


def globe_feeds():
    out = {"quakes": [], "iss": None, "home": None}
    try:
        out["home"] = geocode("")
    except Exception:
        pass
    try:
        r = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson", headers=UA, timeout=10).json()
        out["quakes"] = [{"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0],
                          "mag": f["properties"]["mag"], "place": f["properties"]["place"]} for f in r["features"][:80]]
    except Exception:
        pass
    try:
        r = requests.get("https://api.wheretheiss.at/v1/satellites/25544", headers=UA, timeout=8).json()
        out["iss"] = {"lat": r["latitude"], "lon": r["longitude"], "alt": round(r["altitude"]), "vel": round(r["velocity"])}
    except Exception:
        pass
    return out


@tool("GLOBE MODE: open the 3D holographic Earth (live day/night, home, earthquakes, the ISS). place = somewhere to fly "
      "to (city/country), or blank for home.",
      {"place": ("string", "Where to fly to (optional)", False)})
def globe(place=""):
    target = None
    if place:
        try:
            target = geocode(place)
        except Exception as e:
            return f"Couldn't find {place}: {e}"
    _emit("globe", target=target)
    return f"Globe open{' — flying to ' + target['name'] if target else ''}."

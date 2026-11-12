"""ORION OS — when ORION *is* the desktop (Linux, booted from the ORION OS USB).

Gives the interface what a desktop needs: apps (launch / switch / close), Wi-Fi, volume, brightness, battery,
power (shut down / restart / sleep), files, and system info. Everything uses standard Linux tools
(nmcli, wpctl/pactl, brightnessctl, wmctrl, systemctl, xdg-open)."""
import configparser
import glob
import os
import re
import shutil
import subprocess
import time

from .tools import tool

ACTIVE = os.path.exists("/etc/orion-os") or os.environ.get("ORION_OS") == "1"


def _run(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


# ------------------------------------------------------------------ apps
HIDE = re.compile(r"(?i)^(xterm|uxterm|openbox|obconf|lxappearance|python|vim|htop|info|debian|ibus|im-config|gcr|nm-|"
                  r"org\.freedesktop|software-properties|.*settings-daemon|yelp|xdg-|display-im6|io\.elementary)")
ICONS = {"web": "🌐", "browser": "🌐", "epiphany": "🌐", "firefox": "🌐", "file": "📁", "pcmanfm": "📁", "terminal": "⌨",
         "text": "📝", "mousepad": "📝", "image": "🖼", "eog": "🖼", "ristretto": "🖼", "video": "🎬", "vlc": "🎬", "mpv": "🎬",
         "music": "🎵", "calculator": "🧮", "galculator": "🧮", "pdf": "📄", "evince": "📄", "steam": "🎮", "game": "🎮",
         "screenshot": "📸", "archive": "🗜", "disk": "💽", "gparted": "💽", "volume": "🔊", "pavucontrol": "🔊", "code": "💻"}


def apps():
    out, seen = [], set()
    for f in sorted(glob.glob("/usr/share/applications/*.desktop") + glob.glob(os.path.expanduser("~/.local/share/applications/*.desktop"))):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(f, encoding="utf-8")
            d = cp["Desktop Entry"]
        except Exception:
            continue
        if d.get("NoDisplay", "false").lower() == "true" or d.get("Type") != "Application" or d.get("Terminal", "false") == "true":
            continue
        name, base = d.get("Name", ""), os.path.basename(f)[:-8]
        if not name or name in seen or HIDE.match(base) or "orion" in base.lower():
            continue
        seen.add(name)
        key = (base + " " + name + " " + d.get("Categories", "")).lower()
        icon = next((v for k, v in ICONS.items() if k in key), "▣")
        out.append({"id": base, "name": name, "icon": icon, "cat": (d.get("Categories", "") or "Other").split(";")[0],
                    "desc": d.get("Comment", "")[:80]})
    return out


def launch(app_id):
    if not re.fullmatch(r"[\w.+-]+", app_id or ""):
        return False
    if shutil.which("gtk-launch"):
        subprocess.Popen(["gtk-launch", app_id], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([app_id], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def windows():
    code, out = _run(["wmctrl", "-lx"])
    if code:
        return []
    ws = []
    for ln in out.splitlines():
        p = ln.split(None, 4)
        if len(p) < 5 or "orion" in p[2].lower() or p[1] == "-1":
            continue
        ws.append({"id": p[0], "cls": p[2].split(".")[-1], "title": p[4][:80]})
    return ws


def window_action(wid, action):
    if not re.fullmatch(r"0x[0-9a-f]+", wid or ""):
        return False
    _run(["wmctrl", "-i", "-a" if action == "focus" else "-c", wid])
    return True


def focus_orion():
    _run(["wmctrl", "-a", "ORION"])


# ------------------------------------------------------------------ status: wifi / sound / brightness / battery
def wifi_list():
    _run(["nmcli", "dev", "wifi", "rescan"], 8)
    code, out = _run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list"])
    nets, seen = [], set()
    for ln in out.splitlines():
        p = ln.split(":")
        if len(p) < 4 or not p[1] or p[1] in seen:
            continue
        seen.add(p[1])
        nets.append({"ssid": p[1], "on": p[0] == "*", "signal": int(p[2] or 0), "secure": bool(p[3])})
    return sorted(nets, key=lambda n: (-n["on"], -n["signal"]))


def wifi_connect(ssid, password=""):
    cmd = ["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password else [])
    code, out = _run(cmd, 40)
    return {"ok": code == 0, "msg": out.strip().splitlines()[-1] if out.strip() else ""}


def wifi_power(on):
    _run(["nmcli", "radio", "wifi", "on" if on else "off"])


def _volume():
    code, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    m = re.search(r"([\d.]+)", out)
    if code == 0 and m:
        return round(float(m.group(1)) * 100), "MUTED" in out
    code, out = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    m = re.search(r"(\d+)%", out)
    return (int(m.group(1)) if m else 50), False


def set_volume(pct=None, mute=None):
    if pct is not None:
        pct = max(0, min(150, int(pct)))
        if _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{pct / 100:.2f}"])[0]:
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])
    if mute is not None:
        if _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if mute else "0"])[0]:
            _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0"])


def _brightness():
    code, out = _run(["brightnessctl", "-m"])
    p = out.strip().split(",")
    return int(p[3].rstrip("%")) if code == 0 and len(p) > 3 else None


def set_brightness(pct):
    _run(["brightnessctl", "set", f"{max(5, min(100, int(pct)))}%"])


def status():
    import psutil
    vol, muted = _volume()
    b = psutil.sensors_battery()
    code, out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"], 6)
    net = next((ln.split(":") for ln in out.splitlines() if ln.startswith("yes:")), None)
    code2, eth = _run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"], 6)
    wired = any(ln.startswith("ethernet:connected") for ln in eth.splitlines())
    return {"os": True, "volume": vol, "muted": muted, "brightness": _brightness(),
            "battery": {"pct": round(b.percent), "plugged": b.power_plugged} if b else None,
            "wifi": {"ssid": net[1], "signal": int(net[2] or 0)} if net else None, "wired": wired,
            "windows": windows(), "uptime": int(time.time() - psutil.boot_time()),
            "persist": os.path.exists("/run/casper-persist") or _persistent()}


def _persistent():
    try:
        with open("/proc/mounts") as f:
            return any("casper-rw" in ln or "writable" in ln for ln in f)
    except Exception:
        return False


def power(action):
    cmd = {"shutdown": ["systemctl", "poweroff"], "restart": ["systemctl", "reboot"], "sleep": ["systemctl", "suspend"]}.get(action)
    if cmd:
        subprocess.Popen(cmd)
        return True
    return False


# ------------------------------------------------------------------ files
def files(path=""):
    home = os.path.expanduser("~")
    p = os.path.realpath(os.path.join(home, path or ""))
    if not p.startswith(home):
        p = home
    out = []
    try:
        for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower())):
            if e.name.startswith("."):
                continue
            st = e.stat()
            out.append({"name": e.name, "dir": e.is_dir(), "size": st.st_size, "mtime": int(st.st_mtime)})
    except Exception:
        pass
    return {"path": os.path.relpath(p, home) if p != home else "", "items": out[:500]}


def open_path(path):
    home = os.path.expanduser("~")
    p = os.path.realpath(os.path.join(home, path or ""))
    if p.startswith(home) and os.path.exists(p):
        subprocess.Popen(["xdg-open", p], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


# ------------------------------------------------------------------ tools for the brain (only useful on ORION OS)
@tool("ORION OS: open an installed app (browser, files, terminal, text editor…) by name.",
      {"name": ("string", "App name", True)})
def os_open_app(name):
    a = apps()
    n = name.lower()
    hit = next((x for x in a if x["name"].lower() == n), None) or next((x for x in a if n in x["name"].lower() or n in x["id"].lower()), None)
    if not hit:
        return f"No app called {name}. Installed: " + ", ".join(x["name"] for x in a[:25])
    launch(hit["id"])
    return f"Opening {hit['name']}."


@tool("ORION OS: set volume (0-100) or mute/unmute.",
      {"level": ("integer", "0-100", False), "mute": ("boolean", "Mute on/off", False)})
def os_volume(level=None, mute=None):
    set_volume(level, mute)
    v, m = _volume()
    return f"Volume {v}%{' (muted)' if m else ''}."


@tool("ORION OS: list Wi-Fi networks, or connect to one (the user must give the password).",
      {"ssid": ("string", "Network to join (blank = list)", False), "password": ("string", "Password", False)})
def os_wifi(ssid="", password=""):
    if not ssid:
        return "\n".join(f"{'✓ ' if n['on'] else ''}{n['ssid']} ({n['signal']}%{', locked' if n['secure'] else ''})" for n in wifi_list()[:12]) or "No networks found."
    r = wifi_connect(ssid, password)
    return "Connected." if r["ok"] else f"Couldn't connect: {r['msg']}"

"""ORION OS — when ORION *is* the desktop (Linux, booted from the ORION OS USB).

Gives the interface what a desktop needs: apps (launch / switch / close), Wi-Fi, volume, brightness, battery,
power (shut down / restart / sleep), files, and system info. Everything uses standard Linux tools
(nmcli, wpctl/pactl, brightnessctl, wmctrl, systemctl, xdg-open)."""
import configparser
import ctypes
import glob
import os
import re
import shlex
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


FRIENDLY = {"galculator": ("Calculator", "Sums and scientific maths"), "lxterminal": ("Terminal", "Command line"),
            "mpv": ("Media player", "Videos and music"), "org.gnome.Epiphany": ("Web", "Browse the web"),
            "org.xfce.mousepad": ("Text editor", "Write and edit text"), "org.xfce.ristretto": ("Photos", "View your pictures"),
            "pavucontrol": ("Sound", "Speakers and microphones"), "pcmanfm": ("Files", "Your documents, music and downloads")}
HIDE_IDS = {"org.xfce.mousepad-settings", "pcmanfm-desktop-pref", "lxterminal-preferences"}


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
        if not name or name in seen or HIDE.match(base) or "orion" in base.lower() or base in HIDE_IDS:
            continue
        if base in FRIENDLY:
            name = FRIENDLY[base][0]
            d = dict(d)
            d["Comment"] = FRIENDLY[base][1]
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
        return True
    cmd = None
    for d in ("/usr/share/applications", os.path.expanduser("~/.local/share/applications")):
        f = os.path.join(d, app_id + ".desktop")
        if os.path.exists(f):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            cp.read(f, encoding="utf-8")
            ex = cp["Desktop Entry"].get("Exec", "")
            cmd = [a for a in shlex.split(ex) if not re.fullmatch(r"%[a-zA-Z]", a)]
    try:
        subprocess.Popen(cmd or [app_id], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


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
ALIASES = {"browser": "web", "internet": "web", "chrome": "web", "firefox": "web", "explorer": "files", "file manager": "files",
           "notepad": "text editor", "editor": "text editor", "music": "media player", "video": "media player", "vlc": "media player",
           "pictures": "photos", "images": "photos", "cmd": "terminal", "console": "terminal"}


def open_by_name(name):
    a = apps()
    n = ALIASES.get(name.lower().strip(), name.lower().strip())
    hit = next((x for x in a if x["name"].lower() == n), None) or \
        next((x for x in a if n in x["name"].lower() or n in x["id"].lower() or n in x["desc"].lower()), None)
    if not hit:
        return None, a
    launch(hit["id"])
    return hit, a


@tool("ORION OS: open an installed app (browser, files, terminal, text editor…) by name.",
      {"name": ("string", "App name", True)})
def os_open_app(name):
    hit, a = open_by_name(name)
    if not hit:
        return f"No app called {name}. Installed: " + ", ".join(x["name"] for x in a[:25])
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


# ------------------------------------------------------------------ idle time and the lock screen
class _XSSInfo(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int), ("kind", ctypes.c_int), ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]


_xss = None


def idle_seconds():
    """How long since the last key press or mouse move anywhere on the PC (not just in ORION)."""
    global _xss
    try:
        if _xss is None:
            x11, xss = ctypes.cdll.LoadLibrary("libX11.so.6"), ctypes.cdll.LoadLibrary("libXss.so.1")
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XSSInfo)
            xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XSSInfo)]
            dpy = x11.XOpenDisplay(None)
            if not dpy:
                _xss = False
                return None
            _xss = (xss, dpy, x11.XDefaultRootWindow(dpy), xss.XScreenSaverAllocInfo())
        if not _xss:
            return None
        xss, dpy, root, info = _xss
        xss.XScreenSaverQueryInfo(dpy, root, info)
        return info.contents.idle // 1000
    except Exception:
        _xss = False
        return None


def _pin_hash(pin, salt):
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", str(pin).encode(), bytes.fromhex(salt), 120000).hex()


class Lock:
    """Lock-screen PIN (stored only as a salted hash) with a cool-down after wrong guesses."""
    def __init__(self, cfg, save):
        self.cfg, self.save, self.fails, self.until = cfg, save, 0, 0

    def status(self):
        return {"pin": bool(self.cfg.get("os_pin_hash")), "idle_min": int(self.cfg.get("os_lock_idle", 10)),
                "wait": max(0, int(self.until - time.time()))}

    def check(self, pin):
        if time.time() < self.until:
            return {"ok": False, "wait": int(self.until - time.time())}
        h = self.cfg.get("os_pin_hash")
        if not h or _pin_hash(pin, self.cfg.get("os_pin_salt", "")) == h:
            self.fails = 0
            return {"ok": True}
        self.fails += 1
        if self.fails >= 5:
            self.until, self.fails = time.time() + 30, 0
        return {"ok": False, "wait": max(0, int(self.until - time.time()))}

    def set_pin(self, pin, old=""):
        if self.cfg.get("os_pin_hash") and not self.check(old)["ok"]:
            return {"ok": False, "msg": "Your current PIN wasn't right."}
        if pin:
            if not re.fullmatch(r"\d{4,8}", str(pin)):
                return {"ok": False, "msg": "Use 4 to 8 digits."}
            salt = os.urandom(16).hex()
            self.cfg["os_pin_salt"], self.cfg["os_pin_hash"] = salt, _pin_hash(pin, salt)
        else:
            self.cfg.pop("os_pin_hash", None)
            self.cfg.pop("os_pin_salt", None)
        self.save(self.cfg)
        return {"ok": True}

    def set_idle(self, minutes):
        self.cfg["os_lock_idle"] = max(0, min(240, int(minutes)))
        self.save(self.cfg)
        return self.status()


@tool("ORION OS: lock the screen.")
def os_lock_screen():
    from .tools import CTX
    CTX.get("emit") and CTX["emit"]("os_lock")
    return "Locked."


# ------------------------------------------------------------------ PC stats, screenshots
def sysinfo():
    import psutil
    temp = None
    try:
        t = psutil.sensors_temperatures()
        vals = [x.current for k in ("coretemp", "k10temp", "cpu_thermal", "acpitz") for x in t.get(k, []) if x.current]
        temp = round(max(vals)) if vals else None
    except Exception:
        pass
    vm, du = psutil.virtual_memory(), psutil.disk_usage(os.path.expanduser("~"))
    return {"cpu": round(psutil.cpu_percent(interval=.3)), "ram": round(vm.percent), "ram_gb": round(vm.total / 2**30),
            "temp": temp, "disk_free": round(du.free / 2**30, 1), "uptime": int(time.time() - psutil.boot_time())}


SHOTS = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")


def screenshot():
    """Saves the whole screen to Pictures/Screenshots (runs the helper in its own process, GTK-safe)."""
    os.makedirs(SHOTS, exist_ok=True)
    code, out = _run(["python3", os.path.join(os.path.dirname(__file__), "osshot.py")], 20)
    path = out.strip().splitlines()[-1] if out.strip() else ""
    return path if code == 0 and os.path.exists(path) else None


def online():
    import socket
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return True
    except Exception:
        return False


def wifi_ssid():
    code, out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], 6)
    return next((ln.split(":", 1)[1] for ln in out.splitlines() if ln.startswith("yes:")), None)


@tool("ORION OS: take a screenshot of the whole screen (saved to Pictures/Screenshots).")
def os_screenshot():
    p = screenshot()
    return f"Screenshot saved: {p}" if p else "Couldn't take a screenshot."


@tool("ORION OS: shut down, restart or sleep the PC. Shows a 15-second countdown the user can cancel. Only when the user asks.",
      {"action": ("string", "shutdown | restart | sleep", True)})
def os_power_off(action="shutdown"):
    from .tools import CTX
    if action not in ("shutdown", "restart", "sleep"):
        return "Say shutdown, restart or sleep."
    CTX.get("emit") and CTX["emit"]("os_power_countdown", action=action, seconds=15, name="You asked")
    return f"{action.title()} in 15 seconds — there's a Cancel button on screen."


@tool("ORION OS: change the sky behind ORION. sky: night, aurora, dawn or deep.",
      {"sky": ("string", "night | aurora | dawn | deep", True)})
def os_sky(sky="night"):
    from .tools import CTX
    if sky not in SKIES:
        return "Skies: " + ", ".join(SKIES)
    cfg = CTX.get("config")
    if cfg is not None:
        cfg["os_sky"] = sky
        from . import config
        config.save(cfg)
    CTX.get("emit") and CTX["emit"]("os_sky", sky=sky)
    return f"Sky set to {sky}."


SKIES = ("night", "aurora", "dawn", "deep")

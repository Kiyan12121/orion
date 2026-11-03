"""PC power tools: window layouts, per-app volume, Downloads tidy (with undo), big files, duplicates,
screen text (OCR), colour picker, speed test, startup apps, habits, break reminders and ambient sounds."""
import datetime as dt
import hashlib
import json
import os
import shutil
import threading
import time

from .paths import DATA_DIR
from .tools import CTX, tool

HOME = os.path.expanduser("~")


def _emit(kind, **d):
    e = CTX.get("emit")
    if e:
        e(kind, **d)


def _card(kind, title, **d):
    try:
        from .holo import emit_card
        emit_card(kind, title, **d)
    except Exception:
        pass


def _size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


# ------------------------------------------------------------------ window layouts
def _windows():
    import win32gui
    out = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).strip():
            l, t, r, b = win32gui.GetWindowRect(h)
            if r - l > 120 and b - t > 80:
                out.append((h, win32gui.GetWindowText(h)))
    win32gui.EnumWindows(cb, None)
    return out


def _work_area():
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right - r.left, r.bottom - r.top


@tool("WINDOW LAYOUT: arrange open windows. layout: split (two side by side), thirds, quarters, focus (one big, others "
      "minimised), stack. apps: comma list of window names in order, e.g. 'discord, chrome'.",
      {"layout": ("string", "split | thirds | quarters | focus | stack", True),
       "apps": ("string", "Window names in order (part of the title)", False)})
def window_layout(layout, apps=""):
    if os.name != "nt":
        return "Window layouts work on Windows."
    import win32con
    import win32gui
    wins = _windows()
    names = [a.strip().lower() for a in (apps or "").split(",") if a.strip()]
    chosen = []
    for n in names:
        hit = next((w for w in wins if n in w[1].lower() and w not in chosen and "orion" not in w[1].lower()), None)
        if hit:
            chosen.append(hit)
    if not chosen:
        chosen = [w for w in wins if "orion" not in w[1].lower()][:{"split": 2, "thirds": 3, "quarters": 4}.get(layout, 2)]
    if not chosen:
        return "No windows to arrange."
    x, y, W, H = _work_area()
    lay = (layout or "split").lower()
    if lay == "focus":
        for h, _ in wins:
            if h != chosen[0][0] and "orion" not in win32gui.GetWindowText(h).lower():
                win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
        win32gui.ShowWindow(chosen[0][0], win32con.SW_MAXIMIZE)
        return f"Focus: {chosen[0][1][:50]} — everything else minimised."
    if lay == "quarters":
        rects = [(x, y, W // 2, H // 2), (x + W // 2, y, W // 2, H // 2), (x, y + H // 2, W // 2, H // 2), (x + W // 2, y + H // 2, W // 2, H // 2)]
    elif lay == "thirds":
        rects = [(x + i * W // 3, y, W // 3, H) for i in range(3)]
    elif lay == "stack":
        rects = [(x, y + i * H // len(chosen), W, H // len(chosen)) for i in range(len(chosen))]
    else:
        rects = [(x, y, W // 2, H), (x + W // 2, y, W // 2, H)]
    for (h, _), (rx, ry, rw, rh) in zip(chosen, rects):
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
        win32gui.MoveWindow(h, rx, ry, rw, rh, True)
    return "Arranged: " + ", ".join(t[:30] for _, t in chosen[:len(rects)])


# ------------------------------------------------------------------ per-app volume
@tool("PER-APP VOLUME: set, raise, lower or mute ONE app's volume (e.g. turn Discord down, mute Chrome).",
      {"app": ("string", "App name, e.g. discord, chrome, spotify", True),
       "action": ("string", "set | up | down | mute | unmute", True),
       "level": ("integer", "0-100 for set", False)})
def app_volume(app, action, level=None):
    try:
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    except Exception:
        return "Per-app volume needs pycaw (run 1_SETUP.bat)."
    hit = 0
    for s in AudioUtilities.GetAllSessions():
        if not s.Process or app.lower().replace(".exe", "") not in s.Process.name().lower():
            continue
        v = s._ctl.QueryInterface(ISimpleAudioVolume)
        cur = v.GetMasterVolume()
        a = (action or "").lower()
        if a == "mute":
            v.SetMute(1, None)
        elif a == "unmute":
            v.SetMute(0, None)
        elif a == "up":
            v.SetMasterVolume(min(1.0, cur + .2), None)
        elif a == "down":
            v.SetMasterVolume(max(0.0, cur - .2), None)
        else:
            v.SetMasterVolume(max(0, min(100, int(level if level is not None else 50))) / 100, None)
        hit += 1
    return f"{app}: {action} done." if hit else f"{app} isn't playing any sound right now."


# ------------------------------------------------------------------ Downloads tidy (undoable)
TYPES = {"Images": ".jpg .jpeg .png .gif .webp .bmp .heic .svg .ico", "Videos": ".mp4 .mkv .mov .avi .webm .flv",
         "Audio": ".mp3 .wav .ogg .flac .m4a", "Documents": ".pdf .doc .docx .txt .ppt .pptx .xls .xlsx .csv .odt .rtf .md",
         "Archives": ".zip .rar .7z .tar .gz", "Installers": ".exe .msi .apk .jar", "Code": ".py .js .html .css .json .lua .java .cpp .ts"}
UNDO = os.path.join(DATA_DIR, "tidy_undo.json")


@tool("TIDY DOWNLOADS: sort the Downloads folder into Images/Videos/Audio/Documents/Archives/Installers/Code/Other "
      "(moves only, never deletes; can be undone with tidy_undo). preview=true just shows what would move.",
      {"preview": ("boolean", "Only show what would happen", False), "folder": ("string", "Folder (default Downloads)", False)})
def tidy_downloads(preview=False, folder=""):
    base = folder or os.path.join(HOME, "Downloads")
    if not os.path.isdir(base):
        return f"Can't find {base}."
    moves, counts = [], {}
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if not os.path.isfile(p) or time.time() - os.path.getmtime(p) < 3600 or f.startswith("."):
            continue                                  # leave anything still downloading / brand new
        ext = os.path.splitext(f)[1].lower()
        dest = next((k for k, v in TYPES.items() if ext in v.split()), "Other")
        counts[dest] = counts.get(dest, 0) + 1
        moves.append((p, os.path.join(base, dest, f)))
    if not moves:
        return "Downloads is already tidy."
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    if preview:
        return f"Would sort {len(moves)} files: {summary}."
    done = []
    for src, dst in moves:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            root, ext = os.path.splitext(dst)
            dst = f"{root} ({int(time.time())}){ext}"
        try:
            shutil.move(src, dst)
            done.append([src, dst])
        except Exception:
            pass
    from .safeio import write_json
    write_json(UNDO, done)
    return f"Sorted {len(done)} files into folders ({summary}). Say 'undo the tidy' to put them back."


@tool("Undo the last Downloads tidy (puts every file back where it was).")
def tidy_undo():
    try:
        with open(UNDO, encoding="utf-8") as fh:
            done = json.load(fh)
    except Exception:
        return "Nothing to undo."
    back = 0
    for src, dst in done:
        if os.path.exists(dst) and not os.path.exists(src):
            shutil.move(dst, src)
            back += 1
    os.replace(UNDO, UNDO + ".old")
    return f"Put {back} files back."


# ------------------------------------------------------------------ big files + duplicates (report only)
def _walk(base, limit=60000):
    n = 0
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "AppData", "$Recycle.Bin", "Windows")]
        for f in files:
            n += 1
            if n > limit:
                return
            p = os.path.join(root, f)
            try:
                yield p, os.path.getsize(p)
            except OSError:
                continue


def _folder(name):
    n = (name or "").strip().lower()
    for k in ("downloads", "documents", "desktop", "videos", "pictures", "music"):
        if n in ("", k):
            return os.path.join(HOME, k.title()) if n else os.path.join(HOME, "Downloads")
    return os.path.expanduser(name) if name else os.path.join(HOME, "Downloads")


@tool("BIG FILES: the largest files in a folder (Downloads, Videos, Documents, Desktop… or a path) to free up space.",
      {"folder": ("string", "Folder name or path", False), "top": ("integer", "How many (default 12)", False)})
def big_files(folder="", top=12):
    base = _folder(folder) if folder.lower() != "home" else HOME
    files = sorted(_walk(base), key=lambda x: -x[1])[:int(top or 12)]
    if not files:
        return "No files found."
    lines = [f"{_size(s):>9}  {os.path.relpath(p, base)}" for p, s in files]
    _card("text", f"Biggest files · {os.path.basename(base)}", text="\n".join(lines))
    return f"Biggest files in {base} (total shown {_size(sum(s for _, s in files))}):\n" + "\n".join(lines)


@tool("DUPLICATE FILES: find identical files in a folder and how much space they waste (report only — never deletes).",
      {"folder": ("string", "Folder name or path", False)})
def find_duplicates(folder=""):
    base = _folder(folder) if folder.lower() != "home" else HOME
    by_size = {}
    for p, s in _walk(base):
        if s > 50_000:
            by_size.setdefault(s, []).append(p)
    groups = []
    for s, ps in by_size.items():
        if len(ps) < 2:
            continue
        hashes = {}
        for p in ps:
            try:
                h = hashlib.sha1()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                hashes.setdefault(h.hexdigest(), []).append(p)
            except OSError:
                pass
        groups += [(s, g) for g in hashes.values() if len(g) > 1]
    if not groups:
        return f"No duplicates in {base}."
    groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
    wasted = sum(s * (len(g) - 1) for s, g in groups)
    lines = [f"{_size(s)} × {len(g)}: " + " | ".join(os.path.relpath(p, base) for p in g[:3]) for s, g in groups[:12]]
    return f"{len(groups)} sets of duplicates wasting {_size(wasted)} in {base}:\n" + "\n".join(lines)


# ------------------------------------------------------------------ screen text + colour picker
@tool("SCREEN TEXT: read (OCR) all the text on screen — or the active window — and copy it to the clipboard.",
      {"window_only": ("boolean", "Only the active window", False)})
def screen_text(window_only=False):
    import pyautogui
    img = pyautogui.screenshot()
    if window_only and os.name == "nt":
        try:
            import win32gui
            l, t, r, b = win32gui.GetWindowRect(win32gui.GetForegroundWindow())
            img = img.crop((max(0, l), max(0, t), r, b))
        except Exception:
            pass
    text = ""
    try:
        import pytesseract
        text = pytesseract.image_to_string(img)
    except Exception:
        try:
            from .vision import ask_image
            text, _, _ = ask_image(img, "Transcribe all readable text on this screen exactly, top to bottom.")
        except Exception as e:
            return f"Couldn't read the screen: {e}"
    text = text.strip()
    if not text:
        return "No text found on screen."
    try:
        import pyperclip
        pyperclip.copy(text)
    except Exception:
        pass
    return f"Copied {len(text.split())} words to your clipboard:\n{text[:1500]}"


@tool("COLOUR PICKER: the colour under the mouse pointer (hex + RGB), copied to the clipboard.")
def pick_colour():
    import pyautogui
    x, y = pyautogui.position()
    r, g, b = pyautogui.pixel(x, y)[:3]
    hx = f"#{r:02X}{g:02X}{b:02X}"
    try:
        import pyperclip
        pyperclip.copy(hx)
    except Exception:
        pass
    _card("text", "Colour picked", text=f"{hx}\nrgb({r}, {g}, {b})")
    return f"{hx} — rgb({r}, {g}, {b}) (copied)"


# ------------------------------------------------------------------ speed test, startup apps
@tool("INTERNET SPEED TEST: download speed and ping.")
def speed_test():
    import requests
    pings = []
    for _ in range(3):
        t = time.time()
        try:
            requests.get("https://speed.cloudflare.com/__down?bytes=0", timeout=5)
            pings.append((time.time() - t) * 1000)
        except Exception:
            pass
    t = time.time()
    size = 0
    try:
        with requests.get("https://speed.cloudflare.com/__down?bytes=25000000", stream=True, timeout=30) as r:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if time.time() - t > 12:
                    break
    except Exception as e:
        return f"Speed test failed: {type(e).__name__}"
    secs = max(.01, time.time() - t)
    mbps = size * 8 / secs / 1e6
    ping = min(pings) if pings else None
    verdict = "great for gaming and streaming" if mbps > 50 and (ping or 99) < 40 else "fine for most things" if mbps > 15 else "slow — try a cable or restarting the router"
    _card("points", "Speed test", items=[f"⬇ {mbps:.1f} Mbps", f"Ping {ping:.0f} ms" if ping else "Ping —", verdict])
    return f"Download {mbps:.1f} Mbps, ping {ping:.0f} ms — {verdict}." if ping else f"Download {mbps:.1f} Mbps — {verdict}."


@tool("STARTUP APPS: what launches when Windows starts (slow boot? this is why). Read-only.")
def startup_apps():
    if os.name != "nt":
        return "Windows only."
    import winreg
    items = []
    for hive, path in ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                       (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")):
        try:
            k = winreg.OpenKey(hive, path)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                    items.append(name)
                    i += 1
                except OSError:
                    break
        except OSError:
            pass
    sf = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(sf):
        items += [os.path.splitext(f)[0] for f in os.listdir(sf) if not f.endswith(".ini")]
    if not items:
        return "Nothing starts with Windows."
    return (f"{len(items)} apps start with Windows: " + ", ".join(sorted(set(items))) +
            ". To turn some off: Task Manager › Startup apps (I won't change it for you).")


# ------------------------------------------------------------------ habits
HABITS = os.path.join(DATA_DIR, "habits.json")


def _hload():
    try:
        with open(HABITS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _hsave(h):
    from .safeio import write_json
    write_json(HABITS, h, indent=1)


def habits():
    h = _hload()
    today = dt.date.today()
    out = []
    for name, v in h.items():
        days = set(v.get("done", []))
        streak, d = 0, today if today.isoformat() in days else today - dt.timedelta(days=1)
        while d.isoformat() in days:
            streak += 1
            d -= dt.timedelta(days=1)
        week = [(today - dt.timedelta(days=k)).isoformat() in days for k in range(6, -1, -1)]
        out.append({"name": name, "streak": streak, "today": today.isoformat() in days, "week": week, "best": v.get("best", 0)})
    return out


@tool("HABITS: add a habit, tick it off for today, remove one, or list them with streaks.",
      {"action": ("string", "add | done | remove | list", True), "name": ("string", "Habit name", False)})
def habit(action, name=""):
    h = _hload()
    a = (action or "list").lower()
    key = next((k for k in h if k.lower() == (name or "").lower().strip()), (name or "").strip())
    if a == "add" and key:
        h.setdefault(key, {"done": [], "best": 0})
        _hsave(h)
        return f"Tracking '{key}'. Say 'done {key}' each day."
    if a == "remove" and key in h:
        h.pop(key)
        _hsave(h)
        return f"Stopped tracking '{key}'."
    if a == "done" and key:
        v = h.setdefault(key, {"done": [], "best": 0})
        t = dt.date.today().isoformat()
        if t not in v["done"]:
            v["done"].append(t)
        _hsave(h)
        st = next((x["streak"] for x in habits() if x["name"] == key), 1)
        v["best"] = max(v.get("best", 0), st)
        _hsave(h)
        return f"✓ {key} — {st}-day streak{' 🔥' if st >= 3 else ''}."
    lst = habits()
    if not lst:
        return "No habits yet — try 'track a habit: revise 30 minutes'."
    return "\n".join(f"{'✓' if x['today'] else '·'} {x['name']}: {x['streak']}-day streak (best {x['best']})" for x in lst)


# ------------------------------------------------------------------ break reminders + ambient sounds
class Breaks:
    """Every ~50 min of non-stop PC use: a stretch/water/eyes reminder (not while gaming)."""
    TIPS = ["Stretch break, {t} — stand up for a minute.", "Water break, {t}.", "Eyes break, {t}: look at something far away for 20 seconds.",
            "You've been at it 50 minutes, {t}. Shoulders down, quick stretch."]

    def __init__(self, cfg, say, toast):
        self.cfg, self.say, self.toast = cfg, say, toast
        self.active_since = time.time()
        self.k = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        from .jobs import idle_seconds
        while True:
            time.sleep(30)
            try:
                if idle_seconds() > 300:
                    self.active_since = time.time()
                    continue
                every = int(self.cfg.get("break_minutes", 50) or 0)
                if not every or time.time() - self.active_since < every * 60:
                    continue
                self.active_since = time.time()
                g = CTX.get("gaming")
                if g and g.active:
                    continue
                msg = self.TIPS[self.k % len(self.TIPS)].format(t=self.cfg.get("user_title", "sir"))
                self.k += 1
                self.toast(msg)
                if self.cfg.get("break_voice", False):
                    self.say(msg)
            except Exception:
                pass


@tool("AMBIENT SOUND for focus: rain, brown noise, white noise, waves, cafe, space hum — or off. Plays from ORION's window.",
      {"sound": ("string", "rain | brown | white | waves | cafe | space | off", True),
       "minutes": ("integer", "Stop after N minutes (optional)", False)})
def ambient(sound, minutes=0):
    _emit("ambient", sound=(sound or "off").lower(), minutes=int(minutes or 0))
    return "Ambient sound off." if (sound or "").lower() == "off" else f"Playing {sound}" + (f" for {minutes} min." if minutes else ".")

"""Everything ORION can physically do on the PC.

Each tool is a function registered with @tool(...). The AI sees the description + parameters
and decides when to call it. Tools marked dangerous=True ask you first (while safe_mode is on).
"""
import ctypes
import datetime
import difflib
import html
import json
import os
import shutil
import platform
import re
import subprocess
import threading
import time
import urllib.parse
import webbrowser

import requests

from .paths import DATA_DIR

IS_WIN = platform.system() == "Windows"

# Optional libraries — ORION still runs if any are missing, that tool just reports it.
try:
    import pyautogui
    pyautogui.FAILSAFE = True   # slam the mouse into a screen corner to abort any automation
    pyautogui.PAUSE = 0.05
except Exception:
    pyautogui = None
try:
    import psutil
except Exception:
    psutil = None
try:
    import pyperclip
except Exception:
    pyperclip = None
try:
    import pytesseract
except Exception:
    pytesseract = None

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# ---------------------------------------------------------------------------------------------
REGISTRY = {}


def tool(description, params=None, dangerous=False):
    """params: {"name": ("type", "description", required?)}"""
    params = params or {}

    def wrap(fn):
        props, req = {}, []
        for pname, (ptype, pdesc, required) in params.items():
            props[pname] = {"type": ptype, "description": pdesc}
            if ptype == "array":
                props[pname]["items"] = {"type": "string"}
            if required:
                req.append(pname)
        REGISTRY[fn.__name__] = {
            "fn": fn,
            "dangerous": dangerous,
            "schema": {"type": "function", "function": {
                "name": fn.__name__, "description": description,
                "parameters": {"type": "object", "properties": props, "required": req}}},
        }
        return fn
    return wrap


def _need(lib, name):
    if lib is None:
        raise RuntimeError(f"'{name}' isn't installed — run setup.bat again.")


# ---------------------------------------------------------------------------------------------
# Context set by the app at start-up
CTX = {"memory": None, "config": {}, "notify": lambda text: None, "open_claude": None,
       "set_theme": None, "cancel": threading.Event()}

# ---------------------------------------------------------------------------------------------
# Safeguards — these apply even with safe mode OFF. ORION simply refuses these.
BLOCKLIST = [
    r"\bformat(\.com)?\s+[a-z]:", r"\bdiskpart\b", r"\bbcdedit\b", r"\bcipher\s+/w", r"\bvssadmin\b.*\bdelete",
    r"\bwbadmin\b.*\bdelete", r"\breg(\.exe)?\s+delete\s+(hklm|hkey_local_machine)",
    r"remove-item[^|;\n]*-recurse[^|;\n]*[a-z]:\\?\s*(['\"]|$|;)", r"\b(rd|rmdir)\s+/s[^|;\n]*[a-z]:\\?\s*(['\"]|$)",
    r"\b(del|erase|rd|rmdir|remove-item|rm|ri)\b[^|;\n]*[a-z]:\\windows(\\|\b|['\"]|$)",
    r"\b(del|erase|rd|rmdir|remove-item|rm|ri)\b[^|;\n]*\\users\\[^\\\s'\"]+\\?\s*(['\"]|$)",
    r"set-mppreference[^\n]*-disable", r"(stop|disable)[^\n]*windefend", r"\bclear-disk\b", r"\binitialize-disk\b",
    r"\bnet\s+user\b[^\n]*(/delete|/add)", r"\btakeown\b[^\n]*system", r"\bicacls\b[^\n]*\\windows",
]
PROTECTED_DIRS = [os.path.expandvars(r"%SystemRoot%").lower(), r"c:\windows", r"c:\program files"]


def _blocked(text):
    low = text.lower()
    return next((p for p in BLOCKLIST if re.search(p, low)), None)


ACTIVITY_LOG = os.path.join(DATA_DIR, "activity.log")
CHANGES = os.path.join(DATA_DIR, "changes.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")


def _activity(line):
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + line.replace("\n", " ")[:400] + "\n")
    except Exception:
        pass


def _changes():
    try:
        with open(CHANGES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_changes(c):
    with open(CHANGES, "w", encoding="utf-8") as f:
        json.dump(c[-50:], f, indent=1)

# ---------------------------------------------------------------------------------------------
# Apps & websites
SITES = {
    "youtube": "https://youtube.com", "google": "https://google.com", "gmail": "https://mail.google.com",
    "github": "https://github.com", "roblox": "https://roblox.com", "twitch": "https://twitch.tv",
    "tiktok": "https://tiktok.com", "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
    "vinted": "https://vinted.co.uk", "whop": "https://whop.com", "netflix": "https://netflix.com",
    "reddit": "https://reddit.com", "x": "https://x.com", "twitter": "https://x.com",
    "instagram": "https://instagram.com", "snapchat": "https://web.snapchat.com",
    "google drive": "https://drive.google.com", "drive": "https://drive.google.com",
    "shopify": "https://admin.shopify.com", "bbc bitesize": "https://bbc.co.uk/bitesize",
}

APP_ALIASES = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "powershell": "powershell",
    "task manager": "taskmgr", "settings": "ms-settings:", "control panel": "control",
    "edge": "msedge", "chrome": "chrome", "spotify": "spotify:", "store": "ms-windows-store:",
    "snipping tool": "snippingtool", "camera": "microsoft.windows.camera:",
}

_shortcut_index = None


def _start_menu_index():
    """Every Start Menu / Desktop shortcut -> path. Built once, then cached."""
    global _shortcut_index
    if _shortcut_index is not None:
        return _shortcut_index
    idx = {}
    roots = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.expandvars(r"%Public%\Desktop"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith((".lnk", ".url", ".exe", ".appref-ms")):
                    name = os.path.splitext(f)[0].lower()
                    if "uninstall" in name:
                        continue
                    idx.setdefault(name, os.path.join(dirpath, f))
    _shortcut_index = idx
    return idx


def _launch(target):
    if IS_WIN:
        os.startfile(target)
    else:
        subprocess.Popen(["xdg-open", target])


@tool("Open an application, game or website by name (e.g. 'spotify', 'roblox studio', 'discord', "
      "'youtube'). Searches the Start Menu and Desktop for installed apps.",
      {"name": ("string", "App or site name", True)})
def open_app(name):
    web = re.search(r"\b(website|site|web|browser|online)\b", name.lower())
    q = re.sub(r"\b(open|launch|start|run|the|app|application|desktop|program|website|site|web|browser|online|in|on)\b", "",
               name.lower()).strip(" ,.").removesuffix(".exe").strip()
    q = re.sub(r"\s+", " ", q) or name.lower().strip()
    if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", q):        # looks like a domain
        webbrowser.open(q if q.startswith("http") else "https://" + q)
        return f"Opened {q}."
    idx = _start_menu_index() if IS_WIN else {}
    hit = None
    if not (web and q in SITES):
        # installed apps win over websites ("claude" = the Claude app, not claude.ai)
        hit = idx.get(q) or next((p for n, p in idx.items() if n.startswith(q)), None) \
            or next((p for n, p in idx.items() if q in n.split()), None)
    if not hit and q in SITES:
        webbrowser.open(SITES[q])
        return f"Opened {q} in the browser."
    if not hit:
        hit = next((p for n, p in idx.items() if q in n), None)
    if not hit:
        close = difflib.get_close_matches(q, list(idx.keys()), n=1, cutoff=0.6)
        hit = idx[close[0]] if close else None
    if hit:
        _launch(hit)
        return f"Launched {os.path.splitext(os.path.basename(hit))[0]}."
    if q in APP_ALIASES:
        try:
            _launch(APP_ALIASES[q])
            return f"Launched {q}."
        except Exception:
            pass
    try:
        _launch(q)
        return f"Launched {q}."
    except Exception:
        return f"NOT_FOUND: couldn't find an app called '{name}'."


@tool("Close a running app by name (e.g. 'chrome', 'roblox'). Force-closes it — unsaved work is lost.",
      {"name": ("string", "App/process name", True)}, dangerous=True)
def close_app(name):
    _need(psutil, "psutil")
    q = name.lower().removesuffix(".exe")
    killed = set()
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if q in n and n not in ("python.exe", "pythonw.exe", "orion.exe"):
            try:
                p.terminate()
                killed.add(n)
            except Exception:
                pass
    return f"Closed: {', '.join(sorted(killed))}" if killed else f"No running app matched '{name}'."


@tool("List the main apps currently running (names only).")
def list_running_apps():
    _need(psutil, "psutil")
    names = sorted({(p.info["name"] or "") for p in psutil.process_iter(["name"])})
    skip = ("svchost", "system", "registry", "csrss", "wininit", "winlogon", "smss", "lsass",
            "services", "dwm", "fontdrvhost", "conhost", "runtimebroker", "sihost", "ctfmon")
    names = [n for n in names if n and not n.lower().startswith(skip)]
    return ", ".join(names[:120])


@tool("Open a website URL, or search Google if given plain words.",
      {"url_or_query": ("string", "A URL or a search query", True)})
def open_website(url_or_query):
    s = url_or_query.strip()
    if re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", s):
        url = s if s.startswith("http") else "https://" + s
    else:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(s)
    webbrowser.open(url)
    return f"Opened {url}"


# ---------------------------------------------------------------------------------------------
# Research — lets ORION actually learn things and answer from the web
@tool("Search the web and return the top results (title, link, snippet) so you can answer "
      "questions about current or unknown things. Use fetch_page to read a result.",
      {"query": ("string", "What to search for", True)})
def web_search(query):
    errors = []
    def _search_browser(q):
        from .browser import search
        return search(q)
    for engine in (_search_bing, _search_ddg_html, _search_ddg_lite, _search_browser, _search_wikipedia):
        try:
            res = engine(query)
            if res:
                head = ("(Normal web search was blocked — these are Wikipedia matches only, they may be off-topic. "
                        "For shopping/sites use browser_open instead.)\n\n") if engine is _search_wikipedia else ""
                return head + "\n\n".join(f"{t}\n{u}\n{sn}" for t, u, sn in res[:6])
        except Exception as e:
            errors.append(f"{engine.__name__[8:]}: {type(e).__name__}")
    return "No results." + (f" ({'; '.join(errors)})" if errors else "")


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<.*?>", "", s or ""))).strip()


def _search_bing(q):
    r = requests.get("https://www.bing.com/search", params={"q": q, "setlang": "en-GB", "cc": "GB"},
                     headers={**UA, "Accept-Language": "en-GB,en;q=0.9"}, timeout=10)
    out = []
    for block in re.findall(r'<li class="b_algo"(.*?)</li>', r.text, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url = html.unescape(m.group(1))
        u = re.search(r"[?&]u=a1([^&]+)", url)            # bing.com/ck/a?...&u=a1<base64 url>
        if u:
            import base64
            try:
                b = u.group(1)
                url = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "ignore")
            except Exception:
                pass
        sn = re.search(r'<p[^>]*>(.*?)</p>', block, re.S) or re.search(r'class="b_lineclamp\d?"[^>]*>(.*?)</', block, re.S)
        out.append((_clean(m.group(2)), url, _clean(sn.group(1)) if sn else ""))
    return out


def _search_ddg_html(q):
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": q}, headers=UA, timeout=10)
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
        href = html.unescape(m.group(1))
        mm = re.search(r"uddg=([^&]+)", href)
        link = urllib.parse.unquote(mm.group(1)) if mm else href
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', r.text[m.end():m.end() + 3000], re.S)
        out.append((_clean(m.group(2)), link, _clean(sn.group(1)) if sn else ""))
    return out


def _search_ddg_lite(q):
    r = requests.get("https://lite.duckduckgo.com/lite/", params={"q": q}, headers=UA, timeout=10)
    links = re.findall(r"<a[^>]+href=\"([^\"]+)\"[^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>", r.text, re.S)
    snips = re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", r.text, re.S)
    out = []
    for i, (href, title) in enumerate(links):
        mm = re.search(r"uddg=([^&]+)", href)
        out.append((_clean(title), urllib.parse.unquote(mm.group(1)) if mm else href,
                    _clean(snips[i]) if i < len(snips) else ""))
    return out


def _search_wikipedia(q):
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=10, params={
        "action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 5})
    return [(x["title"] + " — Wikipedia", "https://en.wikipedia.org/wiki/" + urllib.parse.quote(x["title"].replace(" ", "_")),
             _clean(x.get("snippet", ""))) for x in r.json().get("query", {}).get("search", [])]


@tool("Download a web page and return its readable text (first ~5000 characters).",
      {"url": ("string", "Page URL", True)})
def fetch_page(url):
    r = requests.get(url, headers=UA, timeout=15)
    t = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", r.text)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()[:5000]


# ---------------------------------------------------------------------------------------------
# Keyboard, mouse, screen
@tool("Type text into whatever is focused (works with emojis/symbols). Optionally press Enter after.",
      {"text": ("string", "Text to type", True),
       "press_enter": ("boolean", "Press Enter afterwards", False)})
def type_text(text, press_enter=False):
    _need(pyautogui, "pyautogui")
    if pyperclip:
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if old is not None:
            threading.Timer(1.0, lambda: pyperclip.copy(old)).start()
    else:
        pyautogui.write(text, interval=0.01)
    if press_enter:
        pyautogui.press("enter")
    return "Typed."


@tool("Press a key or key combo, e.g. 'enter', 'esc', 'ctrl+s', 'alt+tab', 'win+d', 'ctrl+shift+esc'.",
      {"keys": ("string", "Key or combo joined with +", True),
       "times": ("integer", "How many times (default 1)", False)})
def press_keys(keys, times=1):
    _need(pyautogui, "pyautogui")
    parts = [k.strip().lower().replace("windows", "win") for k in keys.split("+")]
    for _ in range(max(1, min(int(times or 1), 50))):
        pyautogui.hotkey(*parts) if len(parts) > 1 else pyautogui.press(parts[0])
        time.sleep(0.05)
    return f"Pressed {keys}."


@tool("Click the mouse at screen coordinates.",
      {"x": ("integer", "X pixel", True), "y": ("integer", "Y pixel", True),
       "button": ("string", "left, right or middle", False),
       "double": ("boolean", "Double click", False)})
def mouse_click(x, y, button="left", double=False):
    _need(pyautogui, "pyautogui")
    pyautogui.click(int(x), int(y), clicks=2 if double else 1, button=button or "left")
    return f"Clicked {button or 'left'} at ({x},{y})."


@tool("Scroll the mouse wheel. Positive = up, negative = down.",
      {"amount": ("integer", "Scroll clicks, e.g. -5", True)})
def scroll(amount):
    _need(pyautogui, "pyautogui")
    pyautogui.scroll(int(amount) * 100)
    return "Scrolled."


def _screenshot():
    _need(pyautogui, "pyautogui")
    img = pyautogui.screenshot()
    path = os.path.join(DATA_DIR, "last_screen.png")
    img.save(path)
    return img, path


def _ocr_ready():
    if pytesseract is None:
        return False
    tp = CTX["config"].get("tesseract_path")
    if tp and os.path.exists(tp):
        pytesseract.pytesseract.tesseract_cmd = tp
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@tool("Look at the screen: takes a screenshot and returns the visible text. Use before clicking things.")
def read_screen():
    img, path = _screenshot()
    if not _ocr_ready():
        return (f"Screenshot saved to {path} ({img.width}x{img.height}), but text reading needs "
                "Tesseract OCR installed (see README).")
    text = pytesseract.image_to_string(img)
    return f"Screen {img.width}x{img.height}. Visible text:\n{text.strip()[:4000]}"


def _find_text(target, img=None):
    if img is None:
        img, _ = _screenshot()
    if not _ocr_ready():
        raise RuntimeError("Finding things on screen needs Tesseract OCR (see README).")
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words = [(d["text"][i], d["left"][i], d["top"][i], d["width"][i], d["height"][i])
             for i in range(len(d["text"])) if d["text"][i].strip()]
    tgt = target.lower().split()
    best = None
    for i in range(len(words)):
        chunk = words[i:i + len(tgt)]
        phrase = " ".join(w[0].lower() for w in chunk)
        score = difflib.SequenceMatcher(None, phrase, " ".join(tgt)).ratio()
        if best is None or score > best[0]:
            x1, y1 = chunk[0][1], min(w[2] for w in chunk)
            x2 = chunk[-1][1] + chunk[-1][3]
            y2 = max(w[2] + w[4] for w in chunk)
            best = (score, (x1 + x2) // 2, (y1 + y2) // 2, phrase)
    if not best or best[0] < 0.7:
        return None
    return best


@tool("Find some text on screen (a button, link, menu item) and return its coordinates.",
      {"text": ("string", "The text to look for", True)})
def find_on_screen(text):
    hit = _find_text(text)
    if not hit:
        return f"Couldn't see '{text}' on screen."
    return f"Found '{hit[3]}' at ({hit[1]},{hit[2]})."


@tool("Find text on screen (e.g. a button label) and click it.",
      {"text": ("string", "The visible text to click", True),
       "double": ("boolean", "Double click", False)})
def click_text(text, double=False):
    hit = _find_text(text)
    if not hit:
        return f"Couldn't see '{text}' on screen."
    pyautogui.click(hit[1], hit[2], clicks=2 if double else 1)
    return f"Clicked '{hit[3]}' at ({hit[1]},{hit[2]})."


@tool("Wait a few seconds (e.g. for an app to finish opening).",
      {"seconds": ("number", "1-15", True)})
def wait(seconds):
    if CTX["cancel"].wait(max(0.2, min(float(seconds), 15))):
        return "Stopped by user."
    return "Waited."


# ---------------------------------------------------------------------------------------------
# Media & system
@tool("Control media/volume: play_pause, next, previous, volume_up, volume_down, mute.",
      {"action": ("string", "One of the actions", True),
       "steps": ("integer", "For volume: how many steps (default 5)", False)})
def media(action, steps=5):
    _need(pyautogui, "pyautogui")
    keymap = {"play_pause": "playpause", "play": "playpause", "pause": "playpause",
              "next": "nexttrack", "previous": "prevtrack", "volume_up": "volumeup",
              "volume_down": "volumedown", "mute": "volumemute"}
    key = keymap.get(action)
    if not key:
        return "Unknown media action."
    n = int(steps or 5) if "volume" in key and key != "volumemute" else 1
    for _ in range(n):
        pyautogui.press(key)
    return f"Done: {action}."


@tool("Get CPU, RAM, disk, battery and uptime.")
def system_status():
    _need(psutil, "psutil")
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    up = datetime.timedelta(seconds=int(time.time() - psutil.boot_time()))
    s = (f"CPU {psutil.cpu_percent(interval=0.4):.0f}% | RAM {vm.percent:.0f}% "
         f"({vm.used / 2**30:.1f}/{vm.total / 2**30:.1f} GB) | Disk {disk.percent:.0f}% "
         f"({disk.free / 2**30:.0f} GB free) | Uptime {up}")
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat:
        s += f" | Battery {bat.percent:.0f}%{' charging' if bat.power_plugged else ''}"
    return s


@tool("Get the current date and time.")
def get_time():
    return datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")


@tool("Set a timer/reminder. ORION will announce it when it goes off.",
      {"minutes": ("number", "Minutes from now", True),
       "label": ("string", "What it's for", False)})
def set_timer(minutes, label=""):
    secs = max(1, float(minutes) * 60)
    label = label or "Timer"
    threading.Timer(secs, lambda: CTX["notify"](f"{label} — time's up.")).start()
    return f"Timer set for {minutes:g} min: {label}."


@tool("Lock the PC.")
def lock_pc():
    if IS_WIN:
        ctypes.windll.user32.LockWorkStation()
        return "Locked."
    return "Locking only works on Windows."


@tool("Shut down, restart or sleep the PC.",
      {"action": ("string", "shutdown, restart or sleep", True)}, dangerous=True)
def power(action):
    if not IS_WIN:
        return "Only works on Windows."
    cmds = {"shutdown": "shutdown /s /t 5", "restart": "shutdown /r /t 5",
            "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"}
    if action not in cmds:
        return "Use shutdown, restart or sleep."
    subprocess.Popen(cmds[action], shell=True)
    return f"{action.title()} in progress."


@tool("Take a screenshot and save it to the Pictures folder.")
def save_screenshot():
    img, _ = _screenshot()
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "ORION")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
    img.save(path)
    return f"Saved to {path}"


@tool("Run a PowerShell command and return its output. Use for anything no other tool covers "
      "(file operations, network info, installed programs, etc).",
      {"command": ("string", "PowerShell command", True)}, dangerous=True)
def run_command(command):
    hit = _blocked(command)
    if hit:
        return ("BLOCKED: that command is on ORION's permanent blocklist (it could wreck Windows or your "
                "data). Refused — tell the user plainly.")
    args = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
            if IS_WIN else ["bash", "-c", command])
    flags = 0x08000000 if IS_WIN else 0   # CREATE_NO_WINDOW
    p = subprocess.run(args, capture_output=True, text=True, timeout=90, creationflags=flags)
    out = (p.stdout or "") + (("\n[stderr] " + p.stderr) if p.stderr.strip() else "")
    return out.strip()[:4000] or f"(no output, exit code {p.returncode})"


# ---------------------------------------------------------------------------------------------
# Files & clipboard
def _expand(path):
    p = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
    for name in ("desktop", "documents", "downloads", "pictures", "music", "videos"):
        if p.lower() == name or p.lower().startswith(name + os.sep) or p.lower().startswith(name + "/"):
            p = os.path.join(os.path.expanduser("~"), name.title(), p[len(name) + 1:])
            break
    return p


@tool("List files in a folder. Shortcuts like 'desktop', 'downloads', 'documents' work.",
      {"path": ("string", "Folder path", True)})
def list_files(path):
    p = _expand(path)
    items = sorted(os.listdir(p))
    lines = [("[DIR] " if os.path.isdir(os.path.join(p, i)) else "") + i for i in items[:200]]
    return f"{p}:\n" + "\n".join(lines) if lines else f"{p} is empty."


@tool("Read a text file (code, notes, etc).", {"path": ("string", "File path", True)})
def read_file(path):
    with open(_expand(path), "r", encoding="utf-8", errors="replace") as f:
        return f.read(8000)


@tool("Create or overwrite a text file (scripts, notes, code).",
      {"path": ("string", "File path", True), "content": ("string", "Full file content", True)},
      dangerous=True)
def write_file(path, content):
    p = os.path.abspath(_expand(path))
    if any(p.lower().startswith(d) for d in PROTECTED_DIRS if d):
        return "BLOCKED: ORION won't write inside Windows or Program Files."
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    backup = None
    if os.path.exists(p):    # back up the old version first so it can be undone
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, datetime.datetime.now().strftime("%Y%m%d_%H%M%S_")
                              + os.path.basename(p))
        shutil.copy2(p, backup)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    c = _changes()
    c.append({"path": p, "backup": backup, "t": time.time()})
    _save_changes(c)
    return f"Wrote {len(content)} characters to {p}" + (" (old version backed up)" if backup else "")


@tool("Undo the last file ORION created or changed (restores the backup, or deletes a newly created file).")
def undo_last_change():
    c = _changes()
    if not c:
        return "Nothing to undo."
    last = c.pop()
    _save_changes(c)
    if last["backup"] and os.path.exists(last["backup"]):
        shutil.copy2(last["backup"], last["path"])
        return f"Restored the previous version of {last['path']}."
    if os.path.exists(last["path"]):
        os.remove(last["path"])
        return f"Removed {last['path']} (it was newly created)."
    return "That file no longer exists — nothing to undo."


@tool("Open a file or folder with its default program.", {"path": ("string", "Path", True)})
def open_path(path):
    _launch(_expand(path))
    return f"Opened {path}."


@tool("Read what's on the clipboard.")
def clipboard_get():
    _need(pyperclip, "pyperclip")
    return pyperclip.paste()[:4000] or "(clipboard is empty)"


@tool("Put text on the clipboard.", {"text": ("string", "Text", True)})
def clipboard_set(text):
    _need(pyperclip, "pyperclip")
    pyperclip.copy(text)
    return "Copied to clipboard."


# ---------------------------------------------------------------------------------------------
# Memory & escalation
@tool("Save a long-term fact about the user or their projects (preferences, names, goals) so you "
      "remember it in future sessions.", {"fact": ("string", "The fact, as one short sentence", True)})
def remember(fact):
    CTX["memory"].add_fact(fact)
    return "Saved to memory."


@tool("Delete saved memories containing a keyword.", {"keyword": ("string", "Keyword", True)})
def forget(keyword):
    n = CTX["memory"].forget(keyword)
    return f"Forgot {n} item(s)."


@tool("Hand over to Claude: opens Claude with a question already written. Use when you can't do "
      "the task with your tools, aren't confident, or the user wants in-depth help, teaching, "
      "big coding jobs or advice.",
      {"question": ("string", "A complete, self-contained message for Claude including all context", True)})
def ask_claude(question):
    CTX["open_claude"](question)
    return "Opened Claude with the question (also copied to clipboard)."


@tool("Switch ORION's mode (colours + personality): standby, serious, stealth, executive or hacker.",
      {"mode": ("string", "standby | serious | stealth | executive | hacker", True)})
def set_theme(mode):
    mode = mode.lower().strip().replace(" mode", "")
    if mode not in ("standby", "serious", "stealth", "executive", "hacker"):
        return "Unknown mode."
    CTX["set_theme"](mode)
    return f"{mode.title()} mode engaged."


@tool("Ask for the full toolset when you need a tool you weren't given.",
      {"reason": ("string", "What you need to do", False)})
def request_more_tools(reason=""):
    return "All tools are now available."


# ---------------------------------------------------------------------------------------------
class Toolbox:
    def __init__(self, config, emit, confirm):
        self.config = config
        self.emit = emit          # emit(kind, **data) -> UI
        self.confirm = confirm    # confirm(text) -> bool

    def schemas(self, allowed=None):
        """allowed = set of tool names, or None for everything."""
        return [t["schema"] for n, t in REGISTRY.items() if allowed is None or n in allowed]

    def run(self, name, args):
        t = REGISTRY.get(name)
        if not t:
            return f"ERROR: no tool called {name}"
        args = args if isinstance(args, dict) else {}
        try:   # models sometimes send {"": ""} or extra keys — keep only real parameters
            import inspect
            params = inspect.signature(t["fn"]).parameters
            if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
                args = {k: v for k, v in args.items() if k in params}
        except (TypeError, ValueError):
            args = {k: v for k, v in args.items() if k}
        pretty = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in args.items())
        self.emit("tool", name=name, args=pretty, status="running")
        if t["dangerous"] and self.config.get("safe_mode", False):
            if not self.confirm(f"{name}({pretty})"):
                self.emit("tool", name=name, args=pretty, status="denied")
                _activity(f"DENIED {name}({pretty})")
                return "The user denied permission for this action."
        try:
            result = str(t["fn"](**args))
            status = ("blocked" if result.startswith(("BLOCKED", "REJECTED")) else
                      "error" if result.startswith(("ERROR", "NOT_FOUND", "TEST FAILED")) else "ok")
        except TypeError as e:
            result, status = f"ERROR: bad arguments: {e}", "error"
        except Exception as e:
            result, status = f"ERROR: {type(e).__name__}: {e}", "error"
        self.emit("tool", name=name, args=pretty, status=status)
        _activity(f"{status.upper():7} {name}({pretty}) -> {result[:200]}")
        return result

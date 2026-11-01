"""Health check: every part of ORION in one list — green, amber or red — each with a FIX button.
Also: one-click backup + restore of all ORION data to a private GitHub Gist."""
import base64
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import requests

from .paths import APP_DIR, DATA_DIR, FROZEN, SKILLS_DIR

FLAGS = 0x08000000 if os.name == "nt" else 0
BACKUP_FILES = ["memory.json", "schedule.json", "study.json", "shortcuts.json", "earnings.json", "devqueue.json",
                "gamestats.json", "jobs.json", "routines_state.json", "usage.json", "root_log.json", "root_layout.json",
                "voiceprint.npy"]


def _ok(id, name, detail, fix=None, fix_label=None):
    return {"id": id, "name": name, "state": "ok", "detail": detail, "fix": fix, "fix_label": fix_label}


def _warn(id, name, detail, fix=None, fix_label="FIX"):
    return {"id": id, "name": name, "state": "warn", "detail": detail, "fix": fix, "fix_label": fix_label}


def _bad(id, name, detail, fix=None, fix_label="FIX"):
    return {"id": id, "name": name, "state": "bad", "detail": detail, "fix": fix, "fix_label": fix_label}


def _check_key(p):
    if not p.get("api_key"):
        return "missing"
    try:
        r = requests.get(p["base_url"].rstrip("/") + "/models", timeout=8,
                         headers={"Authorization": f"Bearer {p['api_key']}"})
        if r.status_code in (401, 403):
            return "rejected"
        return "ok" if r.status_code < 500 else "down"
    except Exception:
        return "offline"


def run_checks(api):
    """api = the ORION Api object. Returns a list of check results (runs network checks in parallel)."""
    cfg = api._cfg
    out = []
    # --- AI brains
    keys = {}

    def k(p):
        keys[p["id"]] = _check_key(p)
    ts = [threading.Thread(target=k, args=(p,)) for p in cfg["providers"]]
    [t.start() for t in ts]
    [t.join(12) for t in ts]
    working = 0
    for p in cfg["providers"]:
        st = keys.get(p["id"], "offline")
        nm = f"{p['label']} brain"
        if st == "ok":
            working += 1
            out.append(_ok("key_" + p["id"], nm, "Key works."))
        elif st == "missing":
            out.append(_warn("key_" + p["id"], nm, "No key — free extra allowance if you add one.", "open:" + p.get("key_url", ""), "GET KEY"))
        elif st == "rejected":
            out.append(_bad("key_" + p["id"], nm, "Key was rejected — make a new one and paste it in Settings.", "open:" + p.get("key_url", ""), "NEW KEY"))
        else:
            out.append(_warn("key_" + p["id"], nm, "Couldn't reach it right now (internet or their servers)."))
    if not working:
        out.insert(0, _bad("brains", "Cloud brains", "No working cloud brain — ORION falls back to the local one.", "settings", "SETTINGS"))
    # --- local brain
    loc = api._brain.local
    if loc.ping():
        out.append(_ok("local", "Local brain", f"Ollama running · using {loc.fast[0]}"))
    elif shutil.which("ollama") or os.path.exists(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")):
        out.append(_warn("local", "Local brain", "Ollama is installed but not running.", "ollama_start", "START"))
    else:
        out.append(_warn("local", "Local brain", "Not installed — the offline backup brain.", "local_install", "INSTALL"))
    # --- tools
    try:
        from .video import ffmpeg
        ffmpeg()
        out.append(_ok("ffmpeg", "Video tools (ffmpeg)", "Installed."))
    except Exception:
        out.append(_bad("ffmpeg", "Video tools (ffmpeg)", "Missing — Studio, Shorts and clips need it.", "winget:Gyan.FFmpeg", "INSTALL"))
    tess = cfg.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if os.path.exists(tess) or shutil.which("tesseract"):
        out.append(_ok("ocr", "Screen reading (Tesseract)", "Installed."))
    else:
        out.append(_bad("ocr", "Screen reading (Tesseract)", "Missing — Root control uses it.", "winget:UB-Mannheim.TesseractOCR", "INSTALL"))
    try:
        import playwright  # noqa: F401
        exe = None
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
            exe = glob.glob(os.path.join(base, "chromium*"))
        except Exception:
            pass
        if exe or os.name != "nt":
            out.append(_ok("browser", "Hidden browser", "Ready."))
        else:
            out.append(_bad("browser", "Hidden browser", "Chromium not downloaded yet.", "browser_install", "INSTALL"))
    except Exception:
        out.append(_bad("browser", "Hidden browser", "Playwright isn't installed.", "pip:playwright", "INSTALL"))
    # --- voice
    out.append(_ok("tts", "Voice", "Natural neural voice.") if api._speaker.neural_ok
               else _warn("tts", "Voice", "Using the robotic offline voice (edge-tts missing or no internet).", "pip:edge-tts", "FIX"))
    out.append(_ok("mic", "Microphone", "Found.") if api._recorder.available
               else _bad("mic", "Microphone", "No microphone found (or sounddevice missing).", "pip:sounddevice", "FIX"))
    try:
        from .listen import extras_status
        ex = extras_status()
        if ex.get("wake") is None and ex.get("voice_id") is None:
            out.append(_ok("extras", "Wake word + Voice ID", "Installed."))
        else:
            out.append(_warn("extras", "Wake word + Voice ID", "Not installed (optional).", "extras", "INSTALL"))
    except Exception:
        pass
    # --- Root
    try:
        from .root import root_window
        w = root_window(launch=False)
        if w:
            from . import root_uia
            p = root_uia.read_panel(w[0]) or {}
            if p.get("view") == "list" and p.get("conversations"):
                out.append(_ok("root", "Root reading", f"Reads {len(p['conversations'])} DMs directly (accessibility)."))
            elif p.get("view") == "conversation":
                out.append(_ok("root", "Root reading", f"Reading an open chat with {p.get('with')}."))
            else:
                out.append(_warn("root", "Root reading", "Can't read Root's DM panel properly yet — run the diagnostic "
                                 "and send the file to get it fixed.", "root_diag", "DIAGNOSE"))
    except Exception:
        pass
    # --- phone
    rc = cfg.get("remote", {})
    from . import phone
    seen = time.time() - phone.LAST_SEEN[0]
    if not rc.get("enabled"):
        out.append(_warn("remote", "Phone link", "Phone & laptop access is off.", "remote_on", "TURN ON"))
    elif phone.LAST_SEEN[0] and seen < 300:
        out.append(_ok("remote", "Phone link", "Your phone checked in " + (f"{int(seen)}s ago." if seen < 120 else f"{int(seen // 60)} min ago.")))
    else:
        out.append(_warn("remote", "Phone link", "On, but your phone hasn't connected recently. Check Tailscale is on, and "
                         "allow Python through the Windows firewall (private networks).", "firewall", "HOW"))
    out.append(_ok("push", "Phone notifications", "ntfy set up.") if cfg.get("notify", {}).get("ntfy_topic")
               else _warn("push", "Phone notifications", "Not set up — you won't get pings when the app is closed.", "push_on", "TURN ON"))
    # --- disk + system
    try:
        du = shutil.disk_usage(os.path.abspath(os.sep))
        free = du.free / 2**30
        if free < 5:
            out.append(_bad("disk", "Disk space", f"Only {free:.1f} GB free.", "clean", "CLEAN UP"))
        elif free < 20:
            out.append(_warn("disk", "Disk space", f"{free:.0f} GB free.", "clean", "CLEAN UP"))
        else:
            out.append(_ok("disk", "Disk space", f"{free:.0f} GB free."))
    except Exception:
        pass
    if FROZEN:
        out.append(_bad("exe", "How ORION is running", "You're running ORION.exe — it can't update or use voice extras. "
                        "Open ORION from the Desktop/Start Menu shortcut instead.", "shortcut", "MAKE SHORTCUT"))
    else:
        out.append(_ok("exe", "How ORION is running", f"From source on Python {sys.version.split()[0]} — updates work."))
    # --- updates + backup
    try:
        u = api._updater.check()
        out.append(_warn("update", "Updates", f"Version {u['version']} is ready.", "update", "INSTALL")
                   if u else _ok("update", "Updates", "Up to date."))
    except Exception:
        out.append(_warn("update", "Updates", "Couldn't check (offline?)."))
    last = cfg.get("backup", {}).get("last")
    tok = cfg.get("sync", {}).get("github_token")
    if not tok:
        out.append(_warn("backup", "Cloud backup", "Add a GitHub token in Devices › Sync to back up to the cloud."))
    elif not last or time.time() - last > 7 * 86400:
        out.append(_warn("backup", "Cloud backup", "No cloud backup this week.", "backup", "BACK UP"))
    else:
        out.append(_ok("backup", "Cloud backup", "Last backup " + time.strftime("%a %d %b %H:%M", time.localtime(last)), "backup", "BACK UP"))
    out.append(_ok("profile", "Device profile", ("Lite (low-RAM laptop): wake word, clip buffer and overnight video "
                                                 "jobs are off.") if api.lite_profile else "Full — every feature on."))
    order = {"bad": 0, "warn": 1, "ok": 2}
    return sorted(out, key=lambda x: order[x["state"]])


def _pip(pkg):
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg], capture_output=True, text=True,
                       creationflags=FLAGS, timeout=900)
    return r.returncode == 0, (r.stdout + r.stderr)[-300:]


def fix(api, fid):
    """Runs a fix. Returns a short message."""
    if fid.startswith("open:"):
        import webbrowser
        webbrowser.open(fid[5:])
        return "Opened the page in your browser — paste the new key in Settings."
    if fid.startswith("winget:"):
        r = subprocess.run(["winget", "install", "-e", "--id", fid[7:], "--silent", "--accept-source-agreements",
                            "--accept-package-agreements"], capture_output=True, text=True, creationflags=FLAGS, timeout=1200)
        return "Installed — restart ORION to pick it up." if r.returncode == 0 else f"winget said: {(r.stdout + r.stderr)[-200:]}"
    if fid.startswith("pip:"):
        ok, log = _pip(fid[4:])
        return "Installed — restart ORION." if ok else f"pip failed: {log}"
    if fid == "browser_install":
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, text=True,
                           creationflags=FLAGS, timeout=1200)
        return "Browser installed." if r.returncode == 0 else f"Failed: {(r.stdout + r.stderr)[-200:]}"
    if fid == "ollama_start":
        exe = shutil.which("ollama") or os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        subprocess.Popen([exe, "serve"], creationflags=FLAGS)
        return "Starting the local brain…"
    if fid == "local_install":
        bat = os.path.join(APP_DIR, "2_INSTALL_LOCAL_BRAIN.bat")
        if os.path.exists(bat):
            os.startfile(bat)
            return "Opened the local brain installer — follow the window."
        return "2_INSTALL_LOCAL_BRAIN.bat is missing from the ORION folder."
    if fid == "extras":
        api._install_extras(voice_id=True)
        return "Installing voice extras — watch the chat for progress."
    if fid == "remote_on":
        api.devices_action("remote_on")
        return "Phone access is on — see Devices for the address and PIN."
    if fid == "push_on":
        api.devices_action("push_on")
        return "Notifications on — see Devices for the ntfy topic to subscribe to."
    if fid == "firewall":
        return ("Open Windows Security › Firewall › Allow an app through firewall › Change settings › tick "
                "'Python' for Private networks. Also make sure Tailscale is connected on both devices.")
    if fid == "clean":
        from .routines import clear_temp
        return clear_temp()
    if fid == "shortcut":
        r = subprocess.run([sys.executable, os.path.join(APP_DIR, "make_shortcut.py")], capture_output=True, text=True,
                           creationflags=FLAGS, timeout=60)
        return (r.stdout or r.stderr)[-300:]
    if fid == "update":
        api.devices_action("update_install")
        return "Installing the update — ORION will restart."
    if fid == "backup":
        return backup_cloud(api._cfg)
    if fid == "root_diag":
        from .root import root_diagnose
        return root_diagnose()
    if fid == "settings":
        return "Open Settings (gear, bottom-left) and paste a free key."
    return "Nothing to do."


# ------------------------------------------------------------------ cloud backup
def _zip_data():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in BACKUP_FILES:
            p = os.path.join(DATA_DIR, n)
            if os.path.exists(p):
                z.write(p, "data/" + n)
        for p in glob.glob(os.path.join(SKILLS_DIR, "**", "*"), recursive=True):
            if os.path.isfile(p) and "__pycache__" not in p:
                z.write(p, "skills/" + os.path.relpath(p, SKILLS_DIR).replace("\\", "/"))
    return buf.getvalue()


def _gh(cfg):
    tok = cfg.get("sync", {}).get("github_token")
    if not tok:
        raise RuntimeError("Add a GitHub token in Devices › Sync first.")
    return {"Authorization": f"token {tok}", "Accept": "application/vnd.github+json"}


def backup_cloud(cfg):
    from . import config as config_mod
    data = _zip_data()
    if len(data) > 9 * 2**20:
        return "Backup is over 9 MB — too big for a Gist."
    files = {"orion-backup.b64": {"content": base64.b64encode(data).decode()},
             "info.json": {"content": json.dumps({"made": time.strftime("%Y-%m-%d %H:%M"), "bytes": len(data)})}}
    b = cfg.setdefault("backup", {})
    h = _gh(cfg)
    if b.get("gist_id"):
        r = requests.patch(f"https://api.github.com/gists/{b['gist_id']}", headers=h, json={"files": files}, timeout=60)
        if r.status_code == 404:
            b.pop("gist_id")
    if not b.get("gist_id"):
        r = requests.post("https://api.github.com/gists", headers=h, timeout=60,
                          json={"description": "ORION backup (private)", "public": False, "files": files})
    r.raise_for_status()
    b["gist_id"] = r.json()["id"]
    b["last"] = time.time()
    config_mod.save(cfg)
    return f"Backed up {len(data) // 1024} KB to your private GitHub Gist."


def restore_cloud(cfg):
    b = cfg.get("backup", {})
    h = _gh(cfg)
    gid = b.get("gist_id")
    if not gid:   # find it on the account
        r = requests.get("https://api.github.com/gists?per_page=100", headers=h, timeout=30)
        r.raise_for_status()
        gid = next((g["id"] for g in r.json() if g.get("description") == "ORION backup (private)"), None)
        if not gid:
            return "No ORION backup found on your GitHub."
    r = requests.get(f"https://api.github.com/gists/{gid}", headers=h, timeout=60)
    r.raise_for_status()
    f = r.json()["files"].get("orion-backup.b64") or {}
    content = f.get("content")
    if f.get("truncated") and f.get("raw_url"):
        content = requests.get(f["raw_url"], headers=h, timeout=60).text
    raw = base64.b64decode(content)
    safety = os.path.join(DATA_DIR, f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    with open(safety, "wb") as fh:
        fh.write(_zip_data())
    n = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if ".." in name or name.startswith("/"):
                continue
            dest = os.path.join(DATA_DIR if name.startswith("data/") else SKILLS_DIR, name.split("/", 1)[1])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(z.read(name))
            n += 1
    return f"Restored {n} file(s). Your old data was saved to {os.path.basename(safety)}. Restart ORION."

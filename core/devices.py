"""ORION Network: phone + laptop access, push notifications, sync and self-updates. All free.

- Remote: a small PIN-protected server so your phone/laptop can talk to this PC's ORION from anywhere
  (via Tailscale — a free private network between YOUR devices; nothing is exposed to the internet).
- Push: notifications to your phone through ntfy (free app, no account) — reminders, DMs, missions done.
- Sync: memory + schedule shared between your PC, laptop and phone via a private GitHub Gist.
- Updates: checks your GitHub repo for a new ORION release and installs it in one click.
"""
import hashlib
import hmac
import io
import json
import urllib.parse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from . import config as config_mod
from .paths import APP_DIR, DATA_DIR, FROZEN, RES_DIR

# ====================================================================== push notifications (ntfy)
class Push:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def topic(self):
        return self.cfg.setdefault("notify", {}).get("ntfy_topic", "")

    def enable(self):
        if not self.topic:
            self.cfg["notify"]["ntfy_topic"] = "orion-" + secrets.token_hex(8)
            config_mod.save(self.cfg)
        return self.topic

    def send(self, text, title=None, priority=3, tags="robot"):
        if not self.topic:
            return False
        try:
            requests.post(f"https://ntfy.sh/{self.topic}", data=text.encode("utf-8"), timeout=8,
                          headers={"Title": (title or self.cfg.get("assistant_name", "ORION")).encode("ascii", "ignore"),
                                   "Priority": str(priority), "Tags": tags})
            return True
        except Exception:
            return False


# ====================================================================== remote access server
def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    tail = [ip for ip in ips if ip.startswith("100.")]          # Tailscale addresses are 100.x.x.x
    lan = [ip for ip in ips if not ip.startswith(("100.", "127."))]
    return {"tailscale": tail, "lan": lan}


class Remote:
    """api: the desktop Api object (ask(text) -> reply, plus state helpers)."""

    def __init__(self, cfg, api):
        self.cfg = cfg
        self.api = api
        self.server = None
        self.fails = {}

    @property
    def rc(self):
        return self.cfg.setdefault("remote", {})

    def ensure_pin(self):
        if not self.rc.get("pin"):
            self.rc["pin"] = f"{secrets.randbelow(900000) + 100000}"
            config_mod.save(self.cfg)
        return self.rc["pin"]

    def start(self):
        if self.server:
            return True
        self.ensure_pin()
        remote = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-PIN")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def _json(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.end_headers()

            def _authed(self):
                ip = self.client_address[0]
                f = remote.fails.get(ip, (0, 0))
                if f[0] >= 8 and time.time() - f[1] < 600:
                    self._json(429, {"error": "Too many wrong PINs — wait 10 minutes."})
                    return False
                if hmac.compare_digest(self.headers.get("X-PIN", ""), str(remote.rc.get("pin", ""))):
                    remote.fails.pop(ip, None)
                    return True
                remote.fails[ip] = (f[0] + 1, time.time())
                self._json(401, {"error": "Wrong PIN"})
                return False

            def do_GET(self):
                if self.path in ("/", "/index.html", "/app"):
                    with open(os.path.join(RES_DIR, "ui", "mobile.html"), "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/manifest.json":
                    self._json(200, {"name": "ORION", "short_name": "ORION", "display": "standalone",
                                     "background_color": "#03060c", "theme_color": "#03060c", "start_url": "/"})
                    return
                if not self._authed():
                    return
                if self.path == "/api/state":
                    self._json(200, remote.api.remote_state())
                elif self.path.startswith("/api/files/"):
                    name = os.path.basename(urllib.parse.unquote(self.path[len("/api/files/"):].split("?")[0]))
                    fp = os.path.join(DATA_DIR, "outbox", name)
                    if not name or not os.path.isfile(fp):
                        self._json(404, {"error": "no such file"})
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(os.path.getsize(fp)))
                    self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                    self._cors()
                    self.end_headers()
                    with open(fp, "rb") as f:
                        shutil.copyfileobj(f, self.wfile)
                elif self.path.startswith("/api/screen"):
                    jpg = remote.api.screen_jpeg()
                    if not jpg:
                        self._json(503, {"error": "screenshot unavailable"})
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(jpg)
                else:
                    try:
                        self._json(200, remote.api.remote_get(self.path))
                    except KeyError:
                        self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._authed():
                    return
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n else b""
                if self.path == "/api/cam":
                    self._json(200, remote.api.cam_frame(raw))
                    return
                if self.path == "/api/transcribe":
                    self._json(200, {"text": remote.api.transcribe_bytes(raw)})
                    return
                if self.path.startswith("/api/drop"):
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    self._json(200, remote.api.file_drop((q.get("name") or ["file"])[0], raw))
                    return
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    body = {}
                if self.path == "/api/send":
                    self._json(200, remote.api.ask(body.get("text", ""), source=body.get("source", "phone")))
                elif self.path == "/api/action":
                    self._json(200, {"result": remote.api.remote_action(body.get("action", ""), body.get("value"))})
                else:
                    try:
                        self._json(200, remote.api.remote_post(self.path, body))
                    except KeyError:
                        self._json(404, {"error": "not found"})

        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", int(self.rc.get("port", 7777))), H)
        except OSError as e:
            self.server = None
            raise RuntimeError(f"Couldn't open port {self.rc.get('port', 7777)}: {e}")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server = None

    def info(self):
        ips = local_ips()
        port = self.rc.get("port", 7777)
        return {"running": bool(self.server), "pin": self.rc.get("pin", ""), "port": port,
                "tailscale": [f"http://{ip}:{port}" for ip in ips["tailscale"]],
                "lan": [f"http://{ip}:{port}" for ip in ips["lan"]]}


# ====================================================================== sync (private GitHub Gist)
SYNC_FILES = {n: os.path.join(DATA_DIR, n) for n in (
    "memory.json", "schedule.json", "notes.json", "homework.json", "study.json", "shortcuts.json", "earnings.json",
    "crm.json", "goals.json", "scholar.json", "rides.json", "ideas.json", "hours.json")}
STATE_PATH = os.path.join(DATA_DIR, "sync_state.json")


def _by_id(local, remote, key="id", limit=2000):
    """Lists of records: keep everything from both devices; the local copy wins for the same record."""
    out = {}
    for x in (remote or []) + (local or []):
        k = x.get(key) if isinstance(x, dict) else None
        out[k or json.dumps(x, sort_keys=True)] = x
    return list(out.values())[-limit:]


def _merge(name, local, remote):
    """Combine two devices' copies instead of one overwriting the other."""
    if name == "memory.json":
        facts = {f["text"].lower(): f for f in remote.get("facts", []) + local.get("facts", [])}
        hist = {}
        for h in remote.get("history", []) + local.get("history", []):
            hist[h.get("id") or (h.get("role", "") + str(h.get("content", ""))[:80])] = h
        hist = sorted(hist.values(), key=lambda h: h.get("t", 0))[-60:]
        return {"facts": list(facts.values())[-600:], "history": hist}
    if isinstance(local, list) or isinstance(remote, list):
        key = "phrase" if name == "shortcuts.json" else "id"
        return _by_id(local if isinstance(local, list) else [], remote if isinstance(remote, list) else [], key)
    if name == "study.json":
        decks = dict(remote.get("decks", {}))
        decks.update(local.get("decks", {}))
        log = {k: max(local.get("log", {}).get(k, 0), remote.get("log", {}).get(k, 0))
               for k in set(local.get("log", {})) | set(remote.get("log", {}))}
        ex = {e["subject"]: e for e in remote.get("exams", []) + local.get("exams", [])}
        return {"decks": decks, "log": log, "exams": list(ex.values())}
    if isinstance(local, dict) and isinstance(remote, dict) and name not in ("schedule.json",):
        out = dict(remote)
        for k, v in local.items():
            if isinstance(v, list) and isinstance(out.get(k), list):
                out[k] = _by_id(v, out[k])
            else:
                out[k] = v
        return out
    if name == "schedule.json":
        ev = {e["id"]: e for e in remote.get("events", []) + local.get("events", [])}
        removed = set(local.get("removed", [])) | set(remote.get("removed", []))
        return {"events": [e for k, e in ev.items() if k not in removed],
                "fired": sorted(set(local.get("fired", [])) | set(remote.get("fired", [])))[-300:],
                "briefed": max(local.get("briefed", ""), remote.get("briefed", "")),
                "removed": sorted(removed)[-500:]}
    return local


class Sync:
    API = "https://api.github.com/gists"

    def __init__(self, cfg, emit):
        self.cfg = cfg
        self.emit = emit
        self.status = "off"
        self._lock = threading.Lock()

    @property
    def sc(self):
        return self.cfg.setdefault("sync", {})

    @property
    def enabled(self):
        return bool(self.sc.get("github_token"))

    def _h(self):
        return {"Authorization": f"token {self.sc['github_token']}", "Accept": "application/vnd.github+json"}

    def _state(self):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _read(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "{}"

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(5)
        while True:
            if self.enabled:
                try:
                    self.sync_now()
                except Exception as e:
                    self.status = f"error: {str(e)[:80]}"
            time.sleep(120)

    def sync_now(self):
        with self._lock:
            if not self.sc.get("gist_id"):
                files = {k: {"content": self._read(p)} for k, p in SYNC_FILES.items() if os.path.exists(p)} or \
                        {"memory.json": {"content": "{}"}}
                r = requests.post(self.API, headers=self._h(), timeout=20,
                                  json={"description": "ORION sync (private)", "public": False, "files": files})
                r.raise_for_status()
                self.sc["gist_id"] = r.json()["id"]
                config_mod.save(self.cfg)
            r = requests.get(f"{self.API}/{self.sc['gist_id']}", headers=self._h(), timeout=20)
            r.raise_for_status()
            remote_files = r.json().get("files", {})
            state, changed_remote, push = self._state(), False, {}
            for name, path in SYNC_FILES.items():
                if not os.path.exists(path) and name not in remote_files:
                    continue
                local_txt = self._read(path)
                remote_txt = (remote_files.get(name) or {}).get("content", "{}")
                if local_txt == remote_txt:
                    continue
                try:
                    merged = _merge(name, json.loads(local_txt or "{}"), json.loads(remote_txt or "{}"))
                except json.JSONDecodeError:
                    continue
                txt = json.dumps(merged, indent=1)
                if txt != local_txt:
                    from .safeio import write_json
                    write_json(path, merged)
                    changed_remote = True
                if txt != remote_txt:
                    push[name] = {"content": txt}
            if push:
                requests.patch(f"{self.API}/{self.sc['gist_id']}", headers=self._h(), timeout=20,
                               json={"files": push}).raise_for_status()
            state["last"] = time.strftime("%H:%M")
            from .safeio import write_json
            write_json(STATE_PATH, state)
            self.status = f"synced {state['last']}"
            if changed_remote:
                self.emit("synced")
            return self.status


# ====================================================================== self-updater (GitHub Releases)
KEEP = {"config.json", "data", "projects", "skills"}


def _ver(v):
    return tuple(int(x) for x in "".join(c for c in v if c.isdigit() or c == ".").split(".") if x)


class Updater:
    def __init__(self, cfg, emit):
        self.cfg = cfg
        self.emit = emit
        self.latest = None

    def check(self):
        repo = self.cfg.get("update", {}).get("repo")
        if not repo:
            return None
        h = {"Accept": "application/vnd.github+json"}
        tok = self.cfg.get("sync", {}).get("github_token")
        if tok:
            h["Authorization"] = f"token {tok}"
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=h, timeout=10)
        if r.status_code != 200:
            return None
        j = r.json()
        tag = j.get("tag_name", "")
        asset = next((a for a in j.get("assets", []) if a["name"].lower().startswith("orion") and
                      a["name"].endswith(".zip")), None)
        if _ver(tag) > _ver(config_mod.VERSION) and asset:
            self.latest = {"version": tag, "notes": (j.get("body") or "")[:1500], "url": asset["browser_download_url"],
                           "api_url": asset["url"]}
            self.emit("update", **self.latest)
            return self.latest
        return None

    def start(self):
        def run():
            time.sleep(20)
            try:
                if self.cfg.get("update", {}).get("check", True):
                    self.check()
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def source_root():
        """The folder holding ORION.pyw. When running the built ORION.exe (orion\\dist\\ORION), that's two levels up."""
        if os.path.exists(os.path.join(APP_DIR, "ORION.pyw")):
            return APP_DIR
        d = APP_DIR
        for _ in range(3):
            d = os.path.dirname(d)
            if os.path.exists(os.path.join(d, "ORION.pyw")):
                return d
        return APP_DIR

    @staticmethod
    def _copy(src_file, dst_file, tries=8):
        """Copy one file, retrying while OneDrive / antivirus has it locked."""
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
        last = None
        for i in range(tries):
            try:
                shutil.copy2(src_file, dst_file)
                return
            except (PermissionError, OSError) as e:
                last = e
                time.sleep(0.6 + i * 0.4)
        raise RuntimeError(f"Couldn't replace {os.path.basename(dst_file)} — it's locked "
                           f"(OneDrive syncing or antivirus?). Pause OneDrive and try again. ({last})")

    def install(self, log=lambda m: None):
        if not self.latest:
            self.check()
        if not self.latest:
            raise RuntimeError("No update available.")
        new_ver = self.latest["version"].lstrip("v")
        log(f"Downloading ORION {new_ver}…")
        h = {"Accept": "application/octet-stream"}
        tok = self.cfg.get("sync", {}).get("github_token")
        if tok:
            h["Authorization"] = f"token {tok}"
        try:
            r = requests.get(self.latest["api_url"], headers=h, timeout=300)
            r.raise_for_status()
            data = r.content
        except Exception:
            r = requests.get(self.latest["url"], timeout=300)     # public download link as a fallback
            r.raise_for_status()
            data = r.content
        tmp = tempfile.mkdtemp(prefix="orion_up_")
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        src = tmp
        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            src = os.path.join(tmp, entries[0])
        root = self.source_root()
        log(f"Installing into {root}…")
        backup = os.path.join(DATA_DIR, "backups", f"orion_{config_mod.VERSION}")
        n = 0
        for dirpath, dirs, files in os.walk(src):
            rel = os.path.relpath(dirpath, src)
            top = rel.split(os.sep)[0]
            if top in KEEP:
                continue
            for f in files:
                if rel == "." and f in KEEP:
                    continue
                s_file = os.path.join(dirpath, f)
                d_file = os.path.normpath(os.path.join(root, rel, f))
                if os.path.exists(d_file):
                    try:
                        self._copy(d_file, os.path.join(backup, rel, f), tries=2)
                    except Exception:
                        pass
                self._copy(s_file, d_file)
                n += 1
        shutil.rmtree(tmp, ignore_errors=True)
        # check it really landed
        with open(os.path.join(root, "core", "config.py"), "r", encoding="utf-8") as fh:
            got = next((ln.split('"')[1] for ln in fh if ln.startswith("VERSION =")), "?")
        if got != new_ver:
            raise RuntimeError(f"Update copied but version reads {got}, not {new_ver}.")
        log(f"Installed {n} files. Updating packages…")
        py = self._python()
        if py:
            try:
                subprocess.run([py.replace("pythonw.exe", "python.exe"), "-m", "pip", "install", "-q", "-r",
                                os.path.join(root, "requirements.txt")], timeout=600, cwd=root,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            except Exception:
                pass
        log("Restarting ORION…")
        self._relaunch(root, py)
        return root

    @staticmethod
    def _python():
        try:
            with open(os.path.join(Updater.source_root(), "python_path.txt"), "r", encoding="utf-8") as fh:
                p = fh.read().strip()
            if os.path.exists(p):
                return p
        except Exception:
            pass
        if not FROZEN:
            d = os.path.dirname(sys.executable)
            w = os.path.join(d, "pythonw.exe")
            return w if os.path.exists(w) else sys.executable
        for v in ("314", "313", "312", "311", "310"):
            for base in (r"%LOCALAPPDATA%\Programs\Python\Python" + v, r"%LOCALAPPDATA%\Python\pythoncore-" + v[0] + "." + v[1:] + "-64"):
                w = os.path.join(os.path.expandvars(base), "pythonw.exe")
                if os.path.exists(w):
                    return w
        return None

    @staticmethod
    def _relaunch(root, py):
        bat = os.path.join(root, "START_ORION.bat")
        if os.name == "nt" and os.path.exists(bat):
            subprocess.Popen(["cmd", "/c", bat], cwd=root, creationflags=0x08000000)
        elif py:
            subprocess.Popen([py, os.path.join(root, "ORION.pyw")], cwd=root,
                             creationflags=0x00000008 if os.name == "nt" else 0)


def pin_hash(pin):
    return hashlib.sha256(pin.encode()).hexdigest()[:12]

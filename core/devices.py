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
from .paths import APP_DIR, DATA_DIR, RES_DIR

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
                if self.path == "/api/transcribe":
                    self._json(200, {"text": remote.api.transcribe_bytes(raw)})
                    return
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    body = {}
                if self.path == "/api/send":
                    self._json(200, remote.api.ask(body.get("text", ""), source="phone"))
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
SYNC_FILES = {"memory.json": os.path.join(DATA_DIR, "memory.json"),
              "schedule.json": os.path.join(DATA_DIR, "schedule.json")}
STATE_PATH = os.path.join(DATA_DIR, "sync_state.json")


def _merge(name, local, remote):
    """Combine two devices' copies instead of one overwriting the other."""
    if name == "memory.json":
        facts = {f["text"].lower(): f for f in remote.get("facts", []) + local.get("facts", [])}
        hist = local.get("history", []) if len(local.get("history", [])) >= len(remote.get("history", [])) \
            else remote.get("history", [])
        return {"facts": list(facts.values())[-200:], "history": hist}
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
                files = {k: {"content": self._read(p)} for k, p in SYNC_FILES.items()}
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
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(txt)
                    changed_remote = True
                if txt != remote_txt:
                    push[name] = {"content": txt}
            if push:
                requests.patch(f"{self.API}/{self.sc['gist_id']}", headers=self._h(), timeout=20,
                               json={"files": push}).raise_for_status()
            state["last"] = time.strftime("%H:%M")
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f)
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

    def install(self):
        if not self.latest:
            raise RuntimeError("No update available.")
        h = {"Accept": "application/octet-stream"}
        tok = self.cfg.get("sync", {}).get("github_token")
        if tok:
            h["Authorization"] = f"token {tok}"
        r = requests.get(self.latest["api_url"], headers=h, timeout=300)
        r.raise_for_status()
        tmp = tempfile.mkdtemp(prefix="orion_up_")
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(tmp)
        src = tmp
        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            src = os.path.join(tmp, entries[0])
        backup = os.path.join(DATA_DIR, "backups", f"orion_{config_mod.VERSION}")
        for name in os.listdir(src):
            if name in KEEP:
                continue
            dst = os.path.join(APP_DIR, name)
            if os.path.exists(dst):
                os.makedirs(backup, exist_ok=True)
                shutil.move(dst, os.path.join(backup, name))
            shutil.move(os.path.join(src, name), dst)
        shutil.rmtree(tmp, ignore_errors=True)
        # restart
        py = sys.executable
        subprocess.Popen([py, os.path.join(APP_DIR, "ORION.pyw")], cwd=APP_DIR,
                         creationflags=0x00000008 if os.name == "nt" else 0)
        return True


def pin_hash(pin):
    return hashlib.sha256(pin.encode()).hexdigest()[:12]

"""One brain across devices.

When the gaming PC is on, the laptop's ORION talks straight to it (same conversation, same tools, same
memory). When the PC is off, the laptop carries on by itself, and everything said on either side is merged
back together next time they meet (and via the private Gist sync in between).
"""
import threading
import time

import requests


class Link:
    def __init__(self, cfg, memory, emit):
        self.cfg = cfg
        self.memory = memory
        self.emit = emit
        self.online = False
        self.pc_name = None
        self._last_pull = 0
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def lc(self):
        return self.cfg.setdefault("link", {"enabled": False, "addr": "", "pin": ""})

    @property
    def enabled(self):
        return bool(self.lc.get("enabled") and self.lc.get("addr"))

    def _url(self, path):
        a = self.lc["addr"].rstrip("/")
        if not a.startswith("http"):
            a = "http://" + a
        if a.count(":") < 2:
            a += ":7777"
        return a + path

    def _h(self):
        return {"X-PIN": str(self.lc.get("pin", ""))}

    def get(self, path, timeout=8):
        r = requests.get(self._url(path), headers=self._h(), timeout=timeout)
        r.raise_for_status()
        return r.json()

    def post(self, path, body, timeout=180):
        r = requests.post(self._url(path), headers=self._h(), json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def _loop(self):
        while True:
            if self.enabled:
                was = self.online
                try:
                    st = self.get("/api/state", 5)
                    self.online, self.pc_name = True, st.get("name", "ORION")
                except Exception:
                    self.online = False
                if self.online != was:
                    self.emit("link", online=self.online)
                    if self.online:
                        self.emit("toast", level="info", text="🔗 Linked to your gaming PC — same conversation everywhere.")
                        self.sync_history()
                elif self.online and time.time() - self._last_pull > 60:
                    self.sync_history()
            time.sleep(15)

    def sync_history(self):
        """Swap conversation turns both ways so either device can carry on."""
        self._last_pull = time.time()
        try:
            mine = self.memory.recent_full(60)
            theirs = self.post("/api/history", {"turns": mine}, 20).get("turns", [])
            n = self.memory.merge_turns(theirs)
            if n:
                self.emit("history_merged", count=n)
            return n
        except Exception:
            return 0

    def ask(self, text):
        """Run a request on the PC (its tools, its brain). Returns (reply, tier, model)."""
        r = self.post("/api/send", {"text": text, "source": "laptop"})
        return r.get("reply", ""), r.get("tier") or "cloud", (r.get("model") or "") + " · via PC"

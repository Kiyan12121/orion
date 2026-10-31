"""Long-term facts + recent conversation, saved to data/memory.json."""
import json
import os
import threading
import time

from .paths import DATA_DIR

MEM_PATH = os.path.join(DATA_DIR, "memory.json")
MAX_FACTS = 200
MAX_HISTORY = 30


class Memory:
    def __init__(self):
        self._lock = threading.Lock()
        self.facts = []
        self.history = []
        if os.path.exists(MEM_PATH):
            try:
                with open(MEM_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.facts = d.get("facts", [])
                self.history = d.get("history", [])
            except Exception:
                pass

    def _save(self):
        with open(MEM_PATH, "w", encoding="utf-8") as f:
            json.dump({"facts": self.facts, "history": self.history}, f, indent=2)

    def add_fact(self, fact):
        fact = fact.strip()
        if not fact:
            return False
        with self._lock:
            if fact.lower() not in (x["text"].lower() for x in self.facts):
                self.facts.append({"text": fact, "t": time.strftime("%Y-%m-%d")})
                self.facts = self.facts[-MAX_FACTS:]
                self._save()
        return True

    def forget(self, keyword):
        kw = keyword.lower().strip()
        with self._lock:
            before = len(self.facts)
            self.facts = [x for x in self.facts if kw not in x["text"].lower()]
            self._save()
            return before - len(self.facts)

    def facts_text(self):
        if not self.facts:
            return "(nothing saved yet)"
        return "\n".join(f"- {x['text']}" for x in self.facts[-60:])

    def add_turn(self, role, content):
        with self._lock:
            self.history.append({"role": role, "content": content})
            self.history = self.history[-MAX_HISTORY:]
            self._save()

    def recent(self, n=12):
        return list(self.history[-n:])

    def clear_history(self):
        with self._lock:
            self.history = []
            self._save()

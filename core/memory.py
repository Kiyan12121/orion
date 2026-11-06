"""Long-term memory + recent conversation, saved to data/memory.json.

v3: facts have a category (person / project / preference / goal / fact) and ORION picks the ones that
matter for each message, so it can remember hundreds of things without stuffing every prompt.
It also learns on its own: every few messages a background pass pulls durable facts out of the chat.
"""
import json
import os
import re
import threading
import time

from .paths import DATA_DIR

MEM_PATH = os.path.join(DATA_DIR, "memory.json")
MAX_FACTS = 600
MAX_HISTORY = 60


def _device():
    import platform
    import socket
    try:
        name = socket.gethostname()
    except Exception:
        name = "pc"
    try:
        import psutil
        ram = psutil.virtual_memory().total / 2**30
        kind = "laptop" if (psutil.sensors_battery() is not None) else "pc"
    except Exception:
        kind = "pc"
    return f"{kind}:{name}"[:40]


DEVICE = _device()
CATS = ("person", "project", "preference", "goal", "fact")
STOP = set("the a an and or but to of in on at for with is are was were be been it this that my me i you "
           "your our we they them he she his her do does did can could would should will just so very "
           "about from as by have has had not no yes what when where who how why which there their".split())


def _words(t):
    return {w for w in re.findall(r"[a-z0-9']{3,}", t.lower()) if w not in STOP}


class Memory:
    def __init__(self):
        self._lock = threading.Lock()
        self.facts = []
        self.history = []
        self._turns_since_learn = 0
        if os.path.exists(MEM_PATH):
            try:
                with open(MEM_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.facts = d.get("facts", [])
                self.history = d.get("history", [])
            except Exception:
                pass
        for x in self.facts:
            x.setdefault("cat", "fact")
            x.setdefault("uses", 0)

    def _save(self):
        from .safeio import write_json
        write_json(MEM_PATH, {"facts": list(self.facts), "history": list(self.history)})

    # ------------------------------------------------------------------ facts
    def add_fact(self, fact, cat="fact", source="you"):
        fact = re.sub(r"\s+", " ", (fact or "")).strip()
        if not fact or len(fact) > 300:
            return False
        cat = cat if cat in CATS else "fact"
        with self._lock:
            low = fact.lower()
            for x in self.facts:
                if x["text"].lower() == low:
                    return True
                # same subject, newer info -> replace (e.g. "favourite game is X" -> "... is Y")
                a, b = _words(x["text"]), _words(fact)
                if a and b and len(a & b) / max(len(a | b), 1) > 0.75:
                    x.update(text=fact, t=time.strftime("%Y-%m-%d"), cat=cat)
                    self._save()
                    return True
            self.facts.append({"text": fact, "t": time.strftime("%Y-%m-%d"), "cat": cat, "uses": 0, "src": source})
            if len(self.facts) > MAX_FACTS:                        # drop the least-used old ones
                self.facts.sort(key=lambda x: (x.get("uses", 0), x["t"]))
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

    def remove(self, index):
        with self._lock:
            if 0 <= index < len(self.facts):
                self.facts.pop(index)
                self._save()
                return True
        return False

    def relevant(self, query, n=28):
        """The facts that matter for this message: anything sharing words with it, plus the newest."""
        q = _words(query or "")
        scored = []
        for i, x in enumerate(self.facts):
            overlap = len(q & _words(x["text"]))
            boost = 0.6 if x.get("cat") in ("preference", "person") else 0
            scored.append((overlap * 2 + boost + i / max(len(self.facts), 1), i))
        top = [i for s, i in sorted(scored, reverse=True)[:n]]
        for i in top:
            if q & _words(self.facts[i]["text"]):
                self.facts[i]["uses"] = self.facts[i].get("uses", 0) + 1
        return [self.facts[i] for i in sorted(top)]

    def facts_text(self, query=""):
        if not self.facts:
            return "(nothing saved yet)"
        return "\n".join(f"- [{x.get('cat', 'fact')}] {x['text']}" for x in self.relevant(query))

    # ------------------------------------------------------------------ conversation
    def add_turn(self, role, content, device=None):
        import socket
        import uuid as _u
        with self._lock:
            self.history.append({"role": role, "content": content, "id": _u.uuid4().hex[:10], "t": time.time(),
                                 "dev": device or DEVICE})
            self.history = self.history[-MAX_HISTORY:]
            if role == "user":
                self._turns_since_learn += 1
            self._save()
        try:
            from .brain6 import archive
            archive(role, content, device or DEVICE)
        except Exception:
            pass

    def recent(self, n=12):
        """Plain role/content turns for the AI (device tags stripped)."""
        return [{"role": h["role"], "content": h["content"]} for h in self.history[-n:]]

    def recent_full(self, n=40):
        return list(self.history[-n:])

    def merge_turns(self, turns):
        """Turns from another device (laptop/phone/PC) join this conversation in time order."""
        with self._lock:
            have = {h.get("id") for h in self.history if h.get("id")}
            new = [t for t in turns if t.get("id") and t["id"] not in have and t.get("role") in ("user", "assistant")]
            if not new:
                return 0
            self.history = sorted(self.history + new, key=lambda h: h.get("t", 0))[-MAX_HISTORY:]
            self._save()
            return len(new)

    def clear_history(self):
        with self._lock:
            self.history = []
            self._save()

    # ------------------------------------------------------------------ learning by itself
    def due_for_learning(self, every=6):
        return self._turns_since_learn >= every

    def learn_from_chat(self, brain):
        """Ask the AI to pull durable facts about the user out of the recent chat."""
        self._turns_since_learn = 0
        chat = "\n".join(f"{m['role'].upper()}: {str(m['content'])[:400]}" for m in self.history[-12:])
        known = "\n".join("- " + x["text"] for x in self.facts[-40:])
        system = ("You maintain a personal assistant's long-term memory about its user. From the chat, extract "
                  "ONLY durable facts the user stated about themselves, their people, projects, preferences or "
                  "goals — things still true next month. Skip one-off requests, moods, and anything already known. "
                  "Never store passwords, keys, bank details or addresses. Reply with JSON only: "
                  '{"facts":[{"text":"...","cat":"person|project|preference|goal|fact"}]} (empty list if none).')
        try:
            out = brain.quick(system, f"Already known:\n{known}\n\nChat:\n{chat}", tier="fast", max_steps=1)
            m = re.search(r"\{.*\}", out or "", re.S)
            new = json.loads(m.group(0)).get("facts", []) if m else []
        except Exception:
            return 0
        n = 0
        for f in new[:6]:
            t = str(f.get("text", ""))
            if re.search(r"password|api key|gsk_|card number|sort code|\b\d{6,}\b", t, re.I):
                continue
            if self.add_fact(t, f.get("cat", "fact"), source="learned"):
                n += 1
        return n

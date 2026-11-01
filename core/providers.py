"""AI brains. Every provider speaks the OpenAI-style API, so one class covers Groq, Cerebras,
OpenRouter, Gemini and local Ollama.

Speed tricks in here:
- streaming: words reach the screen (and the voice) as they're generated
- per-model cooldowns: if one model hits its limit we jump straight to the next instead of waiting
- no "are you alive?" ping before each request
"""
import datetime
import json
import re
import os
import threading
import time

import requests

from .paths import DATA_DIR

USAGE_PATH = os.path.join(DATA_DIR, "usage.json")
_usage_lock = threading.Lock()


def _short_error(code, text, model):
    low = text.lower()
    if code == 429:
        return "free allowance used up for now"
    if code in (401, 403):
        return "API key rejected"
    if "not found" in low or "does not exist" in low or "decommission" in low:
        return f"model '{model.split('/')[-1]}' isn't available"
    return f"error {code}"


class ProviderError(Exception):
    pass


class AuthError(ProviderError):
    pass


class Cancelled(Exception):
    pass


def _today():
    return datetime.date.today().isoformat()


def _load_usage():
    try:
        with open(USAGE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == _today():
            return d
    except Exception:
        pass
    return {"date": _today(), "providers": {}}


USAGE = _load_usage()


def record_usage(pid, tokens):
    with _usage_lock:
        if USAGE["date"] != _today():
            USAGE.clear()
            USAGE.update({"date": _today(), "providers": {}})
        u = USAGE["providers"].setdefault(pid, {"requests": 0, "tokens": 0})
        u["requests"] += 1
        u["tokens"] += int(tokens)
        try:
            with open(USAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(USAGE, f)
        except Exception:
            pass


# best -> worst chat models for an i5 / 16 GB PC (the GT 710 can't help, so it's all CPU + RAM)
LOCAL_RANK = ["qwen2.5:7b", "llama3.1:8b", "qwen3:8b", "gemma3:4b", "qwen3:4b", "qwen2.5:3b", "llama3.2:3b",
              "phi3:mini", "phi4-mini", "gemma2:2b", "qwen2.5:1.5b", "qwen3:1.7b", "llama3.2:1b", "qwen2.5:0.5b"]


def _ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / 2**30
    except Exception:
        return 8


def recommended_local():
    """What 2_INSTALL_LOCAL_BRAIN.bat / Health check suggests downloading for this machine."""
    r = _ram_gb()
    return "qwen2.5:3b" if r >= 7 else "qwen2.5:1.5b"     # 7b is too slow on an older CPU


def best_local(base_url="http://localhost:11434/v1"):
    """The smartest installed Ollama model this machine can comfortably run."""
    try:
        tags = requests.get(base_url.replace("/v1", "") + "/api/tags", timeout=3).json().get("models", [])
    except Exception:
        return None
    names = [m["name"] for m in tags if not re.search(r"embed|moondream|llava|vision", m["name"])]
    if not names:
        return None
    sizes = {m["name"]: m.get("size", 0) / 2**30 for m in tags}
    budget = _ram_gb() * 0.55                     # leave room for Windows + a game

    def rank(n):
        base = n if ":" in n else n + ":latest"
        for i, r in enumerate(LOCAL_RANK):
            if base.startswith(r):
                return i
        return len(LOCAL_RANK)
    fits = [n for n in names if sizes.get(n, 0) <= budget] or names
    return sorted(fits, key=rank)[0]


class Provider:
    def __init__(self, spec, local=False):
        self.id = spec.get("id", "local" if local else spec.get("label", "?").lower())
        self.label = spec.get("label", self.id)
        self.base_url = spec["base_url"].rstrip("/")
        self.api_key = spec.get("api_key", "") if not local else "ollama"
        self.local = local
        if local:
            want = spec.get("model", "auto") or "auto"
            if want == "auto":
                want = best_local(self.base_url) or recommended_local()
            self.fast = self.smart = [want]
        else:
            self.fast = list(spec.get("fast", []))
            self.smart = list(spec.get("smart", []))
        self.stt = spec.get("stt")
        self.vision = list(spec.get("vision", [])) if not local else ([spec["vision_model"]] if spec.get("vision_model") else [])
        self.timeout = spec.get("timeout", 180 if local else 60)
        self.cooldown = {}          # model -> unix time it's usable again
        self.limits = {}            # model -> rate-limit headers seen
        self.dead_models = set()    # retired / unsupported
        self.last_model = None
        self._ping = (0, False)
        self.auth_failed = False

    # ------------------------------------------------------------------ status
    @property
    def configured(self):
        return self.local or (bool(self.api_key) and not self.auth_failed)

    def ready(self):
        if not self.configured:
            return False
        if self.local:
            return self.ping()
        now = time.time()
        return any(m not in self.dead_models and self.cooldown.get(m, 0) <= now
                   for m in self.fast + self.smart)

    def ping(self):
        """Only used for the local brain + status lights; cached 20s."""
        t, ok = self._ping
        if time.time() - t < 20:
            return ok
        try:
            ok = requests.get(f"{self.base_url}/models", timeout=1.2 if self.local else 4,
                              headers=self._headers()).status_code == 200
        except Exception:
            ok = False
        self._ping = (time.time(), ok)
        return ok

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _note_limits(self, model, headers):
        def g(name):
            v = headers.get(name)
            try:
                return int(float(v)) if v is not None else None
            except ValueError:
                return None
        lim = {"req_left": g("x-ratelimit-remaining-requests"), "req_limit": g("x-ratelimit-limit-requests"),
               "tok_left": g("x-ratelimit-remaining-tokens"), "tok_limit": g("x-ratelimit-limit-tokens"),
               "t": time.time()}
        if any(v is not None for k, v in lim.items() if k != "t"):
            self.limits[model] = lim

    def _cool(self, model, headers, default=60):
        wait = default
        ra = headers.get("retry-after")
        try:
            if ra:
                wait = min(float(ra), 3600)
        except ValueError:
            pass
        self.cooldown[model] = time.time() + max(5, wait)

    # ------------------------------------------------------------------ chat
    def chat(self, messages, tools=None, tier="smart", on_delta=None, cancel=None, models=None):
        """Returns {"content": str, "tool_calls": [...], "model": str}."""
        order = list(models) if models else (self.smart + self.fast) if tier == "smart" else (self.fast + self.smart)
        seen, models = set(), []
        for m in order:
            if m not in seen:
                seen.add(m)
                models.append(m)
        now = time.time()
        usable = [m for m in models if m not in self.dead_models and self.cooldown.get(m, 0) <= now]
        if not usable:
            if all(m in self.dead_models for m in models):
                raise ProviderError(f"{self.label}: none of these models exist any more ({', '.join(models[:2])})")
            raise ProviderError(f"{self.label}: free allowance used up for now — resets soon")

        last_err = f"{self.label}: no usable model"
        for model in usable:
            if cancel and cancel.is_set():
                raise Cancelled()
            body = {"model": model, "messages": messages, "temperature": 0.5,
                    "stream": bool(on_delta)}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
            try:
                r = requests.post(f"{self.base_url}/chat/completions", json=body,
                                  headers=self._headers(), timeout=self.timeout, stream=bool(on_delta))
            except requests.RequestException as e:
                self._ping = (time.time(), False)
                raise ProviderError(f"{self.label} unreachable ({type(e).__name__})")

            self._note_limits(model, r.headers)
            if r.status_code == 200:
                try:
                    out = self._read_stream(r, on_delta, cancel) if on_delta else self._read_plain(r)
                except Cancelled:
                    r.close()
                    raise
                except (ValueError, KeyError, requests.RequestException) as e:
                    last_err = f"{self.label}/{model}: bad response ({e})"
                    continue
                out["model"] = model
                self.last_model = model
                est = out.pop("_tokens", None) or (len(json.dumps(messages)) + len(json.dumps(tools or []))
                                                   + len(out["content"])) // 4
                record_usage(self.id, est)
                return out

            text = r.text[:300] if not on_delta else r.content[:300].decode("utf-8", "ignore")
            last_err = f"{self.label}: {_short_error(r.status_code, text, model)}"
            if r.status_code in (401, 403):
                self.auth_failed = True
                raise AuthError(f"{self.label} rejected the API key (re-paste it in Settings)")
            if r.status_code == 429:
                self._cool(model, r.headers)
                continue                       # every model has its own limit -> try the next one
            if r.status_code == 404 and self.local and "not found" in text.lower():
                alt = self._installed_local()           # use whatever Ollama model IS installed
                if alt and alt not in self.fast:
                    self.fast = self.smart = [alt] + self.fast
                    return self.chat(messages, tools, tier, on_delta, cancel, models=[alt])
            if r.status_code in (400, 404, 422):
                low = text.lower()
                if "model" in low and ("not found" in low or "decommission" in low
                                       or "does not exist" in low or "not supported" in low):
                    self.dead_models.add(model)
                continue
            # 5xx: try next model
        raise ProviderError(last_err)

    def _installed_local(self):
        return best_local(self.base_url)

    @staticmethod
    def _read_plain(r):
        j = r.json()
        msg = j["choices"][0]["message"]
        u = j.get("usage") or {}
        return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [],
                "_tokens": u.get("total_tokens")}

    @staticmethod
    def _read_stream(r, on_delta, cancel):
        r.encoding = "utf-8"
        content, calls, tokens = [], {}, None
        for line in r.iter_lines(decode_unicode=True):
            if cancel and cancel.is_set():
                raise Cancelled()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            j = json.loads(data)
            if j.get("error"):
                raise ValueError(str(j["error"])[:200])
            u = j.get("usage") or (j.get("x_groq") or {}).get("usage")
            if u:
                tokens = u.get("total_tokens")
            for ch in j.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content.append(d["content"])
                    on_delta(d["content"])
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", len(calls))
                    slot = calls.setdefault(i, {"id": "", "type": "function",
                                                "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name") and not slot["function"]["name"]:
                        slot["function"]["name"] = f["name"]
                    a = f.get("arguments")
                    if isinstance(a, dict):
                        slot["function"]["arguments"] = json.dumps(a)
                    elif a:
                        slot["function"]["arguments"] += a
        tool_calls = [calls[k] for k in sorted(calls)]
        for n, c in enumerate(tool_calls):
            c["id"] = c["id"] or f"call_{n}"
        return {"content": "".join(content), "tool_calls": tool_calls, "_tokens": tokens}

    # ------------------------------------------------------------------ speech to text
    def transcribe(self, wav_bytes, filename="speech.wav", mime="audio/wav"):
        last = None
        for model in [self.stt, "whisper-large-v3"]:
            if not model:
                continue
            r = requests.post(f"{self.base_url}/audio/transcriptions",
                              headers={"Authorization": f"Bearer {self.api_key}"},
                              files={"file": (filename, wav_bytes, mime)},
                              data={"model": model, "language": "en"}, timeout=60)
            if r.status_code == 200:
                return r.json().get("text", "").strip()
            last = f"HTTP {r.status_code} {r.text[:150]}"
        raise ProviderError(f"Transcription failed: {last}")

    # ------------------------------------------------------------------ HUD meter
    def meter(self):
        u = USAGE["providers"].get(self.id, {"requests": 0, "tokens": 0})
        model = self.last_model or (self.smart[0] if self.smart else None)
        lim = self.limits.get(model) or {}
        now = time.time()
        resting = [m for m in self.fast + self.smart if self.cooldown.get(m, 0) > now]
        return {"id": self.id, "label": self.label, "model": model, "configured": self.configured,
                "requests": u["requests"], "tokens": u["tokens"],
                "req_left": lim.get("req_left"), "req_limit": lim.get("req_limit"),
                "tok_left": lim.get("tok_left"), "tok_limit": lim.get("tok_limit"),
                "resting": len(resting), "models": len(set(self.fast + self.smart))}

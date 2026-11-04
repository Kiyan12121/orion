"""Settings: loaded from config.json, missing keys filled from defaults."""
import copy
import json
import os

from .paths import CONFIG_PATH

VERSION = "5.2.0"

# Any OpenAI-compatible service can be added here. Each has its OWN free allowance,
# so ORION spreads work across all providers that have a key.
# "fast" models handle quick commands; "smart" models handle real thinking.
# Model names change over time — if one is retired ORION just skips to the next.
DEFAULT_PROVIDERS = [
    {"id": "groq", "label": "Groq", "base_url": "https://api.groq.com/openai/v1", "api_key": "",
     # every model has its OWN free allowance, so more models = more free usage per day
     "fast": ["openai/gpt-oss-20b", "meta-llama/llama-4-scout-17b-16e-instruct", "qwen/qwen3-32b"],
     "smart": ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "qwen/qwen3-32b", "llama-3.3-70b-versatile"],
     "stt": "whisper-large-v3-turbo", "key_url": "https://console.groq.com/keys",
     "vision": ["meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"]},
    {"id": "cerebras", "label": "Cerebras", "base_url": "https://api.cerebras.ai/v1", "api_key": "",
     "fast": ["llama3.1-8b"], "smart": ["gpt-oss-120b"],
     "key_url": "https://cloud.cerebras.ai"},
    {"id": "openrouter", "label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "api_key": "",
     "fast": ["openai/gpt-oss-20b:free", "openrouter/free"], "smart": ["openai/gpt-oss-120b:free", "openrouter/free"],
     # openrouter/free = OpenRouter's router: auto-picks a free model that can handle images
     "vision": ["openrouter/free", "google/gemma-3-27b-it:free", "meta-llama/llama-4-scout:free"],
     "key_url": "https://openrouter.ai/keys"},
    {"id": "gemini", "label": "Gemini", "api_key": "",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "fast": ["gemini-2.5-flash-lite"], "smart": ["gemini-2.5-flash"],
     "vision": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
     "key_url": "https://aistudio.google.com/apikey"},
]

DEFAULTS = {
    "assistant_name": "ORION",
    "owner_name": "Kiyan",          # used when ORION speaks to your friends
    "user_title": "sir",
    "brain": "auto",            # auto = cloud pool -> local | cloud | local
    "theme": "standby",         # standby | serious | stealth | executive | hacker
    "providers": DEFAULT_PROVIDERS,
    "local": {"label": "Ollama", "base_url": "http://localhost:11434/v1",
              "model": "auto", "vision_model": "", "timeout": 180},
    "voice": {
        "speak_replies": True,
        "engine": "neural",                 # neural (natural, needs internet) | offline
        "neural_voice": "en-GB-SoniaNeural",
        "neural_rate": "+6%",
        "offline_rate": 180,
    },
    "safe_mode": False,          # True = ask before risky actions. Blocklist + backups always on.
    "fullscreen": True,
    "visuals": "auto",           # auto (lite on <=6GB RAM) | full | lite
    "skip_boot": False,
    "max_steps": 12,
    "autopilot_steps": 40,
    "daily_briefing": True,
    "briefing_time": "07:30",
    "hotkey": "ctrl+alt+space",     # global push-to-talk, works inside games
    "root": {
        "watch": True,               # notice new Root DMs in the background (only when Root is open)
        "gaming_autoreply": True,    # answer DMs while you're in a game
        "gaming_reply": "instant",   # instant = flick to Root and send (≈1s) | queue = send after the game
        "poll_seconds": 25,
    },
    "notify": {"ntfy_topic": ""},   # phone push notifications (set up in Devices)
    "remote": {"enabled": False, "port": 7777, "pin": ""},
    "sync": {"github_token": "", "gist_id": ""},
    "update": {"repo": "Kiyan12121/orion", "check": True},
    "wake": {"enabled": False, "model": "hey_jarvis", "sensitivity": 0.5},
    "voice_id": {"enabled": False, "threshold": 0.72},
    "gaming": {
        "auto": True,
        "games": ["RobloxPlayerBeta.exe", "RobloxPlayer.exe", "Minecraft.Windows.exe", "javaw.exe",
                  "FortniteClient-Win64-Shipping.exe", "VALORANT-Win64-Shipping.exe", "cs2.exe",
                  "RocketLeague.exe", "FiveM.exe", "GTA5.exe"],
        "close_apps": [],            # e.g. ["OneDrive.exe"] — closed when a game starts
        "high_performance": True,
    },
    "retry_when_out": True,       # every brain out of allowance -> queue the request and retry later
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
}

NEURAL_VOICES = [
    ("en-GB-SoniaNeural", "Sonia — British, polished"),
    ("en-GB-LibbyNeural", "Libby — British, warm"),
    ("en-GB-MaisieNeural", "Maisie — British, young"),
    ("en-US-AvaNeural", "Ava — American, natural"),
    ("en-US-JennyNeural", "Jenny — American, friendly"),
    ("en-AU-NatashaNeural", "Natasha — Australian"),
    ("en-IE-EmilyNeural", "Emily — Irish"),
]


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _migrate(data):
    """Bring a v1.0 config.json forward."""
    prov = data.get("providers")
    if isinstance(prov, dict):                       # v1.0 had {"cloud": {...}, "local": {...}}
        key = prov.get("cloud", {}).get("api_key", "")
        lm = (prov.get("local", {}).get("models") or ["qwen2.5:3b"])[0]
        new = copy.deepcopy(DEFAULT_PROVIDERS)
        new[0]["api_key"] = key
        data["providers"] = new
        data.setdefault("local", {})["model"] = lm
    if "mode" in data and "brain" not in data:
        data["brain"] = data.pop("mode")
    data.pop("mode", None)
    # make sure every default provider exists (new ones added in updates) and has new fields
    if isinstance(data.get("providers"), list):
        defaults = {p["id"]: p for p in DEFAULT_PROVIDERS}
        have = {p.get("id") for p in data["providers"]}
        for p in data["providers"]:
            for k, v in defaults.get(p.get("id"), {}).items():
                p.setdefault(k, copy.deepcopy(v))
            if p.get("id") == "groq":            # 2.0.2: retired models out, extra free models in
                for k in ("fast", "smart"):
                    lst = [m for m in p.get(k, []) if m != "llama-3.1-8b-instant"]
                    for m in defaults["groq"][k]:
                        if m not in lst:
                            lst.append(m)
                    p[k] = lst
            if p.get("id") == "openrouter":      # 2.0.1: use OpenRouter's free auto-router (handles images)
                for k in ("vision", "fast", "smart"):
                    lst = p.setdefault(k, [])
                    if "openrouter/free" not in lst:
                        if k == "vision":
                            lst.insert(0, "openrouter/free")
                        else:
                            lst.append("openrouter/free")
        for p in DEFAULT_PROVIDERS:
            if p["id"] not in have:
                data["providers"].append(copy.deepcopy(p))
    loc = data.get("local", {})
    if loc.get("model") in ("qwen2.5:3b", "", None) and not data.get("_v3"):
        loc["model"] = "auto"                 # 3.0: pick the best installed model automatically
    data["_v3"] = True
    v = data.get("voice", {})
    for old in ("rate", "prefer_voice", "stt_model"):
        v.pop(old, None)
    return data


def load():
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    cfg = _merge(DEFAULTS, _migrate(data))
    save(cfg)
    return cfg


def save(cfg):
    from .safeio import write_json
    write_json(CONFIG_PATH, cfg, indent=2)

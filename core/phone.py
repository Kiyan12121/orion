"""Things ORION (on the PC) can make your PHONE do. Actions are queued here and the phone app collects and
runs them next time it checks in (every ~10 seconds while open). If the app is closed, a push notification
tells you to open it."""
import re
import threading
import time
import uuid

from .tools import CTX, tool

_lock = threading.Lock()
QUEUE = []          # pending actions for the phone
LAST_SEEN = [0.0]   # when the phone last checked in


def push(kind, **data):
    a = {"id": uuid.uuid4().hex[:8], "kind": kind, "t": time.time(), **data}
    with _lock:
        QUEUE.append(a)
        del QUEUE[:-30]
    online = time.time() - LAST_SEEN[0] < 60
    if not online:
        notify = CTX.get("push_phone")
        if notify:
            notify({"alarm": "⏰ Open ORION on your phone to set the alarm.",
                    "timer": "⏱ Open ORION on your phone to start the timer.",
                    "call": "📞 ORION is calling — open the app to answer.",
                    "open": "📱 Open ORION on your phone to finish that.",
                    "torch": "🔦 Open ORION on your phone to use the torch.",
                    "ring": "📢 ORION is trying to find your phone!",
                    "clip": "📋 ORION sent you something — open the app to copy it.",
                    "file": "📁 ORION sent you a file — open the app to save it."}.get(kind, "Open ORION on your phone."))
    return a, online


URGENT = ("call", "ring")      # the phone's background link service wakes the phone for these


def wake():
    """Called by the phone's always-on background service (~every 20s, even with the app closed).
    Hands over calls / find-my-phone rings so the phone can ring right away."""
    LAST_SEEN[0] = time.time()
    with _lock:
        out = [a for a in QUEUE if a["kind"] in URGENT]
        QUEUE[:] = [a for a in QUEUE if a["kind"] not in URGENT]
    return out


def take():
    """Called by the phone when it checks in."""
    LAST_SEEN[0] = time.time()
    with _lock:
        out = list(QUEUE)
        QUEUE.clear()
    return out


def _hm(s):
    s = str(s).strip().lower().replace(".", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        raise ValueError("time must look like 07:30 or 7am")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ValueError("invalid time")
    return h, mi


def _say(online, what):
    return what + ("" if online else " (your phone app is closed — I've sent a notification to open it)")


@tool("Set an ALARM on the user's PHONE (their real phone alarm clock).",
      {"time": ("string", "Alarm time, e.g. '07:00' or '6:45am'", True), "label": ("string", "Alarm label", False)})
def phone_alarm(time, label="ORION"):
    h, m = _hm(time)
    _, online = push("alarm", hour=h, minute=m, message=label or "ORION")
    return _say(online, f"Alarm for {h:02d}:{m:02d} sent to your phone.")


@tool("Start a TIMER on the user's PHONE.",
      {"minutes": ("number", "Length in minutes", True), "label": ("string", "Label", False)})
def phone_timer(minutes, label="ORION"):
    secs = max(1, int(float(minutes) * 60))
    _, online = push("timer", seconds=secs, message=label or "ORION")
    return _say(online, f"{minutes:g}-minute timer sent to your phone.")


@tool("Open an app on the user's PHONE (e.g. Spotify, Snapchat, YouTube).",
      {"name": ("string", "App name", True)})
def phone_open_app(name):
    _, online = push("open", name=name)
    return _say(online, f"Opening {name} on your phone.")


@tool("Make ORION CALL the user's phone (full-screen incoming call, then a voice conversation). "
      "Use for 'call me', 'ring me when…', wake-up calls. Optionally say why.",
      {"reason": ("string", "What the call is about — ORION opens with this", False)})
def phone_call(reason=""):
    _, online = push("call", reason=reason or "")
    return _say(online, "Calling your phone now.")


@tool("Turn the user's PHONE torch (flashlight) on or off.", {"on": ("boolean", "True = on", True)})
def phone_torch(on):
    _, online = push("torch", on=bool(on))
    return _say(online, "Torch " + ("on." if on else "off."))


@tool("FIND MY PHONE: make the user's phone ring loudly (even on silent) so they can find it.")
def find_my_phone():
    _, online = push("ring")
    return _say(online, "Ringing your phone now.")


@tool("Send text or a link to the user's PHONE clipboard (they tap to copy it).",
      {"text": ("string", "What to send", True)})
def phone_send_text(text):
    _, online = push("clip", text=str(text)[:5000])
    return _say(online, "Sent to your phone.")


@tool("Send a FILE from this PC to the user's phone.", {"path": ("string", "Full path of the file", True)})
def send_file_to_phone(path):
    import os
    import shutil
    from .paths import DATA_DIR
    path = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
    if not os.path.isfile(path):
        return f"ERROR: no file at {path}"
    if os.path.getsize(path) > 200 * 2**20:
        return "ERROR: that file is over 200 MB — too big to send."
    out = os.path.join(DATA_DIR, "outbox")
    os.makedirs(out, exist_ok=True)
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(path))
    shutil.copy2(path, os.path.join(out, name))
    _, online = push("file", name=name, size=os.path.getsize(path))
    return _say(online, f"Sending {name} to your phone.")

"""7.1: one shared, cached list of running process names.
Before this, the game watcher, stream watcher, automations and focus mode each walked every process on the PC
on their own timers. Now they share one snapshot that's at most a few seconds old — a lot less CPU on an i5-2400."""
import threading
import time

try:
    import psutil
except Exception:
    psutil = None

_lock = threading.Lock()
_snap = {"t": 0.0, "names": frozenset(), "raw": {}}
MAX_AGE = 4.0


def _refresh():
    names, raw = set(), {}
    if psutil is not None:
        for p in psutil.process_iter(["name"]):
            try:
                n = p.info["name"] or ""
            except Exception:
                continue
            if n:
                low = n.lower()
                names.add(low)
                raw.setdefault(low, n)
    _snap.update(t=time.monotonic(), names=frozenset(names), raw=raw)


def names(max_age=MAX_AGE):
    """Lower-case process names (with .exe), e.g. {'robloxplayerbeta.exe', 'obs64.exe'}."""
    with _lock:
        if time.monotonic() - _snap["t"] > max_age:
            _refresh()
        return _snap["names"]


def first(wanted, max_age=MAX_AGE):
    """The original-case name of the first running process whose lower-case name is in `wanted`, or None."""
    n = names(max_age)
    for w in wanted:
        if w in n:
            return _snap["raw"].get(w, w)
    return None


def busy():
    """True while ORION is in game mode: background watchers should back off."""
    try:
        from .tools import CTX
        g = CTX.get("gaming")
        return bool(g and g.active)
    except Exception:
        return False


def nap(seconds, busy_factor=3):
    """Sleep, but longer while gaming so ORION stays out of the way."""
    time.sleep(seconds * (busy_factor if busy() else 1))

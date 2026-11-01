"""Turns other apps down (Spotify, YouTube, games…) while ORION is listening, then puts them back.
Like a car stereo dipping for the sat-nav. Uses Windows' per-app volume mixer (pycaw)."""
import os
import threading

_lock = threading.Lock()
_saved = {}            # session key -> original volume


def _sessions():
    from pycaw.pycaw import AudioUtilities
    me = os.getpid()
    for s in AudioUtilities.GetAllSessions():
        try:
            if s.Process and s.Process.pid != me and s.SimpleAudioVolume:
                yield s
        except Exception:
            continue


def available():
    try:
        import pycaw.pycaw  # noqa: F401
        return os.name == "nt"
    except Exception:
        return False


def duck(level=0.15):
    """Lower every other app to `level` (0-1) of its current volume."""
    if not available():
        return 0
    n = 0
    with _lock:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            for s in _sessions():
                key = (s.Process.pid, s.Process.name())
                vol = s.SimpleAudioVolume
                cur = vol.GetMasterVolume()
                if key not in _saved:
                    _saved[key] = cur
                vol.SetMasterVolume(max(0.0, min(1.0, _saved[key] * level)), None)
                n += 1
        except Exception:
            pass
    return n


def restore():
    if not _saved:
        return
    with _lock:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            for s in _sessions():
                key = (s.Process.pid, s.Process.name())
                if key in _saved:
                    s.SimpleAudioVolume.SetMasterVolume(_saved[key], None)
        except Exception:
            pass
        _saved.clear()

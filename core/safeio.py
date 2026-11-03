"""Crash-proof JSON saving for Windows + OneDrive.

OneDrive (and antivirus) briefly lock files while they sync/scan, and two ORION threads can save the same
file at once. Either makes Windows say "Access is denied". This writes to a unique temp file under a lock,
retries the swap for a few seconds, and as a last resort writes the file directly — it never crashes ORION.
"""
import json
import logging
import os
import threading
import time

_locks = {}
_master = threading.Lock()
log = logging.getLogger("orion")


def _lock_for(path):
    with _master:
        return _locks.setdefault(os.path.abspath(path), threading.RLock())


def write_json(path, data, indent=1):
    with _lock_for(path):
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        except OSError as e:
            log.warning("save %s: couldn't write temp file (%s)", path, e)
            return _direct(path, data, indent)
        for i in range(25):                          # ~6 seconds of patience for OneDrive/antivirus
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:
                time.sleep(0.05 + i * 0.02)
            except OSError:
                break
        ok = _direct(path, data, indent)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ok


def _direct(path, data, indent):
    for i in range(10):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            return True
        except PermissionError:
            time.sleep(0.1 + i * 0.05)
        except OSError:
            break
    log.error("save %s failed — will try again next time", path)
    return False


def cleanup_temps(folder):
    """After a failed save, the newest data can be stuck in a *.tmp file. If it's valid and newer than the
    real file, put it back (nothing is lost); then remove leftover temp files."""
    try:
        for n in os.listdir(folder):
            if n.endswith(".tmp") and ".json" in n:
                p = os.path.join(folder, n)
                real = os.path.join(folder, n[:n.index(".json") + 5])
                try:
                    newer = not os.path.exists(real) or os.path.getmtime(p) > os.path.getmtime(real)
                    if newer and os.path.getsize(p) > 2:
                        with open(p, encoding="utf-8") as f:
                            data = json.load(f)
                        write_json(real, data)
                        log.warning("recovered %s from an interrupted save", real)
                except (OSError, ValueError):
                    pass
                if time.time() - os.path.getmtime(p) > 60:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
    except OSError:
        pass

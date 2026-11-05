"""TEMPORARY (CI only): runs ORION's real Local Intel code for Desford on the build machine (which has internet)
and prints the results to the build log so the map renderer can be tested with real data. Never fails the build."""
import base64, gzip, json, os, subprocess, sys, tempfile
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests", "psutil"], timeout=120)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, root)
    import types
    sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))
    from core import localintel as L
    from core.tools import CTX
    L.CACHE = os.path.join(tempfile.gettempdir(), "li.json")
    CTX["config"] = {}
    h = L.home()
    out = {"home": h}
    for k, fn in (("boundary", lambda: L.boundary(h)), ("map", lambda: L.local_map(h)), ("crime", lambda: L.crime(h)),
                  ("area", lambda: L.area(h)), ("flights", lambda: L.flights(h)), ("events", L.world_events)):
        try:
            out[k] = fn()
        except Exception as e:
            out[k] = {"error": repr(e)}
    blob = base64.b64encode(gzip.compress(json.dumps(out).encode())).decode()
    print("ORIONPREVIEW-BEGIN")
    for i in range(0, len(blob), 3000):
        print("ORIONP:" + blob[i:i + 3000])
    print("ORIONPREVIEW-END", len(blob))
except Exception as e:
    print("preview fetch skipped:", e)

"""Where everything lives — works both as a .pyw script and as a built .exe."""
import os
import sys

FROZEN = getattr(sys, "frozen", False)

# Folder the user sees (next to ORION.pyw or ORION.exe) — config + data live here
APP_DIR = (os.path.dirname(sys.executable) if FROZEN
           else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Folder bundled resources (the UI) are unpacked to
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)

DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
UI_PATH = os.path.join(RES_DIR, "ui", "index.html")
LOG_PATH = os.path.join(DATA_DIR, "orion.log")

PROJECTS_DIR = os.path.join(APP_DIR, "projects")
SKILLS_DIR = os.path.join(APP_DIR, "skills")

for _d in (DATA_DIR, PROJECTS_DIR, SKILLS_DIR):
    os.makedirs(_d, exist_ok=True)

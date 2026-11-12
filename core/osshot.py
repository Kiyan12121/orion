"""ORION OS screenshot helper: grabs the whole screen and saves a PNG to ~/Pictures/Screenshots. Prints the file path.
Also bound to the Print Screen key."""
import os
import sys
import time

import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # noqa: E402

d = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
os.makedirs(d, exist_ok=True)
w = Gdk.get_default_root_window()
pb = Gdk.pixbuf_get_from_window(w, 0, 0, w.get_width(), w.get_height())
if pb is None:
    sys.exit(1)
p = os.path.join(d, time.strftime("Screenshot %Y-%m-%d %H.%M.%S.png"))
pb.savev(p, "png", [], [])
print(p)

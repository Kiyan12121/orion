"""Root, read properly: through Windows' accessibility system (the same one screen readers use).

Instead of guessing pixel positions from screenshots, ORION reads the actual text of Root's window —
names, message previews, buttons and the message box — and presses the real controls. It only reads
the Direct Messages panel, so mass pings in server channels are never mistaken for DMs.
Nothing about Root itself is changed: it's exactly what a screen reader does.
"""
import os
import re
import time

from .paths import DATA_DIR

TREE_PATH = os.path.join(DATA_DIR, "root_tree.txt")
SKIP = re.compile(r"@everyone|@here", re.I)
TEXTY = {"TextControl", "HyperlinkControl", "ButtonControl", "ListItemControl", "GroupControl", "CustomControl",
         "DocumentControl", "EditControl", "ImageControl"}


def _auto():
    import uiautomation as auto
    return auto


def walk(hwnd, max_nodes=5000, max_depth=70):
    """Every element in Root's window: name, type, rectangle."""
    auto = _auto()
    root = auto.ControlFromHandle(hwnd)
    out = []

    def rec(ctrl, depth):
        if len(out) >= max_nodes or depth > max_depth:
            return
        try:
            r = ctrl.BoundingRectangle
            out.append({"name": (ctrl.Name or "").strip(), "type": ctrl.ControlTypeName, "depth": depth,
                        "l": r.left, "t": r.top, "r": r.right, "b": r.bottom, "id": ctrl.AutomationId or "",
                        "ctrl": ctrl})
        except Exception:
            return
        try:
            child = ctrl.GetFirstChildControl()
            while child is not None and len(out) < max_nodes:
                rec(child, depth + 1)
                child = child.GetNextSiblingControl()
        except Exception:
            pass
    rec(root, 0)
    return out


def dump(hwnd):
    """Diagnostic: write Root's accessibility tree to data/root_tree.txt (helps fix Root control)."""
    nodes = walk(hwnd)
    with open(TREE_PATH, "w", encoding="utf-8") as f:
        for n in nodes:
            f.write(f"{'  ' * min(n['depth'], 30)}{n['type']} '{n['name'][:90]}' id={n['id'][:40]} "
                    f"[{n['l']},{n['t']},{n['r']},{n['b']}]\n")
    named = sum(1 for n in nodes if n["name"])
    return TREE_PATH, len(nodes), named


def _panel_left(nodes, win):
    """Root docks Direct Messages on the right — find where that panel starts."""
    for key in ("Direct messages", "Direct Messages", "Find a conversation"):
        hit = [n for n in nodes if n["name"].startswith(key) and n["r"] > n["l"]]
        if hit:
            return min(h["l"] for h in hit) - 12
    return win["l"] + int((win["r"] - win["l"]) * 0.64)


def _rows(nodes, top, bottom, left):
    """Group text in the DM panel into visual rows (one conversation or one chat line each)."""
    items = [n for n in nodes if n["type"] in TEXTY and n["name"] and n["l"] >= left and top <= n["t"] < bottom
             and n["r"] - n["l"] > 2 and n["b"] - n["t"] > 2]
    items.sort(key=lambda n: (n["t"], n["l"]))
    rows = []
    for n in items:
        cy = (n["t"] + n["b"]) / 2
        if rows and abs(rows[-1]["cy"] - cy) < 14 or (rows and n["t"] < rows[-1]["b"] - 4 and n["depth"] > 3):
            row = rows[-1]
            if n["name"] not in row["texts"]:
                row["texts"].append(n["name"])
            row["b"] = max(row["b"], n["b"])
            row["nodes"].append(n)
        else:
            rows.append({"cy": cy, "t": n["t"], "b": n["b"], "texts": [n["name"]], "nodes": [n]})
    return rows


def read_panel(hwnd):
    """What's in the DM panel right now: the conversation list, or an open chat."""
    nodes = walk(hwnd)
    if not nodes:
        return None
    win = nodes[0]
    left = _panel_left(nodes, win)
    search = next((n for n in nodes if n["type"] == "EditControl" and "conversation" in n["name"].lower()), None)
    box = next((n for n in nodes if n["type"] == "EditControl" and n["name"].lower().startswith("message")
                and n["l"] >= left), None)
    if box and not (search and search["t"] > 0 and box["b"] < search["t"]):
        # an open chat: header (name) at the top of the panel, messages above the box
        header = next((n for n in nodes if n["l"] >= left and n["type"] in ("TextControl", "ButtonControl")
                       and n["name"] and n["t"] < win["t"] + (win["b"] - win["t"]) * 0.22
                       and n["name"].lower() not in ("direct messages", "back", "close")), None)
        with_who = header["name"] if header else re.sub(r"^message\s*@?", "", box["name"], flags=re.I).strip()
        rows = _rows(nodes, (header["b"] if header else win["t"]), box["t"], left)
        lines = [" ".join(r["texts"]) for r in rows if not SKIP.search(" ".join(r["texts"]))]
        return {"view": "conversation", "with": with_who, "lines": lines[-40:], "box": box, "_nodes": len(nodes)}
    top = search["b"] if search else win["t"] + (win["b"] - win["t"]) * 0.2
    rows = _rows(nodes, top + 4, win["b"], left)
    convs = []
    for r in rows:
        texts = [t for t in r["texts"] if len(t) > 0]
        if not texts or SKIP.search(" ".join(texts)):
            continue
        name = texts[0]
        rest = [t for t in texts[1:] if t != name]
        tm = next((t for t in rest if re.fullmatch(r"(\d+\s?[smhdw]|now|yesterday|\d{1,2}:\d{2}|\d+/\d+/\d+)", t, re.I)), "")
        preview = " ".join(t for t in rest if t != tm)
        if len(name) > 40 or name.lower() in ("direct messages", "find a conversation"):
            continue
        convs.append({"name": name, "preview": preview[:200], "time": tm,
                      "from_me": preview.lower().startswith("you:"),
                      "x": (r["nodes"][0]["l"] + r["nodes"][0]["r"]) // 2, "y": int(r["cy"])})
    return {"view": "list", "conversations": convs[:30], "search": search, "_nodes": len(nodes)}


def click_node(n):
    import pyautogui
    pyautogui.click((n["l"] + n["r"]) // 2, (n["t"] + n["b"]) // 2)


def open_dm(hwnd, name, back_fn=None):
    """Open a DM by name using the real list entry (search box if it's not visible)."""
    import pyautogui
    p = read_panel(hwnd)
    if not p:
        return False
    if p["view"] == "conversation":
        if name.lower() in (p.get("with") or "").lower():
            return True
        nodes = walk(hwnd)
        back = next((n for n in nodes if n["type"] == "ButtonControl" and n["name"].lower() in ("back", "<", "go back")), None)
        if back:
            click_node(back)
        elif back_fn:
            back_fn()
        time.sleep(0.5)
        p = read_panel(hwnd)
        if not p or p["view"] != "list":
            return False
    hit = next((c for c in p["conversations"] if c["name"].lower() == name.lower()), None) or \
        next((c for c in p["conversations"] if name.lower() in c["name"].lower()), None)
    if not hit and p.get("search"):
        click_node(p["search"])
        pyautogui.hotkey("ctrl", "a")
        pyautogui.write(name, interval=0.02)
        time.sleep(1.2)
        p = read_panel(hwnd)
        hit = p and next((c for c in p.get("conversations", []) if name.lower() in c["name"].lower()), None)
    if not hit:
        return False
    pyautogui.click(hit["x"], hit["y"])
    time.sleep(0.9)
    q = read_panel(hwnd)
    return bool(q and q["view"] == "conversation")


def send(hwnd, text, paste):
    """Type into the real message box, press Enter, then re-read the chat to PROVE it sent."""
    import pyautogui
    p = read_panel(hwnd)
    if not p or p["view"] != "conversation" or not p.get("box"):
        return False, "message box not found"
    click_node(p["box"])
    time.sleep(0.15)
    paste(text)
    pyautogui.press("enter")
    for _ in range(6):
        time.sleep(0.6)
        q = read_panel(hwnd)
        if q and q["view"] == "conversation":
            tail = " ".join(q["lines"][-6:]).lower()
            if text.lower()[:40] in tail:
                return True, "verified"
    return False, "sent but couldn't see it in the chat afterwards"

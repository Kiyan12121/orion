"""Vision: ORION can see. Screenshots (or a single app window, even when it's behind other windows)
are sent to a vision model, which answers questions or finds things to click.

Vision brains are tried in order: Groq (Llama 4 vision) -> Gemini -> OpenRouter -> local Ollama
(if a vision_model like 'moondream' is set) -> text-only OCR as a last resort.
"""
import base64
import io
import json
import platform
import re

from .tools import CTX, _need, _ocr_ready, pyautogui, pytesseract, tool

IS_WIN = platform.system() == "Windows"

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = ImageDraw = None

try:
    import psutil
except Exception:
    psutil = None


# ------------------------------------------------------------------ capturing
def screenshot():
    _need(pyautogui, "pyautogui")
    return pyautogui.screenshot()


def find_window(process_name=None, title_part=None):
    """Returns (hwnd, (left, top, right, bottom)) of the biggest visible window matching."""
    if not IS_WIN:
        return None
    import win32gui
    import win32process
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            return
        title = win32gui.GetWindowText(hwnd) or ""
        if title_part and title_part.lower() not in title.lower():
            return
        if process_name and psutil:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if psutil.Process(pid).name().lower() != process_name.lower():
                    return
            except Exception:
                return
        r = win32gui.GetWindowRect(hwnd)
        area = (r[2] - r[0]) * (r[3] - r[1])
        if area > 40000 or win32gui.IsIconic(hwnd):
            found.append((area, hwnd, r))

    win32gui.EnumWindows(cb, None)
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1], found[0][2]


def capture_window(hwnd):
    """Captures a window's contents even if it's behind other windows (not if minimised —
    those are restored without stealing focus first)."""
    import win32con
    import win32gui
    import win32ui
    import ctypes
    was_min = win32gui.IsIconic(hwnd)
    if was_min:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        import time
        time.sleep(0.6)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)   # 2 = include GPU-rendered content
    info = bmp.GetInfo()
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    if was_min:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWMINNOACTIVE)
    return img, (l, t, r, b)


# ------------------------------------------------------------------ asking a vision model
def _encode(img, max_side=1400):
    img = img.convert("RGB")
    scale = min(1.0, max_side / max(img.size))
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode(), scale, img.size


def _grid(img, step=100):
    """Light labelled grid — makes models far better at giving exact coordinates."""
    g = img.convert("RGB").copy()
    d = ImageDraw.Draw(g)
    for x in range(0, g.width, step):
        d.line([(x, 0), (x, g.height)], fill=(255, 0, 255), width=1)
        d.text((x + 2, 2), str(x), fill=(255, 0, 255))
    for y in range(0, g.height, step):
        d.line([(0, y), (g.width, y)], fill=(255, 0, 255), width=1)
        d.text((2, y + 2), str(y), fill=(255, 0, 255))
    return g


def ask_image(img, question, max_side=1400):
    brain = CTX.get("brain")
    data, scale, size = _encode(img, max_side)
    msg = [{"role": "user", "content": [
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}]
    errors = []
    provs = (list(brain.cloud) if brain else []) + ([brain.local] if brain and brain.local.vision else [])
    for p in provs:
        if not p.vision or not p.configured:
            continue
        try:
            out = p.chat(msg, None, "smart", None, CTX.get("cancel"), models=p.vision)
            return out["content"].strip(), scale, size
        except Exception as e:
            errors.append(f"{p.label}: {str(e)[:80]}")
    raise RuntimeError("No vision brain answered (" + "; ".join(errors[-3:]) + "). Add a free Gemini or "
                       "OpenRouter key in Settings, or set a local vision model like 'moondream'.")


def ocr_text(img):
    if not _ocr_ready():
        return None
    return pytesseract.image_to_string(img)


# ------------------------------------------------------------------ tools
@tool("LOOK at the screen and answer a question about it (what's open, what an error says, which button to "
      "press, rate my thumbnail...). Uses a vision model, so it understands images, not just text.",
      {"question": ("string", "What you want to know about the screen", False)})
def look_at_screen(question="Describe what's on the screen and what the user is doing."):
    img = screenshot()
    try:
        ans, _, _ = ask_image(img, question)
        return ans
    except RuntimeError as e:
        txt = ocr_text(img)
        return f"(vision unavailable: {e})\nVisible text instead:\n{txt[:3000]}" if txt else f"ERROR: {e}"


@tool("Look at one app's window (even if it's behind other windows) and answer a question about it.",
      {"app": ("string", "Process name like 'Root.exe', 'chrome.exe', or a word from the window title", True),
       "question": ("string", "What you want to know", False)})
def look_at_window(app, question="Describe this window."):
    proc = app if app.lower().endswith(".exe") else None
    w = find_window(process_name=proc, title_part=None if proc else app)
    if not w:
        return f"Couldn't find a window for '{app}'. Is it open?"
    img, _ = capture_window(w[0])
    ans, _, _ = ask_image(img, question)
    return ans


def locate(description, img=None):
    """Returns (x, y) screen coordinates of the described thing, or None."""
    img = img or screenshot()
    if _ocr_ready() and len(description) < 40:      # fast path: it's visible text
        from .tools import _find_text
        hit = _find_text(description, img)
        if hit:
            return hit[1], hit[2]
    q = (f"The screenshot has a magenta grid labelled in pixels. Find: {description}\n"
         'Reply with ONLY JSON: {"found": true, "x": <int>, "y": <int>} giving the CENTER of it in this image\'s '
         'pixel coordinates, or {"found": false} if it isn\'t visible.')
    ans, scale, _ = ask_image(_grid(img), q)
    m = re.search(r"\{.*\}", ans, re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not j.get("found"):
        return None
    return int(j["x"] / scale), int(j["y"] / scale)


@tool("Find something on screen by DESCRIPTION (an icon, button, picture, field — doesn't need text) and click it.",
      {"description": ("string", "e.g. 'the blue Play button', 'the search box', 'the settings gear icon'", True),
       "double": ("boolean", "Double click", False), "right": ("boolean", "Right click", False)})
def click_on(description, double=False, right=False):
    _need(pyautogui, "pyautogui")
    pos = locate(description)
    if not pos:
        return f"Couldn't see '{description}' on screen."
    pyautogui.click(pos[0], pos[1], clicks=2 if double else 1, button="right" if right else "left")
    return f"Clicked '{description}' at {pos}."

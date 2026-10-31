"""ORION's own web browser (Playwright + Chromium). Runs hidden by default.

It can read pages that need JavaScript, click links/buttons, fill in search boxes and forms, scroll,
and take a screenshot for the vision brain. It keeps its own profile in data/browser_profile, so sites
you log into stay logged in (you do the logging in yourself: say "show the browser").

Safety: ORION never types into password or payment fields, and won't press buy/pay/order buttons.
"""
import os
import queue
import re
import threading

from .paths import DATA_DIR, FROZEN

if FROZEN:   # ORION.exe: use the Chromium that setup installed, not a copy inside the .exe
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
from .tools import CTX, tool

PROFILE = os.path.join(DATA_DIR, "browser_profile")
BLOCK_BUTTONS = re.compile(r"\b(buy|pay|purchase|place order|checkout|confirm order|subscribe now|donate|"
                           r"delete account|transfer|send money)\b", re.I)

# Marks every visible clickable/typeable element with a number ORION can refer to.
TAG_JS = r"""
() => {
  document.querySelectorAll('[data-orion]').forEach(e => e.removeAttribute('data-orion'));
  const sel = 'a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=tab],[contenteditable=true],summary';
  const out = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    if (r.width < 4 || r.height < 4 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (r.bottom < 0 || r.top > innerHeight * 2.5) continue;
    n++; el.setAttribute('data-orion', n);
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    let label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
                 el.getAttribute('title') || el.getAttribute('name') || el.getAttribute('alt') || '').trim().replace(/\s+/g, ' ');
    const kind = tag === 'a' ? 'link' : (tag === 'input' || tag === 'textarea' || el.isContentEditable) ? 'field' :
                 tag === 'select' ? 'dropdown' : 'button';
    out.push(`[${n}] ${kind}${type && kind === 'field' ? '(' + type + ')' : ''}: ${label.slice(0, 70)}`);
    if (n >= 80) break;
  }
  return out;
}
"""
TEXT_JS = r"""
() => {
  const b = document.body; if (!b) return '';
  return (b.innerText || '').replace(/\n{3,}/g, '\n\n').trim();
}
"""


class _Browser:
    """All Playwright calls happen on one dedicated thread (Playwright requires that)."""

    def __init__(self):
        self.q = queue.Queue()
        self.thread = None
        self.page = None
        self.ctx = None
        self.headless = True

    def call(self, fn, timeout=90):
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        box = {}
        done = threading.Event()
        self.q.put((fn, box, done))
        if not done.wait(timeout):
            raise RuntimeError("The browser took too long.")
        if "err" in box:
            raise box["err"]
        return box["val"]

    def _loop(self):
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        while True:
            fn, box, done = self.q.get()
            try:
                if fn == "__restart__":
                    if self.ctx:
                        self.ctx.close()
                    self.ctx = self.page = None
                    box["val"] = True
                else:
                    if self.ctx is None:
                        os.makedirs(PROFILE, exist_ok=True)
                        self.ctx = pw.chromium.launch_persistent_context(
                            PROFILE, headless=self.headless, viewport={"width": 1280, "height": 860},
                            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
                            locale="en-GB")
                        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
                    if self.page.is_closed():
                        self.page = self.ctx.new_page()
                    box["val"] = fn(self.page)
            except Exception as e:
                box["err"] = e
            done.set()


B = _Browser()


def _state(page, text_chars=3500):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(600)
    els = page.evaluate(TAG_JS)
    text = page.evaluate(TEXT_JS)
    return (f"PAGE: {page.title()}\nURL: {page.url}\n\n--- text ---\n{text[:text_chars]}\n\n"
            f"--- things you can click/type (use the number) ---\n" + "\n".join(els))


def _locate(page, target):
    target = str(target).strip()
    if re.fullmatch(r"\[?\d+\]?", target):
        return page.locator(f'[data-orion="{target.strip("[]")}"]').first
    for loc in (page.get_by_role("button", name=target), page.get_by_role("link", name=target),
                page.get_by_placeholder(target), page.get_by_label(target), page.get_by_text(target, exact=False)):
        try:
            if loc.count():
                return loc.first
        except Exception:
            continue
    raise RuntimeError(f"Couldn't find '{target}' on the page — use a number from the list.")


def _restart():
    if B.thread and B.thread.is_alive():
        box, done = {}, threading.Event()
        B.q.put(("__restart__", box, done))
        done.wait(30)


def _available():
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def _guard():
    if not _available():
        raise RuntimeError("The built-in browser isn't installed — run 1_SETUP.bat again.")


# ------------------------------------------------------------------ tools
@tool("Open a web page in ORION's own browser and read it (works on sites that need JavaScript). "
      "Returns the page text plus numbered links/buttons/fields you can use with browser_click/browser_type.",
      {"url": ("string", "Web address (or search words — they'll be searched on Bing)", True)})
def browser_open(url):
    _guard()
    u = url.strip()
    if not re.match(r"^https?://", u):
        u = ("https://" + u) if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", u) else \
            "https://www.bing.com/search?q=" + __import__("urllib.parse").parse.quote(u)
    return B.call(lambda p: (p.goto(u, timeout=30000, wait_until="domcontentloaded"), _state(p))[1])


@tool("Read the current page in ORION's browser again (text + numbered elements).")
def browser_read():
    _guard()
    return B.call(lambda p: _state(p))


@tool("Click a link or button in ORION's browser, by its number from the list or its visible text.",
      {"target": ("string", "Element number like '12', or its text", True)})
def browser_click(target):
    _guard()

    def go(p):
        loc = _locate(p, target)
        label = (loc.inner_text(timeout=2000) if loc.count() else "") or ""
        if BLOCK_BUTTONS.search(label):
            return f"BLOCKED: I won't press '{label.strip()[:40]}' — purchases/payments are for you to do yourself."
        loc.click(timeout=8000)
        return _state(p)
    return B.call(go)


@tool("Type into a field in ORION's browser (search box, form field). Never use for passwords or card details.",
      {"target": ("string", "Field number, placeholder text or label", True),
       "text": ("string", "What to type", True),
       "submit": ("boolean", "Press Enter afterwards", False)})
def browser_type(target, text, submit=False):
    _guard()

    def go(p):
        loc = _locate(p, target)
        info = loc.evaluate("e => [(e.type||'').toLowerCase(), (e.autocomplete||'').toLowerCase(), (e.name||'').toLowerCase()]")
        if info[0] == "password" or info[1].startswith("cc-") or re.search(r"pass|card|cvv|cvc|iban|sort.?code", " ".join(info)):
            return "BLOCKED: that's a password/payment field — the user must type that themselves (say 'show the browser')."
        loc.fill(text, timeout=8000)
        if submit:
            loc.press("Enter")
        return _state(p)
    return B.call(go)


@tool("Scroll ORION's browser page down (or up) to see more.",
      {"direction": ("string", "down or up", False)})
def browser_scroll(direction="down"):
    _guard()
    d = -1 if str(direction).lower().startswith("u") else 1
    return B.call(lambda p: (p.mouse.wheel(0, d * 900), p.wait_for_timeout(500), _state(p))[2])


@tool("Go back to the previous page in ORION's browser.")
def browser_back():
    _guard()
    return B.call(lambda p: (p.go_back(timeout=15000), _state(p))[1])


@tool("Look at the browser page like a person would (screenshot + vision) and answer a question about it.",
      {"question": ("string", "What you want to know", False)})
def browser_look(question="Describe this page."):
    _guard()
    import io
    from PIL import Image
    png = B.call(lambda p: p.screenshot(full_page=False))
    from .vision import ask_image
    return ask_image(Image.open(io.BytesIO(png)), question)[0]


@tool("Show or hide ORION's browser window (show it so the user can log in to a site themselves).",
      {"visible": ("boolean", "True = show the window", True)})
def browser_show(visible):
    _guard()
    want_headless = not bool(visible)
    if B.headless != want_headless:
        B.headless = want_headless
        _restart()                                   # relaunch with the new setting
    return "Browser window shown — log in, then tell me to carry on." if visible else "Browser hidden again."


def search(query, n=6):
    """Used by web_search when normal searching is blocked: search Bing in the real browser."""
    def go(p):
        p.goto("https://www.bing.com/search?q=" + __import__("urllib.parse").parse.quote(query) + "&setlang=en-GB",
               timeout=25000, wait_until="domcontentloaded")
        p.wait_for_timeout(800)
        return p.evaluate("""() => [...document.querySelectorAll('li.b_algo')].slice(0, 8).map(li => {
            const a = li.querySelector('h2 a'); const s = li.querySelector('p, .b_lineclamp2, .b_lineclamp3');
            return a ? [a.innerText, a.href, s ? s.innerText : ''] : null }).filter(Boolean)""")
    return [tuple(x) for x in B.call(go)][:n]

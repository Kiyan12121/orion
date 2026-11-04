"""Holographic cards + live view.

Cards: while ORION talks, small glowing panels pop up around the core — weather, steps, code, charts,
key points, pictures. The AI can show one on purpose with show_card, and some tools make one by themselves.
Live view: when ORION drives its hidden browser or the PC, a panel shows what it's seeing, live.
"""
import base64
import io
import threading
import time

from .tools import CTX, tool

_last_live = [0.0]
LIVE_TOOLS = {"browser_open", "browser_click", "browser_type", "browser_scroll", "browser_back", "browser_read",
              "open_website", "fetch_page"}
SCREEN_TOOLS = {"mouse_click", "type_text", "press_keys", "click_text", "click_on", "open_app", "root_send_message",
                "root_read_chat", "scroll"}


_recent = {}


def emit_card(kind, title, **data):
    """Shows a holographic pop-up. The same card is never shown twice within 3 minutes, and cards with an `id`
    (e.g. 'search') replace the visible one instead of stacking up."""
    emit = CTX.get("emit")
    if not emit:
        return
    import hashlib
    import json as _j
    body = {k: data.get(k) for k in ("items", "text", "points", "results", "value", "at") if data.get(k) is not None}
    sig = hashlib.md5(f"{kind}|{title}|{_j.dumps(body, sort_keys=True, default=str)[:2000]}".encode()).hexdigest()
    now = time.time()
    for k in [k for k, t in _recent.items() if now - t > 180]:
        _recent.pop(k, None)
    if sig in _recent:
        return
    _recent[sig] = now
    emit("card", card={"kind": kind, "title": title[:80], "t": now, **data})


def _jpeg(img, side=900, q=62):
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=q)
    return base64.b64encode(buf.getvalue()).decode()


def after_tool(name, args, result):
    """Called by the toolbox after every tool — turns some results into cards / live frames."""
    try:
        if name in LIVE_TOOLS or name.startswith("browser_"):
            _browser_frame(name, args, result)
        elif name in SCREEN_TOOLS:
            _screen_frame(name, args)
        if name == "weather" and not result.startswith("ERROR"):
            from .life import forecast
            w = forecast(args.get("place", ""))
            emit_card("weather", w["place"], weather=w, id="weather")
        elif name in ("news",) and not result.startswith("ERROR"):
            emit_card("list", "Headlines", items=[l.lstrip("• ")[:140] for l in result.split("\n") if l.strip()][:6], id="news", icon="📰")
        elif name in ("screen_time", "gaming_stats", "earnings_summary", "money_meeting", "scholar_status",
                      "homework_list", "crm_list", "study_stats"):
            emit_card("text", name.replace("_", " ").title(), text=result[:900], id=name)
        elif name == "web_search" and not result.startswith(("ERROR", "No results")):
            res = []
            for block in result.split("\n\n"):
                ls = [l.strip() for l in block.strip().split("\n") if l.strip()]
                url = next((l for l in ls if l.startswith("http")), "")
                if url:
                    i = ls.index(url)
                    res.append({"t": (ls[i - 1] if i else url)[:110], "u": url[:300], "s": " ".join(ls[i + 1:])[:180]})
            if res:
                q = str(args.get("query") or args.get("q") or "")[:60]
                emit_card("results", f"Search · {q}" if q else "Search results", results=res[:5], id="search", icon="🔎")
        elif name == "idea_score":
            emit_card("text", "Idea scorecard", text=result[:900])
    except Exception:
        pass


def _browser_frame(name, args, result=""):
    _last_live[0] = time.time()

    def grab():
        try:
            from .browser import B
            png = B.call(lambda p: (p.screenshot(type="jpeg", quality=55), p.url, p.title()))
            img_b = base64.b64encode(png[0]).decode()
            cap = {"browser_open": "Opening", "open_website": "Opening", "browser_click": "Clicking",
                   "browser_type": "Typing", "browser_scroll": "Scrolling", "browser_back": "Going back",
                   "browser_read": "Reading", "fetch_page": "Reading"}.get(name, "Working")
            what = args.get("target") or args.get("url") or args.get("url_or_query") or args.get("text") or ""
            CTX["emit"]("live", src="browser", img=img_b, url=png[1], title=png[2],
                        caption=f"{cap} {str(what)[:60]}".strip(),
                        found=_found_text(result), tool=name)
        except Exception:
            pass
    threading.Thread(target=grab, daemon=True).start()


def _found_text(result):
    """A short 'what I found' line for the browser window, from the tool's result."""
    r = str(result or "")
    if r.startswith("ERROR"):
        return ""
    lines = [l.strip() for l in r.split("\n") if l.strip() and not l.strip().startswith(("URL:", "Title:", "["))]
    return " ".join(lines)[:320]


def _screen_frame(name, args):
    if time.time() - _last_live[0] < 0.8:
        return
    _last_live[0] = time.time()

    def grab():
        try:
            time.sleep(0.35)
            import pyautogui
            CTX["emit"]("live", src="screen", img=_jpeg(pyautogui.screenshot()), url="", title="Your PC",
                        caption=f"{name.replace('_', ' ')} {str(list(args.values())[:1])[1:-1][:50]}")
        except Exception:
            pass
    threading.Thread(target=grab, daemon=True).start()


@tool("Show a HOLOGRAPHIC CARD beside ORION while you talk, so the user can SEE it. kinds: points (key points), "
      "steps (how-to), checklist (tickable to-dos), chart ('label: number' items), stat (one big number + caption), "
      "ring (a percentage/progress), code, text. Add 1-3 actions = one-click follow-ups.",
      {"kind": ("string", "points | steps | checklist | chart | stat | ring | code | text", True),
       "title": ("string", "Short title", True),
       "items": ("array", "Bullet points / steps / checklist items / 'label: number' pairs for a chart", False),
       "text": ("string", "Text or code, or the caption for stat/ring", False),
       "value": ("string", "For stat: the big number (e.g. '£186' or '7h 20m'); for ring: a percentage 0-100", False),
       "actions": ("array", "Optional 1-3 one-click buttons: short things the user might say next, e.g. 'Quiz me on this'", False)})
def show_card(kind, title, items=None, text="", value="", actions=None):
    kind = kind if kind in ("points", "steps", "checklist", "chart", "stat", "ring", "code", "text") else "points"
    data = {"items": [str(i)[:160] for i in (items or [])][:10], "text": (text or "")[:2500]}
    if value not in (None, ""):
        data["value"] = str(value)[:24]
    if kind == "chart":
        pts = []
        for i in data["items"]:
            if ":" in i:
                k, v = i.rsplit(":", 1)
                try:
                    pts.append([k.strip()[:24], float(v.strip().replace("£", "").replace("%", ""))])
                except ValueError:
                    pass
        data["points"] = pts
    if actions:
        data["actions"] = [{"label": str(a)[:30], "say": str(a)[:200]} for a in actions[:3]]
    emit_card(kind, title, **data)
    return "Card shown."


@tool("Close (or minimise) the pop-up windows/cards on screen — e.g. when the user says 'close that', 'close the browser "
      "window', 'get rid of that'. what: windows | cards | all. minimise=true to tuck them away instead.",
      {"what": ("string", "windows | cards | all", False), "minimise": ("boolean", "Minimise instead of closing", False)})
def close_popups(what="all", minimise=False):
    emit = CTX.get("emit")
    if emit:
        emit("popups", what=what or "all", minimise=bool(minimise))
    return "Done — tucked away." if minimise else "Closed."

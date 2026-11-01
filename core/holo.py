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


def emit_card(kind, title, **data):
    emit = CTX.get("emit")
    if emit:
        emit("card", card={"kind": kind, "title": title[:80], "t": time.time(), **data})


def _jpeg(img, side=900, q=62):
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=q)
    return base64.b64encode(buf.getvalue()).decode()


def after_tool(name, args, result):
    """Called by the toolbox after every tool — turns some results into cards / live frames."""
    try:
        if name in LIVE_TOOLS or name.startswith("browser_"):
            _browser_frame(name, args)
        elif name in SCREEN_TOOLS:
            _screen_frame(name, args)
        if name == "weather" and not result.startswith("ERROR"):
            from .life import forecast
            w = forecast(args.get("place", ""))
            emit_card("weather", w["place"], weather=w)
        elif name in ("news",) and not result.startswith("ERROR"):
            emit_card("list", "Headlines", items=[l.lstrip("• ")[:140] for l in result.split("\n")][:6])
        elif name in ("screen_time", "gaming_stats", "earnings_summary", "money_meeting", "scholar_status",
                      "homework_list", "crm_list", "study_stats"):
            emit_card("text", name.replace("_", " ").title(), text=result[:900])
        elif name == "idea_score":
            emit_card("text", "Idea scorecard", text=result[:900])
    except Exception:
        pass


def _browser_frame(name, args):
    if time.time() - _last_live[0] < 0.8:
        return
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
            CTX["emit"]("live", kind="browser", img=img_b, url=png[1], title=png[2],
                        caption=f"{cap} {str(what)[:60]}".strip())
        except Exception:
            pass
    threading.Thread(target=grab, daemon=True).start()


def _screen_frame(name, args):
    if time.time() - _last_live[0] < 0.8:
        return
    _last_live[0] = time.time()

    def grab():
        try:
            time.sleep(0.35)
            import pyautogui
            CTX["emit"]("live", kind="screen", img=_jpeg(pyautogui.screenshot()), url="", title="Your PC",
                        caption=f"{name.replace('_', ' ')} {str(list(args.values())[:1])[1:-1][:50]}")
        except Exception:
            pass
    threading.Thread(target=grab, daemon=True).start()


@tool("Show a HOLOGRAPHIC CARD beside ORION while you talk — use it for key points, steps, a small table/chart, a "
      "formula or definition, so the user can SEE it. kind: points | steps | chart | code | text.",
      {"kind": ("string", "points | steps | chart | code | text", True),
       "title": ("string", "Short title", True),
       "items": ("array", "Bullet points / steps / 'label: number' pairs for a chart", False),
       "text": ("string", "Text or code (for kind text/code)", False)})
def show_card(kind, title, items=None, text=""):
    kind = kind if kind in ("points", "steps", "chart", "code", "text") else "points"
    data = {"items": [str(i)[:160] for i in (items or [])][:10], "text": (text or "")[:2500]}
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
    emit_card(kind, title, **data)
    return "Card shown."

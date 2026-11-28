"""7.1 new features — built around what you actually do now: streaming, merch and GCSEs.

- Merch hub: log Fourthwall sales, orders to post and design ideas. Sales land in your earnings
  (venture "Merch"), so money automations and the money pages pick them up.
- Week balance: one honest look at this week — hours gaming, hours LIVE, minutes revising — and a nudge.
- Go-live prep: one command before you stream (game mode on, TikTok LIVE Studio open, stream marked).
All local and free: no extra AI calls, no logins.
"""
import datetime as dt
import os
import time
import uuid

from .paths import DATA_DIR
from .safeio import write_json
from .tools import CTX, tool

MERCH = os.path.join(DATA_DIR, "merch.json")


def _load():
    try:
        import json
        with open(MERCH, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("ideas", [])
    d.setdefault("orders", [])
    return d


def _save(d):
    write_json(MERCH, d, indent=1)


def _sales():
    try:
        from .ventures import earnings
        return [e for e in earnings() if e.get("venture", "").lower() == "merch"]
    except Exception:
        return []


def merch_overview():
    d = _load()
    s = _sales()
    month = time.strftime("%Y-%m")
    mon = [x for x in s if x["date"].startswith(month)]
    return {"store": CTX.get("config", {}).get("merch_store_url", ""),
            "month_total": round(sum(x["amount"] for x in mon), 2), "month_sales": len(mon),
            "all_total": round(sum(x["amount"] for x in s), 2), "all_sales": len(s),
            "to_post": [o for o in d["orders"] if not o.get("done")],
            "ideas": d["ideas"][-12:], "recent": sorted(s, key=lambda x: x["date"], reverse=True)[:6]}


@tool("Merch hub (Fourthwall): log a sale (your profit from it), an order you still need to post/check, or a design idea; "
      "or mark an order done. Sales count towards your earnings.",
      {"kind": ("string", "sale | order | idea | done", True),
       "amount": ("number", "For a sale: what you made from it in £", False),
       "item": ("string", "The product or the idea, e.g. 'Rivals hoodie' or 'glow-in-the-dark logo tee'", False),
       "note": ("string", "Optional note (buyer, size, colour…)", False)})
def merch_log(kind, amount=0, item="", note=""):
    kind = (kind or "").lower().strip()
    d = _load()
    if kind == "sale":
        if not amount or float(amount) <= 0:
            return "ERROR: tell me how much you made from the sale."
        from .ventures import earn_add
        rec = earn_add("Merch", float(amount), f"{item} {note}".strip())
        o = merch_overview()
        return f"Logged £{rec['amount']:.2f} merch sale ({item or 'item'}). Merch this month: £{o['month_total']:.2f} from {o['month_sales']} sale(s)."
    if kind == "order":
        d["orders"].append({"id": uuid.uuid4().hex[:5], "item": (item or "order")[:60], "note": (note or "")[:120],
                            "added": time.strftime("%Y-%m-%d"), "done": False})
        _save(d)
        return f"Added to orders to check: {item or 'order'}. {len([o for o in d['orders'] if not o['done']])} open."
    if kind == "idea":
        if not item:
            return "ERROR: what's the idea?"
        d["ideas"].append({"id": uuid.uuid4().hex[:5], "idea": item[:120], "note": (note or "")[:120], "added": time.strftime("%Y-%m-%d")})
        d["ideas"] = d["ideas"][-60:]
        _save(d)
        return f"Saved merch idea: {item}. You've got {len(d['ideas'])} ideas saved."
    if kind == "done":
        q = (item or "").lower()
        for o in d["orders"]:
            if not o["done"] and (not q or q in o["item"].lower() or q == o["id"]):
                o["done"] = True
                _save(d)
                return f"Marked done: {o['item']}."
        return "No open order matched that."
    return "ERROR: kind must be sale, order, idea or done."


@tool("Merch summary: this month's merch money, orders still to post, saved design ideas. Shows a card.")
def merch_summary():
    o = merch_overview()
    items = [f"This month: £{o['month_total']:.2f} from {o['month_sales']} sale(s)",
             f"All time: £{o['all_total']:.2f} from {o['all_sales']} sale(s)"]
    if o["to_post"]:
        items.append("To post/check: " + ", ".join(x["item"] for x in o["to_post"][:4]))
    if o["ideas"]:
        items.append("Latest ideas: " + ", ".join(x["idea"] for x in o["ideas"][-3:]))
    try:
        from .holo import emit_card
        emit_card("points", "Merch", items=items, text=o["store"] or "")
    except Exception:
        pass
    return " | ".join(items) + ("" if o["store"] else " | (Tip: tell me your Fourthwall shop link and I'll open it for you.)")


@tool("Save or open the user's Fourthwall merch shop. url = their shop link to save; leave blank to open it.",
      {"url": ("string", "Shop link to save, e.g. https://yourname-shop.fourthwall.com", False)})
def merch_shop(url=""):
    cfg = CTX.get("config", {})
    if url:
        if not url.startswith("https://"):
            return "ERROR: that should be an https:// link."
        cfg["merch_store_url"] = url.strip()[:200]
        from . import config as config_mod
        config_mod.save(cfg)
        return "Saved your shop link."
    if not cfg.get("merch_store_url"):
        return "ERROR: I don't have your shop link yet — tell me it and I'll remember."
    import webbrowser
    webbrowser.open(cfg["merch_store_url"])
    return "Opened your shop."


# ------------------------------------------------------------------ week balance
def week_balance_data(days=7):
    since = time.time() - days * 86400
    game = 0
    try:
        from .gaming import game_stats
        game = game_stats(days)["total_mins"]
    except Exception:
        pass
    live = 0
    try:
        from .streams import sessions
        live = sum(x.get("mins", 0) for x in sessions() if x.get("end") and x.get("start", 0) > since)
    except Exception:
        pass
    study = 0
    try:
        from .study import _load as sl
        log = sl().get("log", {})
        study = sum(log.get((dt.date.today() - dt.timedelta(days=k)).isoformat(), 0) for k in range(days))
    except Exception:
        pass
    exam = None
    try:
        from .study import overview
        ex = overview().get("exams") or []
        exam = ex[0] if ex else None
    except Exception:
        pass
    # gaming and streaming overlap (you stream while you play) — count game time that wasn't live separately
    play_only = max(0, game - live)
    return {"game_mins": game, "live_mins": live, "play_only_mins": play_only, "study_mins": study, "exam": exam}


def _h(m):
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"


@tool("Week balance: honest look at the last 7 days — hours gaming, hours LIVE on TikTok, minutes revising — "
      "with the next exam countdown and one suggestion. Shows a chart card.")
def week_balance():
    b = week_balance_data()
    title = CTX.get("config", {}).get("user_title", "sir")
    tip = ""
    if b["exam"] and b["exam"]["days"] <= 30 and b["study_mins"] < 120:
        tip = f"{b['exam'].get('subject', 'Your next exam')} is in {b['exam']['days']} days — even 25 minutes a day would make a real difference, {title}."
    elif b["study_mins"] == 0:
        tip = f"No revision logged this week, {title}. A single 25-minute focus round before streaming would get the ball rolling."
    elif b["study_mins"] >= b["play_only_mins"]:
        tip = f"Good balance this week, {title} — revision is keeping pace with gaming."
    else:
        tip = f"Gaming's ahead of revision this week. Try a focus round before you go live, {title}."
    try:
        from .holo import emit_card
        emit_card("chart", "Your week", items=[f"Gaming (off stream): {round(b['play_only_mins'] / 60, 1)}",
                                              f"LIVE: {round(b['live_mins'] / 60, 1)}",
                                              f"Revision: {round(b['study_mins'] / 60, 1)}"],
                  text="Hours, last 7 days. " + tip,
                  points=[["Gaming", round(b["play_only_mins"] / 60, 1)], ["LIVE", round(b["live_mins"] / 60, 1)],
                          ["Revision", round(b["study_mins"] / 60, 1)]],
                  actions=[{"label": "Start a focus round", "say": "start a 25 minute focus round"}])
    except Exception:
        pass
    ex = f" Next exam: {b['exam'].get('subject', 'exam')} in {b['exam']['days']} days." if b["exam"] else ""
    return (f"Last 7 days: gaming {_h(b['play_only_mins'])} off stream, LIVE {_h(b['live_mins'])}, "
            f"revision {_h(b['study_mins'])}.{ex} {tip}")


# ------------------------------------------------------------------ go-live prep
@tool("Get ready to go LIVE: game mode on (ORION hides and frees RAM), TikTok LIVE Studio opened, stream marked as started. "
      "Use when the user says they're about to stream / go live.")
def go_live_prep():
    done = []
    g = CTX.get("gaming")
    if g and not g.active:
        try:
            g.enter("stream", manual=True)
            done.append("game mode on")
        except Exception:
            pass
    run = CTX.get("toolbox_run")
    try:
        if run:
            r = run("open_app", {"name": "TikTok LIVE Studio"})
            if not str(r).startswith(("ERROR", "NOT_FOUND")):
                done.append("LIVE Studio opening")
    except Exception:
        pass
    w = CTX.get("streams")
    try:
        if w and w.start("manual"):
            done.append("stream marked as started")
    except Exception:
        pass
    title = CTX.get("config", {}).get("user_title", "sir")
    return (", ".join(done).capitalize() + f". Good luck out there, {title}.") if done else "Couldn't set anything up — is game mode available?"

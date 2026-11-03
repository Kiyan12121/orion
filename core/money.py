"""CEO mode's money tools: idea scorecards, money goals, a mini CRM, invoices, time-vs-money and the
Monday money meeting. Everything is judged by one question — how does this make Kiyan money?"""
import datetime as dt
import html
import json
import os
import re
import threading
import time
import uuid

from .paths import DATA_DIR
from .tools import CTX, tool

GOALS = os.path.join(DATA_DIR, "goals.json")
CRM = os.path.join(DATA_DIR, "crm.json")
IDEAS = os.path.join(DATA_DIR, "ideas.json")
HOURS = os.path.join(DATA_DIR, "hours.json")
STAGES = ["lead", "contacted", "replied", "call", "proposal", "won", "lost"]
_lock = threading.RLock()


def _load(p, d):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _save(p, v):
    with _lock:
        from .safeio import write_json
        write_json(p, v, indent=1)


def _quick_json(system, user):
    brain = CTX.get("brain")
    out = brain.quick(system, user, tier="smart", max_steps=1) or ""
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}


# ------------------------------------------------------------------ ideas
def ideas():
    return _load(IDEAS, [])


def score_idea(idea):
    data = _quick_json(
        "You are a ruthless, honest business partner for a 16-year-old UK student with a £0 budget, coding and "
        "automation skills, and ~10 hours a week. Score the idea. Reply JSON only: "
        '{"name":"short name","demand":1-10,"competition":1-10 (10 = little competition),"startup_cost_gbp":0,'
        '"time_per_week_h":0,"realistic_gbp_per_week":0,"weeks_to_first_pound":0,"score":1-100,'
        '"verdict":"go|maybe|drop","why":"2 sentences","first_3_steps":["...","...","..."],"risks":["..."]}',
        idea)
    rec = {"id": uuid.uuid4().hex[:6], "idea": idea[:400], "t": time.strftime("%Y-%m-%d"), **data}
    d = ideas()
    d.append(rec)
    _save(IDEAS, d[-200:])
    return rec


# ------------------------------------------------------------------ goals
def goals():
    from .ventures import earnings
    out = []
    e = earnings()
    for g in _load(GOALS, []):
        since = g.get("since", "2000-01-01")
        got = sum(x["amount"] for x in e if x["date"] >= since and (not g.get("venture") or x["venture"] == g["venture"]))
        left_days = max(1, (dt.date.fromisoformat(g["by"]) - dt.date.today()).days)
        need = max(0, g["target"] - got)
        out.append({**g, "got": round(got, 2), "pct": min(100, round(got / g["target"] * 100)) if g["target"] else 0,
                    "per_week": round(need / left_days * 7, 2), "days_left": left_days})
    return out


def goals_text():
    g = goals()
    return " | ".join(f"Goal '{x['name']}': £{x['got']:.0f}/£{x['target']:.0f}, need £{x['per_week']:.2f}/week"
                      for x in g if x["pct"] < 100)


def add_goal(name, target, by, venture=""):
    g = _load(GOALS, [])
    g.append({"id": uuid.uuid4().hex[:6], "name": name[:60], "target": float(target), "by": by,
              "venture": venture, "since": time.strftime("%Y-%m-%d")})
    _save(GOALS, g)


# ------------------------------------------------------------------ CRM
def crm():
    return _load(CRM, [])


def crm_upsert(name, stage="lead", **kw):
    c = crm()
    rec = next((x for x in c if x["name"].lower() == name.lower()), None)
    if not rec:
        rec = {"id": uuid.uuid4().hex[:6], "name": name[:60], "stage": "lead", "notes": [], "value": 0,
               "added": time.strftime("%Y-%m-%d")}
        c.append(rec)
    if stage in STAGES:
        rec["stage"] = stage
    for k in ("contact", "business", "value", "next", "next_date", "venture"):
        if kw.get(k) not in (None, ""):
            rec[k] = kw[k]
    if kw.get("note"):
        rec["notes"].append(f"{time.strftime('%d %b')}: {kw['note'][:200]}")
    rec["updated"] = time.strftime("%Y-%m-%d")
    _save(CRM, c)
    return rec


def crm_followups():
    today = time.strftime("%Y-%m-%d")
    out = []
    for x in crm():
        if x["stage"] in ("won", "lost"):
            continue
        stale = (dt.date.today() - dt.date.fromisoformat(x.get("updated", today))).days
        if (x.get("next_date") and x["next_date"] <= today) or (x["stage"] in ("contacted", "proposal") and stale >= 4):
            out.append(x)
    return out


# ------------------------------------------------------------------ time vs money
def log_hours(venture, minutes):
    h = _load(HOURS, [])
    h.append({"venture": venture, "min": int(minutes), "date": time.strftime("%Y-%m-%d")})
    _save(HOURS, h[-3000:])


def per_hour():
    from .ventures import earnings
    mins, money = {}, {}
    for x in _load(HOURS, []):
        mins[x["venture"]] = mins.get(x["venture"], 0) + x["min"]
    for x in earnings():
        money[x["venture"]] = money.get(x["venture"], 0) + x["amount"]
    return sorted(((v, round(money.get(v, 0) / (m / 60), 2), round(m / 60, 1)) for v, m in mins.items() if m),
                  key=lambda r: -r[1])


# ------------------------------------------------------------------ invoices
def make_invoice(client, items, due_days=14, note=""):
    owner = CTX.get("config", {}).get("owner_name", "Kiyan")
    folder = os.path.join(os.path.expanduser("~"), "Documents", "ORION Invoices")
    os.makedirs(folder, exist_ok=True)
    num = f"INV-{time.strftime('%Y%m')}-{len(os.listdir(folder)) + 1:03d}"
    rows, total = "", 0.0
    for it in items:
        desc = html.escape(str(it.get("desc") or it.get("description") or "Service"))
        qty, price = float(it.get("qty", 1)), float(it.get("price", 0))
        total += qty * price
        rows += f"<tr><td>{desc}</td><td>{qty:g}</td><td>£{price:.2f}</td><td>£{qty * price:.2f}</td></tr>"
    due = (dt.date.today() + dt.timedelta(days=int(due_days))).strftime("%d %B %Y")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{num}</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:40px auto;color:#111}}h1{{letter-spacing:.2em;margin:0}}
.top{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #111;padding-bottom:14px}}
table{{width:100%;border-collapse:collapse;margin-top:26px}}th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}
th{{background:#f4f4f4}}.tot{{text-align:right;font-size:22px;margin-top:18px}}.muted{{color:#666;font-size:13px}}
@media print{{button{{display:none}}}}</style></head><body>
<div class="top"><div><h1>INVOICE</h1><div class="muted">{num}</div></div><div style="text-align:right"><b>{html.escape(owner)}</b><br>
<span class="muted">Issued {time.strftime('%d %B %Y')}<br>Due {due}</span></div></div>
<p><b>Bill to:</b> {html.escape(client)}</p>
<table><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr>{rows}</table>
<div class="tot"><b>Total: £{total:.2f}</b></div>
<p class="muted">{html.escape(note or 'Thank you for your business!')}</p>
<button onclick="print()">Print / Save as PDF</button></body></html>"""
    safe = re.sub(r"[^\w ]", "", client)[:30]
    path = os.path.join(folder, f"{num} {safe}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path, total, num


# ------------------------------------------------------------------ Monday money meeting
def money_meeting_text():
    from .ventures import earn_summary
    s = earn_summary()
    last7 = sum(x["amount"] for x in s["recent"] if x["date"] >= (dt.date.today() - dt.timedelta(days=7)).isoformat())
    lines = [f"💷 Last 7 days: £{last7:.2f}. This month: £{s['this_month']:.2f}. All time: £{s['total']:.2f}."]
    if s["by_venture"]:
        lines.append(f"Best earner: {s['by_venture'][0][0]} (£{s['by_venture'][0][1]:.2f}).")
    ph = per_hour()
    if ph:
        lines.append(f"Best £/hour: {ph[0][0]} at £{ph[0][1]:.2f}/h" + (f"; worst: {ph[-1][0]} at £{ph[-1][1]:.2f}/h." if len(ph) > 1 else "."))
    g = goals_text()
    if g:
        lines.append(g)
    f = crm_followups()
    if f:
        lines.append(f"Follow up this week: {', '.join(x['name'] for x in f[:5])}.")
    top = sorted([i for i in ideas() if i.get("verdict") != "drop"], key=lambda i: -(i.get("score") or 0))[:1]
    if top:
        lines.append(f"Top untested idea: {top[0].get('name')} (score {top[0].get('score')}).")
    return "\n".join(lines)


# ------------------------------------------------------------------ AI tools
@tool("CEO: score a money-making idea honestly (demand, competition, cost, £/week, time to first £, verdict, first steps).",
      {"idea": ("string", "The idea, with any detail the user gave", True)})
def idea_score(idea):
    r = score_idea(idea)
    return (f"{r.get('name')}: score {r.get('score')}/100 — {str(r.get('verdict', '')).upper()}. "
            f"~£{r.get('realistic_gbp_per_week')}/week, first £ in ~{r.get('weeks_to_first_pound')} weeks, "
            f"{r.get('time_per_week_h')}h/week, startup £{r.get('startup_cost_gbp')}. {r.get('why')} "
            f"First steps: {'; '.join(r.get('first_3_steps', []))}.")


@tool("CEO: set a money goal (e.g. £500 by summer) — ORION tracks progress and how much is needed per week.",
      {"name": ("string", "Goal name", True), "target": ("number", "Amount in £", True),
       "by": ("string", "Deadline YYYY-MM-DD", True), "venture": ("string", "Only count one venture (optional)", False)})
def money_goal(name, target, by, venture=""):
    add_goal(name, target, by, venture)
    g = goals()[-1]
    return f"Goal set: £{g['target']:.0f} by {g['by']} — that's £{g['per_week']:.2f} a week from now."


@tool("CEO CRM: add or update a lead/client and their stage (lead, contacted, replied, call, proposal, won, lost).",
      {"name": ("string", "Person or business", True), "stage": ("string", "Stage", False),
       "note": ("string", "What happened", False), "value": ("number", "Deal value £", False),
       "next": ("string", "Next action", False), "next_date": ("string", "YYYY-MM-DD", False)})
def crm_update(name, stage="", note="", value=None, next="", next_date=""):
    r = crm_upsert(name, stage or "lead", note=note, value=value, next=next, next_date=next_date)
    return f"{r['name']} → {r['stage']}." + (f" Next: {r.get('next')} {r.get('next_date', '')}" if r.get("next") else "")


@tool("CEO CRM: list leads/clients and who needs a follow-up.")
def crm_list():
    c = crm()
    f = {x["id"] for x in crm_followups()}
    return "\n".join(f"{'⚠ ' if x['id'] in f else ''}{x['name']} [{x['stage']}] £{x.get('value') or 0} — "
                     f"{x.get('next') or (x['notes'][-1] if x['notes'] else '')}" for x in c) or "No leads yet."


@tool("CEO: make a professional INVOICE (saved to Documents › ORION Invoices, printable to PDF).",
      {"client": ("string", "Who to bill", True),
       "items": ("array", "Items as 'description | qty | price' strings, e.g. 'Booking bot setup | 1 | 30'", True),
       "due_days": ("integer", "Days until due (default 14)", False)})
def invoice_make(client, items, due_days=14):
    parsed = []
    for it in items or []:
        parts = [p.strip() for p in str(it).split("|")]
        parsed.append({"desc": parts[0], "qty": float(parts[1]) if len(parts) > 2 else 1,
                       "price": float(re.sub(r"[^\d.]", "", parts[-1]) or 0)})
    path, total, num = make_invoice(client, parsed, due_days)
    try:
        os.startfile(path)
    except Exception:
        pass
    return f"Invoice {num} for £{total:.2f} saved and opened: {path}"


@tool("CEO: log time spent on a venture (so ORION can work out £ per hour).",
      {"venture": ("string", "Venture", True), "minutes": ("integer", "Minutes", True)})
def time_log(venture, minutes):
    log_hours(venture, minutes)
    ph = {v: r for v, r, _ in per_hour()}
    return f"Logged {minutes} min on {venture}." + (f" You're earning £{ph[venture]:.2f}/hour there." if venture in ph else "")


@tool("CEO: the money meeting — numbers, best earner, £/hour, goals, follow-ups, top idea.")
def money_meeting():
    return money_meeting_text()

"""CEO 6.1 — the money HQ.

- Expenses: log what you spend on a venture, so ORION shows PROFIT, not just takings.
- HQ: this month vs last, profit, weighted pipeline forecast, goal pace, best £/hour, follow-ups due.
- ORION's priorities: 3 concrete things to do this week, worked out from your own numbers (no AI needed).
- Follow-up drafts: personalised follow-up messages for every lead that's gone quiet (saved, never sent).
- Weekly board report: every Sunday evening a short report lands on your phone and PC.
"""
import datetime as dt
import json
import os
import threading
import time
import uuid

from .paths import DATA_DIR
from .safeio import write_json
from .tools import CTX, tool

COSTS = os.path.join(DATA_DIR, "expenses.json")
# chance a deal at each stage turns into money — used for the forecast
STAGE_P = {"lead": .05, "contacted": .1, "replied": .25, "call": .4, "proposal": .6, "won": 1.0, "lost": 0}
_lock = threading.Lock()


def _load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def expenses():
    return _load(COSTS, [])


def expense_add(venture, amount, note="", date=None):
    with _lock:
        e = expenses()
        rec = {"id": uuid.uuid4().hex[:6], "venture": (venture or "Other").strip()[:40], "amount": round(abs(float(amount)), 2),
               "note": (note or "")[:120], "date": date or time.strftime("%Y-%m-%d")}
        e.append(rec)
        write_json(COSTS, e[-5000:])
    return rec


def expense_remove(eid):
    with _lock:
        write_json(COSTS, [x for x in expenses() if x["id"] != eid])


def _month(d=None, back=0):
    d = d or dt.date.today()
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def hq():
    from .money import crm, crm_followups, goals, per_hour
    from .ventures import earnings
    e, c = earnings(), expenses()
    this, last = _month(), _month(back=1)
    inc = lambda k: round(sum(x["amount"] for x in e if x["date"].startswith(k)), 2)
    out = lambda k: round(sum(x["amount"] for x in c if x["date"].startswith(k)), 2)
    today = dt.date.today()
    dom = today.day
    days_in = ((today.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).day
    month_in, month_out = inc(this), out(this)
    pace = round(month_in / dom * days_in, 2) if dom >= 7 else None       # too early in the month to say
    leads = crm()
    open_deals = [x for x in leads if x["stage"] not in ("won", "lost")]
    pipe = round(sum(float(x.get("value") or 0) for x in open_deals), 2)
    weighted = round(sum(float(x.get("value") or 0) * STAGE_P.get(x["stage"], 0) for x in open_deals), 2)
    won = [x for x in leads if x["stage"] == "won"]
    lost = [x for x in leads if x["stage"] == "lost"]
    by_v = {}
    for x in e:
        by_v.setdefault(x["venture"], [0, 0])[0] += x["amount"]
    for x in c:
        by_v.setdefault(x["venture"], [0, 0])[1] += x["amount"]
    ph = per_hour()
    g = goals()
    fu = crm_followups()
    week_in = round(sum(x["amount"] for x in e if x["date"] >= (today - dt.timedelta(days=7)).isoformat()), 2)
    return {
        "month": {"in": month_in, "out": month_out, "profit": round(month_in - month_out, 2), "pace": pace,
                  "last_in": inc(last), "last_profit": round(inc(last) - out(last), 2)},
        "week_in": week_in,
        "pipeline": {"open": len(open_deals), "value": pipe, "forecast": weighted, "won": len(won), "lost": len(lost),
                     "win_rate": round(len(won) / (len(won) + len(lost)) * 100) if won or lost else None,
                     "stages": {s: sum(1 for x in leads if x["stage"] == s) for s in STAGE_P}},
        "ventures": sorted(([v, round(a, 2), round(b, 2), round(a - b, 2)] for v, (a, b) in by_v.items()), key=lambda r: -r[3]),
        "per_hour": ph[:4], "goals": g, "followups": [{"id": x["id"], "name": x["name"], "stage": x["stage"]} for x in fu],
        "priorities": priorities(month_in, pace, inc(last), g, fu, ph, open_deals, week_in),
        "expenses": sorted(c, key=lambda x: x["date"], reverse=True)[:20],
    }


def priorities(month_in, pace, last_in, g, fu, ph, open_deals, week_in):
    """Three things worth doing this week, straight from the numbers."""
    p = []
    if fu:
        names = ", ".join(x["name"] for x in fu[:3])
        p.append({"icon": "📨", "text": f"Follow up with {names}" + (f" and {len(fu) - 3} more" if len(fu) > 3 else "") +
                  " — they've gone quiet. Quiet leads are the cheapest money you'll ever make.", "act": "followups"})
    behind = [x for x in g if x["pct"] < 100 and x["per_week"] > max(week_in, 0.01)]
    if behind:
        x = behind[0]
        p.append({"icon": "🎯", "text": f"'{x['name']}' needs £{x['per_week']:.0f}/week — you made £{week_in:.0f} in the last 7 days. "
                  f"{x['days_left']} days left.", "act": "goal"})
    if len(ph) >= 2 and ph[0][1] > ph[-1][1] * 2 and ph[0][1] > 0:
        p.append({"icon": "⏱", "text": f"{ph[0][0]} pays £{ph[0][1]:.2f}/h vs {ph[-1][0]} at £{ph[-1][1]:.2f}/h — shift an hour across this week.",
                  "act": "time"})
    if not open_deals:
        p.append({"icon": "🔎", "text": "Your pipeline is empty — run the Lead Finder for 15 local businesses and send 5 pitches.", "act": "leads"})
    elif len(open_deals) < 5:
        p.append({"icon": "🔎", "text": f"Only {len(open_deals)} open deal(s). Top up to 10 with the Lead Finder so one 'no' doesn't stall you.", "act": "leads"})
    if pace is None:
        pass
    elif last_in and pace < last_in * .8:
        p.append({"icon": "📉", "text": f"On pace for £{pace:.0f} this month vs £{last_in:.0f} last month. One extra sale closes the gap.", "act": "pace"})
    elif last_in and pace > last_in * 1.2:
        p.append({"icon": "🚀", "text": f"On pace for £{pace:.0f} — {round((pace / last_in - 1) * 100)}% up on last month. Keep doing what's working.", "act": "pace"})
    if not p:
        p.append({"icon": "💡", "text": "Log your earnings and time this week so I can spot what really pays.", "act": "log"})
    return p[:3]


def board_report():
    h = hq()
    m, pl = h["month"], h["pipeline"]
    lines = [f"📊 Weekly board report — {dt.date.today():%d %b}",
             f"Last 7 days: £{h['week_in']:.2f} in. This month: £{m['in']:.2f} in, £{m['out']:.2f} out, £{m['profit']:.2f} profit "
             + (f"(on pace for £{m['pace']:.0f}; last month £{m['last_in']:.0f})." if m["pace"] is not None else f"(last month £{m['last_in']:.0f})."),
             f"Pipeline: {pl['open']} open deal(s) worth £{pl['value']:.0f} — forecast £{pl['forecast']:.0f}."]
    if h["followups"]:
        lines.append(f"Follow-ups due: {', '.join(x['name'] for x in h['followups'][:5])}.")
    lines += [f"{p['icon']} {p['text']}" for p in h["priorities"]]
    return "\n".join(lines)


def draft_followups(brain, out_dir=None):
    """Personalised follow-ups for every quiet lead → a text file to copy from. Never sends anything."""
    from .money import crm_followups
    fu = crm_followups()
    if not fu:
        return None, 0
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "Documents", "ORION Leads")
    os.makedirs(out_dir, exist_ok=True)
    parts = []
    for x in fu[:12]:
        notes = "; ".join(x.get("notes", [])[-4:])
        prompt = (f"Lead: {x['name']} ({x.get('business', '')}). Stage: {x['stage']}. Notes: {notes or 'none'}. "
                  f"Value: £{x.get('value') or '?'}.")
        try:
            msg = brain.quick("Write a short, friendly, specific follow-up message (max 70 words) from a UK 16-year-old who runs a small "
                              "automation/dev service, to this lead. One clear question at the end. No pushiness, no fake urgency. "
                              "Output only the message.", prompt, tier="fast", max_steps=1)
        except Exception as e:
            msg = f"(couldn't draft: {e})"
        parts.append(f"=== {x['name']} — {x['stage']} ===\n{(msg or '').strip()}\n")
    fp = os.path.join(out_dir, f"Follow-ups {time.strftime('%Y-%m-%d %H%M')}.txt")
    with open(fp, "w", encoding="utf-8") as f:
        f.write("Follow-up drafts from ORION — nothing has been sent. Copy, tweak, send.\n\n" + "\n".join(parts))
    return fp, len(parts)


class Weekly:
    """Sunday 18:00 board report (once a week)."""

    def __init__(self, cfg, notify):
        self.cfg, self.notify = cfg, notify
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(60)
        while True:
            try:
                now = dt.datetime.now()
                wk = now.strftime("%G-%V")
                if (now.weekday() == 6 and now.hour >= 18 and self.cfg.get("ceo_weekly", True)
                        and self.cfg.get("ceo_weekly_last") != wk):
                    from .ventures import earnings
                    if earnings() or expenses():
                        self.cfg["ceo_weekly_last"] = wk
                        from . import config
                        config.save(self.cfg)
                        self.notify(board_report(), important=False)
            except Exception:
                pass
            time.sleep(600)


# ------------------------------------------------------------------ tools
@tool("CEO: log money SPENT on a venture (so profit is right).",
      {"venture": ("string", "Which venture", True), "amount": ("number", "£ spent", True), "note": ("string", "What on", False)})
def expense_log(venture, amount, note=""):
    r = expense_add(venture, amount, note)
    return f"Logged £{r['amount']:.2f} spent on {r['venture']}."


@tool("CEO HQ: the full money picture — this month in/out/profit, pace, pipeline forecast, goals, best £/hour, and the "
      "3 priorities for this week. Use for 'how's business', 'CEO report', 'what should I focus on to make money'.")
def ceo_report():
    return board_report()


@tool("CEO: draft personalised follow-up messages for every lead that's gone quiet (saved to a file, never sent).")
def followups_draft():
    brain = CTX.get("brain")
    if not brain:
        return "Brain not ready."
    fp, n = draft_followups(brain)
    return f"Drafted {n} follow-up(s) → {fp}" if fp else "No leads need a follow-up right now."

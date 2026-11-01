"""Ventures: money + projects.

- Dev queue: coding to-dos (Hatchlands Luau scripts, bots, tools) that Night Shift works through overnight.
- Lead finder: builds a list of local businesses for the automation-services pitch and drafts the emails.
- Earnings tracker: log what each venture makes; totals by month and venture.
"""
import json
import os
import re
import threading
import time
import uuid

from .paths import DATA_DIR, PROJECTS_DIR
from .tools import CTX, tool

DEV = os.path.join(DATA_DIR, "devqueue.json")
EARN = os.path.join(DATA_DIR, "earnings.json")
VENTURES = ["Hatchlands", "Content / YouTube", "Automation services", "Root bot", "Dropshipping", "Other"]
_lock = threading.Lock()

LUAU_RULES = """You are writing Roblox Luau for the game "{project}" (a pet hatching / rebirth idle game).
Rules:
- Save every script as a .lua file inside {folder}, in sub-folders mirroring Studio, e.g.
  ServerScriptService/PetHatching.server.lua, ReplicatedStorage/Modules/PetConfig.lua,
  StarterPlayerScripts/HatchUI.client.lua  (.server = Script, .client = LocalScript, plain = ModuleScript).
- Start each file with a comment saying exactly where it goes in Studio and what it needs (RemoteEvents, folders).
- Use modern Luau: task.wait/task.spawn, typed where helpful, RemoteEvents validated on the server (never trust
  the client), DataStore calls wrapped in pcall with retries, no deprecated APIs (wait(), spawn(), delay()).
- Re-read every file you write and check it for syntax mistakes and nil errors before finishing.
- Finish by writing {folder}/REVIEW.md: what each file does, how to install it in Studio, and how to test it.
"""


def _load(p, d):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _save(p, v):
    with _lock:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(v, f, indent=1)


# ------------------------------------------------------------------ dev queue
def dev_list():
    return _load(DEV, [])


def dev_add(task, project="Projects"):
    if re.search(r"hatchland", f"{task} {project}", re.I):
        raise ValueError("Hatchlands is off-limits for ORION — that one's just you and your collaborator.")
    d = dev_list()
    t = {"id": uuid.uuid4().hex[:6], "task": task.strip()[:600], "project": (project or "Projects").strip()[:40],
         "status": "todo", "added": time.time(), "job": None, "result": ""}
    d.append(t)
    _save(DEV, d)
    return t


def dev_remove(tid):
    _save(DEV, [t for t in dev_list() if t["id"] != tid])


def queue_dev_tasks(jobs, ids=None):
    """Turn to-dos into overnight jobs (one per task)."""
    d = dev_list()
    n = 0
    for t in d:
        if t["status"] != "todo" or (ids and t["id"] not in ids):
            continue
        folder = os.path.join(PROJECTS_DIR, re.sub(r"[^\w\- ]", "", t["project"]) or "Projects",
                              time.strftime("%Y-%m-%d ") + re.sub(r"[^\w]+", "-", t["task"].lower())[:36].strip("-"))
        lua = re.search(r"hatchlands|roblox|luau|lua\b|studio|obby|pet|rebirth", t["project"] + " " + t["task"], re.I)
        rules = LUAU_RULES.format(project=t["project"], folder=folder) if lua else (
            f"Build this as a project in {folder}. Test it with code_run and fix errors. Write REVIEW.md when done.")
        j = jobs.add(f"[DEV QUEUE] {t['task']}\n\n{rules}", source="routine", title=f"🛠 {t['project']}: {t['task'][:60]}",
                     heavy=True, autopilot=True)
        t.update(status="queued", job=j["id"], folder=folder)
        n += 1
    _save(DEV, d)
    return f"Queued {n} dev task(s)." if n else "Dev queue is empty."


def dev_sync(jobs):
    """Copy job results back onto the to-do list."""
    d = dev_list()
    changed = False
    for t in d:
        if t["status"] == "queued" and t.get("job"):
            j = jobs.get(t["job"])
            if j and j["status"] in ("done", "failed", "cancelled"):
                t["status"] = "done" if j["status"] == "done" else "todo"
                t["result"] = (j.get("result") or "")[:600]
                changed = True
    if changed:
        _save(DEV, d)
    return d


# ------------------------------------------------------------------ earnings
def earnings():
    return _load(EARN, [])


def earn_add(venture, amount, note="", date=None):
    e = earnings()
    rec = {"id": uuid.uuid4().hex[:6], "venture": venture.strip()[:40] or "Other", "amount": round(float(amount), 2),
           "note": (note or "")[:120], "date": date or time.strftime("%Y-%m-%d")}
    e.append(rec)
    _save(EARN, e)
    return rec


def earn_remove(eid):
    _save(EARN, [x for x in earnings() if x["id"] != eid])


def earn_summary():
    e = earnings()
    month = time.strftime("%Y-%m")
    by_v, by_m = {}, {}
    for x in e:
        by_v[x["venture"]] = round(by_v.get(x["venture"], 0) + x["amount"], 2)
        by_m[x["date"][:7]] = round(by_m.get(x["date"][:7], 0) + x["amount"], 2)
    months = []
    y, m = time.localtime().tm_year, time.localtime().tm_mon
    for k in range(5, -1, -1):
        mm, yy = m - k, y
        while mm <= 0:
            mm += 12
            yy -= 1
        key = f"{yy}-{mm:02d}"
        months.append({"month": key, "total": by_m.get(key, 0)})
    return {"total": round(sum(x["amount"] for x in e), 2), "this_month": by_m.get(month, 0),
            "by_venture": sorted(by_v.items(), key=lambda kv: -kv[1]), "months": months,
            "recent": sorted(e, key=lambda x: x["date"], reverse=True)[:30], "ventures": VENTURES}


# ------------------------------------------------------------------ AI tools
@tool("Add a coding task to the DEV QUEUE (built in the background). For bots, tools and scripts the user wants built "
      "later. NEVER for Hatchlands.",
      {"task": ("string", "What to build, in detail", True),
       "project": ("string", "Project name", False),
       "now": ("boolean", "Start it now instead of overnight", False)})
def dev_task_add(task, project="Projects", now=False):
    try:
        t = dev_add(task, project or "Projects")
    except ValueError as e:
        return str(e)
    if now and CTX.get("jobs"):
        queue_dev_tasks(CTX["jobs"], [t["id"]])
        return f"Started on it now (task {t['id']}). Scripts will be saved under projects\\{t['project']}."
    return f"Added to the {t['project']} dev queue (task {t['id']}). Night Shift will build it overnight."


@tool("Show the dev queue.")
def dev_task_list():
    d = dev_list()
    return "\n".join(f"[{t['id']}] {t['status'].upper()} {t['project']}: {t['task'][:100]}" for t in d[-20:]) or "Dev queue is empty."


@tool("LEAD FINDER: research local businesses that could use automation services and draft pitch emails. Runs "
      "as a background mission and saves a spreadsheet (CSV) + email drafts. Nothing is sent.",
      {"business_type": ("string", "e.g. 'barbers', 'driving instructors', 'cafes'", True),
       "area": ("string", "e.g. 'Leicester' or 'Hinckley'", True),
       "count": ("integer", "How many leads (default 15)", False),
       "offer": ("string", "What the user is offering, e.g. 'booking bots and automated reminders'", False)})
def leads_find(business_type, area, count=15, offer=""):
    q = CTX.get("jobs")
    if not q:
        return "Job queue isn't running."
    folder = os.path.join(os.path.expanduser("~"), "Documents", "ORION Leads",
                          re.sub(r"[^\w\- ]", "", f"{business_type} {area}").strip())
    offer = offer or "simple automations: booking/enquiry bots, automatic reminders and review requests"
    text = (f"[MISSION] Find up to {int(count or 15)} real {business_type} in {area} that could benefit from {offer}.\n"
            "Use web_search and your hidden browser (browser_open/fetch_page) to find each business's name, website, "
            "public contact email or contact-form URL, phone (if listed publicly), and one specific observation "
            "(e.g. no online booking, slow to reply, no reviews requested).\n"
            f"Create the folder {folder}. Save leads.csv with columns: name,website,email_or_form,phone,observation,"
            "score (1-5 fit). Then write emails.md with a short, friendly, personalised pitch email for the top 5 "
            "(no fake claims, mention it's a local student-run service, include an easy opt-out line). "
            "Only use information businesses publish themselves. Do NOT send anything.")
    j = q.add(text, source="mission", title=f"🔎 Leads: {business_type} in {area}", autopilot=True)
    return f"On it (ticket {j['id']}). The lead list and email drafts will be saved to Documents › ORION Leads."


@tool("Log money earned by one of the user's ventures.",
      {"venture": ("string", "Hatchlands, Content / YouTube, Automation services, Root bot, Dropshipping, Other", True),
       "amount": ("number", "Amount in £", True), "note": ("string", "What it was for", False)})
def earning_add(venture, amount, note=""):
    r = earn_add(venture, amount, note)
    s = earn_summary()
    return f"Logged £{r['amount']:.2f} for {r['venture']}. This month: £{s['this_month']:.2f}."


@tool("How much the user's ventures have earned (this month, total, by venture).")
def earnings_summary():
    s = earn_summary()
    if not s["recent"]:
        return "Nothing logged yet."
    by = ", ".join(f"{v} £{a:.2f}" for v, a in s["by_venture"])
    return f"This month £{s['this_month']:.2f}. All time £{s['total']:.2f}. By venture: {by}."

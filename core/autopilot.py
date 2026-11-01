"""Autopilot: give ORION a goal and it plans, acts, tests and fixes on its own."""
from .tools import CTX, tool

AUTOPILOT_RULES = """
AUTOPILOT MODE — you are working autonomously on a goal. The user is not watching each step.
1. FIRST call update_plan with 3-8 short, concrete steps.
2. Work through the steps with tools. Call update_plan(current=N) as you move on, so the HUD shows progress.
3. For anything involving code: project_create -> code_write -> code_run to TEST it -> read errors ->
   fix with code_edit -> run again. Up to 5 fix attempts per problem. Never claim code works unless a
   run proved it. For GUI apps, check it at least starts without errors (use a short timeout).
4. Don't ask the user questions — make sensible choices and mention them at the end.
5. Prefer Python (standard library + pip packages). For Windows apps that should be double-clicked,
   finish with make_exe and tell the user where the .exe is.
6. When finished: update_plan with done=true, then give a SHORT summary — what you built/did, where it
   is, how to use it, and anything you couldn't do.
7. If you're stuck after retries, finish with an honest summary of what works, what doesn't and why.
"""


@tool("Autopilot: show or update your step-by-step plan on the user's HUD.",
      {"steps": ("array", "The full list of steps (send it the first time, or when the plan changes)", False),
       "current": ("integer", "Index (0-based) of the step you're working on now", False),
       "done": ("boolean", "True when the whole goal is finished", False),
       "note": ("string", "Short status note", False)})
def update_plan(steps=None, current=0, done=False, note=""):
    plan = CTX.setdefault("plan", {"steps": [], "current": 0, "done": False, "note": ""})
    if steps:
        plan["steps"] = [str(s)[:120] for s in steps][:12]
    plan["current"] = int(current or 0)
    plan["done"] = bool(done)
    plan["note"] = note[:160] if note else plan.get("note", "")
    CTX.get("emit", lambda *a, **k: None)("plan", **plan)
    return "Plan updated."

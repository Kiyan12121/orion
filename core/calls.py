"""When ORION rings the user's phone by itself.

Kiyan's choice: finished jobs + schedule reminders. Calls are skipped during quiet hours and while
gaming (a normal notification is sent instead), and never more than one call every few minutes.
"""
import time

from . import phone

DEFAULTS = {"jobs": True, "reminders": True, "morning": False, "dms": False,
            "quiet_from": "23:00", "quiet_to": "07:00", "not_while_gaming": True, "min_job_seconds": 45}

_last = [0.0]


def settings(cfg):
    c = cfg.setdefault("calls", {})
    for k, v in DEFAULTS.items():
        c.setdefault(k, v)
    return c


def _mins(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def quiet_now(cfg):
    c = settings(cfg)
    a, b = _mins(c["quiet_from"]), _mins(c["quiet_to"])
    if a is None or b is None or a == b:
        return False
    t = time.localtime()
    now = t.tm_hour * 60 + t.tm_min
    return (a <= now < b) if a < b else (now >= a or now < b)


def maybe_call(cfg, kind, reason, gaming=None):
    """kind: jobs | reminders | morning | dms. Returns True if a call was placed."""
    c = settings(cfg)
    if not c.get(kind):
        return False
    if quiet_now(cfg):
        return False
    try:
        from .daily import at_school_now
        if at_school_now(cfg):            # never ring during school — the phone app holds it for 3:10
            phone.push("msg", text=reason[:300])
            return False
    except Exception:
        pass
    if c.get("not_while_gaming") and gaming is not None and gaming.active:
        return False
    if time.time() - _last[0] < 180:          # don't machine-gun calls
        return False
    _last[0] = time.time()
    phone.push("call", reason=reason[:300])
    return True


def job_reason(job, title="sir"):
    res = (job.get("result") or "").strip().split("\n")[0][:200]
    if job["status"] == "done":
        return f"Your job is finished: {job['title']}. {res}"
    return f"I'm afraid a job failed: {job['title']}. {res}"


def worth_calling(cfg, job):
    """Short jobs from an open phone app don't need a call — the answer is already on screen."""
    took = (job.get("finished") or 0) - (job.get("started") or 0)
    app_open = time.time() - phone.LAST_SEEN[0] < 30
    if job.get("source") == "phone" and app_open:
        return False
    return took >= settings(cfg)["min_job_seconds"] or job.get("source") in ("routine", "retry", "voice", "mission")

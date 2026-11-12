"""The thinking part.  reflex -> cloud pool (Groq, Cerebras, ...) -> local Ollama -> queue & retry later.

The agent keeps going even if a provider runs out mid-task: it hands the SAME conversation to the
next provider, so actions are never repeated. In Autopilot it will also wait out short rate limits.
"""
import json
import platform
import re
import time

from . import learning, modes, reflexes
from .autopilot import AUTOPILOT_RULES
from .providers import AuthError, Cancelled, ProviderError
from .tools import REGISTRY

THEMES = {
    "standby":   "Calm, sharp and quietly witty — a refined British AI butler. Light dry humour is welcome.",
    "serious":   "SERIOUS MODE: no jokes, no small talk, no filler. Short, precise, all business.",
    "stealth":   "STEALTH MODE: extremely brief. One short line unless more is explicitly requested.",
    "executive": "EXECUTIVE MODE: formal, polished and eloquent, like a private secretary to a CEO.",
    "hacker":    "HACKER MODE: terse, technical, lowercase terminal style. Use dev jargon. No pleasantries.",
}

PERSONA = """You are {name}, a personal AI assistant with real control of {title_cap}'s computer.
Personality: {theme}
Address the user as "{title}". Replies are read aloud, so keep them SHORT (1-3 sentences) unless \
asked for detail. No markdown headings. Put code in ``` blocks.

Rules:
- When asked to DO something, do it with tools — don't explain how. Chain tools for multi-step jobs.
- For coding requests, build it in a project (project_create, code_write, code_run to test, fix errors).
- If you need a tool you weren't given, call request_more_tools.
- Use web_search/fetch_page for anything current or unknown. Never invent facts. For sites that need
  clicking, searching or forms, use your own browser (browser_open, then browser_click/browser_type by number).
  Never type passwords or payment details — ask the user to do that via browser_show.
- "Set an alarm" / "wake me up" / "call me" / "torch" mean the user's PHONE — use the phone_* tools.
- Use the schedule tools for plans, bookings, reminders and "am I free" questions.
- If the user shares something worth keeping (preferences, projects, people), call remember.
- Web work happens in YOUR hidden browser (web_search, fetch_page, browser_*, open_website). Never pop pages up on
  the user's screen unless they ask to see it (open_website show=true).
- If a task is huge, break it down and use queue_job / autopilot. Never mention Claude or other assistants.
- The conversation is shared across the user's PC, laptop and phone — 'carry on' / 'what were we talking about'
  may refer to something said on another device; use the recent history.
- When something is easier to SEE (steps, key points, a formula, numbers to compare), call show_card while
  you talk — it appears as a holographic card beside you. Use it generously (plans, comparisons, results, summaries)
  and add 1-3 actions: one-click follow-ups the user is likely to want next (e.g. "Quiz me on this", "Make flashcards").
- NEVER work on Hatchlands (the user's Roblox game) in any way — no scripts, plans or Studio help. It's his own
  project with his human collaborator. If asked, say politely that Hatchlands is off-limits for you.
- You have a SKILL LIBRARY of 850+ ready-made skills (calculators, converters, GCSE subject helpers, essay and maths
  tools, business writers, coding, content, life admin). For specialised tasks call skill_find, then skill_use.
  The user can also run one directly by typing /skillname.
- You can show 3D holograms (hologram tool) to explain science/space/shapes, open the 3D globe (globe tool, e.g. 'show me
  Tokyo'), run a threat scan of the PC, and do the 'suit up' sequence. Use them when they'd genuinely help or wow.
- For crime in their area / 'is it safe round here' / planes overhead / flood warnings / air quality, call local_intel (opens the holographic local map and gives real police.uk numbers). Report the numbers calmly — never alarmist.
- For a job with 3+ steps that you're doing now, call plan_show first (a live checklist appears), then plan_tick as each
  step finishes. For 'what did I say about…' / 'remember when…' / anything from older chats, call recall.
- Never claim you did something you didn't. If a tool returns ERROR, say so briefly and try another way.

Now: {now}. System: {os}.{extra}
Memory about {title}:
{facts}"""

SMART = re.compile(r"\b(code|script|program|build|make|create|write|fix|debug|explain|why|how (do|does|to|can)|"
                   r"plan|research|compare|analy[sz]e|essay|app|bot|website|summari[sz]e|learn|teach|story|"
                   r"translate|calculate|work out|figure|recommend|should i|ideas?|design|review)\b", re.I)

CORE = {"plan_show", "plan_tick", "recall", "show_card", "close_popups", "skill_find", "skill_use", "habit", "ambient", "screensaver_show", "suit_up", "threat_scan_tool", "hologram", "globe", "local_intel", "queue_job", "mission_start", "weather", "note_add", "homework_add", "get_time", "open_app", "open_website", "web_search", "remember",
        "request_more_tools", "set_theme", "schedule_add", "schedule_list", "check_availability"}
GROUPS = {
    "orionos": ({"os_open_app", "os_volume", "os_wifi", "os_lock_screen", "os_screenshot", "os_power_off", "os_sky"}, r"lock|screenshot|screen ?shot|shut ?down|restart|reboot|sleep|sky|aurora|wi-?fi|volume|louder|quieter|mute|open (the )?(browser|files|terminal|editor|app)|network"),
    "automation": ({"automation_add", "automation_list", "automation_remove", "routine_add", "routine_list"},
                   r"when(ever)? i |every time|automat|whenever|if i (open|close|start|haven)|rule|trigger|routine"),
    "computer": ({"type_text", "press_keys", "mouse_click", "scroll", "read_screen", "find_on_screen",
                  "click_text", "wait", "list_running_apps", "close_app"},
                 r"click|type|press|screen|scroll|window|button|close|tab|key|mouse|select|menu|notepad|"
                 r"into|then|and (then )?(type|click|search)"),
    "system": ({"system_status", "media", "set_timer", "lock_pc", "power", "save_screenshot", "run_command",
                "list_running_apps", "close_app", "gaming_mode", "clip_that", "gaming_stats", "party_plan", "game_profile",
                "gaming_wrap", "window_layout", "app_volume", "tidy_downloads", "tidy_undo", "big_files", "find_duplicates",
                "screen_text", "pick_colour", "speed_test", "startup_apps"},
               r"arrange|side by side|layout|snap|tidy|downloads|big files|duplicate|disk space|free up|speed ?test|internet speed|"
               r"wifi|startup|colou?r (picker|under)|text on (the )?screen|ocr|copy the text|"
               r"volume|music|song|play|pause|skip|timer|cpu|ram|memory usage|battery|shut ?down|"
               r"restart|sleep|lock|screenshot|command|powershell|install|process|running|slow|wifi|ip|gam|clip|party|"
               r"hours played|play with|invite"),
    "files": ({"list_files", "read_file", "write_file", "open_path", "clipboard_get", "clipboard_set",
               "undo_last_change", "run_command"},
              r"file|folder|desktop|downloads|documents|save|\.txt|\.bat|clipboard|copy|paste|undo|delete|"
              r"rename|move"),
    "coder": ({"project_create", "project_list", "code_write", "code_edit", "code_read", "code_run",
               "make_exe", "project_open", "update_plan"},
              r"code|script|program|app\b|project|build|python|node|\.py|\.js|exe|bot|tool|automat|make me"),
    "browser": ({"browser_open", "browser_read", "browser_click", "browser_type", "browser_scroll", "browser_back",
                 "browser_look", "browser_show"},
                r"browser|website|web ?page|site|form|fill|sign ?up|book|order|price|deal|compare|scrape|read this|"
                r"log ?in|search for|look up|find me|check (the )?(site|page)|youtube|amazon|ebay|vinted"),
    "web": ({"web_search", "fetch_page", "open_website"},
            r"search|look up|google|website|news|who |what is|price|weather|latest|find|link|url|read this"),
    "memory": ({"remember", "forget"}, r"remember|forget|memory|my name|i like|i am|i'm"),
    "schedule": ({"schedule_add", "schedule_list", "schedule_remove", "check_availability", "set_timer"},
                 r"schedule|book|remind|calendar|free|busy|plan|tomorrow|tonight|monday|tuesday|wednesday|"
                 r"thursday|friday|saturday|sunday|week|appointment|revision|event|\bat \d|pm\b|am\b"),
    "skills": ({"skill_create", "skill_list", "skill_delete", "shortcut_add", "shortcut_list", "shortcut_remove"},
               r"learn|skill|teach yourself|new ability|shortcut|when i say|every time i say|macro"),
    "ventures": ({"dev_task_add", "dev_task_list", "leads_find", "earning_add", "earnings_summary", "mission_start"},
                 r"hatchlands|roblox|luau|dev queue|to-?do|leads?|prospect|businesses|pitch|client|earn|made £|"
                 r"money|income|profit|sold|sale|paid|£\d"),
    "auto": ({"message_user", "autonomous_mode", "set_routine"},
             r"autonom|on your own|by yourself|while i'?m away|message me|text me|routine|wake up at|school (starts|ends)|"
             r"holiday|half term"),
    "life": ({"homework_add", "homework_list", "homework_done", "weather", "news", "note_add", "notes_find",
              "clipboard_history", "screen_time", "find_files", "dictation", "voice_memo"},
             r"homework|assignment|due|weather|rain|coat|umbrella|cold|hot|forecast|news|headline|note|idea|jot|"
             r"clipboard|copied|screen ?time|how long (was|have) i|find (my |a |the )?file|where'?s (my|the) file|"
             r"dictat|type what i say|memo|voice note|brain ?dump"),
    "money": ({"idea_score", "money_goal", "crm_update", "crm_list", "invoice_make", "time_log", "money_meeting",
               "earning_add", "earnings_summary", "leads_find", "money_wrap", "price_calc", "expense_log", "ceo_report",
               "followups_draft"},
              r"wrapped|quote|how much (should|to) (i )?charge|idea|money|earn|£|goal|lead|client|customer|crm|invoice|bill |per hour|price|charge|business|sale|profit|spent|spend|expense|ceo|follow.?up|pipeline"),
    "scholar": ({"subject_add", "tutor_start", "tutor_progress", "exam_paper", "topic_rate", "revision_plan_tool",
                 "timetable_set", "scholar_status", "homework_add", "homework_list", "grade_predict", "essay_mark",
                 "working_check"},
                r"predict|essay|my working|where did i go wrong|check (my|this)|teach me|tutor|explain|exam paper|past paper|mock|mark (my|this)|grade|topic|revision (plan|timetable)|"
                r"timetable|lesson|gcse|subject|exam board|aqa|edexcel|ocr"),
    "study": ({"study_make_flashcards", "study_quiz", "study_mark", "focus_start", "focus_stop", "exam_add",
               "study_stats"},
              r"revis|study|flashcard|quiz me|test me|exam|gcse|homework|focus|pomodoro|mock|paper \d|biology|"
              r"chemistry|physics|maths|english lit|history|geography"),
    "phone": ({"phone_alarm", "phone_timer", "phone_open_app", "phone_call", "phone_torch", "find_my_phone",
               "phone_send_text", "send_file_to_phone"},
              r"phone|alarm|wake me|timer on|ring me|call me|torch|flashlight|on my mobile|my s23|lost|where'?s my"),
    "jobs": ({"queue_job", "list_jobs", "routine_add", "routine_list", "routine_run_now"},
             r"queue|later|background|overnight|night|while i'?m|when i'?m away|routine|every (day|morning|night|week)|"
             r"automat|job|tidy|clean ?up|back ?up|backup|temp|health"),
    "root": ({"root_check_messages", "root_read_chat", "root_send_message", "root_afk", "root_diagnose", "check_availability",
              "schedule_add"},
             r"\broot\b|message|messages|\bdm|dms|inbox|text |tell \w+|reply|afk|chat with|msg|ping"),
    "vision": ({"look_at_screen", "look_at_window", "click_on"},
               r"screen|see|look|what's this|whats this|error|this window|click|thumbnail|picture|image|icon"),
    "video": ({"video_autocut", "video_captions", "video_shorts", "video_info", "video_metadata", "list_files"},
              r"video|clip|youtube|shorts|caption|subtitle|edit|vod|stream|mp4|tiktok"),
}
if not __import__("os").path.exists("/etc/orion-os"):         # ORION OS desktop tools only exist on ORION OS
    GROUPS.pop("orionos", None)
AUTOPILOT_RE = re.compile(r"^\s*(auto ?pilot|autonomous(ly)?)\s*[:,\-]?\s*", re.I)


def pick_tier(text):
    return "smart" if len(text) > 160 or SMART.search(text) else "fast"


def pick_tools(texts):
    names = set(CORE)
    blob = " ".join(texts).lower()
    for group, pattern in GROUPS.values():
        if re.search(pattern, blob):
            names |= group
    return names


class AllFailed(Exception):
    pass


class Brain:
    def __init__(self, config, memory, toolbox, emit, extra_context=lambda: ""):
        from .providers import Provider
        self._Provider = Provider
        self.cfg = config
        self.memory = memory
        self.tools = toolbox
        self.emit = emit
        self.extra_context = extra_context
        self.force_cloud = False          # set by Gaming Mode
        self.reload_providers()

    def reload_providers(self):
        self.cloud = [self._Provider(p) for p in self.cfg["providers"] if p.get("api_key")]
        self.local = self._Provider({**self.cfg["local"], "id": "local"}, local=True)
        self.groq_like = next((p for p in self.cloud if p.stt), None)

    def status(self):
        return {"brain": self.cfg["brain"], "theme": self.cfg["theme"],
                "cloud": {"ok": any(p.ready() for p in self.cloud), "count": len(self.cloud),
                          "labels": [p.label for p in self.cloud if p.configured]},
                "local": {"ok": self.local.ping(), "model": self.local.fast[0]}}

    def meters(self):
        return [p.meter() for p in self.cloud]

    def _chain(self):
        mode = self.cfg.get("brain", "auto")
        if mode == "cloud" or self.force_cloud:
            return list(self.cloud)
        if mode == "local":
            return [self.local]
        return list(self.cloud) + [self.local]

    def _system(self, autopilot=False, text=""):
        title = self.cfg.get("user_title", "sir")
        extra = self.extra_context() or ""
        if autopilot:
            extra += "\n" + AUTOPILOT_RULES
        return PERSONA.format(name=self.cfg.get("assistant_name", "ORION"), title=title,
                              title_cap=title.capitalize(), os=platform.platform(),
                              now=time.strftime("%A %d %B %Y, %H:%M"),
                              theme=modes.persona(self.cfg.get("theme", "standby"), self.cfg),
                              extra=("\n" + extra) if extra else "", facts=self.memory.facts_text(text))

    # ------------------------------------------------------------------ main entry
    def handle(self, text, on_delta=None, cancel=None, autopilot=False):
        """Returns (reply, tier, model_label)."""
        name = self.cfg.get("assistant_name", "ORION")
        m = AUTOPILOT_RE.match(text)
        if m and len(text) > m.end() + 3:
            autopilot, text = True, text[m.end():]

        if not autopilot:
            sc = learning.expand(text)
            if sc:
                self.emit("toast", level="info", text=f"⚡ Shortcut: {sc[:80]}")
                text = sc
            r = reflexes.match(text, name)
            if r:
                tool_name, args, reply_fn = r
                result = self.tools.run(tool_name, args)
                if not result.startswith(("ERROR", "NOT_FOUND")):
                    reply = reply_fn(result)
                    self._log(text, reply)
                    return reply, "reflex", None

        if not autopilot and self.cfg.get("auto_mode", True):
            new = modes.detect(text, self.cfg.get("theme", "standby"))
            if new:
                from .tools import CTX
                if CTX.get("set_theme"):
                    CTX["set_theme"](new)
                    self.emit("toast", level="info", text=f"◆ {modes.MODES[new]['label']} mode")
        try:
            reply, prov, model = self._agent(text, on_delta, cancel, autopilot)
            self._log(("[autopilot] " if autopilot else "") + text, reply)
            return reply, ("local" if prov.local else "cloud"), f"{prov.label} {model.split('/')[-1]}"
        except AllFailed as e:
            title = self.cfg.get("user_title", "sir")
            why = "\n".join("• " + x.strip() for x in str(e).split(";") if x.strip())
            retry = ""
            from .tools import CTX
            jobs = CTX.get("jobs")
            import threading
            if (jobs and not text.startswith("[") and self.cfg.get("retry_when_out", True)
                    and threading.get_ident() != CTX.get("job_thread")):
                j = jobs.add(text, source="retry", title="Retry: " + text[:60], autopilot=autopilot)
                jobs.retry_later(j["id"])
                retry = f" I've queued it (ticket {j['id']}) and will retry automatically once a brain is free."
            return (f"Every brain I have is out of allowance right now, {title}.{retry}\n{why}"), "reflex", None

    def _log(self, user, reply):
        self.memory.add_turn("user", user)
        self.memory.add_turn("assistant", reply)
        try:
            learning.log_request(user)
        except Exception:
            pass
        if self.memory.due_for_learning() and self.cfg.get("auto_learn", True):
            import threading

            def learn():
                n = self.memory.learn_from_chat(self)
                if n:
                    self.emit("toast", level="info", text=f"🧠 Learned {n} new thing(s) about you.")
            threading.Thread(target=learn, daemon=True).start()

    def quick(self, system, user, allowed=frozenset(), tier="smart", max_steps=4):
        """A small, fenced-off agent: only the given tools, no memory, no streaming.
        Used for replying to friends — their text can never reach the full toolset."""
        allowed = set(allowed)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        state = {}
        for _ in range(max_steps):
            out, _p = self._call(messages, allowed, tier, None, None, False, state)
            calls = [c for c in out["tool_calls"] if c.get("function", {}).get("name") in allowed]
            if not calls:
                return out["content"]
            messages.append({"role": "assistant", "content": out["content"] or "", "tool_calls": calls})
            for c in calls:
                fn = c["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                messages.append({"role": "tool", "tool_call_id": c.get("id") or fn["name"], "name": fn["name"],
                                 "content": self.tools.run(fn["name"], args)[:2000]})
        out, _p = self._call(messages, set(), tier, None, None, False, state)
        return out["content"]

    # ------------------------------------------------------------------ provider failover per step
    def _call(self, messages, allowed, tier, on_delta, cancel, autopilot, state):
        errors, waits = [], 0
        while True:
            chain = self._chain()
            start = state.get("idx", 0)
            for i in list(range(start, len(chain))) + list(range(0, start)):
                prov = chain[i]
                if cancel and cancel.is_set():
                    raise Cancelled()
                if not prov.ready():
                    continue
                schemas = self.tools.schemas(self._local_subset(allowed) if prov.local else allowed)
                if state.get("prov") is not prov:
                    self.emit("status", text=f"{prov.label} · {'deep think' if tier == 'smart' else 'quick'}…")
                try:
                    out = prov.chat(messages, schemas, tier, on_delta, cancel)
                    state.update(idx=i, prov=prov)
                    return out, prov
                except AuthError as e:
                    errors.append(str(e))
                    self.emit("toast", level="warn", text=f"{e} — check Settings.")
                except ProviderError as e:
                    errors.append(str(e))
                    self.emit("status", text=f"{prov.label} busy — switching brain…")
            # nothing could answer
            soonest = self._soonest_cooldown()
            if autopilot and soonest is not None and soonest < 75 and waits < 8:
                waits += 1
                self.emit("status", text=f"Free allowance resting — resuming in {int(soonest) + 1}s…")
                if cancel and cancel.wait(soonest + 1):
                    raise Cancelled()
                if not cancel:
                    time.sleep(soonest + 1)
                continue
            seen = []
            for x in errors:
                if x not in seen:
                    seen.append(x)
            raise AllFailed("; ".join(seen[-4:]) if seen else "no brain available")

    def _soonest_cooldown(self):
        now = time.time()
        waits = [t - now for p in self.cloud for t in p.cooldown.values() if t > now]
        return min(waits) if waits else None

    @staticmethod
    def _local_subset(allowed):
        keep = CORE | {"media", "type_text", "press_keys", "system_status", "set_timer", "close_app"}
        return keep if allowed is None else (allowed & keep)

    @staticmethod
    def _trim(messages, limit=48000):
        """Keep long Autopilot runs inside the token budget by shrinking old tool outputs."""
        size = sum(len(str(m.get("content", ""))) for m in messages)
        for m in messages[2:-6]:
            if size <= limit:
                break
            if m["role"] == "tool" and len(m["content"]) > 300:
                size -= len(m["content"]) - 120
                m["content"] = m["content"][:120] + " …[trimmed]"

    def _agent(self, text, on_delta, cancel, autopilot):
        messages = [{"role": "system", "content": self._system(autopilot, text)}]
        messages += self.memory.recent(4 if autopilot else 10)
        messages.append({"role": "user", "content": text})
        recent_user = [m["content"] for m in self.memory.recent(4) if m["role"] == "user"]
        allowed = None if autopilot else (pick_tools([text] + recent_user)
                                          | {n for n in REGISTRY if n.startswith("skill_")}
                                          | {t for g in modes.groups(self.cfg.get("theme", "standby"), self.cfg)
                                             for t in GROUPS.get(g, (set(),))[0]})
        tier = "smart" if autopilot else pick_tier(text)
        max_steps = int(self.cfg.get("autopilot_steps", 40) if autopilot else self.cfg.get("max_steps", 12))
        limit = 3500 if autopilot else 6000
        said, state, out, prov = [], {}, None, None

        def stream(chunk):
            on_delta and on_delta(chunk)

        for step in range(max_steps):
            if cancel and cancel.is_set():
                raise Cancelled()
            if said and on_delta:
                on_delta("\n\n")
            if autopilot:
                self._trim(messages)
            out, prov = self._call(messages, allowed, tier, stream if on_delta else None, cancel, autopilot, state)
            if out["content"].strip():
                said.append(out["content"].strip())
            calls = out["tool_calls"]
            if not calls:
                return "\n\n".join(said) or "Done.", prov, out["model"]
            messages.append({"role": "assistant", "content": out["content"] or "", "tool_calls": calls})
            for c in calls:
                if cancel and cancel.is_set():
                    raise Cancelled()
                fn = c.get("function", {})
                fname = fn.get("name", "")
                try:
                    args = fn.get("arguments") or "{}"
                    args = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    args = {}
                if fname == "request_more_tools":
                    allowed, result = None, "All tools are now available."
                else:
                    if allowed is not None and fname not in allowed:
                        allowed = None
                    result = self.tools.run(fname, args)
                messages.append({"role": "tool", "tool_call_id": c.get("id") or fname,
                                 "name": fname, "content": result[:limit]})
            if step >= 1:
                tier = "smart"
        messages.append({"role": "user", "content": "Stop using tools now. Briefly say what you did and what's left."})
        out, prov = self._call(messages, set(), tier, stream if on_delta else None, cancel, autopilot, state)
        said.append(out["content"].strip() or "I've hit my step limit on that one.")
        return "\n\n".join(said), prov, out["model"]

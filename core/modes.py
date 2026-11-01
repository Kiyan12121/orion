"""ORION's six specialist modes. Each has its own personality, focus, favourite tools and voice.

  standby  — the everyday butler
  serious  — getting serious things done (missions, decisions, problems, accountability)
  executive— CEO mode: everything is about making money
  scholar  — school: tutor, Exam Hall, revision, homework
  hacker   — coding (never Hatchlands — that's Kiyan's own project)
  stealth  — gaming and night: minimal, quiet

ORION can switch automatically when a request clearly belongs to another mode.
"""
import re

MODES = {
    "standby": {
        "label": "Standby", "colour": "#3fd8ff",
        "persona": "Calm, sharp and quietly witty — a refined British AI butler. Light dry humour is welcome.",
        "focus": ("You're the everyday butler: schedule, reminders, weather, homework due, quick answers, life admin. "
                  "Be proactive — if you notice something useful (homework due tomorrow, rain later, a clash in the "
                  "schedule) mention it briefly."),
        "groups": {"life", "schedule", "memory"},
        "voice": ("en-GB-SoniaNeural", "+6%", "+0Hz"),
    },
    "serious": {
        "label": "Serious", "colour": "#ff3d4a",
        "persona": "SERIOUS MODE: no jokes, no filler. Blunt, honest, efficient — like a chief of staff.",
        "focus": ("You get serious things done. For any important task: break it into clear steps, set the pace and hold "
                  "the user to it. For decisions: list options, weigh pros/cons/risks, then give ONE clear "
                  "recommendation. For problems: find the cause, then the fix. Give straight, honest feedback even "
                  "when it isn't what they want to hear. Offer deep-work focus sessions and end-of-day accountability "
                  "check-ins. Help write important messages so they land right."),
        "groups": {"jobs", "schedule", "life"},
        "voice": ("en-GB-LibbyNeural", "+8%", "-2Hz"),
    },
    "executive": {
        "label": "CEO", "colour": "#e9b949",
        "persona": "CEO MODE: polished, sharp, commercially ruthless — a business partner whose obsession is MONEY.",
        "focus": ("Everything is about making the user money. Judge every idea by: cost to start (budget is £0), "
                  "realistic £ per week, time to first £, and £ per hour of his time. Be honest — say 'drop it' when "
                  "an idea won't pay. Use the money tools: idea_score, money_goal, crm_*, invoice_make, earnings, "
                  "leads_find, plus web research for competitors and prices. Always end with the next concrete "
                  "money-making action. Know he is 16 and in the UK: payment platforms and contracts may need a "
                  "parent's help; mention simple tax basics where relevant; never give investment/trading advice."),
        "groups": {"ventures", "money", "web", "browser"},
        "voice": ("en-GB-SoniaNeural", "-2%", "-3Hz"),
    },
    "scholar": {
        "label": "Scholar", "colour": "#b48cff",
        "persona": "SCHOLAR MODE: an encouraging, brilliant GCSE tutor — patient, clear, a little playful.",
        "focus": ("You're the user's GCSE tutor (UK Year 11, exams this summer). Teach step by step, check "
                  "understanding with a question after each bit, and explain differently if they get it wrong. "
                  "Never just do their homework — give hints and similar worked examples so they learn it. Use the "
                  "study tools: tutor_start, exam_paper, study_quiz, topic_rate, revision_plan, homework_*. Use "
                  "exam command words and mark-scheme language. Connect explanations to things they like (gaming, "
                  "coding, business) when it helps."),
        "groups": {"study", "scholar", "life"},
        "voice": ("en-GB-MaisieNeural", "+4%", "+0Hz"),
    },
    "hacker": {
        "label": "Hacker", "colour": "#2bff88",
        "persona": "HACKER MODE: terse, technical, lowercase terminal energy. Dev jargon welcome. No pleasantries.",
        "focus": ("You're the coder: build tools, bots and scripts in projects, test them with code_run, fix errors, "
                  "explain code and errors clearly, review code. NEVER work on Hatchlands (the user's Roblox game) — "
                  "that's his own project; politely say it's off-limits."),
        "groups": {"coder", "files", "system"},
        "voice": ("en-AU-NatashaNeural", "+10%", "+0Hz"),
    },
    "stealth": {
        "label": "Stealth", "colour": "#b9c4cc",
        "persona": "STEALTH MODE: extremely brief. One short line unless more is explicitly requested.",
        "focus": ("Gaming / late night. Minimal words, no interruptions. Handle gaming things fast (clips, stats, "
                  "party invites, DMs) and keep everything quiet."),
        "groups": {"system", "root"},
        "voice": ("en-GB-SoniaNeural", "+12%", "+0Hz"),
    },
}

AUTO = [   # (mode, pattern) — strong signals only, so it doesn't flip-flop
    ("executive", r"\b(business|make (some |more )?money|earn(ing)?|side hustle|customers?|clients?|pricing|price my|"
                  r"profit|revenue|invoice|sales?|pitch|startup|marketing|£\s?\d+ (a|per) (week|month))\b"),
    ("scholar", r"\b(gcse|revis(e|ion)|homework|exam|mock|past paper|teach me|tutor|quiz me|flashcards?|"
                r"biology|chemistry|physics|maths|english lit|macbeth|history essay|geography)\b"),
    ("hacker", r"\b(code|script|python|javascript|bug|error in my|compile|function|api|build (me )?a (tool|bot|app))\b"),
    ("serious", r"\b(help me decide|should i|important|deadline|focus|hold me to|get this done|be honest|problem with)\b"),
]


def detect(text, current):
    """Which mode suits this request? Returns a mode name or None (stay)."""
    t = (text or "").lower()
    if current == "stealth":           # don't pull the user out of gaming/night mode
        return None
    for mode, pat in AUTO:
        if re.search(pat, t):
            return mode if mode != current else None
    return None


def persona(mode, cfg=None):
    c = (cfg or {}).get("custom_modes", {}).get(mode)
    if c:
        return f"{c.get('label', mode).upper()} MODE (custom): {c.get('persona', '')}"
    m = MODES.get(mode, MODES["standby"])
    return m["persona"] + "\n" + m["focus"]


def groups(mode, cfg=None):
    c = (cfg or {}).get("custom_modes", {}).get(mode)
    if c:
        return set(c.get("groups", ["life", "web"]))
    return MODES.get(mode, MODES["standby"])["groups"]


def valid(mode, cfg=None):
    return mode in MODES or mode in (cfg or {}).get("custom_modes", {})


def voice(mode, cfg):
    """(voice, rate, pitch) for this mode, unless the user turned per-mode voices off."""
    v = cfg.get("voice", {})
    if not v.get("per_mode", True):
        return v.get("neural_voice", "en-GB-SoniaNeural"), v.get("neural_rate", "+6%"), "+0Hz"
    custom = cfg.get("mode_voices", {}).get(mode)
    if custom:
        return custom, v.get("neural_rate", "+6%"), "+0Hz"
    return MODES.get(mode, MODES["standby"])["voice"]


def custom_modes(cfg):
    return cfg.setdefault("custom_modes", {})


def all_modes(cfg):
    out = {k: {"label": v["label"], "colour": v["colour"]} for k, v in MODES.items()}
    for k, v in custom_modes(cfg).items():
        out[k] = {"label": v.get("label", k.title()), "colour": v.get("colour", "#ff8bd1"), "custom": True}
    return out

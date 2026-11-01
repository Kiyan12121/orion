"""Tier 1: instant commands that need no AI at all. Works offline, answers in milliseconds."""
import re

FILLER = re.compile(r"^(hey |ok |okay )?(orion[, ]+)?(can you |could you |please |pls )*", re.I)


def _clean(text, name):
    t = text.strip().rstrip(".!?")
    t = re.sub(rf"^(hey |ok |okay )?{re.escape(name)}[,!.:]?\s*", "", t, flags=re.I)
    t = FILLER.sub("", t)
    t = re.sub(r"\s+(please|pls|for me)$", "", t, flags=re.I)
    return t.strip()


# (pattern, tool, args-builder, reply-builder)
RULES = [
    (r"^(check|read|show|any)( my| new| for)*( root)? (messages|dms|inbox|msgs)( on root)?$|^check root$|^(do i have|have i got|got) any (new )?(messages|dms)$",
     "root_check_messages", lambda m: {}, None),
    (r"^(i'?m|i am|going|set me|put me) (as )?(afk|away)( (until|till|for|back) (.+))?$",
     "root_afk", lambda m: {"on": True, "note": (m.group(4) or "").strip()}, None),
    (r"^(i'?m|i am) back$|^(turn )?afk( mode)? off$|^stop afk$", "root_afk", lambda m: {"on": False}, None),
    (r"^(turn )?gaming mode (on|off)$|^(enable|disable|start|stop) gaming mode$", "gaming_mode",
     lambda m: {"on": not re.search(r"off|disable|stop", m.group(0))}, None),
    (r"^(what('s| is) )?(on )?(my )?(schedule|plans?|agenda)( today| for today)?$|^what('s| is) on today$",
     "schedule_list", lambda m: {"days": 1}, lambda r, m: re.sub(r" \[id \w+\]", "", r) if r != "Nothing scheduled." else "Your schedule is clear today."),
    (r"^(switch to |activate |engage |enable |go )?(standby|serious|stealth|executive|hacker)( mode)?$",
     "set_theme", lambda m: {"mode": m.group(2)}, None),
    (r"^(clip that|clip it|save that|record that)$", "clip_that", lambda m: {}, None),
    (r"^(find|ring|where'?s|where is) my phone\??$", "find_my_phone", lambda m: {}, None),
    (r"^undo( that| last change| the last change)?$", "undo_last_change", lambda m: {}, None),
    (r"^(open|go to|visit) (the )?(website|site|url|link|page) (\S+)$", "open_website",
     lambda m: {"url_or_query": m.group(4), "show": True}, lambda r, m: "Opening it now."),
    (r"^(open|launch|start|run) (?!a |the file|my file)((?:(?! and | then | to | with | in ).){2,40})$",
     "open_app",
     lambda m: {"name": m.group(2)}, None),
    (r"^(turn (the )?)?(volume|sound) up$|^louder$", "media",
     lambda m: {"action": "volume_up"}, lambda r, m: "Volume up."),
    (r"^(turn (the )?)?(volume|sound) down$|^quieter$", "media",
     lambda m: {"action": "volume_down"}, lambda r, m: "Volume down."),
    (r"^(mute|unmute)( (the )?(volume|sound))?$", "media",
     lambda m: {"action": "mute"}, lambda r, m: "Toggled mute."),
    (r"^(pause|play|resume)( (the )?(music|song|video))?$", "media",
     lambda m: {"action": "play_pause"}, lambda r, m: "Done."),
    (r"^(next|skip)( (song|track))?$", "media",
     lambda m: {"action": "next"}, lambda r, m: "Skipping."),
    (r"^(previous|last|go back)( (song|track))?$", "media",
     lambda m: {"action": "previous"}, lambda r, m: "Previous track."),
    (r"^(what('s| is) the )?time( is it)?$|^what time is it$", "get_time",
     lambda m: {}, lambda r, m: f"It's {r.split(', ')[-1]}."),
    (r"^(what('s| is) the |today'?s )?date( today)?$|^what day is it$", "get_time",
     lambda m: {}, lambda r, m: f"It's {r.rsplit(',', 1)[0]}."),
    (r"^(system )?(status|stats|diagnostics)$|^how('s| is) (my |the )?(pc|computer) doing$",
     "system_status", lambda m: {}, lambda r, m: r),
    (r"^lock( (my |the )?(pc|computer|screen))?$", "lock_pc",
     lambda m: {}, lambda r, m: "Locking up."),
    (r"^(take a |save a )?screenshot$", "save_screenshot",
     lambda m: {}, lambda r, m: "Screenshot taken. " + r),
    (r"^(set a )?timer (for )?(\d+(\.\d+)?) ?(min|mins|minutes|m)$", "set_timer",
     lambda m: {"minutes": float(m.group(3)), "label": "Timer"}, None),
]


def match(text, name="ORION"):
    """Returns (tool_name, args, reply_fn) or None."""
    t = _clean(text, name)
    for pattern, tool_name, args_fn, reply_fn in RULES:
        m = re.match(pattern, t, re.I)
        if m:
            return tool_name, args_fn(m), (lambda r, m=m, fn=reply_fn: fn(r, m) if fn else r)
    return None

"""Skill Library — hundreds of ready-made skills ORION can use (and you can run directly with /name).

Two kinds:
  • local  — instant tools that run on the PC/phone with no AI (calculators, converters, generators…)
  • prompt — expert playbooks: ORION runs your input through a specialist set of instructions
The brain only sees two tools (skill_find / skill_use), so a big library never slows it down.
"""
import base64
import datetime as dt
import hashlib
import json
import math
import random
import re
import secrets
import string

from .tools import CTX, tool

SKILLS = {}


def _add(name, title, cat, desc, prompt=None, fn=None, example="", tier="smart"):
    SKILLS[name] = {"name": name, "title": title, "cat": cat, "desc": desc, "kind": "local" if fn else "prompt",
                    "prompt": prompt, "fn": fn, "example": example, "tier": tier}


def _nums(t):
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*(?:e-?\d+)?", t or "")]


def _money(x):
    return f"£{x:,.2f}"


# =============================================================================== LOCAL (instant) skills
def _convert(t):
    t = (t or "").lower()
    m = re.search(r"(-?[\d.]+)\s*([a-z°/ ]+?)\s+(?:to|in|into)\s+([a-z°/ ]+)$", t.strip())
    if not m:
        return "Try: '5 miles to km', '30 c to f', '2 kg to lb', '500 ml to cups'."
    v, a, b = float(m.group(1)), m.group(2).strip(), m.group(3).strip()
    temps = {"c": "c", "°c": "c", "celsius": "c", "f": "f", "°f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}
    if a in temps and b in temps:
        c = {"c": v, "f": (v - 32) * 5 / 9, "k": v - 273.15}[temps[a]]
        out = {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[temps[b]]
        return f"{v:g} {a} = {out:.2f} {b}"
    U = {  # to base units: metres, kg, litres, seconds, bytes, m/s
        "mm": ("l", .001), "cm": ("l", .01), "m": ("l", 1), "metre": ("l", 1), "metres": ("l", 1), "km": ("l", 1000),
        "in": ("l", .0254), "inch": ("l", .0254), "inches": ("l", .0254), "ft": ("l", .3048), "foot": ("l", .3048),
        "feet": ("l", .3048), "yd": ("l", .9144), "yard": ("l", .9144), "yards": ("l", .9144), "mile": ("l", 1609.344),
        "miles": ("l", 1609.344), "g": ("w", .001), "gram": ("w", .001), "grams": ("w", .001), "kg": ("w", 1),
        "lb": ("w", .45359237), "lbs": ("w", .45359237), "pound": ("w", .45359237), "pounds": ("w", .45359237),
        "oz": ("w", .028349523), "stone": ("w", 6.35029318), "st": ("w", 6.35029318), "tonne": ("w", 1000),
        "ml": ("v", .001), "l": ("v", 1), "litre": ("v", 1), "litres": ("v", 1), "cup": ("v", .2365882),
        "cups": ("v", .2365882), "pint": ("v", .56826125), "pints": ("v", .56826125), "gallon": ("v", 4.54609),
        "gallons": ("v", 4.54609), "tsp": ("v", .00492892), "tbsp": ("v", .0147868),
        "s": ("t", 1), "sec": ("t", 1), "seconds": ("t", 1), "min": ("t", 60), "mins": ("t", 60), "minutes": ("t", 60),
        "h": ("t", 3600), "hr": ("t", 3600), "hours": ("t", 3600), "day": ("t", 86400), "days": ("t", 86400),
        "week": ("t", 604800), "weeks": ("t", 604800), "year": ("t", 31557600), "years": ("t", 31557600),
        "b": ("d", 1), "kb": ("d", 1e3), "mb": ("d", 1e6), "gb": ("d", 1e9), "tb": ("d", 1e12),
        "mph": ("s", .44704), "kmh": ("s", 1 / 3.6), "km/h": ("s", 1 / 3.6), "kph": ("s", 1 / 3.6), "m/s": ("s", 1)}
    if a not in U or b not in U:
        return f"I don't know the unit '{a if a not in U else b}'."
    if U[a][0] != U[b][0]:
        return "Those units measure different things."
    return f"{v:g} {a} = {v * U[a][1] / U[b][1]:.4g} {b}"


def _percent(t):
    n = _nums(t)
    low = (t or "").lower()
    if "out of" in low and len(n) >= 2:
        return f"{n[0]:g} out of {n[1]:g} = {n[0] / n[1] * 100:.2f}%"
    if "of" in low and len(n) >= 2:
        return f"{n[0]:g}% of {n[1]:g} = {n[0] / 100 * n[1]:.4g}"
    if ("change" in low or "from" in low) and len(n) >= 2:
        return f"From {n[0]:g} to {n[1]:g} is a {(n[1] - n[0]) / n[0] * 100:+.2f}% change"
    if len(n) >= 2:
        return f"{n[0]:g} is {n[0] / n[1] * 100:.2f}% of {n[1]:g}"
    return "Try '15% of 80', '24 out of 30', or 'change from 50 to 65'."


def _discount(t):
    n = _nums(t)
    if len(n) < 2:
        return "Try 'price 40, 25% off'."
    p, d = n[0], n[1]
    return f"{_money(p)} with {d:g}% off = {_money(p * (1 - d / 100))} (you save {_money(p * d / 100)})"


def _vat(t):
    n = _nums(t)
    if not n:
        return "Give a price, e.g. '120 add vat' or '144 remove vat'."
    p = n[0]
    if "remove" in (t or "").lower() or "inc" in (t or "").lower():
        return f"{_money(p)} incl. VAT → {_money(p / 1.2)} before VAT (VAT {_money(p - p / 1.2)})"
    return f"{_money(p)} + 20% VAT = {_money(p * 1.2)} (VAT {_money(p * .2)})"


def _compound(t):
    n = _nums(t)
    if len(n) < 3:
        return "Try 'start 100, monthly 20, 5% for 3 years'."
    start, monthly = n[0], (n[1] if len(n) >= 4 else 0)
    rate, years = (n[2], n[3]) if len(n) >= 4 else (n[1], n[2])
    bal = start
    for _ in range(int(years * 12)):
        bal = bal * (1 + rate / 100 / 12) + monthly
    put_in = start + monthly * int(years * 12)
    return f"After {years:g} years: {_money(bal)} (you put in {_money(put_in)}, growth {_money(bal - put_in)})"


def _goal(t):
    n = _nums(t)
    if len(n) < 2:
        return "Try 'save 500 in 20 weeks' or 'save 300 by 2027-03-01, have 40'."
    target = n[0]
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    have = n[-1] if "have" in t.lower() else 0
    if m:
        weeks = max(1, (dt.date.fromisoformat(m.group(1)) - dt.date.today()).days / 7)
    else:
        weeks = n[1] * (4.345 if "month" in t.lower() else 1)
    need = max(0, target - have)
    return f"Save {_money(need / weeks)} a week ({_money(need / weeks * 4.345)} a month) to reach {_money(target)} in {weeks:.0f} weeks."


def _split(t):
    n = _nums(t)
    if len(n) < 2:
        return "Try '48.60 between 4' (add '10% tip' if you like)."
    total, people = n[0], max(1, int(n[1]))
    tip = n[2] if len(n) > 2 else 0
    each = total * (1 + tip / 100) / people
    return f"{_money(total)}{f' + {tip:g}% tip' if tip else ''} ÷ {people} = {_money(each)} each"


def _hourly(t):
    n = _nums(t)
    if len(n) < 2:
        return "Try 'earned 60 in 4.5 hours'."
    return f"{_money(n[0])} for {n[1]:g} hours = {_money(n[0] / n[1])}/hour"


def _breakeven(t):
    n = _nums(t)
    if len(n) < 3:
        return "Try 'fixed 200, cost per item 3, price 8'."
    fixed, var, price = n[0], n[1], n[2]
    if price <= var:
        return "You lose money on every sale — the price must be above the cost per item."
    units = math.ceil(fixed / (price - var))
    return f"Break-even: {units} sales (profit per sale {_money(price - var)}); after that every sale is profit."


def _days_until(t):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t or "")
    if not m:
        m2 = re.search(r"(\d{1,2})[/ ](\d{1,2})(?:[/ ](\d{2,4}))?", t or "")
        if not m2:
            return "Give a date like 2027-05-14 or 14/5."
        y = int(m2.group(3)) if m2.group(3) else dt.date.today().year
        y = y + 2000 if y < 100 else y
        d = dt.date(y, int(m2.group(2)), int(m2.group(1)))
        if not m2.group(3) and d < dt.date.today():
            d = d.replace(year=y + 1)
    else:
        d = dt.date.fromisoformat(m.group(1))
    days = (d - dt.date.today()).days
    school = sum(1 for k in range(max(0, days)) if (dt.date.today() + dt.timedelta(days=k + 1)).weekday() < 5)
    return f"{d.strftime('%a %d %b %Y')} is {days} days away ({days // 7} weeks {days % 7} days, ~{school} weekdays)."


def _age(t):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t or "")
    if not m:
        return "Give a date like 2010-06-01."
    b = dt.date.fromisoformat(m.group(1))
    today = dt.date.today()
    years = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    nxt = b.replace(year=today.year)
    if nxt < today:
        nxt = nxt.replace(year=today.year + 1)
    return f"{years} years old · {(today - b).days:,} days · next birthday in {(nxt - today).days} days"


def _timezone(t):
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        return "Time zones need Python 3.9+."
    z = {"london": "Europe/London", "uk": "Europe/London", "new york": "America/New_York", "ny": "America/New_York",
         "la": "America/Los_Angeles", "los angeles": "America/Los_Angeles", "tokyo": "Asia/Tokyo", "paris": "Europe/Paris",
         "berlin": "Europe/Berlin", "sydney": "Australia/Sydney", "dubai": "Asia/Dubai", "india": "Asia/Kolkata",
         "delhi": "Asia/Kolkata", "toronto": "America/Toronto", "chicago": "America/Chicago", "lagos": "Africa/Lagos",
         "madrid": "Europe/Madrid", "beijing": "Asia/Shanghai", "singapore": "Asia/Singapore", "est": "America/New_York",
         "pst": "America/Los_Angeles", "cet": "Europe/Paris", "utc": "UTC"}
    low = (t or "").lower()
    places = [k for k in z if re.search(rf"\b{re.escape(k)}\b", low)]
    if not places:
        return "Try 'time in tokyo' or '7pm london in new york'."
    tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
    src = ZoneInfo(z[places[0]]) if len(places) > 1 else ZoneInfo("Europe/London")
    dst = ZoneInfo(z[places[-1]])
    if tm and (tm.group(3) or tm.group(2)):
        h = int(tm.group(1)) % 12 + (12 if tm.group(3) == "pm" else 0) if tm.group(3) else int(tm.group(1))
        base = dt.datetime.now(src).replace(hour=h, minute=int(tm.group(2) or 0), second=0, microsecond=0)
    else:
        base = dt.datetime.now(src)
    return f"{base.strftime('%H:%M %a')} ({src.key}) = {base.astimezone(dst).strftime('%H:%M %a')} in {dst.key}"


def _password(t):
    n = _nums(t)
    length = int(n[0]) if n else 16
    length = max(8, min(length, 64))
    alpha = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"
    if "words" in (t or "").lower() or "passphrase" in (t or "").lower():
        words = ("orbit nova falcon river cobalt ember pixel quartz tiger lunar maple rocket echo atlas jade sonic "
                 "vortex cedar comet raven delta harbor frost glider nimbus onyx prism summit tundra zephyr").split()
        return "-".join(secrets.choice(words) for _ in range(4)) + "-" + str(secrets.randbelow(90) + 10)
    while True:
        p = "".join(secrets.choice(alpha) for _ in range(length))
        if any(c.isdigit() for c in p) and any(c.isupper() for c in p) and any(c in "!@#$%^&*-_=+?" for c in p):
            return p + "\n(Generated on your device — not saved anywhere. Put it in a password manager.)"


def _pick(t):
    items = [x.strip() for x in re.split(r",|\bor\b|\n", t or "") if x.strip()]
    if len(items) < 2:
        return "Give me options separated by commas or 'or'."
    return f"🎲 {random.choice(items)}"


def _dice(t):
    m = re.search(r"(\d*)d(\d+)", (t or "").lower())
    if "coin" in (t or "").lower():
        return random.choice(["Heads", "Tails"])
    n, s = (int(m.group(1) or 1), int(m.group(2))) if m else (1, 6)
    rolls = [random.randint(1, s) for _ in range(min(n, 50))]
    return f"🎲 {rolls} = {sum(rolls)}"


def _wordcount(t):
    t = t or ""
    words = len(re.findall(r"\b[\w'’-]+\b", t))
    sents = max(1, len(re.findall(r"[.!?]+", t)))
    return (f"{words} words · {len(t)} characters ({len(t.replace(' ', ''))} without spaces) · {sents} sentences · "
            f"~{max(1, round(words / 230))} min to read · ~{max(1, round(words / 140))} min to say out loud")


def _case(t):
    t = t or ""
    title = " ".join(w.capitalize() for w in t.split())
    snake = re.sub(r"\W+", "_", t.strip().lower()).strip("_")
    camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), snake)
    return f"UPPER: {t.upper()}\nlower: {t.lower()}\nTitle: {title}\nsnake_case: {snake}\ncamelCase: {camel}\nkebab-case: {snake.replace('_', '-')}"


def _b64(t):
    t = (t or "").strip()
    if t.lower().startswith("decode "):
        try:
            return base64.b64decode(t[7:].strip()).decode("utf-8", "replace")
        except Exception:
            return "That isn't valid base64."
    return base64.b64encode(t.removeprefix("encode ").encode()).decode()


def _hash(t):
    b = (t or "").encode()
    return f"SHA-256: {hashlib.sha256(b).hexdigest()}\nMD5: {hashlib.md5(b).hexdigest()}"


def _json(t):
    try:
        return "Valid JSON ✓\n" + json.dumps(json.loads(t), indent=2, ensure_ascii=False)[:3500]
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}"


def _colour(t):
    t = (t or "").strip()
    m = re.search(r"#?([0-9a-fA-F]{6})\b", t)
    if m:
        h = m.group(1)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{h.upper()} = rgb({r}, {g}, {b})"
    n = [int(x) for x in _nums(t)][:3]
    if len(n) == 3:
        return f"rgb({n[0]}, {n[1]}, {n[2]}) = #{n[0]:02X}{n[1]:02X}{n[2]:02X}"
    return "Give a hex like #3fd8ff or rgb like 63 216 255."


def _base(t):
    t = (t or "").strip().lower()
    try:
        if t.startswith("0b") or re.fullmatch(r"[01]{5,}", t):
            v = int(t, 2) if not t.startswith("0b") else int(t[2:], 2)
        elif t.startswith("0x") or re.fullmatch(r"[0-9a-f]*[a-f][0-9a-f]*", t):
            v = int(t.removeprefix("0x"), 16)
        else:
            v = int(_nums(t)[0])
    except Exception:
        return "Give a number: 42, 0b101010 or 0x2a."
    return f"Decimal {v} · Binary {bin(v)[2:]} · Hex {hex(v)[2:].upper()} · Octal {oct(v)[2:]}"


def _roman(t):
    t = (t or "").strip().upper()
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
            (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    if re.fullmatch(r"[MDCLXVI]+", t):
        n, i = 0, 0
        for v, s in vals:
            while t[i:i + len(s)] == s:
                n += v
                i += len(s)
        return f"{t} = {n}"
    n = int(_nums(t)[0]) if _nums(t) else 0
    if not 0 < n < 4000:
        return "Give a number from 1 to 3999, or a Roman numeral."
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _primes(t):
    n = int(_nums(t)[0]) if _nums(t) else 0
    if n < 2:
        return "Give a whole number above 1."
    f, x, d = [], n, 2
    while d * d <= x:
        while x % d == 0:
            f.append(d)
            x //= d
        d += 1
    if x > 1:
        f.append(x)
    return f"{n} is {'prime ✓' if f == [n] else 'not prime'} · prime factors: {' × '.join(map(str, f))}"


def _hcf(t):
    n = [int(x) for x in _nums(t)]
    if len(n) < 2:
        return "Give two or more whole numbers."
    h = n[0]
    lc = n[0]
    for x in n[1:]:
        h = math.gcd(h, x)
        lc = lc * x // math.gcd(lc, x)
    return f"HCF = {h} · LCM = {lc}"


def _quadratic(t):
    n = _nums(t)
    if len(n) < 3:
        return "Give a, b and c for ax² + bx + c = 0, e.g. '1 -5 6'."
    a, b, c = n[:3]
    if a == 0:
        return f"Not quadratic — x = {-c / b:.4g}" if b else "No x term."
    disc = b * b - 4 * a * c
    vx = -b / (2 * a)
    tp = f"Turning point: ({vx:.4g}, {a * vx * vx + b * vx + c:.4g})"
    if disc < 0:
        return f"Discriminant {disc:g} < 0 → no real roots. {tp}"
    r1, r2 = (-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a)
    if disc == 0:
        return f"x = {r1:.4g} (repeated root)\n{tp}"
    return (f"x = {r1:.4g} or x = {r2:.4g}\nWorking: x = (−b ± √(b²−4ac)) / 2a = ({-b:g} ± √{disc:g}) / {2 * a:g}\n{tp}")


def _simul(t):
    n = _nums(t)
    if len(n) < 6:
        return "Give a1 b1 c1 a2 b2 c2 for a1x + b1y = c1 and a2x + b2y = c2, e.g. '2 3 13 1 -1 -1'."
    a1, b1, c1, a2, b2, c2 = n[:6]
    det = a1 * b2 - a2 * b1
    if det == 0:
        return "No single solution (the lines are parallel or the same)."
    return f"x = {(c1 * b2 - c2 * b1) / det:.4g}, y = {(a1 * c2 - a2 * c1) / det:.4g}"


def _pythag(t):
    n = _nums(t)
    if len(n) < 2:
        return "Give two sides, e.g. '3 4' (legs) or 'hyp 13 side 5'."
    if "hyp" in (t or "").lower():
        h, s = max(n[:2]), min(n[:2])
        return f"Missing side = √({h:g}² − {s:g}²) = {math.sqrt(h * h - s * s):.4g}"
    return f"Hypotenuse = √({n[0]:g}² + {n[1]:g}²) = {math.hypot(n[0], n[1]):.4g}"


def _sdt(t):
    low = (t or "").lower()
    n = _nums(t)
    if len(n) < 2:
        return "Give two of speed/distance/time, e.g. 'distance 12 km time 0.5 h'."
    if "speed" in low and "distance" in low:
        return f"Time = distance ÷ speed = {n[1] / n[0] if low.index('speed') < low.index('distance') else n[0] / n[1]:.4g}"
    if "distance" in low and "time" in low:
        d, tm = (n[0], n[1]) if low.index("distance") < low.index("time") else (n[1], n[0])
        return f"Speed = distance ÷ time = {d / tm:.4g}"
    if "speed" in low and "time" in low:
        return f"Distance = speed × time = {n[0] * n[1]:.4g}"
    return "Say which two you know (speed, distance, time)."


def _ohm(t):
    low = (t or "").lower()
    v = re.search(r"(-?[\d.]+)\s*v\b", low)
    i = re.search(r"(-?[\d.]+)\s*a\b", low)
    r = re.search(r"(-?[\d.]+)\s*(ohm|Ω)", low)
    if v and i:
        V, I = float(v.group(1)), float(i.group(1))
        return f"R = V ÷ I = {V / I:.4g} Ω · P = V × I = {V * I:.4g} W"
    if v and r:
        V, R = float(v.group(1)), float(r.group(1))
        return f"I = V ÷ R = {V / R:.4g} A · P = V²/R = {V * V / R:.4g} W"
    if i and r:
        I, R = float(i.group(1)), float(r.group(1))
        return f"V = I × R = {I * R:.4g} V · P = I²R = {I * I * R:.4g} W"
    return "Give two of: volts (12 V), amps (2 A), ohms (6 ohm)."


def _energycost(t):
    n = _nums(t)
    if len(n) < 2:
        return "Try '300 W for 4 hours' (add 'at 25p' for your price per kWh)."
    w, h = n[0], n[1]
    p = n[2] if len(n) > 2 else 24.5
    kwh = w / 1000 * h
    return f"{kwh:.2f} kWh ≈ {kwh * p:.1f}p (at {p:g}p/kWh) · per month if daily: {_money(kwh * p * 30 / 100)}"


def _density(t):
    n = _nums(t)
    if len(n) < 2:
        return "Give mass and volume, e.g. 'mass 200 g volume 50 cm3'."
    return f"Density = mass ÷ volume = {n[0] / n[1]:.4g} (units: mass unit per volume unit)"


def _grade(t):
    n = _nums(t)
    if not n:
        return "Give a score like '54/80' or '68%'."
    pct = n[0] / n[1] * 100 if len(n) > 1 and n[1] > 0 else n[0]
    from .scholar import grade_for
    return f"{pct:.0f}% ≈ grade {grade_for(pct)} (rough guide — real boundaries change every year)"


def _lines(t):
    rows = [r for r in (t or "").splitlines() if r.strip()]
    uniq = list(dict.fromkeys(rows))
    return f"{len(rows)} lines, {len(uniq)} unique.\n\nSorted (no duplicates):\n" + "\n".join(sorted(uniq, key=str.lower))


def _morse(t):
    M = {'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.', 'g': '--.', 'h': '....', 'i': '..',
         'j': '.---', 'k': '-.-', 'l': '.-..', 'm': '--', 'n': '-.', 'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.',
         's': '...', 't': '-', 'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-', 'y': '-.--', 'z': '--..',
         '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....', '6': '-....',
         '7': '--...', '8': '---..', '9': '----.'}
    t = (t or "").strip()
    if set(t) <= set(".-/ "):
        R = {v: k for k, v in M.items()}
        return " ".join("".join(R.get(c, "?") for c in w.split()) for w in t.split("/")).upper()
    return " / ".join(" ".join(M.get(c, "") for c in w) for w in t.lower().split())


def _nato(t):
    N = "Alfa Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliett Kilo Lima Mike November Oscar Papa Quebec " \
        "Romeo Sierra Tango Uniform Victor Whiskey X-ray Yankee Zulu".split()
    return " · ".join(N[ord(c) - 97] if c.isalpha() and c.isascii() else c for c in (t or "").lower() if c.strip())


def _regex(t):
    m = re.match(r"\s*/(.+)/([a-z]*)\s+(.+)$", t or "", re.S)
    if not m:
        return "Format: /pattern/flags text to test — e.g. /\\d+/ there are 3 cats and 12 dogs"
    flags = re.I if "i" in m.group(2) else 0
    try:
        hits = re.findall(m.group(1), m.group(3), flags | re.M)
    except re.error as e:
        return f"Pattern error: {e}"
    return f"{len(hits)} match(es): {hits[:30]}"


def _pomodoro(t):
    n = _nums(t)
    total = int(n[0]) if n else 120
    if "hour" in (t or "").lower() and n and n[0] < 10:
        total = int(n[0] * 60)
    plan, mins, k = [], 0, 1
    start = dt.datetime.now().replace(second=0, microsecond=0)
    while mins + 25 <= total:
        s = start + dt.timedelta(minutes=mins)
        plan.append(f"{s:%H:%M} focus #{k} (25)")
        mins += 25
        brk = 15 if k % 4 == 0 else 5
        if mins + brk < total:
            plan.append(f"{start + dt.timedelta(minutes=mins):%H:%M} break ({brk})")
        mins += brk
        k += 1
    return "\n".join(plan) or "Give at least 25 minutes."


def _revsplit(t):
    n = _nums(t)
    subj = [s.strip() for s in re.split(r",|\n", re.sub(r"[\d.]+\s*(hours?|hrs?|h|mins?|minutes?)", "", t or "")) if s.strip()]
    total = (n[0] * 60 if n and n[0] < 12 else (n[0] if n else 120))
    if not subj:
        return "Give subjects and time: 'maths, physics, english 2 hours'."
    each = total / len(subj)
    return "\n".join(f"{s}: {each:.0f} min" for s in subj) + f"\n(total {total:.0f} min — put the hardest first)"


def _ride(t):
    n = _nums(t)
    if not n:
        return "Give a distance: '3.2 km' or '2 miles'."
    km = n[0] * (1.609 if "mile" in (t or "").lower() else 1)
    return f"{km:.1f} km by bike ≈ {km / 16 * 60:.0f} min at a steady 16 km/h (≈{km / 22 * 60:.0f} min fast, {km / 12 * 60:.0f} min easy)"


def _readtime(t):
    w = len((t or "").split())
    return f"{w} words: ~{max(1, round(w / 230))} min reading · ~{max(1, round(w / 140))} min as a speech"


for args in [
    ("convert", "Unit converter", "Tools", "Convert lengths, weights, volumes, temps, times, data, speeds.", _convert, "5 miles to km"),
    ("percent", "Percentages", "Tools", "X% of Y, X out of Y, percentage change.", _percent, "24 out of 30"),
    ("discount", "Discount calculator", "Money", "Price after a % off.", _discount, "price 40, 25% off"),
    ("vat", "VAT calculator", "Money", "Add or remove UK VAT (20%).", _vat, "120 add vat"),
    ("compound", "Savings growth", "Money", "Compound interest with monthly top-ups.", _compound, "start 100, monthly 20, 5% for 3 years"),
    ("savegoal", "Savings goal planner", "Money", "How much to save per week/month to hit a target.", _goal, "save 500 in 20 weeks"),
    ("splitbill", "Split the bill", "Money", "Split a total between people (with tip).", _split, "48.60 between 4, 10% tip"),
    ("hourly", "£ per hour", "Money", "What you earned per hour.", _hourly, "earned 60 in 4.5 hours"),
    ("breakeven", "Break-even", "Money", "Sales needed to cover your costs.", _breakeven, "fixed 200, cost per item 3, price 8"),
    ("daysuntil", "Days until", "Tools", "Countdown to a date (with weekdays).", _days_until, "2027-05-14"),
    ("age", "Age calculator", "Tools", "Exact age and next birthday.", _age, "2010-06-01"),
    ("timezone", "Time zones", "Tools", "Convert times between cities.", _timezone, "7pm london in new york"),
    ("password", "Password generator", "Tools", "Strong passwords or passphrases (made locally, never saved).", _password, "20"),
    ("pick", "Decide for me", "Tools", "Pick randomly from options.", _pick, "pizza, burger or tacos"),
    ("dice", "Dice / coin", "Tools", "Roll dice (2d6) or flip a coin.", _dice, "2d6"),
    ("wordcount", "Word counter", "Writing", "Words, characters, sentences, reading & speaking time.", _wordcount, "paste text"),
    ("case", "Text case", "Writing", "UPPER, lower, Title, snake_case, camelCase, kebab-case.", _case, "my cool project"),
    ("base64", "Base64", "Code", "Encode, or 'decode …'.", _b64, "hello"),
    ("hash", "Hash", "Code", "SHA-256 and MD5 of some text.", _hash, "hello"),
    ("json", "JSON check", "Code", "Validate and pretty-print JSON.", _json, '{"a":1}'),
    ("colour", "Colour codes", "Code", "Hex ↔ RGB.", _colour, "#3fd8ff"),
    ("bases", "Number bases", "Code", "Decimal, binary, hex, octal.", _base, "42"),
    ("regex", "Regex tester", "Code", "Test a pattern against text.", _regex, "/\\d+/ 3 cats and 12 dogs"),
    ("roman", "Roman numerals", "Maths", "Numbers ↔ Roman numerals.", _roman, "2027"),
    ("primes", "Prime factors", "Maths", "Is it prime? Prime factor decomposition.", _primes, "360"),
    ("hcf", "HCF & LCM", "Maths", "Highest common factor and lowest common multiple.", _hcf, "24 36"),
    ("quadratic", "Quadratic solver", "Maths", "Roots, working and turning point of ax²+bx+c.", _quadratic, "1 -5 6"),
    ("simultaneous", "Simultaneous equations", "Maths", "Solve two linear equations.", _simul, "2 3 13 1 -1 -1"),
    ("pythagoras", "Pythagoras", "Maths", "Missing side of a right-angled triangle.", _pythag, "3 4"),
    ("sdt", "Speed/distance/time", "Science", "Work out the missing one.", _sdt, "distance 12 time 0.5"),
    ("ohm", "Ohm's law", "Science", "V = IR and power.", _ohm, "12 V 2 A"),
    ("energycost", "Energy cost", "Science", "Cost of running something (W × hours).", _energycost, "300 W for 4 hours"),
    ("density", "Density", "Science", "Density = mass ÷ volume.", _density, "mass 200 volume 50"),
    ("gradecalc", "Score → grade", "School", "Rough GCSE grade from a score.", _grade, "54/80"),
    ("sortlines", "Sort & dedupe lines", "Writing", "Sort a list and remove duplicates.", _lines, "paste a list"),
    ("morse", "Morse code", "Fun", "Text ↔ Morse.", _morse, "sos"),
    ("nato", "NATO alphabet", "Fun", "Spell it out (Alfa, Bravo…).", _nato, "orion"),
    ("pomodoro", "Pomodoro plan", "School", "Focus/break timetable from now.", _pomodoro, "2 hours"),
    ("revsplit", "Split revision time", "School", "Share time across subjects.", _revsplit, "maths, physics, english 2 hours"),
    ("ridetime", "Bike ride time", "Life", "How long a ride takes at different paces.", _ride, "3.2 km"),
    ("readtime", "Reading/speech time", "Writing", "How long text takes to read or say.", _readtime, "paste text"),
]:
    _add(args[0], args[1], args[2], args[3], fn=args[4], example=args[5])

# =============================================================================== PROMPT playbooks
P = [
    # ---- School: English
    ("essayplan", "Essay plan (PEEL)", "School", "Plan an essay: thesis + PEEL paragraphs with quotes to use.",
     "Plan a GCSE essay for the question given. Give a one-line thesis, then 3-4 PEEL paragraphs (Point, Evidence/quote, Explain/analyse with a key word zoom, Link to question + context). End with a conclusion idea. Keep it tight."),
    ("quotes", "Quote bank", "School", "Key short quotes for a text/character/theme, with analysis.",
     "Give 10 short, memorable quotes (max 8 words each) for the text/character/theme given, each with a one-line analysis and the theme it supports. Only real quotes you are confident about; say if unsure."),
    ("poem", "Poem analysis", "School", "Analyse a poem: meaning, language, structure, form, context.",
     "Analyse the poem/extract given for GCSE: overall meaning, 4 language techniques with effect, structure & form choices, context, and a comparison idea with another anthology poem."),
    ("unseen", "Unseen poetry", "School", "Step-by-step approach for an unseen poem.",
     "Walk through the unseen poem given like a top student: first impressions, speaker/situation, 3 key quotes with analysis, structure, a one-sentence 'big idea'."),
    ("creative", "Creative writing boost", "School", "Openings, descriptive techniques and an upgraded paragraph.",
     "For the prompt given, give 3 gripping opening lines, a list of 6 techniques to use (with examples), and an upgraded version of any paragraph provided. Aim for grade 9 description."),
    ("spag", "SPaG fixer", "School", "Fix spelling, punctuation and grammar and explain the rules.",
     "Correct the spelling, punctuation and grammar in the text. Show the corrected text, then list each fix with the rule, briefly."),
    ("languagetech", "Language techniques finder", "School", "Spot techniques in a passage and explain effects.",
     "Find the language techniques in this passage (name, quote, effect on reader). Then say which one is the most powerful and why."),
    ("compare", "Compare two texts", "School", "Comparison plan with connectives and quotes.",
     "Build a comparison of the two texts/poems given: similarities, differences, methods, with comparative connectives and 2 quotes each."),
    ("commandwords", "Command words", "School", "What 'describe/explain/evaluate…' really need for full marks.",
     "Explain exactly what the exam command word(s) given require for full marks, with a short model answer pattern for each."),
    # ---- School: general
    ("explain5", "Explain like I'm 5", "School", "Super-simple explanation with an analogy.",
     "Explain the topic as simply as possible with one everyday analogy, then give the proper GCSE-level version in 3 sentences."),
    ("mnemonic", "Mnemonic maker", "School", "Memorable mnemonics for a list or process.",
     "Create 3 catchy mnemonics (one rude-free funny one) to remember the list/process given. Show what each letter stands for."),
    ("mindmap", "Mind map", "School", "Text mind map of a topic.",
     "Make a text mind map of the topic: central idea, 5-7 branches, 2-4 sub-points each. Use indentation and arrows."),
    ("onepager", "One-page revision sheet", "School", "Everything key on one page.",
     "Make a one-page GCSE revision sheet on the topic: key definitions, key facts/equations, a diagram described in words if useful, 3 exam tips, 3 common mistakes."),
    ("flashcardsfrom", "Flashcards from notes", "School", "Turn notes into Q/A flashcards.",
     "Turn the notes given into 12 short Q → A flashcards. Format: Q: … / A: …"),
    ("examq", "Exam question + mark scheme", "School", "Write an exam-style question with a mark scheme.",
     "Write one realistic GCSE exam question on the topic (with marks), a full mark scheme, and a model answer."),
    ("markscheme", "Mark my answer", "School", "Mark an answer against a mark scheme style.",
     "Mark the student's answer like a GCSE examiner: marks out of the total, what earned marks, what was missing, and a model answer."),
    ("sciencepractical", "Required practical", "School", "Method, variables, risks and results for a required practical.",
     "For the GCSE required practical named: aim, equipment, numbered method, independent/dependent/control variables, risks, expected results, and 3 likely exam questions with answers."),
    ("mathsteps", "Maths step-by-step", "School", "Solve a maths question showing every step.",
     "Solve the maths question showing each step on its own line with the reason. Then give a similar practice question with the answer hidden at the end."),
    ("workedexample", "Worked examples", "School", "Three worked examples, easy → hard.",
     "Give 3 worked examples on the topic, increasing in difficulty, each with full working, then 3 practice questions with answers at the end."),
    ("sourceq", "History source analysis", "School", "NOP: Nature, Origin, Purpose + content + context.",
     "Analyse the historical source using Nature, Origin, Purpose, content and own knowledge; judge its usefulness/reliability with a clear verdict."),
    ("interpretation", "History interpretations", "School", "How/why interpretations differ.",
     "Explain how and why the interpretations differ, which is more convincing, using provenance and knowledge."),
    ("casestudy", "Geography case study", "School", "Case study facts: place, causes, effects, responses.",
     "Give a GCSE geography case study summary for the topic: named place, key facts & figures, causes, effects (social/economic/environmental), responses, evaluation."),
    ("mfltranslate", "French/Spanish helper", "School", "Translate both ways + grammar notes + vocab.",
     "Translate the text (detect French/Spanish/English), then explain any tricky grammar (tenses, agreements) and list 8 useful vocab items."),
    ("speaking", "MFL speaking prep", "School", "Answers for speaking exam questions with opinions & tenses.",
     "Write a strong GCSE speaking answer to the question in the target language, using 3 tenses, opinions with reasons, and a complex structure; then the English meaning."),
    ("tracetable", "Trace table", "School", "Trace an algorithm step by step.",
     "Trace the algorithm/pseudocode given with a trace table (columns for each variable and output). Then say what it does."),
    ("pseudo2py", "Pseudocode → Python", "School", "Convert OCR/AQA pseudocode to Python and explain.",
     "Convert the pseudocode to clean Python 3, then explain each line simply."),
    ("rearguments", "RE arguments", "School", "For/against with religious & non-religious views.",
     "For the RE statement: arguments for and against, Christian and one other religion's views with teachings, a non-religious view, and a justified conclusion."),
    # ---- Future
    ("personalstatement", "College application", "Future", "Sixth form / college personal statement.",
     "Write a strong, honest sixth-form/college personal statement from the details given. Specific, enthusiastic, 250-350 words."),
    ("cv16", "CV (first job)", "Future", "A clean CV for a 16-year-old.",
     "Write a one-page CV for a UK Year 11 student from the details given: profile, skills, experience/projects, education, interests. No made-up facts."),
    ("jobapply", "Part-time job application", "Future", "Application message for a part-time job.",
     "Write a short, professional application message/email for the part-time job given, from a reliable 16-year-old."),
    ("interview", "Interview prep", "Future", "Likely questions with strong answers.",
     "List 10 likely interview questions for the role/course given, each with a strong answer structure (STAR) and an example."),
    ("workexp", "Work experience email", "Future", "Ask a company for work experience.",
     "Write a polite, specific email asking the business for work experience, from a Year 11 student."),
    # ---- Money / CEO
    ("ideacheck", "Business idea check", "Money", "Is it worth doing? Customers, competition, costs, first step.",
     "Assess the business idea for a UK 16-year-old with £0 budget: who pays, how much, competition, risks, a 0-10 score, and the first 3 steps to test it this week for free."),
    ("coldemail", "Cold email / DM pitch", "Money", "Short pitch that gets replies.",
     "Write a cold email AND a short DM pitching the offer to the business given. Personal, specific benefit, one clear call to action, under 120 words. Honest about being a young founder."),
    ("followup", "Follow-up message", "Money", "Polite nudge after no reply.",
     "Write 2 short follow-up messages (day 3 and day 10) for the situation given. Friendly, not pushy."),
    ("salespage", "Sales page copy", "Money", "Headline, benefits, proof, CTA.",
     "Write landing page copy for the product/service: headline, subheadline, 5 benefit bullets, how it works (3 steps), FAQ (4), call to action."),
    ("productdesc", "Product description", "Money", "Descriptions that sell.",
     "Write a punchy product description (short + long version) and 5 SEO keywords for the item given."),
    ("brandname", "Brand names", "Money", "Name ideas with available-sounding domains.",
     "Give 15 brand name ideas for the business, grouped by style, each with a one-line reason and a .com/.co.uk style domain suggestion."),
    ("slogan", "Slogans", "Money", "Taglines.", "Write 12 short slogans/taglines for the brand, from safe to bold."),
    ("pricing", "Pricing strategy", "Money", "Tiers, anchors and what to charge.",
     "Suggest pricing for the offer: 3 tiers with what's included, the anchor, a launch offer, and how to justify the price."),
    ("customerreply", "Customer reply", "Money", "Reply to a customer message or complaint.",
     "Write a calm, professional reply to the customer message that solves the problem and keeps them happy."),
    ("reviewreply", "Review reply", "Money", "Reply to a good or bad review.", "Write a short public reply to the review given — gracious, specific, professional."),
    ("negotiate", "Negotiation script", "Money", "What to say to get a better deal.",
     "Write a negotiation plan and script for the situation: goal, walk-away point, opening line, 3 responses to pushback."),
    ("swot", "SWOT analysis", "Money", "Strengths, weaknesses, opportunities, threats.", "Do a sharp SWOT for the business/idea with 3-5 points each and 3 actions."),
    ("leancanvas", "Lean canvas", "Money", "One-page business model.",
     "Fill a lean canvas for the idea: problem, customer segments, unique value prop, solution, channels, revenue, costs, key metrics, unfair advantage."),
    ("fiverr", "Gig listing", "Money", "Fiverr/Upwork-style gig title, description and packages.",
     "Write a freelance gig listing for the service: title, description, 3 packages with prices, FAQ, tags."),
    ("automationideas", "Automation ideas for a business", "Money", "What a local business could automate.",
     "For the type of local business given, list 8 things they could automate cheaply (bookings, reminders, reviews…), the tool to use, time saved per week, and what to charge to set it up."),
    ("budgetplan", "Monthly budget", "Money", "Simple budget from income and spending.",
     "Make a simple monthly budget from the details: income, needs, wants, savings (50/30/20 adjusted for a teen), and 3 ways to save more."),
    ("invoicewording", "Payment reminder", "Money", "Polite chaser for an unpaid invoice.", "Write a polite but firm payment reminder for the invoice details given."),
    # ---- Content / creator
    ("hooks", "Video hooks", "Content", "Scroll-stopping first lines for TikTok/Shorts.", "Write 12 scroll-stopping hooks (first 2 seconds) for a short video about the topic."),
    ("shortscript", "Short video script", "Content", "30-60s script with hook, beats, CTA.",
     "Write a 45-second TikTok/Shorts script: hook, 4 beats with on-screen text, ending with a call to action. Include shot ideas."),
    ("ytmeta", "YouTube title & description", "Content", "Titles, description, tags, chapters.",
     "For the video described, give 8 click-worthy (honest) titles, a description with chapters, and 15 tags."),
    ("thumbnail", "Thumbnail ideas", "Content", "Thumbnail concepts and text.", "Give 5 thumbnail concepts (composition, expression, 2-4 words of text, colours)."),
    ("contentplan", "Content calendar", "Content", "2 weeks of post ideas.", "Make a 14-day content calendar for the niche: post idea, format, hook, best time to post."),
    ("streamplan", "Stream plan", "Content", "Schedule, titles and segments for streams.",
     "Plan a week of streams for the game/niche: schedule, titles, segment ideas, community goals, and clip-worthy moments to aim for."),
    ("caption", "Captions & hashtags", "Content", "Captions with hashtags.", "Write 5 captions (short/funny/hype) with 10 relevant hashtags for the post described."),
    ("sponsor", "Sponsor pitch", "Content", "Pitch a brand for a small creator deal.", "Write a short, credible sponsorship pitch from a small creator to the brand, with what you offer and a price idea."),
    ("cliptitle", "Clip titles", "Content", "Titles for gaming clips.", "Give 10 titles for the gaming clip described — funny, hype, and searchable."),
    # ---- Code
    ("explaincode", "Explain code", "Code", "What this code does, line by line.", "Explain what the code does: summary, then line-by-line in plain English, then any bugs or risks."),
    ("debug", "Debug an error", "Code", "Find the cause and fix.", "Find the cause of the error/bug given. Explain why it happens, then give the fixed code and how to avoid it next time."),
    ("refactor", "Refactor", "Code", "Cleaner, faster code.", "Refactor the code to be cleaner and clearer without changing behaviour. Explain the changes."),
    ("unittests", "Write tests", "Code", "Unit tests for a function.", "Write thorough unit tests (pytest or the language's norm) for the code, covering edge cases."),
    ("codereview", "Code review", "Code", "Review like a senior dev.", "Review the code: bugs, security, readability, performance. Give a prioritised list with fixes."),
    ("readme", "README writer", "Code", "Project README.", "Write a clear README: what it does, features, install, usage, config, troubleshooting."),
    ("commitmsg", "Commit message", "Code", "Conventional commit messages.", "Write a good commit message (subject ≤ 60 chars + body) for the changes described."),
    ("regexbuild", "Regex builder", "Code", "Build a regex from a description.", "Write a regex for the description, explain each part, and give 3 matching and 3 non-matching examples."),
    ("sql", "SQL helper", "Code", "Write or fix SQL queries.", "Write the SQL query for the request (state assumptions about tables), then explain it."),
    ("luahelp", "Roblox Lua helper", "Code", "Roblox scripting help (Luau).",
     "Help with the Roblox Luau scripting request: explain the approach, give clean commented code, and say where to put it (ServerScriptService etc.). Note any security issues (never trust the client)."),
    ("discordbot", "Discord bot command", "Code", "discord.py / discord.js command code.", "Write the Discord bot command described (discord.py by default) with comments and setup notes."),
    ("powershell", "PowerShell/command explainer", "Code", "Explain or write a terminal command.",
     "Explain the command (or write one for the task). Warn clearly if anything is destructive."),
    ("gitfix", "Git rescue", "Code", "Fix a git problem.", "Explain how to fix the git situation described, step by step, safest option first."),
    ("apiexplain", "API explainer", "Code", "How to use an API with example requests.", "Explain how to use the API/endpoint described with example requests and responses in Python."),
    ("mcplugin", "Minecraft plugin spec", "Code", "Plan a Spigot/Paper plugin.", "Write a spec and starter code outline for the Minecraft (Paper) plugin described: commands, events, config, permissions."),
    # ---- Gaming
    ("lowendpc", "Low-end PC settings", "Gaming", "More FPS, less lag: best settings for weak hardware (i5-2400 + GT 710).",
     "Give the best in-game and Windows settings to maximise FPS for the game on an i5-2400, GT 710, 16GB RAM. Be specific: resolution scale, shadows, etc. Free tweaks only."),
    ("loadout", "Loadout / build advisor", "Gaming", "Best builds for a game and playstyle.", "Suggest the strongest current-style loadouts/builds for the game and playstyle given; note that metas change with patches."),
    ("strategy", "Strategy guide", "Gaming", "Tips to get better at a game.", "Give a focused improvement plan for the game: 5 fundamentals, 3 drills, common mistakes, and a 7-day practice plan."),
    ("teamname", "Team / clan names", "Gaming", "Name ideas.", "Give 20 team/clan names with tags (3-4 letters) for the vibe described."),
    ("bracket", "Tournament bracket", "Gaming", "Make a bracket for mates.", "Create a fair tournament bracket/schedule for the players given, with rules and tiebreakers."),
    ("patchnotes", "Patch notes summary", "Gaming", "What changed and what it means.", "Summarise the patch notes given: biggest changes, who wins/loses, what to change in your play."),
    # ---- Life
    ("reply", "Reply drafter", "Life", "Draft a reply to a message.", "Draft 3 replies to the message (short, friendly, firm) in a natural teen-appropriate voice."),
    ("apology", "Apology", "Life", "Sincere apology message.", "Write a sincere, short apology for the situation — own it, no excuses, offer to make it right."),
    ("birthday", "Birthday message", "Life", "Personal birthday messages.", "Write 4 birthday messages (funny, heartfelt, short, for a card) for the person described."),
    ("giftideas", "Gift ideas", "Life", "Thoughtful gifts on a budget.", "Suggest 12 gift ideas for the person and budget given, mixing cheap, DIY and experiences."),
    ("dayout", "Plan a day out", "Life", "A plan for a day out.", "Plan a day out from the details (place, budget, people): timeline, travel, costs, backup plan."),
    ("packing", "Packing list", "Life", "Checklist for a trip.", "Make a packing checklist for the trip described, grouped, with forgotten-item reminders."),
    ("cheapmeals", "Meals from what's in", "Life", "Cheap, quick meals from ingredients.", "Suggest 4 quick, cheap meals using mainly the ingredients listed, with short steps."),
    ("decide", "Decision helper", "Life", "Pros/cons and a recommendation.", "Help decide: pros and cons of each option, what matters most, and a clear recommendation with the reasoning."),
    ("conflict", "Handle a disagreement", "Life", "How to sort out a falling-out.", "Give calm, practical advice for the disagreement described and a message they could send to start fixing it."),
    ("habit", "Habit plan", "Life", "Build a habit that sticks.", "Make a 30-day plan to build the habit: tiny start, trigger, tracking, what to do after missing a day."),
    ("motivate", "Pep talk", "Life", "A proper Jarvis-style pep talk.", "Give a short, genuine pep talk in a calm British butler voice for the situation. Specific, not cheesy, end with one next action."),
    ("journal", "Journal prompts", "Life", "Prompts to reflect.", "Give 8 journaling prompts for the mood/topic given."),
    ("factcheck", "Claim checker", "Life", "How believable is a claim?", "Assess the claim: what's likely true/false, what evidence would settle it, red flags. Be clear about uncertainty and don't invent sources."),
    ("debate", "Both sides", "Life", "Strongest arguments on both sides.", "Give the strongest arguments for and against the statement, then the key question that decides it."),
    ("bikefix", "Bike fix", "Life", "Fix a bike problem.", "Diagnose the bike problem described and give step-by-step fixes with tools needed and when to take it to a shop."),
    ("formalemail", "Formal email", "Life", "Formal email (school, company…).", "Rewrite/write the email to be polite, clear and formal, with a good subject line."),
    ("lettertoschool", "Letter to school", "Life", "Letter/email to a teacher or school.", "Write a respectful email to the teacher/school about the situation."),
    ("complaint", "Complaint", "Life", "Effective complaint letter.", "Write an effective complaint: facts, impact, what you want, deadline. Firm and polite."),
    ("thankyou", "Thank-you note", "Life", "Genuine thanks.", "Write a short, genuine thank-you note for the situation."),
    ("newsexplain", "Explain the news", "Life", "What a news story means.", "Explain the news story simply: what happened, why it matters, different viewpoints. Say if facts may have changed."),
    ("sleepplan", "Wind-down plan", "Life", "A better evening routine.", "Make a realistic wind-down routine from the details (screens, revision, bedtime) with small changes to sleep better."),
]
for name, title, cat, desc, prompt in P:
    _add(name, title, cat, desc, prompt=prompt)

TONES = {"formal": "formal and polished", "casual": "casual and relaxed", "funny": "funny and witty", "jarvis": "like JARVIS — a calm, witty British AI butler",
         "pro": "professional and confident", "friendly": "warm and friendly", "persuasive": "persuasive", "concise": "as short as possible without losing meaning",
         "detailed": "more detailed and specific", "kind": "kind and supportive", "confident": "confident and assertive", "polite": "extra polite",
         "excited": "excited and hype", "simple": "in simple English (reading age 10)", "academic": "academic, for an essay", "shakespeare": "in Shakespearean English",
         "pirate": "like a pirate", "genz": "in Gen Z slang (keep it understandable)", "poetic": "poetic and vivid", "mysterious": "mysterious and dramatic"}
for k, v in TONES.items():
    _add(f"tone_{k}", f"Rewrite: {k}", "Writing", f"Rewrite text {v}.", prompt=f"Rewrite the text {v}. Keep the meaning. Output only the rewrite.", tier="fast")

FORMATS = {"bullets": "clear bullet points", "table": "a markdown table", "thread": "a 6-post social thread", "tiktok": "a 45-second TikTok script",
           "email": "an email with subject line", "intro": "a strong essay introduction", "tldr": "a one-line TL;DR", "summary5": "5 bullet summary",
           "quiz": "a 5-question multiple-choice quiz with answers", "timeline": "a dated timeline", "steps": "a numbered step-by-step guide",
           "faq": "an FAQ (6 questions)", "proscons": "a pros and cons list", "headlines": "10 headline options", "haiku": "a haiku",
           "rap": "an original 8-bar rap verse", "story": "a short story (200 words)", "speech": "a 1-minute speech", "notes": "revision notes with headings",
           "glossary": "a glossary of key terms"}
for k, v in FORMATS.items():
    _add(f"to_{k}", f"Turn into: {k}", "Writing", f"Turn text into {v}.", prompt=f"Turn the content into {v}. Output only that.", tier="fast")

SUBJECTS = {"maths": "GCSE Maths", "englang": "GCSE English Language", "englit": "GCSE English Literature", "biology": "GCSE Biology",
            "chemistry": "GCSE Chemistry", "physics": "GCSE Physics", "combined": "GCSE Combined Science", "compsci": "GCSE Computer Science",
            "history": "GCSE History", "geography": "GCSE Geography", "french": "GCSE French", "spanish": "GCSE Spanish",
            "re": "GCSE Religious Studies", "business": "GCSE Business", "dt": "GCSE Design & Technology", "pe": "GCSE PE (theory)",
            "german": "GCSE German", "furthermaths": "Level 2 Further Maths", "stats": "GCSE Statistics", "psychology": "GCSE Psychology",
            "sociology": "GCSE Sociology", "media": "GCSE Media Studies", "music": "GCSE Music", "art": "GCSE Art & Design",
            "drama": "GCSE Drama", "food": "GCSE Food Preparation & Nutrition", "citizenship": "GCSE Citizenship"}
TASKS = {"explain": ("Explain", "Explain the topic simply, then at full GCSE depth, with one example."),
         "quiz": ("Quick quiz", "Write a 5-question quiz on the topic (mixed difficulty) with answers at the end."),
         "examq": ("Exam question", "Write an exam-style question on the topic with marks, mark scheme and a model answer."),
         "mistakes": ("Common mistakes", "List the most common mistakes students make on the topic and how to avoid each."),
         "mnemonic": ("Memory tricks", "Give mnemonics and memory tricks for the topic's key facts."),
         "sheet": ("Revision sheet", "Make a one-page revision sheet for the topic."),
         "vocab": ("Key words", "List the key vocabulary/terms for the topic with exam-ready definitions."),
         "example": ("Worked example", "Give a fully worked example on the topic, then a practice one with the answer."),
         "cards": ("10 flashcards", "Make 10 Q → A flashcards on the topic."),
         "grade9": ("Grade 9 tips", "What separates a grade 9 answer from a grade 6 on this topic? Be specific."),
         "plan20": ("20-min session", "Plan a focused 20-minute revision session on the topic, minute by minute, with active recall."),
         "checklist": ("Topic checklist", "Make a checklist of everything a student must know for this topic, to RAG-rate.")}
for sk, sname in SUBJECTS.items():
    for tk, (tt, tp) in TASKS.items():
        _add(f"{sk}_{tk}", f"{sname.replace('GCSE ', '')}: {tt}", "Subjects",
             f"{sname} — {tt.lower()} (give the topic).",
             prompt=f"You are an expert {sname} teacher (AQA unless told otherwise). {tp}", example="e.g. a topic name")


# =============================================================================== engine
STOP = set("a an the my me i to for of on in it is and or with how what can you please do make help this that".split())


def find(query, n=8, cat=None):
    q = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 1 and w not in STOP]
    q = [w[:4] if len(w) > 4 else w for w in q]                       # crude stemming: price/pricing, revise/revision
    scored = []
    for s in SKILLS.values():
        if cat and s["cat"].lower() != cat.lower():
            continue
        hay = f"{s['name']} {s['title']} {s['cat']} {s['desc']}".lower()
        score = sum(3 if w in s["name"] else 2 if w in s["title"].lower() else 1 for w in q if w in hay)
        score -= 0.5 if s["cat"] == "Subjects" else 0                   # general skills first, unless a subject is named
        if score or not q:
            scored.append((score, s["name"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [SKILLS[n_] for _, n_ in scored[:n]]


def run(name, text=""):
    s = SKILLS.get((name or "").strip().lower().lstrip("/"))
    if not s:
        hits = find(name, 3)
        return f"No skill called '{name}'. Did you mean: {', '.join('/' + h['name'] for h in hits)}?"
    if s["kind"] == "local":
        try:
            return str(s["fn"](text or ""))
        except Exception as e:
            return f"That didn't work ({type(e).__name__}). Example: /{s['name']} {s['example']}"
    brain = CTX.get("brain")
    if not brain:
        return "My brain isn't ready yet."
    if not (text or "").strip():
        return f"/{s['name']} needs something to work on — {s['desc']}"
    system = ("You are ORION, a calm, witty British AI butler helping Kiyan, a UK Year 11 student who runs small ventures. "
              f"SKILL: {s['title']}. {s['prompt']} Be accurate; if unsure of a fact, say so. Use clear formatting.")
    return brain.quick(system, text[:12000], tier=s.get("tier", "smart"), max_steps=1) or "No answer came back."


def slash(text):
    """'/name input' typed in chat → (name, result) or None."""
    m = re.match(r"^/([a-z][a-z0-9_]{1,30})\b\s*(.*)$", (text or "").strip(), re.S)
    if not m or m.group(1) not in SKILLS:
        return None
    return m.group(1), run(m.group(1), m.group(2))


def catalog():
    cats = {}
    for s in SKILLS.values():
        cats.setdefault(s["cat"], 0)
        cats[s["cat"]] += 1
    return {"count": len(SKILLS), "cats": cats,
            "skills": [{k: s[k] for k in ("name", "title", "cat", "desc", "kind", "example")} for s in SKILLS.values()]}


@tool("SKILL LIBRARY: search ORION's library of 400+ ready-made skills (calculators, converters, GCSE subject helpers, "
      "essay/maths tools, money & business writers, coding helpers, content, life admin). Use it when a request matches "
      "a specialised task, then call skill_use.",
      {"query": ("string", "What the user wants, in a few words", True)})
def skill_find(query):
    hits = find(query, 8)
    if not hits:
        return "No matching skills."
    return "\n".join(f"/{s['name']} — {s['title']}: {s['desc']}" + (f" (e.g. {s['example']})" if s["example"] else "") for s in hits)


@tool("Run a skill from the SKILL LIBRARY by name (from skill_find) on the user's input.",
      {"name": ("string", "Skill name, e.g. 'quadratic' or 'essayplan'", True),
       "input": ("string", "The text/numbers/topic to run it on", True)})
def skill_use(name, input=""):
    return run(name, input)

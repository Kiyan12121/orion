"""ORION 6 skill pack — hundreds more skills on top of the 505 in skillbook.

  • ~80 new instant local tools (maths, science, money, dates, text, code, gaming, fun) — no AI, no internet
  • 8 new study tasks for every GCSE subject (27 subjects × 8 = 216 skills)
  • ~70 new expert playbooks (school, writing, content, business, coding, life, gaming)
"""
import datetime as dt
import html
import json
import math
import random
import re
import statistics
import string
import time
import urllib.parse
import uuid
from fractions import Fraction

from .skillbook import SKILLS, SUBJECTS, _add, _nums


def _f(x, d=4):
    x = round(x, d)
    return str(int(x)) if x == int(x) else f"{x:,.{d}f}".rstrip("0").rstrip(".")


def _need(n, k, msg):
    if len(n) < k:
        raise ValueError(msg)
    return n


# ------------------------------------------------------------------ maths
def _stats(t):
    n = _nums(t)
    if len(n) < 2:
        return "Give some numbers: '3, 7, 7, 10, 12'."
    md = statistics.multimode(n)
    return (f"n={len(n)} · mean {_f(statistics.mean(n))} · median {_f(statistics.median(n))} · "
            f"mode {', '.join(_f(m) for m in md) if len(md) < len(n) else 'none'} · range {_f(max(n) - min(n))}\n"
            f"Q1 {_f(statistics.quantiles(n, n=4)[0])} · Q3 {_f(statistics.quantiles(n, n=4)[2])} · "
            f"std dev {_f(statistics.pstdev(n))} (population) / {_f(statistics.stdev(n))} (sample) · total {_f(sum(n))}")


def _factorial(t):
    n = int(_need(_nums(t), 1, "Give a number.")[0])
    if n > 170 or n < 0:
        return "Pick 0–170."
    return f"{n}! = {math.factorial(n):,}"


def _ncr(t):
    a, b = [int(x) for x in _need(_nums(t), 2, "Give n and r: '10 choose 3'.")[:2]]
    return f"{a}C{b} = {math.comb(a, b):,} (combinations) · {a}P{b} = {math.perm(a, b):,} (arrangements)"


def _ratio(t):
    n = _nums(t)
    m = re.search(r"share\s*£?\s*([\d.]+).*?(?:in|ratio)\s*([\d.:\s]+)", t or "", re.I)
    if m:
        total = float(m.group(1))
        parts = [float(x) for x in re.findall(r"[\d.]+", m.group(2))]
        s = sum(parts)
        return " : ".join(_f(total * p / s, 2) for p in parts) + f"  (each part = {_f(total / s, 2)})"
    ints = [int(x) for x in n if x == int(x)]
    if len(ints) >= 2:
        g = math.gcd(*ints)
        return "Simplest form: " + " : ".join(str(i // g) for i in ints)
    return "Try '12:18' to simplify or 'share 60 in 2:3:5'."


def _fraction(t):
    s = (t or "").replace("÷", "/ ").replace("×", "*")
    m = re.match(r"\s*(-?\d+\s*/\s*\d+|-?\d+(?:\.\d+)?)\s*([-+*]|of|divided by|/ )\s*(-?\d+\s*/\s*\d+|-?\d+(?:\.\d+)?)\s*$", s, re.I)
    if not m:
        n = _nums(t)
        if n:
            fr = Fraction(str(n[0])).limit_denominator(1000)
            return f"{n[0]} = {fr}"
        return "Try '3/4 + 2/5', '2/3 of 5/8' or '0.375'."
    a, op, b = Fraction(m.group(1).replace(" ", "")), m.group(2).strip().lower(), Fraction(m.group(3).replace(" ", ""))
    r = a + b if op == "+" else a - b if op == "-" else a * b if op in ("*", "of") else a / b
    whole = f" = {r.numerator // r.denominator} {r.numerator % r.denominator}/{r.denominator}" if abs(r) > 1 and r.denominator != 1 else ""
    return f"{a} {op} {b} = {r}{whole} ≈ {float(r):.4g}"


def _stdform(t):
    n = _need(_nums(t), 1, "Give a number.")[0]
    if n == 0:
        return "0"
    e = math.floor(math.log10(abs(n)))
    return f"{(f'{n:,.0f}' if abs(n) >= 1 and n == int(n) else f'{n:g}')} = {n / 10 ** e:.4g} × 10^{e}"


def _sigfig(t):
    n = _nums(t)
    if not n:
        return "Give a number and how many s.f.: '0.004567 2'."
    x, k = n[0], int(n[1]) if len(n) > 1 else 3
    if x == 0:
        return "0"
    r = round(x, k - 1 - math.floor(math.log10(abs(x))))
    return f"{_f(x, 10)} to {k} s.f. = {_f(r, 10)} · to {k} d.p. = {round(x, k)}"


def _area(t):
    s, n = (t or "").lower(), _nums(t)
    if not n:
        return "e.g. 'circle 5', 'cylinder r 3 h 10', 'sphere 4', 'cone r 3 h 7', 'triangle 6 4', 'trapezium 3 5 4', 'cuboid 2 3 4'."
    if "cylinder" in s:
        r, h = n[0], n[1]
        return f"Cylinder r={_f(r)} h={_f(h)}: volume πr²h = {_f(math.pi * r * r * h, 2)} · surface area {_f(2 * math.pi * r * (r + h), 2)}"
    if "sphere" in s:
        r = n[0]
        return f"Sphere r={_f(r)}: volume 4/3πr³ = {_f(4 / 3 * math.pi * r ** 3, 2)} · surface area 4πr² = {_f(4 * math.pi * r * r, 2)}"
    if "cone" in s:
        r, h = n[0], n[1]
        l = math.hypot(r, h)
        return f"Cone r={_f(r)} h={_f(h)}: volume ⅓πr²h = {_f(math.pi * r * r * h / 3, 2)} · slant {_f(l, 3)} · curved area πrl = {_f(math.pi * r * l, 2)}"
    if "cuboid" in s or "box" in s:
        a, b, c = n[:3]
        return f"Cuboid: volume {_f(a * b * c)} · surface area {_f(2 * (a * b + b * c + a * c))}"
    if "trapez" in s:
        a, b, h = n[:3]
        return f"Trapezium: ½(a+b)h = {_f((a + b) / 2 * h)}"
    if "triangle" in s:
        return f"Triangle: ½ × base × height = {_f(n[0] * n[1] / 2)}"
    if "circle" in s or len(n) == 1:
        r = n[0] / 2 if "diameter" in s else n[0]
        return f"Circle r={_f(r)}: area πr² = {_f(math.pi * r * r, 3)} · circumference 2πr = {_f(2 * math.pi * r, 3)}"
    return f"Rectangle: area {_f(n[0] * n[1])} · perimeter {_f(2 * (n[0] + n[1]))}"


def _line(t):
    n = _need([float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", t or "")], 4, "Give two points: '(1,2) (5,10)'.")
    x1, y1, x2, y2 = n[:4]
    if x1 == x2:
        return f"Vertical line x = {_f(x1)} · distance {_f(abs(y2 - y1))}"
    m = (y2 - y1) / (x2 - x1)
    c = y1 - m * x1
    return (f"Gradient {_f(m)} ({Fraction(y2 - y1).limit_denominator() / Fraction(x2 - x1).limit_denominator() if all(v == int(v) for v in n[:4]) else _f(m)}) · "
            f"y = {_f(m)}x {'+' if c >= 0 else '-'} {_f(abs(c))} · midpoint ({_f((x1 + x2) / 2)}, {_f((y1 + y2) / 2)}) · "
            f"length {_f(math.hypot(x2 - x1, y2 - y1), 3)} · perpendicular gradient {_f(-1 / m) if m else '∞'}")


def _nth(t):
    n = _nums(t)
    if len(n) < 3:
        return "Give at least 3 terms: '5, 8, 11, 14'."
    d = [b - a for a, b in zip(n, n[1:])]
    if len(set(round(x, 9) for x in d)) == 1:
        return f"Linear: nth term = {_f(d[0])}n {'+' if n[0] - d[0] >= 0 else '-'} {_f(abs(n[0] - d[0]))} · 10th term {_f(n[0] + 9 * d[0])}"
    d2 = [b - a for a, b in zip(d, d[1:])]
    if len(set(round(x, 9) for x in d2)) == 1:
        a = d2[0] / 2
        rest = [n[i] - a * (i + 1) ** 2 for i in range(len(n))]
        b = rest[1] - rest[0]
        c = rest[0] - b
        return f"Quadratic: nth term = {_f(a)}n² {'+' if b >= 0 else '-'} {_f(abs(b))}n {'+' if c >= 0 else '-'} {_f(abs(c))}"
    if all(x != 0 for x in n) and len(set(round(b / a, 9) for a, b in zip(n, n[1:]))) == 1:
        r = n[1] / n[0]
        return f"Geometric: nth term = {_f(n[0])} × {_f(r)}^(n-1) · 10th term {_f(n[0] * r ** 9)}"
    return "Not linear, quadratic or geometric."


def _trig(t):
    s, n = (t or "").lower(), _nums(t)
    if not n:
        return "e.g. 'sin 30', 'cos 60', 'tan 45', 'asin 0.5'."
    x = n[0]
    for fn, f in (("asin", math.asin), ("acos", math.acos), ("atan", math.atan)):
        if fn in s:
            return f"{fn}({_f(x)}) = {_f(math.degrees(f(x)), 4)}°"
    for fn, f in (("sin", math.sin), ("cos", math.cos), ("tan", math.tan)):
        if fn in s:
            return f"{fn}({_f(x)}°) = {_f(f(math.radians(x)), 6)}"
    return f"sin {_f(x)}° = {math.sin(math.radians(x)):.4f} · cos = {math.cos(math.radians(x)):.4f} · tan = {math.tan(math.radians(x)):.4f}"


def _sqrt(t):
    n = _need(_nums(t), 1, "Give a number.")[0]
    out = [f"√{_f(n)} = {_f(math.sqrt(abs(n)), 6)}{'i' if n < 0 else ''}", f"∛{_f(n)} = {_f(math.copysign(abs(n) ** (1 / 3), n), 6)}",
           f"{_f(n)}² = {_f(n * n)}", f"{_f(n)}³ = {_f(n ** 3)}"]
    if n == int(n) and n > 0:                          # simplify surd
        k = int(n)
        best = max((i for i in range(1, int(k ** .5) + 1) if k % (i * i) == 0), default=1)
        if best > 1 and best * best != k:
            out.append(f"√{k} = {best}√{k // (best * best)}")
    return " · ".join(out)


def _bounds(t):
    n = _need(_nums(t), 1, "Give a value and accuracy: '7.4 to 1 dp' or '300 nearest 10'.")
    x = n[0]
    s = (t or "").lower()
    m = re.search(r"(\d+)\s*(d\.?p|s\.?f)", s)
    if m and "d" in m.group(2):
        h = 0.5 * 10 ** -int(m.group(1))
    elif "nearest" in s and len(n) > 1:
        h = n[1] / 2
    else:
        h = 0.5
    return f"{_f(x)} → lower bound {_f(x - h, 6)} · upper bound {_f(x + h, 6)}  (error interval {_f(x - h, 6)} ≤ x < {_f(x + h, 6)})"


def _multiplier(t):
    n = _need(_nums(t), 2, "e.g. '250 increase 12% for 3 years' or '80 decrease 15%'.")
    x, p = n[0], n[1]
    yrs = int(n[2]) if len(n) > 2 else 1
    m = 1 + p / 100 if "decrease" not in (t or "").lower() and "depreciat" not in (t or "").lower() else 1 - p / 100
    return f"Multiplier {_f(m)} · {_f(x)} × {_f(m)}^{yrs} = {_f(x * m ** yrs, 2)}"


def _reverse_pct(t):
    n = _need(_nums(t), 2, "e.g. 'after 20% off it costs 48'.")
    p, v = (n[0], n[1]) if "%" in (t or "").split(str(int(n[1])))[0] else (n[1], n[0])
    m = 1 - p / 100 if re.search(r"off|decrease|less|reduc", t or "", re.I) else 1 + p / 100
    return f"Original = {_f(v)} ÷ {_f(m)} = {_f(v / m, 2)}"


# ------------------------------------------------------------------ science (GCSE equations)
def _phys(t):
    s, n = (t or "").lower(), _nums(t)
    eq = {
        "ke": ("Kinetic energy", lambda m, v: f"Eₖ = ½mv² = {_f(.5 * m * v * v, 3)} J", "mass kg, speed m/s"),
        "gpe": ("Gravitational PE", lambda m, h: f"Eₚ = mgh = {_f(m * 9.8 * h, 3)} J (g = 9.8)", "mass kg, height m"),
        "power": ("Power", lambda e, tt: f"P = E/t = {_f(e / tt, 3)} W", "energy J, time s"),
        "momentum": ("Momentum", lambda m, v: f"p = mv = {_f(m * v, 3)} kg m/s", "mass kg, velocity m/s"),
        "pressure": ("Pressure", lambda f, a: f"p = F/A = {_f(f / a, 3)} Pa", "force N, area m²"),
        "wave": ("Wave speed", lambda f, l: f"v = fλ = {_f(f * l, 3)} m/s", "frequency Hz, wavelength m"),
        "spring": ("Hooke's law", lambda k, e: f"F = ke = {_f(k * e, 3)} N · elastic PE ½ke² = {_f(.5 * k * e * e, 4)} J", "spring constant N/m, extension m"),
        "shc": ("Specific heat", lambda m, c, dt=None: f"ΔE = mcΔθ = {_f(m * c * (dt or 0), 3)} J", "mass kg, c J/kg°C, temp change °C"),
        "charge": ("Charge", lambda i, tt: f"Q = It = {_f(i * tt, 3)} C", "current A, time s"),
        "elecpower": ("Electrical power", lambda v, i: f"P = VI = {_f(v * i, 3)} W", "voltage V, current A"),
        "efficiency": ("Efficiency", lambda u, tot: f"efficiency = useful/total = {_f(u / tot * 100, 2)}%", "useful, total"),
        "weight": ("Weight", lambda m: f"W = mg = {_f(m * 9.8, 3)} N", "mass kg"),
        "accel": ("Acceleration", lambda dv, tt: f"a = Δv/t = {_f(dv / tt, 3)} m/s²", "change in velocity m/s, time s"),
        "forcema": ("Newton's 2nd law", lambda m, a: f"F = ma = {_f(m * a, 3)} N", "mass kg, acceleration m/s²"),
        "density2": ("Density", lambda m, v: f"ρ = m/V = {_f(m / v, 4)}", "mass, volume"),
        "work": ("Work done", lambda f, d: f"W = Fs = {_f(f * d, 3)} J", "force N, distance m"),
        "moment": ("Moment", lambda f, d: f"M = Fd = {_f(f * d, 3)} N m", "force N, perpendicular distance m"),
        "suvat": ("v² = u² + 2as", lambda u, a, s2: f"v = {_f(math.sqrt(max(0, u * u + 2 * a * s2)), 4)} m/s", "u m/s, a m/s², s m"),
    }
    key = next((k for k in eq if k in s.replace(" ", "")), None) or next(
        (k for k, v in eq.items() if v[0].lower().split()[0] in s), None)
    if not key:
        return "Equations: " + ", ".join(f"{k} ({v[2]})" for k, v in eq.items())
    name, fn, need = eq[key]
    try:
        return f"{name}: {fn(*n)}"
    except TypeError:
        return f"{name} needs: {need}"


def _moles(t):
    s, n = t or "", _nums(t)
    mr = {"H": 1, "C": 12, "N": 14, "O": 16, "Na": 23, "Mg": 24, "Al": 27, "S": 32, "Cl": 35.5, "K": 39, "Ca": 40, "Fe": 56,
          "Cu": 63.5, "Zn": 65, "Br": 80, "Ag": 108, "I": 127, "Li": 7, "F": 19, "P": 31, "Si": 28, "Ba": 137, "Pb": 207, "Mn": 55}
    m = re.search(r"\b((?:[A-Z][a-z]?\d*|\((?:[A-Z][a-z]?\d*)+\)\d*)+)\b", s)
    if not m:
        return "e.g. 'H2SO4' for Mr, or '9.8 g of H2SO4' for moles."
    f = m.group(1)

    def mass(form):
        tot = 0
        for grp, mult in re.findall(r"\(([^)]+)\)(\d*)", form):
            tot += mass(grp) * int(mult or 1)
        form = re.sub(r"\([^)]+\)\d*", "", form)
        for el, k in re.findall(r"([A-Z][a-z]?)(\d*)", form):
            if el not in mr:
                raise KeyError(el)
            tot += mr[el] * int(k or 1)
        return tot
    try:
        M = mass(f)
    except KeyError as e:
        return f"Unknown element {e}."
    out = f"Mr of {f} = {_f(M, 2)}"
    nn = [x for x in n if str(x) not in f]
    if re.search(r"\d\s*g\b", s) and nn:
        out += f" · {_f(nn[0])} g = {_f(nn[0] / M, 4)} mol"
    elif re.search(r"mol", s, re.I) and nn:
        out += f" · {_f(nn[0])} mol = {_f(nn[0] * M, 3)} g"
    return out


def _resist(t):
    n = _nums(t)
    if len(n) < 2:
        return "Give resistances: 'series 4 6 10' or 'parallel 4 6'."
    if "parallel" in (t or "").lower():
        return f"Parallel: total = {_f(1 / sum(1 / x for x in n), 4)} Ω"
    return f"Series: total = {_f(sum(n))} Ω"


def _halflife(t):
    n = _need(_nums(t), 3, "e.g. 'start 800 half-life 5 years after 20 years'.")
    a, hl, tt = n[:3]
    return f"After {_f(tt)}: {_f(a * 0.5 ** (tt / hl), 4)} left ({_f(tt / hl, 3)} half-lives)"


# ------------------------------------------------------------------ money
def _loan(t):
    n = _need(_nums(t), 3, "e.g. 'borrow 3000 at 7% for 3 years'.")
    p, r, y = n[:3]
    i = r / 100 / 12
    k = int(y * 12)
    pay = p / k if i == 0 else p * i / (1 - (1 + i) ** -k)
    return f"£{pay:,.2f}/month for {k} months · total £{pay * k:,.2f} · interest £{pay * k - p:,.2f}"


def _margin(t):
    n = _need(_nums(t), 2, "Give cost and price: 'cost 4 sell 10'.")
    c, p = n[:2]
    return f"Profit £{p - c:,.2f} · margin {(p - c) / p * 100:.1f}% · markup {(p - c) / c * 100:.1f}%"


def _unitprice(t):
    pairs = re.findall(r"£?\s*([\d.]+)\s*(?:for|/)\s*([\d.]+)\s*([a-z]*)", (t or "").lower())
    if len(pairs) < 2:
        return "e.g. '£1.20 for 500g vs £2 for 1000g'."
    rows = [(float(a) / float(b), a, b, u) for a, b, u in pairs]
    best = min(rows)
    return "\n".join(f"£{a} for {b}{u}: £{v:.4f} per {u or 'unit'}{'  ← best value' if (v, a, b, u) == best else ''}" for v, a, b, u in rows)


def _inflation(t):
    n = _need(_nums(t), 2, "e.g. '100 at 3% for 10 years'.")
    v, r = n[:2]
    y = n[2] if len(n) > 2 else 1
    return f"£{v:,.2f} today costs £{v * (1 + r / 100) ** y:,.2f} in {_f(y)} years · today's £{v:,.0f} will only buy £{v / (1 + r / 100) ** y:,.2f} of today's stuff"


def _tip(t):
    n = _need(_nums(t), 1, "Give the bill: '45.80'.")
    b = n[0]
    return " · ".join(f"{p}% = £{b * p / 100:.2f} (total £{b * (1 + p / 100):.2f})" for p in (10, 12.5, 15))


def _subs(t):
    n = _nums(t)
    if not n:
        return "List monthly subscriptions: 'spotify 11.99, netflix 10.99, xbox 12'."
    m = sum(n)
    return f"£{m:,.2f}/month = £{m * 12:,.2f}/year · that's {m * 12 / 15:.0f} hours of work at £15/h"


def _wage(t):
    n = _need(_nums(t), 2, "e.g. '£11.44 an hour, 12 hours a week'.")
    h, w = n[:2]
    return f"£{h * w:,.2f}/week · £{h * w * 52 / 12:,.2f}/month · £{h * w * 52:,.2f}/year (before any tax)"


# ------------------------------------------------------------------ dates & time
def _weekday(t):
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", t or "")
    if not m:
        return "Give a date: '2027-05-14' or '14/05/2027'."
    if m.group(1):
        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        y = int(m.group(6))
        d = dt.date(y + 2000 if y < 100 else y, int(m.group(5)), int(m.group(4)))
    return f"{d:%A %d %B %Y} · week {d.isocalendar()[1]} · day {d.timetuple().tm_yday} of the year"


def _adddays(t):
    n = _need(_nums(t), 1, "e.g. '45 days from today' or '3 weeks from 2027-01-10'.")
    k = n[0] * (7 if "week" in (t or "") else 1)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t or "")
    base = dt.date(*map(int, m.groups())) if m else dt.date.today()
    if m:
        k = n[0] * (7 if "week" in (t or "") else 1)
    sign = -1 if re.search(r"\bago|before\b", t or "") else 1
    d = base + dt.timedelta(days=sign * k)
    return f"{d:%A %d %B %Y}"


def _sleep(t):
    m = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?", t or "")
    if not m:
        return "Give a wake-up time: 'wake 7:30'."
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    wake = dt.datetime.combine(dt.date.today(), dt.time(h % 24, mi))
    times = [(wake - dt.timedelta(minutes=90 * c + 15)).strftime("%H:%M") for c in (6, 5, 4)]
    return f"To wake at {wake:%H:%M} between sleep cycles, try to fall asleep by {times[0]} (9h), {times[1]} (7.5h) or {times[2]} (6h — not ideal on school nights)."


def _unix(t):
    n = _nums(t)
    if n and n[0] > 1e8:
        return f"{dt.datetime.fromtimestamp(n[0] / (1000 if n[0] > 1e12 else 1)):%A %d %b %Y %H:%M:%S}"
    return f"Now: {int(time.time())} (seconds) · {int(time.time() * 1000)} (ms)"


def _duration(t):
    m = re.findall(r"(\d{1,2})[:.](\d{2})", t or "")
    if len(m) < 2:
        return "Give two times: '8:45 to 15:10'."
    (h1, m1), (h2, m2) = m[:2]
    a, b = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
    d = (b - a) % 1440
    return f"{d // 60}h {d % 60}m ({d} minutes)"


# ------------------------------------------------------------------ text & code
def _textops(op):
    def f(t):
        t = t or ""
        lines = t.splitlines()
        return {"reverse": t[::-1], "sortlines": "\n".join(sorted(lines, key=str.lower)),
                "dedupe": "\n".join(dict.fromkeys(lines)), "numberlines": "\n".join(f"{i + 1}. {l}" for i, l in enumerate(lines)),
                "squash": re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", t)).strip(),
                "slug": re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-"),
                "acronym": "".join(w[0].upper() for w in re.findall(r"[A-Za-z]+", t)),
                "urlencode": urllib.parse.quote(t), "urldecode": urllib.parse.unquote(t),
                "htmlescape": html.escape(t), "htmlunescape": html.unescape(t),
                "charcodes": " ".join(f"{c}={ord(c)}" for c in t[:60]),
                "letterfreq": ", ".join(f"{c}:{n}" for c, n in sorted(((c, t.lower().count(c)) for c in set(t.lower()) if c.isalpha()), key=lambda x: -x[1])[:15]),
                }[op]
    return f


def _uuid(t):
    n = int((_nums(t) or [1])[0])
    return "\n".join(str(uuid.uuid4()) for _ in range(max(1, min(n, 20))))


def _lorem(t):
    words = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore "
             "magna aliqua ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi").split()
    n = int((_nums(t) or [50])[0])
    out = [random.choice(words) for _ in range(min(n, 1000))]
    return (" ".join(out).capitalize() + ".")


def _jwt(t):
    import base64
    parts = (t or "").strip().split(".")
    if len(parts) < 2:
        return "Paste a JWT (xxx.yyy.zzz). Decoded locally — never sent anywhere."
    dec = lambda s: json.dumps(json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))), indent=2)
    try:
        return "Header:\n" + dec(parts[0]) + "\nPayload:\n" + dec(parts[1]) + "\n(signature not checked)"
    except Exception as e:
        return f"Couldn't decode: {e}"


def _cidr(t):
    import ipaddress
    try:
        net = ipaddress.ip_network((t or "").strip(), strict=False)
    except ValueError as e:
        return f"{e} — try '192.168.1.0/24'."
    return (f"{net} · {net.num_addresses:,} addresses · netmask {net.netmask} · first {net[0]} · last {net[-1]}"
            + (" · private" if net.is_private else ""))


def _csvjson(t):
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO((t or "").strip())))
    return json.dumps(rows, indent=2) if rows else "Paste CSV with a header row."


def _minify(t):
    try:
        return json.dumps(json.loads(t), separators=(",", ":"))
    except Exception as e:
        return f"Not valid JSON: {e}"


def _bytes(t):
    n = _need(_nums(t), 1, "e.g. '1500000000 bytes' or '4.7 GB'.")[0]
    s = (t or "").lower()
    mult = {"kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3}
    b = n * next((v for k, v in mult.items() if re.search(rf"\b{k}\b", s)), 1)
    return " · ".join(f"{b / v:,.3f} {k.upper().replace('I', 'i')}" for k, v in mult.items()) + f" · {b:,.0f} bytes"


def _download(t):
    n = _need(_nums(t), 2, "e.g. '50 GB at 80 Mbps'.")
    size, speed = n[:2]
    s = (t or "").lower()
    gb = size / 1000 if "mb" in s.split("at")[0] else size
    secs = gb * 8000 / speed
    return f"≈ {int(secs // 3600)}h {int(secs % 3600 // 60)}m {int(secs % 60)}s at a steady {_f(speed)} Mbps (real-world is usually 10-20% slower)"


# ------------------------------------------------------------------ gaming
def _kd(t):
    n = _need(_nums(t), 2, "Give kills and deaths (and assists): '24 9 5'.")
    k, d = n[:2]
    a = n[2] if len(n) > 2 else 0
    return f"K/D {k / max(d, 1):.2f} · KDA {(k + a) / max(d, 1):.2f}"


def _winrate(t):
    n = _need(_nums(t), 2, "Give wins and losses: '37 21'.")
    w, l = n[:2]
    need = math.ceil((0.6 * (w + l) - w) / 0.4) if w / (w + l) < .6 else 0
    return f"Win rate {w / (w + l) * 100:.1f}% ({_f(w + l)} games)" + (f" · {need} straight wins to reach 60%" if need else "")


def _sens(t):
    n = _need(_nums(t), 2, "Give in-game sensitivity and DPI: '0.4 800' (Valorant-style).")
    s, dpi = n[:2]
    edpi = s * dpi
    cm = 2.54 * 360 / (dpi * s * 0.07)
    return f"eDPI {edpi:,.0f} · ≈ {cm:.1f} cm per 360° (Valorant/CS yaw 0.07)"


def _fps(t):
    n = _need(_nums(t), 1, "Give FPS: '144'.")[0]
    return f"{_f(n)} fps = {1000 / n:.2f} ms per frame"


# ------------------------------------------------------------------ fun
EIGHT = ["It is certain.", "Without a doubt.", "You may rely on it.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
         "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Don't count on it.",
         "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."]


def _eight(t):
    return "🎱 " + random.choice(EIGHT)


def _rps(t):
    me = random.choice(["rock", "paper", "scissors"])
    you = next((x for x in ("rock", "paper", "scissors") if x in (t or "").lower()), None)
    if not you:
        return f"I pick {me}. Your move?"
    res = "Draw." if me == you else "You win!" if (you, me) in (("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")) else "I win."
    return f"You: {you} · Me: {me} → {res}"


def _teams(t):
    names = [x.strip() for x in re.split(r",|\n", re.sub(r"\b\d+\s*teams?\b", "", t or "")) if x.strip()]
    k = int((re.findall(r"(\d+)\s*teams?", t or "") or [2])[0])
    if len(names) < 2:
        return "List names and team count: 'sam, alex, jo, kai, 2 teams'."
    random.shuffle(names)
    return "\n".join(f"Team {i + 1}: {', '.join(names[i::k])}" for i in range(k))


def _randnum(t):
    n = _nums(t)
    lo, hi = (n[0], n[1]) if len(n) > 1 else (1, n[0] if n else 100)
    return f"🎲 {random.randint(int(lo), int(hi))}"


def _lottery(t):
    return "Lotto-style: " + " ".join(map(str, sorted(random.sample(range(1, 60), 6)))) + " (just for fun)"


def _wouldyou(t):
    q = ["fly or be invisible", "always be 10 minutes early or 20 minutes late", "have unlimited Robux or unlimited V-Bucks",
         "live without music or without games", "explore space or the deep ocean", "be famous on TikTok or rich and unknown",
         "only eat pizza or only eat burgers", "have a pet dragon or a pet dinosaur", "time travel to the past or the future",
         "never use your phone again or never play games again"]
    return "Would you rather " + random.choice(q) + "?"


def _fact(t):
    f = ["Honey never spoils — edible honey has been found in 3,000-year-old Egyptian tombs.",
         "Octopuses have three hearts and blue blood.", "A day on Venus is longer than a year on Venus.",
         "Bananas are berries, but strawberries aren't.", "The Eiffel Tower grows about 15 cm taller in summer heat.",
         "There are more possible chess games than atoms in the observable universe.",
         "Sharks existed before trees.", "Wombat poo is cube-shaped.", "Your stomach gets a new lining every few days.",
         "The first computer bug was an actual moth found in a Harvard computer in 1947."]
    return "🧠 " + random.choice(f)


def _anagram(t):
    w = re.sub(r"[^a-z]", "", (t or "").lower())
    if not w:
        return "Give a word."
    letters = list(w)
    random.shuffle(letters)
    return f"Scrambled: {''.join(letters)} · sorted letters: {''.join(sorted(w))}"


def _palindrome(t):
    s = re.sub(r"[^a-z0-9]", "", (t or "").lower())
    return "✓ Palindrome!" if s and s == s[::-1] else "✗ Not a palindrome."


def _caesar(t):
    n = _nums(t)
    k = int(n[0]) if n else 3
    s = re.sub(r"^\s*-?\d+\s*", "", t or "")
    sh = lambda c, b: chr((ord(c) - b + k) % 26 + b)
    return "".join(sh(c, 65) if c.isupper() else sh(c, 97) if c.islower() else c for c in s)


def _binarytext(t):
    s = (t or "").strip()
    if re.fullmatch(r"[01\s]+", s):
        return "".join(chr(int(b, 2)) for b in s.split())
    return " ".join(f"{ord(c):08b}" for c in s[:80])


LOCALS = [
    ("stats", "Averages & spread", "Maths", "Mean, median, mode, range, quartiles, standard deviation.", _stats, "3, 7, 7, 10, 12"),
    ("factorial", "Factorial", "Maths", "n!", _factorial, "10"),
    ("ncr", "Combinations", "Maths", "nCr and nPr.", _ncr, "10 choose 3"),
    ("ratio", "Ratios", "Maths", "Simplify a ratio or share an amount.", _ratio, "share 60 in 2:3:5"),
    ("fraction", "Fractions", "Maths", "Add, subtract, multiply, divide fractions; decimals → fractions.", _fraction, "3/4 + 2/5"),
    ("stdform", "Standard form", "Maths", "Write a number in standard form.", _stdform, "0.000345"),
    ("sigfig", "Rounding", "Maths", "Round to significant figures and decimal places.", _sigfig, "0.004567 2"),
    ("shapes", "Area & volume", "Maths", "Circle, triangle, trapezium, cuboid, cylinder, cone, sphere.", _area, "cylinder r 3 h 10"),
    ("line", "Straight lines", "Maths", "Gradient, equation, midpoint and length between two points.", _line, "(1,2) (5,10)"),
    ("nthterm", "nth term", "Maths", "Find the nth term of a linear, quadratic or geometric sequence.", _nth, "5, 8, 11, 14"),
    ("trig", "Trig values", "Maths", "sin/cos/tan and inverses in degrees.", _trig, "sin 30"),
    ("roots", "Roots & powers", "Maths", "Square/cube roots, squares, cubes, simplify surds.", _sqrt, "72"),
    ("bounds", "Bounds", "Maths", "Upper/lower bounds and error intervals.", _bounds, "7.4 to 1 dp"),
    ("multiplier", "Percentage multipliers", "Maths", "Repeated % increase/decrease.", _multiplier, "250 increase 12% for 3 years"),
    ("reversepct", "Reverse percentages", "Maths", "Find the original before a % change.", _reverse_pct, "after 20% off it costs 48"),
    ("physeq", "Physics equations", "Science", "KE, GPE, power, momentum, pressure, waves, springs, electricity, SUVAT…", _phys, "ke 70 12"),
    ("moles", "Moles & Mr", "Science", "Relative formula mass and mass ↔ moles.", _moles, "9.8 g of H2SO4"),
    ("resistors", "Resistors", "Science", "Series and parallel totals.", _resist, "parallel 4 6"),
    ("halflife", "Half-life", "Science", "How much is left after some half-lives.", _halflife, "start 800 half-life 5 after 20"),
    ("loan", "Loan repayments", "Money", "Monthly payment and total interest.", _loan, "borrow 3000 at 7% for 3 years"),
    ("margin", "Profit margin", "Money", "Profit, margin and markup.", _margin, "cost 4 sell 10"),
    ("unitprice", "Best value", "Money", "Compare price per gram/ml/item.", _unitprice, "£1.20 for 500g vs £2 for 1000g"),
    ("inflation", "Inflation", "Money", "What money is worth in the future.", _inflation, "100 at 3% for 10 years"),
    ("tip", "Tip calculator", "Money", "10 / 12.5 / 15% tips.", _tip, "45.80"),
    ("subs", "Subscription audit", "Money", "What your subscriptions cost per year.", _subs, "spotify 11.99, netflix 10.99"),
    ("wage", "Wage calculator", "Money", "Hourly pay → week, month, year.", _wage, "11.44 an hour, 12 hours a week"),
    ("weekday", "What day is it?", "Tools", "Day of the week, week number, day of the year.", _weekday, "2027-05-14"),
    ("adddays", "Add days", "Tools", "Date N days/weeks from today or a date.", _adddays, "45 days from today"),
    ("sleepcalc", "Sleep cycles", "Life", "Bedtimes that line up with 90-minute sleep cycles.", _sleep, "wake 7:30"),
    ("unixtime", "Unix timestamps", "Code", "Timestamp ↔ date.", _unix, "1767225600"),
    ("duration", "Time between", "Tools", "Time between two clock times.", _duration, "8:45 to 15:10"),
    ("reverse", "Reverse text", "Writing", "Backwards text.", _textops("reverse"), "hello"),
    ("sortlines", "Sort lines", "Writing", "Sort lines A→Z.", _textops("sortlines"), "paste lines"),
    ("dedupe", "Remove duplicate lines", "Writing", "Keep each line once.", _textops("dedupe"), "paste lines"),
    ("numberlines", "Number lines", "Writing", "Add 1. 2. 3. to lines.", _textops("numberlines"), "paste lines"),
    ("squash", "Clean up spacing", "Writing", "Remove extra spaces and blank lines.", _textops("squash"), "paste text"),
    ("slug", "URL slug", "Code", "Turn a title into a-url-slug.", _textops("slug"), "My Cool Post!"),
    ("acronym", "Acronym", "Writing", "First letters of each word.", _textops("acronym"), "as soon as possible"),
    ("urlencode", "URL encode", "Code", "Percent-encode text.", _textops("urlencode"), "a b&c"),
    ("urldecode", "URL decode", "Code", "Decode %20 etc.", _textops("urldecode"), "a%20b"),
    ("htmlescape", "HTML escape", "Code", "Escape < > & \".", _textops("htmlescape"), "<b>hi</b>"),
    ("htmlunescape", "HTML unescape", "Code", "&amp; → &.", _textops("htmlunescape"), "&lt;b&gt;"),
    ("charcodes", "Character codes", "Code", "Unicode code of each character.", _textops("charcodes"), "Hi!"),
    ("letterfreq", "Letter frequency", "Writing", "Most common letters (great for codebreaking).", _textops("letterfreq"), "paste text"),
    ("uuid", "UUID generator", "Code", "Random UUIDs.", _uuid, "5"),
    ("lorem", "Lorem ipsum", "Code", "Placeholder text.", _lorem, "60"),
    ("jwt", "JWT decoder", "Code", "Decode a JWT locally.", _jwt, "eyJ…"),
    ("cidr", "Subnet calculator", "Code", "IP range info.", _cidr, "192.168.1.0/24"),
    ("csvjson", "CSV → JSON", "Code", "Convert CSV with headers to JSON.", _csvjson, "name,age\nsam,16"),
    ("minify", "Minify JSON", "Code", "Shrink JSON onto one line.", _minify, '{"a": 1}'),
    ("bytes", "File sizes", "Code", "Bytes ↔ KB/MB/GB/TB (and KiB…).", _bytes, "4.7 GB"),
    ("downloadtime", "Download time", "Gaming", "How long a download takes.", _download, "50 GB at 80 Mbps"),
    ("kd", "K/D ratio", "Gaming", "K/D and KDA.", _kd, "24 9 5"),
    ("winrate", "Win rate", "Gaming", "Win % and wins needed to hit 60%.", _winrate, "37 21"),
    ("sens", "Sensitivity / eDPI", "Gaming", "eDPI and cm/360.", _sens, "0.4 800"),
    ("frametime", "FPS → frame time", "Gaming", "Milliseconds per frame.", _fps, "144"),
    ("8ball", "Magic 8-ball", "Fun", "Ask a yes/no question.", _eight, "will I pass maths?"),
    ("rps", "Rock paper scissors", "Fun", "Play a round.", _rps, "rock"),
    ("teams", "Team picker", "Fun", "Split names into random teams.", _teams, "sam, alex, jo, kai, 2 teams"),
    ("random", "Random number", "Fun", "Random number in a range.", _randnum, "1 100"),
    ("lotto", "Lucky numbers", "Fun", "Six random numbers.", _lottery, ""),
    ("wouldyou", "Would you rather", "Fun", "A random would-you-rather.", _wouldyou, ""),
    ("fact", "Random fact", "Fun", "A random interesting fact.", _fact, ""),
    ("anagram", "Anagram / scramble", "Fun", "Scramble a word.", _anagram, "orion"),
    ("palindrome", "Palindrome check", "Fun", "Reads the same backwards?", _palindrome, "racecar"),
    ("caesar", "Caesar cipher", "Fun", "Shift letters (give the shift first).", _caesar, "3 attack at dawn"),
    ("binarytext", "Text ↔ binary", "Code", "Text to 8-bit binary and back.", _binarytext, "Hi"),
]

# ------------------------------------------------------------------ more study tasks for every subject
TASKS6 = {
    "sixmark": ("6-mark plan", "Plan a 6-mark (or longest-mark) answer on the topic: the points to make, in order, with the key words examiners want."),
    "teachback": ("Teach me back", "Ask me 5 questions one by one to check I understand the topic, starting easy. Wait for each answer, then mark it."),
    "realworld": ("Real-world link", "Explain where this topic shows up in real life / the news / jobs, with 3 vivid examples."),
    "compare": ("Compare & contrast", "Compare the topic with the thing it's most often confused with, in a clear table, then a one-line memory hook."),
    "timeline": ("Story / timeline", "Explain the topic as a short story or step-by-step sequence so it's easy to remember."),
    "harder": ("Stretch question", "Give one genuinely hard grade 8-9 question on the topic with a full model answer."),
    "summary": ("60-second summary", "Summarise the topic in under 100 words for a last look before the exam."),
    "spec": ("Spec check", "List exactly what the specification says students need to know for this topic (AQA unless told otherwise), as tickable bullet points."),
}

PLAYBOOKS = [
    # school & study
    ("revisiontimetable", "Revision timetable", "School", "A weekly revision timetable around school, with your exams.", "Build a realistic weekly GCSE revision timetable as a table (days × slots) around a school day ending 15:10, with short sessions, breaks and rest time. Prioritise the subjects/exams given."),
    ("examnerves", "Exam nerves", "School", "Calm, practical tips before an exam.", "Give calm, practical, evidence-based tips to manage exam nerves the night before and on the day. Short and kind."),
    ("feedbackfix", "Act on teacher feedback", "School", "Turn feedback (WWW/EBI) into a fix list.", "Turn this teacher feedback into a short action plan: what to fix, how, and a 10-minute practice task for each point."),
    ("quotebank", "Quote bank", "School", "Key quotes for a text with analysis.", "For the named GCSE text, give 10 short key quotes grouped by theme/character, each with a one-line analysis and a technique."),
    ("contextpoints", "Context points", "School", "Historical/social context for a set text.", "Give the key context points for this GCSE English Literature text and how to weave them into an answer."),
    ("mathsmethod", "Which method?", "School", "Which maths method fits this question.", "Look at the maths question and explain which method to use and why, then give the first step only so the student can finish it."),
    ("practicalwriteup", "Practical write-up", "School", "Structure a science practical write-up.", "Help structure a GCSE science required-practical write-up: aim, hypothesis, variables, method, risk assessment, results table, conclusion, evaluation."),
    ("languagepaper", "English Language Q-by-Q", "School", "How to answer each English Language question.", "Explain how to approach each question on AQA GCSE English Language Paper 1 and 2: timings, marks, structure and a sentence starter for each."),
    ("historyessay", "History essay builder", "School", "Plan a 'how far do you agree' answer.", "Plan a GCSE History 'how far do you agree' / 16-mark answer: both sides with specific own knowledge, then a supported judgement."),
    ("geogcase", "Geography case study", "School", "Learnable case-study summary.", "Summarise the named GCSE Geography case study as learnable facts: location, causes, effects (social/economic/environmental), responses, key stats."),
    ("ccompsci", "Computer Science trace", "School", "Explain code or an algorithm for CS GCSE.", "Explain this algorithm/code at GCSE Computer Science level, then trace it with a small example in a trace table."),
    ("mfllearn", "Language phrases", "School", "Useful phrases for a speaking/writing topic.", "Give 15 high-level phrases for this GCSE language topic (target language + English), including opinions, tenses and a complex structure."),
    # writing
    ("emailteacher", "Email to a teacher", "Writing", "Polite email to a teacher.", "Write a short, polite email to a teacher about this (deadline extension, missed lesson, question). Respectful, clear subject line."),
    ("textreply", "Text reply ideas", "Writing", "3 ways to reply to a message.", "Give 3 different ways to reply to this message (chill, friendly, direct). Keep them natural for a 16-year-old."),
    ("rewritekind", "Make it kinder", "Writing", "Rewrite to sound nicer without losing the point.", "Rewrite this message so it's kinder and calmer but still makes the point."),
    ("rewriteconfident", "Make it confident", "Writing", "Rewrite to sound more confident.", "Rewrite this so it sounds confident and clear, not pushy."),
    ("shorten", "Shorten it", "Writing", "Cut text by half, keep the meaning.", "Rewrite this at about half the length, keeping every important point."),
    ("expand", "Expand it", "Writing", "Develop notes into full paragraphs.", "Turn these notes into well-written paragraphs."),
    ("titleideas", "Title ideas", "Writing", "10 titles for anything.", "Give 10 strong title options for this, varied in style."),
    ("storystart", "Story starter", "Writing", "An opening paragraph for creative writing.", "Write a gripping opening paragraph (GCSE creative-writing level, grade 9 vocabulary) based on this idea or picture description."),
    ("describe", "Descriptive writing", "Writing", "Rich description of a scene.", "Write a short piece of descriptive writing about this scene using varied sentence structures and senses. Then list the techniques used."),
    ("speechpersuade", "Persuasive speech", "Writing", "A persuasive speech with techniques.", "Write a persuasive speech on this using AFOREST techniques, then label the techniques used."),
    # content & creator
    ("tiktokidea", "TikTok ideas", "Content", "10 TikTok ideas for a niche.", "Give 10 specific TikTok video ideas for this niche, each with a 3-second hook and the format."),
    ("ytoutline", "YouTube outline", "Content", "Outline a YouTube video.", "Outline a YouTube video on this: hook, intro, sections with timestamps, call to action, and 5 title options."),
    ("hashtags", "Hashtags", "Content", "Relevant hashtags.", "Give 15 relevant hashtags for this post: 5 big, 5 medium, 5 niche."),
    ("bio", "Profile bio", "Content", "A short profile bio.", "Write 5 short profile bios for this person/brand (TikTok/Insta/Discord length)."),
    ("streamtitle", "Stream titles", "Content", "Catchy stream titles.", "Give 10 catchy stream titles for this game/plan."),
    ("collabdm", "Collab DM", "Content", "Message a creator about a collab.", "Write a short, friendly DM asking this creator to collab. Specific, not cringe."),
    ("commentreply", "Reply to comments", "Content", "Replies to comments, including hate.", "Suggest calm, funny or classy replies to these comments (handle hate without feeding it)."),
    ("thumbtext", "Thumbnail text", "Content", "3-word thumbnail text options.", "Give 10 punchy thumbnail text options (max 4 words) for this video."),
    # business
    ("businessidea", "Business ideas", "Money", "Zero-budget business ideas.", "Give 8 business ideas that need £0 to start and could work for a 16-year-old in the UK, with first steps for each. Keep it legal and realistic."),
    ("pricecheck", "Price my service", "Money", "What to charge.", "Suggest fair prices/tiers for this service in the UK with reasoning and an upsell."),
    ("landingcopy", "Landing page copy", "Money", "Headline, benefits, CTA.", "Write landing-page copy for this: headline, subheadline, 3 benefits, social-proof placeholder, FAQ, call to action."),
    ("dmpitch", "DM pitch", "Money", "Short pitch message to a business.", "Write a short, specific DM/email pitching this service to a local business. One clear offer, one question to reply to."),
    ("objection", "Handle 'too expensive'", "Money", "Reply to a price objection.", "Give 3 ways to respond to this objection without discounting straight away."),
    ("weeklyreview", "Weekly business review", "Money", "Review the week's numbers.", "Turn these weekly numbers/notes into a short review: wins, problems, one experiment for next week."),
    ("terms", "Simple terms", "Money", "Plain-English terms for a small service.", "Write simple plain-English terms for this small service (payment, refunds, delivery). Note it isn't legal advice."),
    ("receiptmsg", "Thank-you after purchase", "Money", "Message after someone buys.", "Write a thank-you message to send after a customer buys, with next steps and a review request."),
    # coding
    ("explainerror", "Explain this error", "Code", "What an error means and how to fix it.", "Explain this error message in plain English, the likely cause, and the fix. Show corrected code if code is given."),
    ("addcomments", "Comment my code", "Code", "Add clear comments.", "Add clear, helpful comments to this code without changing it."),
    ("convertcode", "Convert code", "Code", "Translate code to another language.", "Convert this code to the requested language idiomatically."),
    ("bigo", "Big-O", "Code", "Time/space complexity.", "Give the time and space complexity of this code with a one-paragraph explanation and a faster approach if there is one."),
    ("gitignore", ".gitignore", "Code", "A .gitignore for a project type.", "Write a sensible .gitignore for this kind of project."),
    ("apidesign", "Design an API", "Code", "REST endpoints for an idea.", "Design REST endpoints for this idea: routes, methods, request/response JSON examples."),
    ("htmlpage", "Quick web page", "Code", "A single-file HTML page.", "Write a single-file HTML/CSS/JS page for this. Modern look, no external dependencies."),
    ("pythonscript", "Python script", "Code", "A small Python script.", "Write a small, well-commented Python script that does this, with how to run it."),
    ("batchfile", "Windows .bat", "Code", "A Windows batch script.", "Write a safe Windows .bat script that does this, with comments. Never delete anything without a confirmation prompt."),
    ("sqlexplain", "Explain SQL", "Code", "What a query does.", "Explain what this SQL query does step by step and point out any problems."),
    # life
    ("fridgerecipe", "What can I cook?", "Life", "Recipe from what's in the fridge.", "Suggest 3 simple recipes using mainly these ingredients, with short steps. Student-friendly."),
    ("chores", "Chores rota", "Life", "A fair rota.", "Make a fair weekly chores rota as a table for these people and jobs."),
    ("convostart", "Conversation starters", "Life", "Things to talk about.", "Give 10 easy conversation starters for this situation."),
    ("partyplan", "Plan a hangout", "Life", "Plan a cheap day/evening out.", "Plan a cheap, fun hangout for this group: timings, costs, backup if it rains."),
    ("tidyplan", "Room reset", "Life", "A 30-minute room tidy plan.", "Give a 30-minute room-reset plan in 5-minute bursts."),
    ("mealprep", "Lunch ideas", "Life", "Cheap packed-lunch ideas.", "Give 10 cheap, easy packed-lunch ideas for school. Balanced, no calorie counting."),
    ("routine", "Morning routine", "Life", "A fast school-morning routine.", "Design a realistic school-morning routine that fits the given wake-up and leave times, minute by minute."),
    ("productreview", "Should I buy it?", "Life", "Pros/cons of a purchase.", "Help decide whether to buy this: pros, cons, cheaper alternatives, and what to check first. Neutral."),
    ("phonesetup", "Phone tips", "Life", "Useful tips for a phone.", "Give 10 genuinely useful tips/settings for this phone (e.g. Samsung S23)."),
    ("pcspeed", "Speed up my PC", "Life", "Safe ways to speed up Windows.", "Give safe, step-by-step ways to speed up this Windows PC (no registry hacks, no sketchy downloads)."),
    # gaming
    ("gamerec", "Game recommendations", "Gaming", "Games like the ones you like.", "Recommend 8 games similar to these, with why, price range and platforms."),
    ("buildguide", "Build guide", "Gaming", "A build/strategy for a game.", "Give a beginner-friendly build or strategy for this game/character, with why it works."),
    ("pcbuild", "PC build", "Gaming", "A PC parts list for a budget.", "Suggest a balanced gaming PC parts list for this budget (UK prices approximate), with upgrade path. Note prices change."),
    ("upgradeadvice", "What should I upgrade?", "Gaming", "Best upgrade for an old PC.", "Given these PC specs, what's the single best-value upgrade for gaming and why? Then the next two."),
    ("tournamentrules", "Tournament rules", "Gaming", "Rules for a small tournament.", "Write clear, fair rules for a small friends' tournament in this game."),
    ("clipcaption", "Clip caption", "Gaming", "Captions for a gaming clip.", "Give 10 funny or hype captions for this gaming clip."),
]


def install():
    added = 0
    for name, title, cat, desc, fn, ex in LOCALS:
        if name not in SKILLS:
            _add(name, title, cat, desc, fn=fn, example=ex)
            added += 1
    for sk, sname in SUBJECTS.items():
        for tk, (tt, tp) in TASKS6.items():
            k = f"{sk}_{tk}"
            if k not in SKILLS:
                _add(k, f"{sname.replace('GCSE ', '')}: {tt}", "Subjects", f"{sname} — {tt.lower()} (give the topic).",
                     prompt=f"You are an expert {sname} teacher (AQA unless told otherwise). {tp}", example="e.g. a topic name")
                added += 1
    for name, title, cat, desc, prompt in PLAYBOOKS:
        if name not in SKILLS:
            _add(name, title, cat, desc, prompt=prompt, example="")
            added += 1
    return added


ADDED = install()

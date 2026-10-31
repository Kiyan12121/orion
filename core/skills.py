"""Skills: ORION teaches itself new abilities.

"Learn how to X" -> ORION writes skills/<name>/skill.py with a run(**kwargs) function, checks the
code for dangerous calls, TESTS it in a separate process, and only keeps it if the test passes.
Skills always run in their own process, so a broken skill can't crash ORION.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from .coder import FLAGS, python_exe
from .paths import SKILLS_DIR
from .tools import REGISTRY, _blocked, tool

RUNNER = r'''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("skill", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
args = json.loads(sys.argv[2] or "{}")
res = mod.run(**args)
print("<<RESULT>>" + ("" if res is None else str(res)))
'''

FORBIDDEN = [
    (r"shutil\.rmtree", "deleting folders"), (r"\bos\.(remove|unlink|rmdir|removedirs)\b", "deleting files"),
    (r"\bwinreg\b", "editing the registry"), (r"\bctypes\b", "low-level system calls"),
    (r"\beval\s*\(|\bexec\s*\(|__import__\s*\(", "running hidden code"),
    (r"\.unlink\s*\(|\.rmdir\s*\(", "deleting files"), (r"keylog|pynput\.keyboard\.Listener", "keylogging"),
    (r"(api[_-]?key|password|token)\s*=\s*['\"][^'\"]{8,}", "hard-coded secrets"),
]
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def _check(code):
    problems = [why for pat, why in FORBIDDEN if re.search(pat, code, re.I)]
    for cmd in re.findall(r"(?:system|run|Popen|call|check_output)\s*\(\s*[rf]?['\"]([^'\"]+)", code):
        if _blocked(cmd):
            problems.append(f"blocked command: {cmd[:40]}")
    if not re.search(r"^def run\s*\(", code, re.M):
        problems.append("missing a top-level `def run(...)` function")
    return problems


def _exec(path, args, timeout=30):
    runner = os.path.join(SKILLS_DIR, "_runner.py")
    if not os.path.exists(runner):
        with open(runner, "w", encoding="utf-8") as f:
            f.write(RUNNER)
    try:
        p = subprocess.run([python_exe(), runner, path, json.dumps(args or {})], capture_output=True, text=True,
                           timeout=timeout, creationflags=FLAGS, encoding="utf-8", errors="replace",
                           cwd=os.path.dirname(path))
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    out = p.stdout or ""
    if p.returncode != 0 or "<<RESULT>>" not in out:
        return False, (p.stderr or out)[-2000:] or f"exit code {p.returncode}"
    return True, out.split("<<RESULT>>", 1)[1].strip()[:4000]


def _register(meta):
    name = meta["name"]
    path = os.path.join(SKILLS_DIR, name, "skill.py")
    props = {p: {"type": "string", "description": d} for p, d in meta.get("params", {}).items()}

    def fn(**kwargs):
        ok, out = _exec(path, kwargs, timeout=int(meta.get("timeout", 60)))
        return out if ok else f"ERROR: skill failed: {out}"

    REGISTRY[f"skill_{name}"] = {"fn": fn, "dangerous": False, "skill": True, "schema": {
        "type": "function", "function": {"name": f"skill_{name}", "description": f"[learned skill] {meta['description']}",
                                         "parameters": {"type": "object", "properties": props, "required": []}}}}


def load_all():
    for name in sorted(os.listdir(SKILLS_DIR)):
        mp = os.path.join(SKILLS_DIR, name, "skill.json")
        if os.path.exists(mp):
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("enabled", True):
                    _register(meta)
            except Exception:
                pass


def all_skills():
    out = []
    for name in sorted(os.listdir(SKILLS_DIR)):
        mp = os.path.join(SKILLS_DIR, name, "skill.json")
        if os.path.exists(mp):
            with open(mp, "r", encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def set_enabled(name, on):
    mp = os.path.join(SKILLS_DIR, name, "skill.json")
    with open(mp, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["enabled"] = bool(on)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    if on:
        _register(meta)
    else:
        REGISTRY.pop(f"skill_{name}", None)


@tool("Learn a new reusable skill: write Python code with a top-level `def run(...)` that returns a string. "
      "It is safety-checked and TESTED before being saved; if the test fails you get the error — fix and retry. "
      "Use standard library or common packages (requests, psutil, pyautogui). Don't delete files.",
      {"name": ("string", "snake_case name, e.g. 'weather_report'", True),
       "description": ("string", "What the skill does and when to use it", True),
       "code": ("string", "Full Python source with def run(**params) -> str", True),
       "params": ("array", "Parameters as 'name: description' strings", False),
       "test_args": ("string", "JSON object of arguments for the test run, e.g. {\"city\": \"Leicester\"}", False)})
def skill_create(name, description, code, params=None, test_args="{}"):
    name = name.lower().strip().replace(" ", "_").replace("-", "_")
    if not NAME_RE.match(name):
        return "ERROR: name must be snake_case letters/numbers, 2-31 chars."
    problems = _check(code)
    if problems:
        return "REJECTED by safety check: " + "; ".join(problems) + ". Rewrite without these."
    try:
        targs = json.loads(test_args or "{}")
    except json.JSONDecodeError:
        targs = {}
    tmp = tempfile.mkdtemp(prefix="orion_skill_")
    tpath = os.path.join(tmp, "skill.py")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write(code)
    ok, out = _exec(tpath, targs)
    shutil.rmtree(tmp, ignore_errors=True)
    if not ok:
        return f"TEST FAILED — not saved. Error:\n{out}\nFix the code and call skill_create again."
    pdict = {}
    for p in params or []:
        k, _, d = str(p).partition(":")
        if k.strip():
            pdict[k.strip()] = d.strip() or k.strip()
    folder = os.path.join(SKILLS_DIR, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "skill.py"), "w", encoding="utf-8") as f:
        f.write(code)
    meta = {"name": name, "description": description[:200], "params": pdict, "enabled": True,
            "created": time.strftime("%Y-%m-%d %H:%M"), "test_output": out[:300]}
    with open(os.path.join(folder, "skill.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    _register(meta)
    from .tools import CTX
    CTX.get("emit", lambda *a, **k: None)("skills_changed")
    return f"Skill '{name}' learned and tested. Test output: {out[:300]}. It's now available as skill_{name}."


@tool("List the skills ORION has learned.")
def skill_list():
    s = all_skills()
    return "\n".join(f"{m['name']}{'' if m.get('enabled', True) else ' (disabled)'}: {m['description']}" for m in s) \
        or "No skills learned yet."


@tool("Delete a learned skill.", {"name": ("string", "Skill name", True)}, dangerous=True)
def skill_delete(name):
    folder = os.path.join(SKILLS_DIR, os.path.basename(name.strip()))
    if not os.path.isdir(folder) or name.startswith("_"):
        return "No such skill."
    shutil.rmtree(folder)
    REGISTRY.pop(f"skill_{name}", None)
    from .tools import CTX
    CTX.get("emit", lambda *a, **k: None)("skills_changed")
    return f"Deleted skill {name}."

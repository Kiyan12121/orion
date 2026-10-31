"""Coder mode: a projects/ workspace where ORION writes, runs, tests and fixes code.

Inside projects/ ORION works freely (still backed up + logged). It can run Python, Node and
batch scripts, install packages, and package Python apps into a double-clickable .exe.
"""
import datetime
import os
import re
import shutil
import subprocess
import sys

from .paths import FROZEN, PROJECTS_DIR
from .tools import BACKUP_DIR, CTX, IS_WIN, _blocked, _changes, _save_changes, tool

FLAGS = 0x08000000 if IS_WIN else 0  # no console window popping up


def _safe_name(name):
    n = re.sub(r"[^\w\- ]", "", name).strip().replace(" ", "_")
    return n[:48] or "project"


def _proj_path(project, rel=""):
    base = os.path.realpath(os.path.join(PROJECTS_DIR, _safe_name(project)))
    p = os.path.realpath(os.path.join(base, rel))
    if not (p == base or p.startswith(base + os.sep)):
        raise ValueError("path escapes the project folder")
    return base, p


def python_exe():
    """The real Python to run user code with (not ORION.exe when frozen)."""
    if not FROZEN:
        return sys.executable.replace("pythonw.exe", "python.exe")
    for v in ("313", "312", "311", "310"):
        p = os.path.expandvars(rf"%LOCALAPPDATA%\Programs\Python\Python{v}\python.exe")
        if os.path.exists(p):
            return p
    return "python"


def _show(project, rel, content):
    CTX.get("emit", lambda *a, **k: None)("code", project=project, path=rel, content=content[:60000])


@tool("Create a new coding project folder in ORION's workspace. Returns its path.",
      {"name": ("string", "Project name, e.g. 'close_all_apps'", True),
       "description": ("string", "What the project is for", False)})
def project_create(name, description=""):
    base, _ = _proj_path(name)
    os.makedirs(base, exist_ok=True)
    readme = os.path.join(base, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{description}\n\nCreated by ORION {datetime.date.today()}\n")
    return f"Project ready: {base}"


@tool("List coding projects, or the files inside one project.",
      {"project": ("string", "Project name (leave empty to list all projects)", False)})
def project_list(project=""):
    if not project:
        items = sorted(d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d)))
        return "Projects: " + (", ".join(items) if items else "(none yet)")
    base, _ = _proj_path(project)
    out = []
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git", "build", "dist", ".venv")]
        for f in files:
            rel = os.path.relpath(os.path.join(dp, f), base)
            out.append(f"{rel} ({os.path.getsize(os.path.join(dp, f))}b)")
    return "\n".join(out[:300]) or "(empty)"


@tool("Write a whole file inside a project (creates folders as needed). Use for new files or full rewrites.",
      {"project": ("string", "Project name", True), "path": ("string", "File path inside the project, e.g. main.py", True),
       "content": ("string", "Full file content", True)})
def code_write(project, path, content):
    base, p = _proj_path(project, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    backup = None
    if os.path.exists(p):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, datetime.datetime.now().strftime("%Y%m%d_%H%M%S_") + os.path.basename(p))
        shutil.copy2(p, backup)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    c = _changes()
    c.append({"path": p, "backup": backup})
    _save_changes(c)
    _show(project, path, content)
    return f"Wrote {path} ({content.count(chr(10)) + 1} lines)."


@tool("Edit part of a file in a project by replacing an exact snippet (cheaper than rewriting the whole file).",
      {"project": ("string", "Project name", True), "path": ("string", "File inside the project", True),
       "find": ("string", "Exact existing text to replace (must appear once)", True),
       "replace": ("string", "New text", True)})
def code_edit(project, path, find, replace):
    base, p = _proj_path(project, path)
    with open(p, "r", encoding="utf-8") as f:
        src = f.read()
    n = src.count(find)
    if n == 0:
        return "ERROR: snippet not found — read the file and copy the text exactly."
    if n > 1:
        return f"ERROR: snippet appears {n} times — include more surrounding text so it's unique."
    return code_write(project, path, src.replace(find, replace, 1)).replace("Wrote", "Edited")


@tool("Read a file from a project (with line numbers).",
      {"project": ("string", "Project name", True), "path": ("string", "File inside the project", True)})
def code_read(project, path):
    base, p = _proj_path(project, path)
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()
    _show(project, path, src)
    lines = src.splitlines()
    return "\n".join(f"{i + 1:4} {l}" for i, l in enumerate(lines[:400])) + \
        (f"\n... ({len(lines) - 400} more lines)" if len(lines) > 400 else "")


@tool("Run a command inside a project folder and return output + exit code. Use it to run and TEST code, "
      "e.g. 'python main.py', 'node index.js', 'pip install requests', 'npm install'. "
      "If it fails, read the error, fix the code, and run again.",
      {"project": ("string", "Project name", True), "command": ("string", "Command to run", True),
       "timeout": ("integer", "Seconds before it's stopped (default 60, max 300)", False)})
def code_run(project, command, timeout=60):
    if _blocked(command):
        return "BLOCKED: that command is on the permanent blocklist."
    base, _ = _proj_path(project)
    os.makedirs(base, exist_ok=True)
    cmd = command.strip()
    py = python_exe()
    # lambdas, not replacement strings: Windows paths contain backslashes (C:\Users\...)
    cmd = re.sub(r"^(python3?|py(\s+-3(\.\d+)?)?)(?=\s|$)", lambda m: f'"{py}"', cmd)
    cmd = re.sub(r"^pip3?(?=\s)", lambda m: f'"{py}" -m pip', cmd)
    try:
        p = subprocess.run(cmd, cwd=base, shell=True, capture_output=True, text=True,
                           timeout=max(5, min(int(timeout or 60), 300)), creationflags=FLAGS,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return f"TIMEOUT after {timeout}s (program may be waiting for input or running forever).\n{out[-2000:]}"
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    text = f"exit code {p.returncode}\n"
    if out:
        text += f"--- output ---\n{out[-3500:]}\n"
    if err:
        text += f"--- errors ---\n{err[-3500:]}\n"
    return text


@tool("Package a Python project into a double-clickable .exe (PyInstaller). Takes a few minutes.",
      {"project": ("string", "Project name", True), "entry": ("string", "Main file, e.g. main.py", True),
       "windowed": ("boolean", "True for GUI apps (no console window)", False)})
def make_exe(project, entry, windowed=False):
    base, p = _proj_path(project, entry)
    if not os.path.exists(p):
        return f"ERROR: {entry} not found in {project}."
    py = python_exe()
    subprocess.run(f'"{py}" -m pip install --quiet pyinstaller', shell=True, cwd=base, creationflags=FLAGS,
                   capture_output=True)
    flag = "--windowed" if windowed else "--console"
    r = subprocess.run(f'"{py}" -m PyInstaller --noconfirm --onefile {flag} "{entry}"', shell=True, cwd=base,
                       capture_output=True, text=True, timeout=600, creationflags=FLAGS,
                       encoding="utf-8", errors="replace")
    exe = os.path.join(base, "dist", os.path.splitext(os.path.basename(entry))[0] + (".exe" if IS_WIN else ""))
    if r.returncode != 0 or not os.path.exists(exe):
        return f"ERROR: build failed.\n{(r.stderr or r.stdout)[-2500:]}"
    return f"Built {exe}"


@tool("Open a project folder in File Explorer (or a file in its default app).",
      {"project": ("string", "Project name", True), "path": ("string", "Optional file inside it", False)})
def project_open(project, path=""):
    base, p = _proj_path(project, path)
    if IS_WIN:
        os.startfile(p)
    return f"Opened {p}"

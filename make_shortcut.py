"""Creates ORION shortcuts on the Desktop AND in the Start Menu (works even when OneDrive has moved the Desktop)."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = sys.executable

# remember which Python ORION runs on (used by the updater and START_ORION.bat)
with open(os.path.join(here, "python_path.txt"), "w", encoding="utf-8") as f:
    f.write(pythonw)


def ps_quote(s):
    return s.replace("'", "''")


ps = f"""
$ErrorActionPreference = 'Stop'
$targets = @(
  [Environment]::GetFolderPath('Desktop'),
  (Join-Path ([Environment]::GetFolderPath('Programs')) '')
)
$made = @()
foreach ($dir in $targets) {{
  if (-not $dir) {{ continue }}
  if (-not (Test-Path $dir)) {{ New-Item -ItemType Directory -Force -Path $dir | Out-Null }}
  $lnk = Join-Path $dir 'ORION.lnk'
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $s.TargetPath = '{ps_quote(pythonw)}'
  $s.Arguments = '"{ps_quote(os.path.join(here, "ORION.pyw"))}"'
  $s.WorkingDirectory = '{ps_quote(here)}'
  $s.IconLocation = '{ps_quote(os.path.join(here, "ui", "orion.ico"))}'
  $s.Description = 'ORION personal AI'
  $s.Save()
  $made += $lnk
}}
$made -join "`n"
"""
r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   capture_output=True, text=True)
if r.returncode == 0 and r.stdout.strip():
    print("Shortcuts created:")
    for line in r.stdout.strip().splitlines():
        print("  " + line)
else:
    print("Couldn't create the shortcuts:", (r.stderr or r.stdout).strip()[:400])
    print("You can still start ORION by double-clicking START_ORION.bat in this folder.")

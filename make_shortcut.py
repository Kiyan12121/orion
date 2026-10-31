"""Creates a Desktop shortcut that launches ORION with a double-click (no console window)."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
lnk = os.path.join(desktop, "ORION.lnk")

ps = f"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}')
$s.TargetPath = '{pythonw}'
$s.Arguments = '"{os.path.join(here, "ORION.pyw")}"'
$s.WorkingDirectory = '{here}'
$s.IconLocation = '{os.path.join(here, "ui", "orion.ico")}'
$s.Description = 'ORION personal AI'
$s.Save()
"""
subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
print("Desktop shortcut created:", lnk)

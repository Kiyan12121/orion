@echo off
setlocal EnableDelayedExpansion
title ORION - Build .exe
cd /d "%~dp0"

rem Find a REAL Python (ignores the fake Microsoft Store shortcut)
set "PY="
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe"
)
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY ( echo Python not found - run 1_SETUP.bat first. & pause & exit /b )

echo  Building ORION.exe (optional - the Desktop shortcut already works)...
"%PY%" -m pip install pyinstaller
rem The heavy optional voice extras (PyTorch, SciPy...) are left OUT of the .exe - they'd make it ~2 GB
rem and one of them (webrtcvad) breaks PyInstaller. Wake word / Voice ID work in the Desktop-shortcut version.
"%PY%" -m PyInstaller --noconfirm --clean --windowed --onedir --name ORION ^
  --icon ui\orion.ico --add-data "ui;ui" --collect-all webview ^
  --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 --hidden-import edge_tts ^
  --hidden-import uiautomation ^
  --exclude-module torch --exclude-module torchvision --exclude-module torchaudio ^
  --exclude-module resemblyzer --exclude-module webrtcvad --exclude-module librosa ^
  --exclude-module scipy --exclude-module numba --exclude-module llvmlite --exclude-module sympy ^
  --exclude-module tensorflow --exclude-module tensorboard --exclude-module openwakeword ^
  --exclude-module onnxruntime --exclude-module sklearn --exclude-module pandas --exclude-module matplotlib ^
  --exclude-module IPython --exclude-module jupyter --exclude-module tkinter --exclude-module lxml ^
  ORION.pyw
if errorlevel 1 ( echo Build failed. & pause & exit /b )

if exist config.json copy /y config.json dist\ORION\config.json >nul
if exist data xcopy /e /i /y data dist\ORION\data >nul
echo.
echo  Built: dist\ORION\ORION.exe   (keep the whole ORION folder together)
explorer dist\ORION
pause

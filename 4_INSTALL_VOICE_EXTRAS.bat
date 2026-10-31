@echo off
setlocal EnableDelayedExpansion
title ORION - Voice extras
cd /d "%~dp0"
echo.
echo  Installs:
echo    - Wake word  ("Hey Jarvis" - offline, light on CPU)
echo    - Voice ID   (ORION learns your voice; ~1 GB, gaming PC recommended)
echo.
set "PY="
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY ( echo Python not found - run 1_SETUP.bat first. & pause & exit /b )

echo  [1/2] Wake word...
"%PY%" -m pip install openwakeword onnxruntime
"%PY%" -c "import openwakeword; openwakeword.utils.download_models(['hey_jarvis']); print('wake word model ready')"

echo.
choice /c YN /n /m "  Also install Voice ID? (big download, PC only) [Y/N]: "
if errorlevel 2 goto done
echo  [2/2] Voice ID...
"%PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"%PY%" -m pip install webrtcvad-wheels librosa scipy
"%PY%" -m pip install resemblyzer --no-deps

:done
echo.
echo  Done. In ORION open DEVICES (bottom of the left dock) to switch these on.
pause

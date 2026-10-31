@echo off
setlocal EnableDelayedExpansion
title ORION - Setup
cd /d "%~dp0"
echo.
echo  ===============================================
echo    ORION SETUP  -  installs everything it needs
echo  ===============================================
echo.

call :findpy
if defined PY goto :havepy

echo  Python isn't installed - installing Python 3.12 for you (about 2 minutes)...
echo.
where winget >nul 2>nul
if not errorlevel 1 (
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
  call :findpy
)
if defined PY goto :havepy

echo  Trying direct download from python.org...
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8.exe"
curl -L -o "%TEMP%\python_setup.exe" "%PYURL%"
if exist "%TEMP%\python_setup.exe" (
  "%TEMP%\python_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
  call :findpy
)
if defined PY goto :havepy

echo.
echo  [X] Couldn't install Python automatically.
echo      Install it from https://www.python.org/downloads/  (tick "Add python.exe to PATH")
echo      then run this file again.
start https://www.python.org/downloads/
pause
exit /b

:havepy
echo  Using Python: %PY%
"%PY%" --version
echo.
"%PY%" -m pip --version >nul 2>nul
if errorlevel 1 (
  echo  pip is missing - adding it...
  "%PY%" -m ensurepip --upgrade --default-pip >nul 2>nul
  "%PY%" -m pip --version >nul 2>nul
  if errorlevel 1 (
    curl -L -o "%TEMP%\get-pip.py" https://bootstrap.pypa.io/get-pip.py
    "%PY%" "%TEMP%\get-pip.py"
  )
  "%PY%" -m pip --version >nul 2>nul
  if errorlevel 1 (
    echo  [X] Couldn't add pip. Reinstall Python from python.org and tick "Add python.exe to PATH".
    start https://www.python.org/downloads/
    pause
    exit /b
  )
)
echo  [1/2] Installing packages (a few minutes the first time)...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo  [X] Package install failed - scroll up for the error.
  pause
  exit /b
)
echo.
echo  Installing ORION's built-in browser (Chromium, ~150 MB)...
"%PY%" -m playwright install chromium
echo.
echo  [2/3] Installing tools: ffmpeg (video editing) + Tesseract (screen reading)...
where winget >nul 2>nul
if not errorlevel 1 (
  where ffmpeg >nul 2>nul || winget install -e --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements
  if not exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-source-agreements --accept-package-agreements
) else (
  echo  winget not found - skip. Get ffmpeg from https://www.gyan.dev/ffmpeg/builds/ if you want the video editor.
)
echo.
echo  [3/3] Creating Desktop shortcut...
"%PY%" make_shortcut.py
echo.
echo  ===============================================
echo   DONE. Double-click ORION on your Desktop.
echo   Optional extras:
echo     2_INSTALL_LOCAL_BRAIN.bat   - offline AI brain
echo     4_INSTALL_VOICE_EXTRAS.bat  - "Hey Jarvis" wake word + Voice ID
echo  ===============================================
pause
exit /b

:findpy
rem Finds a REAL Python (ignores the fake Microsoft Store shortcut)
set "PY="
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe"
  if not defined PY if exist "%ProgramFiles%\Python%%V\python.exe" set "PY=%ProgramFiles%\Python%%V\python.exe"
)
if defined PY exit /b
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY exit /b
for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
exit /b

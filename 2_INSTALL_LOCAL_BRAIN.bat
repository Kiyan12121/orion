@echo off
title ORION - Local brain
echo.
echo  Installs Ollama + an AI that runs fully on this computer (offline backup brain).
echo  ORION picks the right size for your RAM automatically.
echo.
set "MODEL=qwen2.5:3b"
for /f %%R in ('powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)"') do set "RAM=%%R"
if defined RAM (
  rem 3b is the sweet spot for an older CPU - 7b is too slow without a strong GPU
  if %RAM% LSS 7 set "MODEL=qwen2.5:1.5b"
)
echo  This PC has about %RAM% GB of RAM - using %MODEL%
echo.

set "OLLAMA=ollama"
where ollama >nul 2>nul
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  ) else (
    echo  Installing Ollama...
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
      echo  winget failed - download it from https://ollama.com/download then run this again.
      start https://ollama.com/download
      pause
      exit /b
    )
    set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  )
)

echo.
echo  Downloading %MODEL% ...
"%OLLAMA%" pull %MODEL%
echo.
echo  Done. ORION finds it automatically (Settings ^> Local model = auto).
echo  It's used when the cloud brains are offline or out of allowance.
pause

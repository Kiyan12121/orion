@echo off
title ORION - Local brain
echo.
echo  Installs Ollama + a small AI that runs fully on this computer (offline backup brain).
echo.
echo    [1] Gaming PC (8GB+ RAM)  - qwen2.5:3b    (~2 GB download, smarter)
echo    [2] Laptop (4GB RAM)      - qwen2.5:1.5b  (~1 GB download, lighter)
echo.
choice /c 12 /n /m "  Choose 1 or 2: "
if errorlevel 2 (set "MODEL=qwen2.5:1.5b") else (set "MODEL=qwen2.5:3b")

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
echo  Done. In ORION: Settings ^> Local model ^> type  %MODEL%  ^> Save.
echo  ORION uses it automatically when the cloud brains are offline or out of allowance.
pause

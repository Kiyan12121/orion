@echo off
rem Starts ORION with no console window. Use this if the Desktop shortcut is missing.
cd /d "%~dp0"
set "PYW="
if exist python_path.txt set /p PYW=<python_path.txt
if defined PYW if exist "%PYW%" ( start "" "%PYW%" "%~dp0ORION.pyw" & exit /b )
where pyw >nul 2>nul && ( start "" pyw -3 "%~dp0ORION.pyw" & exit /b )
for %%V in (314 313 312 311 310) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" ( start "" "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" "%~dp0ORION.pyw" & exit /b )
)
echo Python not found - run 1_SETUP.bat first.
pause

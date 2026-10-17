@echo off
rem Clawdfield - double-click to start. Original work: Miaomiao (GitHub: Miaomiaomeowmeow), CC BY-NC-SA 4.0
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 server.py --open
  goto end
)
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py --open
  goto end
)
echo.
echo   Python was not found on this computer.
echo   1. Download it from https://www.python.org/downloads/
echo   2. When installing, tick "Add python.exe to PATH"
echo   3. Double-click start.bat again
echo.
:end
pause

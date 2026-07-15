@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install_dev.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" app.py --browser
pause

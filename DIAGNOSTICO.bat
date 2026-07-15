@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Diagnostico

if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual inexistente.
  pause
  exit /b 1
)

echo ==========================================================
echo   Diagnostico AuraCD
ECHO ==========================================================
echo.
".venv\Scripts\python.exe" --version
".venv\Scripts\python.exe" -m pip --version
echo.
".venv\Scripts\python.exe" -c "import flask, requests, dotenv; print('Dependencias essenciais: OK')"
echo.
".venv\Scripts\python.exe" -c "import os; print('Windows:', os.name == 'nt')"
echo.
echo Log salvo em: %%APPDATA%%\AuraCD\auracd.log
echo.
if exist "%APPDATA%\AuraCD\auracd.log" type "%APPDATA%\AuraCD\auracd.log"
echo.
pause

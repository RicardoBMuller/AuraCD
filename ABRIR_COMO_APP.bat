@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Janela desktop

if not exist ".venv\Scripts\python.exe" call install_dev.bat
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo O modo janela ainda nao foi instalado.
  echo Execute primeiro INSTALAR_MODO_JANELA.bat.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" app.py --native
if errorlevel 1 pause

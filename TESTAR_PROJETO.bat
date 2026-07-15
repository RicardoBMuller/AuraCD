@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Testes
if not exist ".venv\Scripts\python.exe" call install_dev.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
  echo.
  echo [ERRO] Um ou mais testes falharam.
) else (
  echo.
  echo Todos os testes passaram.
)
pause

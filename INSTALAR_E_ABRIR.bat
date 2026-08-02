@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Instalar e abrir

if not exist ".install_2_6_ok" call install_dev.bat
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar porque a instalacao falhou.
  pause
  exit /b 1
)

call ABRIR_AURACD.bat
exit /b %ERRORLEVEL%

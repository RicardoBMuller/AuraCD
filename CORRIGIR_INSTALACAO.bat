@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Corrigir instalacao

if exist ".install_2_6_ok" del /q ".install_2_6_ok" >nul 2>nul

call install_dev.bat
if errorlevel 1 exit /b 1

echo.
echo Instalacao corrigida. Abrindo o AuraCD...
call ABRIR_AURACD.bat
exit /b %ERRORLEVEL%

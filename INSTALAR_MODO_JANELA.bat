@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Modo janela opcional

if not exist ".venv\Scripts\python.exe" call install_dev.bat
if errorlevel 1 exit /b 1

echo Instalando o componente opcional de janela desktop...
".venv\Scripts\python.exe" -m pip install "pywebview>=6.1,<7"
if errorlevel 1 (
  echo.
  echo [AVISO] Nao foi possivel instalar o modo janela.
  echo O modo navegador continua funcionando normalmente.
  pause
  exit /b 1
)
echo.
echo Instalacao opcional concluida.
pause

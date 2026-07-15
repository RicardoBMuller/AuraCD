@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Instalacao

cls
echo ==========================================================
echo   AuraCD 2.6 - Instalacao local
echo ==========================================================
echo.

echo Pasta do projeto:
echo %CD%
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo [ERRO] O inicializador "py" do Python nao foi encontrado.
  echo.
  echo Instale o Python 3.10 ou superior em https://www.python.org/
  echo Durante a instalacao, marque "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

py -3 -c "import sys; assert sys.version_info >= (3,10); print('Python', sys.version.split()[0])"
if errorlevel 1 (
  echo.
  echo [ERRO] E necessario Python 3.10 ou superior.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [1/3] Criando ambiente virtual...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
) else (
  echo.
  echo [1/3] Ambiente virtual existente encontrado.
)

echo [2/3] Atualizando o instalador de pacotes...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error

echo [3/3] Instalando dependencias essenciais...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m py_compile app.py auracd\cd_player.py auracd\metadata.py auracd\settings.py auracd\demo_player.py auracd\libdiscid_reader.py auracd\collection.py
if errorlevel 1 goto :error

> .install_2_6_ok echo AuraCD 2.6 instalado em %DATE% %TIME%

echo.
echo ==========================================================
echo   Instalacao concluida com sucesso.
echo ==========================================================
echo.
exit /b 0

:error
echo.
echo ==========================================================
echo   [ERRO] A instalacao nao foi concluida.
echo ==========================================================
echo.
echo A janela permanecera aberta para voce copiar a mensagem.
echo.
echo Dica: se o erro mencionar "No matching distribution", confirme que
echo o arquivo requirements.txt desta versao possui requests maior ou igual a 2.32.
pause
exit /b 1

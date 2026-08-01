@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Gerar aplicativo

if not exist ".venv\Scripts\python.exe" call install_dev.bat
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install "pywebview>=6.1,<7"
if errorlevel 1 goto :error

if exist build rmdir /s /q build
if exist dist\AuraCD rmdir /s /q dist\AuraCD
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean AuraCD.spec
if errorlevel 1 goto :error

echo.
echo Aplicativo criado em: dist\AuraCD\AuraCD.exe
echo Teste o aplicativo antes de gerar o instalador.
pause
exit /b 0

:error
echo.
echo [ERRO] Nao foi possivel gerar o aplicativo.
pause
exit /b 1

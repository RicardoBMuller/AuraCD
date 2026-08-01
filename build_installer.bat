@echo off
setlocal
cd /d "%~dp0"
title AuraCD - Gerar instalador

call build_app.bat
if errorlevel 1 exit /b 1

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo.
  echo [ERRO] Inno Setup 6 nao foi encontrado.
  echo Baixe em https://jrsoftware.org/isdl.php e execute novamente.
  pause
  exit /b 1
)

"%ISCC%" "installer\AuraCD.iss"
if errorlevel 1 (
  echo [ERRO] Falha ao gerar o instalador.
  pause
  exit /b 1
)

echo.
echo Instalador criado em dist_installer\AuraCD-Setup.exe
pause

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AuraCD - Player de CDs

if not exist ".venv\Scripts\python.exe" (
  echo O AuraCD ainda nao foi instalado. Iniciando a instalacao...
  call install_dev.bat
  if errorlevel 1 exit /b 1
)

echo ==========================================================
echo   AuraCD 2.7
ECHO ==========================================================
echo.
echo O navegador sera aberto automaticamente.
echo Mantenha esta janela aberta enquanto estiver ouvindo o CD.
echo Para encerrar, pressione CTRL+C ou feche esta janela.
echo.

".venv\Scripts\python.exe" app.py --browser
set "AURACD_EXIT=%ERRORLEVEL%"

if not "%AURACD_EXIT%"=="0" (
  echo.
  echo [ERRO] O AuraCD foi encerrado com o codigo %AURACD_EXIT%.
  echo Consulte o log em: %%APPDATA%%\AuraCD\auracd.log
  echo.
  pause
)
exit /b %AURACD_EXIT%

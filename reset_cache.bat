@echo off
setlocal
set "AURACD_DATA=%APPDATA%\AuraCD"
echo Esta acao apagara o cache e as associacoes manuais de CDs.
choice /M "Continuar"
if errorlevel 2 exit /b 0
if exist "%AURACD_DATA%\cache" rmdir /s /q "%AURACD_DATA%\cache"
echo Cache apagado.
pause

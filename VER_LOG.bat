@echo off
if exist "%APPDATA%\AuraCD\auracd.log" (
  notepad "%APPDATA%\AuraCD\auracd.log"
) else (
  echo O arquivo de log ainda nao existe.
  pause
)

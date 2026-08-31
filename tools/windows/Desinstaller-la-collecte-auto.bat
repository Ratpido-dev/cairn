@echo off
REM Retire la tache planifiee. Les parties deja archivees restent en place :
REM rien n'est supprime dans Documents\cairn-parties.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cairn-collecte.ps1" -Desinstaller
echo.
pause

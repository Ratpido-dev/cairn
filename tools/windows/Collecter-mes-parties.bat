@echo off
REM Double-clic : archive les parties Hearthstone de cette session.
REM Le vrai travail est dans cairn-collecte.ps1, a cote de ce fichier.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cairn-collecte.ps1" %*
echo.
pause

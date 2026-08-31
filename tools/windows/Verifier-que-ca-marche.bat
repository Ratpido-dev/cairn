@echo off
REM Dit si la collecte automatique est bien en place, sous quel compte,
REM ou elle ecrit, et combien de parties sont deja archivees.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cairn-collecte.ps1" -Verifier
echo.
pause

@echo off
REM Double-clic UNE SEULE FOIS : la collecte devient automatique.
REM
REM Elle se relance a chaque ouverture de session Windows, puis toutes les
REM 20 minutes, sur secteur comme sur batterie. Plus rien a faire ensuite,
REM meme apres un redemarrage du PC.
REM
REM Pour tout arreter : Desinstaller-la-collecte-auto.bat
setlocal
set SCRIPT=%~dp0cairn-collecte.ps1

if not exist "%SCRIPT%" (
    echo Fichier introuvable : %SCRIPT%
    echo Garde tous les fichiers dans le meme dossier.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Installer
echo.
pause

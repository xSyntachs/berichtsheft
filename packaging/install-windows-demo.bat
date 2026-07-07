@echo off
rem Demo-Build (mit Reset und Ausbilder-Werkzeug) aus dem GitHub-Release. Ueber
rem curl geladen kein Mark-of-the-Web, also kein SmartScreen-Dialog.
setlocal
set "dest=%USERPROFILE%\Berichtsheft-Suite"
if not exist "%dest%" mkdir "%dest%"
echo Lade berichtsheft-demo.exe ...
curl -fL -# -o "%dest%\berichtsheft-demo.exe" "https://github.com/xSyntachs/berichtsheft/releases/latest/download/berichtsheft-demo.exe"
echo.
echo Fertig. Starten:  "%dest%\berichtsheft-demo.exe"
pause

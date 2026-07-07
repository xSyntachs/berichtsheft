@echo off
rem Laedt die Windows-EXE der Berichtsheft-Suite aus dem GitHub-Release. Ueber
rem curl geladen bekommt sie kein Mark-of-the-Web, also kein SmartScreen-Dialog.
setlocal
set "dest=%USERPROFILE%\Berichtsheft-Suite"
if not exist "%dest%" mkdir "%dest%"
echo Lade berichtsheft.exe ...
curl -fL -# -o "%dest%\berichtsheft.exe" "https://github.com/xSyntachs/berichtsheft/releases/latest/download/berichtsheft.exe"
echo.
echo Fertig. Starten:  "%dest%\berichtsheft.exe"
pause

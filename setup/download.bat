@echo off
rem Lädt die Windows-EXE der Berichtsheft-Suite aus dem GitHub-Release und
rem startet sie. Doppelklick genügt. Über curl geladen bekommt die EXE kein
rem Mark-of-the-Web, also kein SmartScreen-Dialog.
setlocal
echo Berichtsheft-Suite herunterladen
echo.
echo   [1] Normal
echo   [2] Demo (nur zum Testen)
echo.
choice /c 12 /d 1 /t 30 /m "Welche Version"
if errorlevel 2 (set "bin=berichtsheft-demo.exe") else (set "bin=berichtsheft.exe")
set "dest=%USERPROFILE%\Berichtsheft-Suite"
if not exist "%dest%" mkdir "%dest%"
echo Lade %bin% ...
curl -fL -# -o "%dest%\%bin%" "https://github.com/xSyntachs/berichtsheft/releases/latest/download/%bin%"
echo.
echo Fertig. Das Programm liegt unter "%dest%\%bin%" und startet jetzt.
start "" "%dest%\%bin%"

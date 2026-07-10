@echo off
rem Windows-Einstieg zum Bauen. Ruft die PowerShell-Version, die die eigentliche
rem Arbeit macht (Windows-EXEs, und falls Docker läuft auch die Linux-Binaries).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*

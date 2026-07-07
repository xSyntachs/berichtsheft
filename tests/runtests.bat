@echo off
chcp 65001 >nul
for %%f in ("%~dp0test_*.py") do (
  python "%%f"
  if errorlevel 1 exit /b 1
)

@echo off
rem Installs the AI engine from the command line (the app's "Setup assistant" does the same thing with a UI).
chcp 65001 >nul
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\install_ai_engine.py %*
) else (
  echo Run run.bat first ^(it creates the app environment^), or use the Setup assistant inside the app.
)
pause

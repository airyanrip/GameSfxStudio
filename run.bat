@echo off
rem GameSfxStudio launcher (run from source). First run: checks Python, asks before installing anything, then starts the app.
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

if exist ".venv\Scripts\python.exe" goto :start

rem ---- 1) find Python 3.11 / 3.12 (py launcher first, then the standard per-user location) ----
set "PY="
if defined GAMESFX_PYTHON set "PY=%GAMESFX_PYTHON%"
for %%V in (3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

rem ---- 2) not found: ask, then install (signature-verified, current user only, no admin) ----
if not defined PY (
  echo.
  echo Python 3.11 or 3.12 was not found. It is needed to run GameSfxStudio from source.
  echo.
  echo If you say yes, the official installer ^(about 25 MB^) is downloaded from python.org,
  echo its digital signature is verified, and Python is installed for YOUR USER only
  echo ^(no administrator rights, PATH is not changed^).
  echo.
  choice /c YN /n /m "Install Python 3.11 now? [Y/N] "
  if errorlevel 2 (
    echo Cancelled. Install Python 3.11 from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_python.ps1"
  if errorlevel 1 (
    echo Python installation failed. See the message above.
    pause
    exit /b 1
  )
  set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)

rem ---- 3) create the app environment and install its (small) requirements ----
echo.
echo Creating the app environment (.venv) and installing requirements...
%PY% -m venv .venv
if errorlevel 1 ( echo Could not create the virtual environment. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 ( echo Package install failed. Check your internet connection and run again. & pause & exit /b 1 )

:start
if defined GAMESFX_NO_START exit /b 0
".venv\Scripts\python.exe" app\main.py
pause

@echo off
rem Builds GameSfxStudio.exe (single file) into the project root.
rem Requires the app environment created by run.bat (.venv). The AI worker files are bundled so the exe works alone.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Run run.bat once first ^(it creates the app environment^).
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller || ( echo Could not install PyInstaller. & exit /b 1 )
cd app
"..\.venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --name GameSfxStudio ^
  --add-data "static;static" --add-data "..\engine\sao\worker.py;engine_bundle" --add-data "..\engine\sao\requirements-ai.txt;engine_bundle" ^
  --collect-submodules uvicorn ^
  --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.loops.auto main.py || exit /b 1
copy /y dist\GameSfxStudio.exe ..\GameSfxStudio.exe
rmdir /s /q build dist >nul 2>nul
del /q GameSfxStudio.spec >nul 2>nul
echo Done: GameSfxStudio.exe

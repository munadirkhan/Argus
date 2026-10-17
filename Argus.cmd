@echo off
rem Start Argus on the desktop: the hub, the floating orb, the tray icon.
rem Safe to double-click; installs and builds on first run only.
cd /d "%~dp0desktop"
if not exist "..\.venv\Scripts\python.exe" (
  echo Argus needs its Python environment first. From the argus folder run:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist "node_modules\electron" call npm install --no-audit --no-fund
if not exist "..\web\node_modules" call npm --prefix ..\web install --no-audit --no-fund
if not exist "..\web\dist\index.html" call npm run build:web
start "" "node_modules\electron\dist\electron.exe" .

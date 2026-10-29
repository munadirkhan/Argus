@echo off
rem Scripted demo for recording the video. No model calls, no spend.
rem Quit your normal Argus first (tray icon > Quit Argus).
rem Script and hotkeys: docs/DEMO_SCRIPT.md
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\demo_setup.py --reset || (pause & exit /b 1)
set ARGUS_DEMO=1
set ARGUS_FAKE=1
set ARGUS_WATCH_ROOT=%~dp0demo\workspace
start "" "desktop\node_modules\electron\dist\electron.exe" desktop

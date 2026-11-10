@echo off
cd /d "%~dp0"
set PYTHONHOME=
set HERMES_DESKTOP_REEXEC=1
"%~dp0.venv\Scripts\python.exe" launcher.py
if errorlevel 1 pause

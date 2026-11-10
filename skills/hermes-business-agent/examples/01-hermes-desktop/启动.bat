@echo off
setlocal
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
set HERMES_DESKTOP_REEXEC=1
"%~dp0Agent系统\.venv\Scripts\python.exe" "%~dp0连接系统\main.py" %*
if errorlevel 1 pause

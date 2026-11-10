@echo off
setlocal
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
set RD_BIZ_STANDALONE=1
"%~dp0..\Agentϵͳ\.venv\Scripts\python.exe" "%~dp0biz_main.py" %*
if errorlevel 1 pause

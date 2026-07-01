@echo off
REM Launch the GUI as administrator, so "Import from browser" can read the
REM (encrypted) cookies from recent Brave/Chrome. A UAC prompt will appear.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -Verb RunAs -WorkingDirectory '%CD%' -FilePath '%CD%\.venv\Scripts\pythonw.exe' -ArgumentList 'gui.py'"

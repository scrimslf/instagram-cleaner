@echo off
REM Double-click launcher for the graphical interface (no terminal window).
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" gui.py
) else (
    start "" pythonw gui.py
)

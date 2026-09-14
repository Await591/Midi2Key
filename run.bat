@echo off
rem Launch Midi2Key without a console window (falls back to python if needed).
cd /d "%~dp0"
where pythonw >nul 2>nul && start "" pythonw "main.pyw" || python "main.py"

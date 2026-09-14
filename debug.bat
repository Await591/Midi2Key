@echo off
rem Launch Midi2Key with a console window so errors are visible.
cd /d "%~dp0"
python "main.py" %*
pause

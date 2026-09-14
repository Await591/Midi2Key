@echo off
rem Run Midi2Key as administrator.
rem Needed when the target game/program runs elevated: Windows UIPI silently
rem drops simulated keys sent from a lower-integrity process.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath 'pythonw.exe' -ArgumentList '%~dp0main.pyw' -WorkingDirectory '%~dp0' -Verb RunAs"

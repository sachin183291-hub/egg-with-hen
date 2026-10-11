@echo off
color 0A
echo ========================================================
echo       GioTag - Live Hen & Comb AI Tracker Launcher
echo ========================================================
echo.
cd /d "c:\Users\sachi\Downloads\giotag project"

if exist "backend\.venv\Scripts\python.exe" (
    echo Using Backend Virtual Environment...
    "backend\.venv\Scripts\python.exe" live_hen_tracker.py
) else (
    echo Using System Python...
    python live_hen_tracker.py
)

pause

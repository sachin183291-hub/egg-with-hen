@echo off
color 0A
echo ========================================
echo       GioTag App Launcher
echo ========================================
echo.
echo Starting Backend Server...
start "GioTag Backend" /d "C:\Users\sachi\Downloads\giotag project\backend" cmd /k "call .venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo Starting Frontend Server...
start "GioTag Frontend" /d "C:\Users\sachi\Downloads\giotag project\frontend" cmd /k "npm run dev"

echo.
echo Waiting for servers to initialize (5 seconds)...
timeout /t 5 /nobreak >nul

echo Opening Application in your default browser...
start http://localhost:5173

echo.
echo Done! You can close this window.
timeout /t 3 >nul

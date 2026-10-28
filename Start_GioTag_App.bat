@echo off
color 0B
echo ======================================================================
echo                  GIOTAG SECURE EVIDENCE SYSTEM
echo ======================================================================
echo.

echo Starting Backend Server (Port 8000)...
start "GioTag Backend" /d "C:\Users\sachi\Downloads\giotag project\backend" cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo Starting AI Tracking Server (Port 5000)...
start "GioTag AI Tracking" /d "C:\Users\sachi\Downloads\giotag project" cmd /k "backend\.venv\Scripts\activate.bat && python flask_app.py"

echo Starting Frontend Dev Server (Port 5173)...
start "GioTag Frontend" /d "C:\Users\sachi\Downloads\giotag project\frontend" cmd /k "npm run dev"

echo.
echo Waiting 4 seconds for servers to initialize...
timeout /t 4 /nobreak >nul

echo.
echo ======================================================================
echo                      ACTIVE APPLICATION LINKS
echo ======================================================================
echo.
echo  [💻 LAPTOP / PC]:
echo     https://localhost:5173
echo.
echo  [📱 MOBILE PHONE] (Connect phone to same Wi-Fi or Laptop Hotspot):
echo     https://10.149.74.237:5173
echo     https://192.168.137.1:5173
echo.
echo  ----------------------------------------------------------------------
echo  IMPORTANT: HOW TO ACCESS ON MOBILE FOR 100%% EXACT HARDWARE GPS:
echo  1. Connect your mobile phone to the same Wi-Fi or Laptop Hotspot.
echo  2. Open Chrome/Safari and visit: https://10.149.74.237:5173
echo  3. When browser says 'Your connection is not private', tap:
echo     'Advanced' -> 'Proceed to 10.149.74.237 (unsafe)'
echo  4. Allow Location Permission when taking photo to get exact satellite GPS!
echo ======================================================================
echo.

echo Opening Dashboard in your browser...
start https://localhost:5173

pause

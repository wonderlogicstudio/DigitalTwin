@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Starting Streamlit app...
if "%DEMO_PORT%"=="" set DEMO_PORT=8501
echo Browser URL: http://localhost:%DEMO_PORT%
echo Press Ctrl+C in this window to stop the app.
python -m streamlit run app.py --server.port=%DEMO_PORT% --server.headless=true --browser.gatherUsageStats=false

if errorlevel 1 (
    echo.
    echo Streamlit app failed.
    pause
    exit /b 1
)

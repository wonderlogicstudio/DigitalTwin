@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Starting Streamlit app...
if "%DEMO_PORT%"=="" set DEMO_PORT=8501
echo Browser URL: http://localhost:%DEMO_PORT%
python scripts\start_streamlit.py --port %DEMO_PORT% --keep-running

if errorlevel 1 (
    echo.
    echo Streamlit app failed.
    pause
    exit /b 1
)

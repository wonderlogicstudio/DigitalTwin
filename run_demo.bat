@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Demo readiness check
python scripts\check_demo_readiness.py
if errorlevel 1 (
    echo.
    echo Demo is not ready.
    echo Run this first:
    echo   python scripts\run_pipeline.py --force --export-charts
    echo.
    pause
    exit /b 1
)

echo.
echo Starting Streamlit demo...
if "%DEMO_PORT%"=="" set DEMO_PORT=8501
echo Browser URL: http://localhost:%DEMO_PORT%
python scripts\start_streamlit.py --port %DEMO_PORT% --keep-running

@echo off
setlocal
cd /d "%~dp0"

rem Keep manual launches isolated from any obsolete in-tree .pyc files.
rem The cache lives in the user's temporary directory and is regenerated from
rem the source in this checkout; project source and artifacts are untouched.
set "PYTHONPYCACHEPREFIX=%TEMP%\FinancialPathTwinPyCache"

echo [Financial Path Twin] Verifying presentation population helpers...
python -c "from src.presentation_population import build_presentation_current_review_signal; print('Presentation helper import: OK')"
if errorlevel 1 (
    echo.
    echo Presentation helper verification failed. Check src\presentation_population.py in this checkout.
    pause
    exit /b 1
)

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

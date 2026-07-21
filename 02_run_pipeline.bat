@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Running pipeline...
python scripts\run_pipeline.py

if errorlevel 1 (
    echo.
    echo Pipeline failed.
    pause
    exit /b 1
)

echo.
echo Pipeline completed.
pause

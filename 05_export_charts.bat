@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Regenerating outputs and exporting chart HTML...
python scripts\run_pipeline.py --force --export-charts

if errorlevel 1 (
    echo.
    echo Chart export pipeline failed.
    pause
    exit /b 1
)

echo.
echo Chart export completed.
echo Output folder: reports\charts
pause

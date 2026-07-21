@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Regenerating all pipeline outputs...
python scripts\run_pipeline.py --force

if errorlevel 1 (
    echo.
    echo Forced pipeline run failed.
    pause
    exit /b 1
)

echo.
echo Forced pipeline run completed.
pause

@echo off
setlocal
cd /d "%~dp0"

echo [Financial Path Twin] Installing Python packages...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Installation completed.
pause

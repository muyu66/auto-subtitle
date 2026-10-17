@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ============================================================
echo   Video Quick Subtitle Tool - Install dependencies
echo ============================================================
echo.

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.9 or newer was not found.
    echo         Install it from https://www.python.org/downloads/
    echo         and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

echo Installing dependencies. This may take a few minutes...
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies. Please check your network.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Done. Double-click the run script to start the tool.
echo ============================================================
pause

@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

if not exist ".venv\Scripts\python.exe" (
    echo Dependencies are not installed. Please run the install script first.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -u main.py %*
set "CODE=%ERRORLEVEL%"

echo.
pause
exit /b %CODE%

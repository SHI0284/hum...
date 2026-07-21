@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python Launcher is not installed.
    echo Install Python 3.11 64-bit and enable the Python Launcher.
    pause
    exit /b 1
)

py -3.11 -m venv .venv
if errorlevel 1 goto :failed

.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :failed

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo HumO setup completed. Run run_windows.bat next.
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup failed. Check that Python 3.11 64-bit is installed.
pause
exit /b 1

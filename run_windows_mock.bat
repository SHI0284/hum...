@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup_windows.bat first.
    pause
    exit /b 1
)

set HUM_MOCK_RECORDING=1
.venv\Scripts\python.exe main.py
if errorlevel 1 pause

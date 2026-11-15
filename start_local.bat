@echo off
chcp 65001 >nul
title Personal AI Assistant - Second Brain (Local)
color 0A

echo =====================================================================
echo    ⚡ PERSONAL AI ASSISTANT - LOCAL RUNNER
echo =====================================================================
echo.

cd /d "%~dp0"

:: 1. Verify Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in system PATH.
    echo Please download and install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)

:: 2. Verify Virtual Environment
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

:: 3. Launch Local Runner
echo [INFO] Starting Local Agent in Polling mode...
python src\local_runner.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] Process exited with code %ERRORLEVEL%.
    pause
)


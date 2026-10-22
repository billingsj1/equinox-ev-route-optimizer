@echo off
title 2025 Equinox EV Route Optimizer
echo ========================================================
echo   Launching 2025 Equinox EV Multi-Objective Optimizer
echo ========================================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Setting up with uv...
    uv venv
    uv pip install -r requirements.txt
)

echo Starting web server on http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn ui.app:app --host 127.0.0.1 --port 8000
pause

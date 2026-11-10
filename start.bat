@echo off
title 2025 Equinox EV Route Optimizer
echo ========================================================
echo   Launching 2025 Equinox EV Multi-Objective Optimizer
echo ========================================================
echo.

cd /d "%~dp0"

REM 1. Detect Python executable (.venv preferred, fallback to system python)
set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PY_EXE=python"
    )
)

if "%PY_EXE%"=="" (
    echo [ERROR] Python environment not found!
    echo Please install Python or set up the virtual environment in .venv.
    echo.
    pause
    exit /b 1
)

REM 2. Check if local server is already running on port 8000
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Local server is already running on http://127.0.0.1:8000
) else (
    echo [INFO] Starting local server at http://127.0.0.1:8000 ...
    start "Equinox EV Route Optimizer (Server)" "%PY_EXE%" "%~dp0run.py" --host 127.0.0.1 --port 8000
    timeout /t 2 /nobreak >nul
)

REM 3. Open dashboard in default browser via HTTP (enables OSM map tiles, APIs, and caching)
echo.
echo [INFO] Opening dashboard in your default browser...
start "" "http://127.0.0.1:8000"

echo.
echo ========================================================
echo   Dashboard running at http://127.0.0.1:8000
echo   (Keep the server window open while using the app)
echo ========================================================
echo.
timeout /t 3 >nul

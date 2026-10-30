@echo off
title 2025 Equinox EV - Route Weather Engine Preview
echo ========================================================
echo   2025 Equinox EV - Route Weather Engine Preview
echo   Along-Route Microclimate & Vehicle Physics Simulator
echo ========================================================
echo.

cd /d "%~dp0"

:: Check if uv or python is available to start the backend server
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] uv detected. Launching local API server...
    start /min "Equinox Weather Server" uv run python run.py
    timeout /t 2 >nul
    start http://127.0.0.1:8000/weather-preview
    goto FINISH
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] python detected. Launching local API server...
    start /min "Equinox Weather Server" python run.py
    timeout /t 2 >nul
    start http://127.0.0.1:8000/weather-preview
    goto FINISH
)

:: If neither uv nor python are on PATH, open the standalone HTML directly
echo Opening standalone preview dashboard directly in your default browser...
start "" "%~dp0weather_preview.html"

:FINISH
echo.
echo [DONE] Dashboard launched in your default web browser!
echo URL: http://127.0.0.1:8000/weather-preview
echo Local file: %~dp0weather_preview.html
echo.
timeout /t 3 >nul

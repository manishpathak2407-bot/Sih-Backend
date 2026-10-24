@echo off
title SkyReady - Predictive Maintenance ^& Fleet Availability Optimizer
echo =================================================================
echo   SKYREADY ^| Predictive Maintenance ^& Fleet Availability Optimizer
echo   Ministry of Defence (MoD) / DSSC - SIH Problem Statement ID 26249
echo   Team ZEN / KILLSWITCHX - "One Loop: Sensor -^> Schedule -^> Spares"
echo =================================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%backend"

echo [+] Starting SkyReady Backend ^& Web Application on http://localhost:8000 ...
echo [+] Interactive API Documentation at http://localhost:8000/docs
echo [+] Tactical C2 Web Dashboard at http://localhost:8000/
echo =================================================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir "%SCRIPT_DIR%backend"
pause

# SkyReady PowerShell Launcher
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  SKYREADY | Predictive Maintenance & Fleet Availability Optimizer" -ForegroundColor Yellow
Write-Host "  Ministry of Defence (MoD) / DSSC • SIH Problem Statement ID 26249" -ForegroundColor Green
Write-Host "  Team ZEN / KILLSWITCHX • 'One Loop: Sensor -> Schedule -> Spares'" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $scriptDir "backend"

Write-Host "[+] Starting SkyReady Backend & Web Application on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "[+] Interactive API Documentation at http://localhost:8000/docs" -ForegroundColor Green
Write-Host "[+] Tactical C2 Web Dashboard at http://localhost:8000/" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir (Join-Path $scriptDir "backend")

# Crypto Rate Agent - PowerShell Local Launcher
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Crypto Rate Agent ⚡ Local Launcher (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[WARNING] .venv not found. Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    Write-Host "Installing requirements..." -ForegroundColor Yellow
    & (Join-Path $ScriptDir ".venv\Scripts\pip.exe") install -r (Join-Path $ScriptDir "requirements.txt")
}

Write-Host "Starting agent..." -ForegroundColor Green
Write-Host "  - To run in No-DB mode (RAM + CSV, max 3 cryptos): .\run.ps1 --no-db" -ForegroundColor Gray
Write-Host "  - Dashboard will be at: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host ""

& $PythonExe (Join-Path $ScriptDir "main.py") @args

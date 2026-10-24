@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo   Crypto Rate Agent ⚡ Local Launcher
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv\
    echo Initializing virtual environment...
    python -m venv .venv
    echo Installing dependencies...
    .\.venv\Scripts\pip install -r requirements.txt
)

echo Starting agent with Python (.venv)...
echo Usage examples:
echo   run.bat              (Runs using mode specified in config.yaml)
echo   run.bat --no-db      (Runs without DB in memory mode + CSV logging, max 3 cryptos)
echo   run.bat --port 8080  (Custom port)
echo.

.\.venv\Scripts\python.exe main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Agent stopped with error code %ERRORLEVEL%.
    pause
)

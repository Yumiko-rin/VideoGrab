@echo off
setlocal
cd /d "%~dp0"
title VideoGrab

echo ==============================================
echo   VideoGrab - local video downloader
echo   Close this window to stop the server
echo ==============================================
echo.

rem ---- 0. Port check: if already running, just open the page ----
netstat -ano | findstr /R /C:":8100 .*LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Port 8100 is already in use. VideoGrab may be running already.
    echo        - If started before: open http://127.0.0.1:8100 directly
    echo        - If Docker edition is running: run "docker compose down" first
    start "" http://127.0.0.1:8100
    pause
    exit /b 0
)

rem ---- 1. Find Python: prefer the official py launcher ----
set "PY="
py -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.10+ not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [0/3] Python: %PY%

rem ---- 2. Virtual env (created on first run, keeps system Python clean) ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] First run: creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem ---- 3. Install dependencies (skipped when present) ----
echo [2/3] Checking dependencies ...
"%VPY%" -m pip show fastapi yt-dlp >nul 2>nul
if errorlevel 1 (
    "%VPY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check your network and retry.
        pause
        exit /b 1
    )
)

rem ---- 4. Chromium (needed by Douyin/Kuaishou, fast when cached) ----
"%VPY%" -m playwright install chromium

rem ---- 5. Start server and open the page ----
echo [3/3] Starting server: http://127.0.0.1:8100
echo.
start "" http://127.0.0.1:8100
"%VPY%" -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
echo.
echo [INFO] Server exited. If there is an error above, screenshot it for feedback.
pause

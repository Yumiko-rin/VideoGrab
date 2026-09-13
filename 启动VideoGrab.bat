@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title VideoGrab - 视频解析下载器

echo ==============================================
echo   VideoGrab 快速启动
echo   关闭本窗口即停止服务
echo ==============================================
echo.

rem ---- 1. 查找 Python ----
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
    echo [错误] 未找到 Python，请先安装 Python 3.10+：https://www.python.org/downloads/
    pause
    exit /b 1
)

rem ---- 2. 虚拟环境（首次运行自动创建，不污染系统 Python） ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行：创建虚拟环境 .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem ---- 3. 安装依赖（已装则跳过） ----
echo [2/3] 检查依赖 ...
"%VPY%" -m pip show fastapi yt-dlp >nul 2>nul
if errorlevel 1 (
    "%VPY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试
        pause
        exit /b 1
    )
)

rem ---- 4. Chromium（抖音支持，已装则秒过） ----
"%VPY%" -m playwright install chromium

rem ---- 5. 启动并打开页面 ----
echo [3/3] 启动服务：http://127.0.0.1:8100
echo.
start "" http://127.0.0.1:8100
"%VPY%" -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
pause

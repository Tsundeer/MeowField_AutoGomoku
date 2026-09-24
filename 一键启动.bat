@echo off
setlocal
cd /d "%~dp0"
title MeowField 自动五子棋

rem ---- 查找 Python ----
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo [错误] 未找到 Python，请先安装 Python 3.9+ 并勾选 "Add Python to PATH"。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

rem ---- 检查依赖，缺失则自动安装 ----
%PY% -c "import cv2, mss, win32gui" >nul 2>nul
if errorlevel 1 (
    echo 首次运行：正在安装依赖（opencv-python / numpy / mss / pywin32）...
    %PY% -m pip install -r requirements.txt
    %PY% -c "import cv2, mss, win32gui" >nul 2>nul
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo 正在启动 MeowField 自动五子棋（关闭 GUI 窗口即退出）...
%PY% main.py
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出，请查看上方报错信息。
    pause
)
endlocal

@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"
title Rain World 存档分析器

rem 1) 优先启动已发布版本：release\RwSaveTool-v* 取最后一个
set "RW_REL="
for /d %%D in ("release\RwSaveTool-v*") do set "RW_REL=%%~fD"
if defined RW_REL if exist "%RW_REL%\RwSaveTool.exe" (
    start "" "%RW_REL%\RwSaveTool.exe"
    exit /b 0
)

rem 2) 其次是本地打包产物
if exist "dist\RwSaveTool\RwSaveTool.exe" (
    start "" "dist\RwSaveTool\RwSaveTool.exe"
    exit /b 0
)

rem 3) 最后退回源码方式（需要 .venv）
if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo [错误] 没找到已发布版本，也没有 .venv 虚拟环境。
    echo.
    echo 请选择一种方式：
    echo   1. 用发布版：双击 release\ 下任意版本的 RwSaveTool.exe
    echo   2. 用源码：在当前目录执行以下命令
    echo        python -m venv .venv
    echo        .venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
    echo.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"
title Rain World 存档分析工具 - 调试模式

echo 当前目录: %CD%
echo.

set "RW_REL="
for /d %%D in ("release\RwSaveTool-v*") do set "RW_REL=%%~fD"
if defined RW_REL (
    echo [提示] 检测到发布版 %RW_REL%，调试模式改为运行源码。
    echo.
)

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 找不到 .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
echo.
echo 程序已退出，返回码 %ERRORLEVEL%
pause

@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"
title Rain World 存档分析器

rem ==================================================================
rem 启动顺序（2026-11-07 调整）：源码优先，打包版兜底。
rem
rem 原来的顺序是先找 release\RwSaveTool-v*\RwSaveTool.exe 和
rem dist\RwSaveTool\RwSaveTool.exe —— 但打包版 exe 里内嵌的是
rem 「打包那一刻」的 ui\rw_gui.html，改了源码再点这个 bat，
rem 看到的仍然是旧界面，很容易误判成「改动没生效」。
rem 所以源码开发期一律走 .venv；只有没有 .venv 时才用打包版。
rem ==================================================================

if exist "ui\rw_gui.html" for %%F in ("ui\rw_gui.html") do echo [界面] ui\rw_gui.html  修改于 %%~tF  大小 %%~zF 字节
echo.

if exist ".venv\Scripts\pythonw.exe" (
    echo [源码] 用 .venv 运行 main.py（源码改动立刻生效）
    start "" ".venv\Scripts\pythonw.exe" main.py
    exit /b 0
)

set "RW_REL="
for /d %%D in ("release\RwSaveTool-v*") do set "RW_REL=%%~fD"
if defined RW_REL if exist "%RW_REL%\RwSaveTool.exe" (
    echo [打包] 没有 .venv，启动 %RW_REL%\RwSaveTool.exe
    echo        注意：这是打包版，界面冻结在打包那一天。
    start "" "%RW_REL%\RwSaveTool.exe"
    exit /b 0
)

if exist "dist\RwSaveTool\RwSaveTool.exe" (
    echo [打包] 没有 .venv，启动 dist\RwSaveTool\RwSaveTool.exe
    echo        注意：这是打包版，界面冻结在打包那一天。
    start "" "dist\RwSaveTool\RwSaveTool.exe"
    exit /b 0
)

echo.
echo [错误] 既没有 .venv 虚拟环境，也没有打包好的 exe。
echo.
echo 请任选一种方式：
echo   1. 用源码：在当前目录执行
echo        python -m venv .venv
echo        .venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
echo   2. 用发布版：解压 release\ 下的 zip，双击里面的 RwSaveTool.exe
echo.
pause
exit /b 1

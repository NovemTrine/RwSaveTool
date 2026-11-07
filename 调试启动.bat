@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"
title Rain World 存档分析器 - 调试模式（源码 + DevTools）

echo 当前目录: %CD%
if exist "ui\rw_gui.html" for %%F in ("ui\rw_gui.html") do echo 界面文件: ui\rw_gui.html  修改于 %%~tF  大小 %%~zF 字节
echo 说明: 本模式直接跑源码，改完 ui/ 或 core/ 重启即可看到；
echo       窗口内按 F12 或右键「检查」打开 DevTools 看报错。
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 找不到 .venv\Scripts\python.exe
    echo        先在当前目录建虚拟环境并装依赖，见 启动.bat 的提示。
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py --debug
echo.
echo 程序已退出，退出码 %ERRORLEVEL%
pause

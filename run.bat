@echo off
REM ============================================================
REM Sharp GUI - 一键启动脚本 (Windows)
REM ============================================================

setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM 检查虚拟环境
if not exist "%SCRIPT_DIR%venv" (
    echo 错误: 虚拟环境不存在
    echo 请先运行: install.bat
    pause
    exit /b 1
)

REM 检查 ml-sharp
if not exist "%SCRIPT_DIR%ml-sharp" (
    echo 错误: ml-sharp 未安装
    echo 请先运行: install.bat
    pause
    exit /b 1
)

REM 激活虚拟环境
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

REM 检查 sharp 命令
where sharp >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 错误: Sharp 未正确安装
    echo 请重新运行: install.bat
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Sharp GUI 启动中...
echo ========================================
echo.
echo 访问地址:
echo   http://127.0.0.1:5050
echo.
echo 按 Ctrl+C 停止服务器
echo.

python app.py

pause

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

REM 检查 HTTPS 证书状态
if exist "%SCRIPT_DIR%cert.pem" if exist "%SCRIPT_DIR%key.pem" (
    echo [HTTPS] 完整功能支持
    echo.
    echo 访问地址:
    echo   本机:   https://127.0.0.1:5050
    echo   局域网: https://[你的IP]:5050
    echo.
    echo 首次访问需接受证书安全警告
) else (
    echo [HTTP] 陀螺仪功能仅本机可用
    echo.
    echo 访问地址:
    echo   本机:   http://127.0.0.1:5050
    echo   局域网: http://[你的IP]:5050 ^(陀螺仪不可用^)
    echo.
    echo 建议运行 python generate_cert.py 生成证书以启用 HTTPS
)
echo.
echo 按 Ctrl+C 停止服务器
echo.

python app.py

pause

@echo off
REM ============================================================
REM Sharp GUI - 一键启动脚本 (Windows)
REM 
REM 用法: run.bat [--legacy]
REM   --legacy  使用原始单文件版本
REM ============================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM 默认使用 React 版本
set USE_LEGACY=false
set SHARP_FRONTEND_MODE=react

REM 解析参数
if "%1"=="--legacy" (
    set USE_LEGACY=true
    set SHARP_FRONTEND_MODE=legacy
)
if "%1"=="-h" goto :show_help
if "%1"=="--help" goto :show_help
goto :main

:show_help
echo 用法 (Usage): run.bat [--legacy]
echo.
echo 选项 (Options):
echo   --legacy    使用原始单文件前端
echo   -h, --help  显示帮助信息
exit /b 0

:main
REM 检查虚拟环境
if not exist "%SCRIPT_DIR%venv" (
    echo ================================================================
    echo   错误: 虚拟环境不存在 (Virtual environment not found)
    echo ================================================================
    echo.
    echo   请先运行安装脚本:
    echo     install.bat
    echo.
    echo ================================================================
    pause
    exit /b 1
)

REM 检查 ml-sharp
if not exist "%SCRIPT_DIR%ml-sharp" (
    echo ================================================================
    echo   错误: ml-sharp 未安装 (ml-sharp not installed)
    echo ================================================================
    echo.
    echo   请先运行安装脚本:
    echo     install.bat
    echo.
    echo ================================================================
    pause
    exit /b 1
)

REM 激活虚拟环境
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

REM 检查 sharp 命令
where sharp >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ================================================================
    echo   错误: Sharp 未正确安装 (Sharp not properly installed)
    echo ================================================================
    echo.
    echo   请重新安装:
    echo     rmdir /s /q venv
    echo     install.bat
    echo.
    echo ================================================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Sharp GUI 启动中...
echo ========================================
echo.

REM 获取本机局域网 IP
for /f "delims=" %%i in ('python -c "import socket; ips=list(set(ip[4][0] for ip in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))); result=next((ip for ip in ips if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16<=int(ip.split('.')[1])<=31 and not ip.startswith('172.17.'))),None); print(result or next((ip for ip in ips if not ip.startswith('127.')),'127.0.0.1'))" 2^>nul') do set LOCAL_IP=%%i
if not defined LOCAL_IP set LOCAL_IP=127.0.0.1

REM 检查 HTTPS 证书状态
if exist "%SCRIPT_DIR%cert.pem" if exist "%SCRIPT_DIR%key.pem" (
    set PROTOCOL=https
    echo [HTTPS] 完整功能支持
) else (
    set PROTOCOL=http
    echo [HTTP] 陀螺仪功能仅本机可用
    echo 运行 python generate_cert.py 可启用 HTTPS
)
echo.
echo 访问地址 (Access URLs):
echo   本机:     %PROTOCOL%://127.0.0.1:5050
echo   局域网:   %PROTOCOL%://%LOCAL_IP%:5050
echo.
echo 按 Ctrl+C 停止服务器
echo.

REM 传递 LAN IP 给 Flask
set SHARP_LAN_IP=%LOCAL_IP%

REM 设置前端模式
if "%USE_LEGACY%"=="true" (
    echo [Legacy 模式] 单文件版本
) else (
    if exist "%SCRIPT_DIR%frontend\dist" (
        echo [React 模式] 现代版本
    ) else (
        echo [警告] React 构建不存在，使用 Legacy 模式
        echo    运行 build.bat 可构建 React 前端
        set SHARP_FRONTEND_MODE=legacy
    )
)
echo.

python app.py

pause

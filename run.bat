@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM Sharp GUI - Launcher Script (Windows)
REM 
REM Usage: run.bat [--legacy] [--verbose]
REM   --legacy   Use legacy single-file frontend
REM   --verbose  Print extra diagnostics for troubleshooting
REM ============================================================

setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Default to React frontend
set USE_LEGACY=false
set SHARP_FRONTEND_MODE=react
if not defined SHARP_LOG_LEVEL set SHARP_LOG_LEVEL=INFO
if not defined SHARP_LOG_FILE set "SHARP_LOG_FILE=%SCRIPT_DIR%sharp-gui-verbose.log"
if not defined PYTHONFAULTHANDLER set PYTHONFAULTHANDLER=1

REM Parse arguments
:parse_args
if "%~1"=="" goto :main
if /I "%~1"=="--legacy" (
    set USE_LEGACY=true
    set SHARP_FRONTEND_MODE=legacy
    shift
    goto :parse_args
)
if /I "%~1"=="--verbose" (
    set SHARP_VERBOSE=1
    set SHARP_LOG_LEVEL=DEBUG
    set "SHARP_LOG_FILE=%SCRIPT_DIR%sharp-gui-verbose.log"
    set PYTHONFAULTHANDLER=1
    shift
    goto :parse_args
)
if "%~1"=="-h" goto :show_help
if "%~1"=="--help" goto :show_help
echo 未知参数: %~1
goto :main

:show_help
echo 用法 (Usage): run.bat [--legacy] [--verbose]
echo.
echo 选项 (Options):
echo   --legacy    使用原始单文件前端
echo   --verbose   输出更多诊断日志，用于反馈问题
echo   -h, --help  显示帮助信息
exit /b 0

:main
REM Check virtual environment
if exist "%SCRIPT_DIR%venv" goto :venv_ok
echo ================================================================
echo   错误: 虚拟环境不存在
echo   Virtual environment not found
echo ================================================================
echo.
echo   请先运行安装脚本:
echo     install.bat
echo.
echo ================================================================
pause
exit /b 1

:venv_ok
REM Check ml-sharp
if exist "%SCRIPT_DIR%ml-sharp" goto :sharp_ok
echo ================================================================
echo   错误: ml-sharp 未安装
echo   ml-sharp not installed
echo ================================================================
echo.
echo   请先运行安装脚本:
echo     install.bat
echo.
echo ================================================================
pause
exit /b 1

:sharp_ok
REM Activate virtual environment
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

REM Check sharp command
where sharp >nul 2>&1
if !ERRORLEVEL! equ 0 goto :sharp_cmd_ok
echo ================================================================
echo   错误: Sharp 未正确安装
echo   Sharp not properly installed
echo ================================================================
echo.
echo   请重新安装:
echo     rmdir /s /q venv
echo     install.bat
echo.
echo ================================================================
pause
exit /b 1

:sharp_cmd_ok

REM Optional native COLMAP for video reconstruction
if exist "%SCRIPT_DIR%.sharp-gui-tools\colmap\bin\colmap.exe" (
    set "PATH=%SCRIPT_DIR%.sharp-gui-tools\colmap\bin;%PATH%"
    echo [Video 3D] Native COLMAP detected
)

echo.
echo ========================================
echo   Sharp GUI 启动中...
echo ========================================
echo.
if "%SHARP_VERBOSE%"=="1" (
    echo [Verbose] 已启用详细诊断日志
    echo [Verbose] 日志文件: %SHARP_LOG_FILE%
)

REM Get LAN IP
for /f "delims=" %%i in ('python -c "import socket; ips=list(set(ip[4][0] for ip in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))); result=next((ip for ip in ips if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16<=int(ip.split('.')[1])<=31 and not ip.startswith('172.17.'))),None); print(result or next((ip for ip in ips if not ip.startswith('127.')),'127.0.0.1'))" 2^>nul') do set LOCAL_IP=%%i
if not defined LOCAL_IP set LOCAL_IP=127.0.0.1

REM Check HTTPS certificate
if exist "%SCRIPT_DIR%cert.pem" if exist "%SCRIPT_DIR%key.pem" (
    set PROTOCOL=https
    echo [HTTPS] 完整功能支持
) else (
    set PROTOCOL=http
    echo [HTTP] 陀螺仪功能仅本机可用
    echo 运行 python tools\generate_cert.py 可启用 HTTPS
)
echo.
echo 访问地址 (Access URLs):
echo   本机:     %PROTOCOL%://127.0.0.1:5050
echo   局域网:   %PROTOCOL%://%LOCAL_IP%:5050
echo.
echo 按 Ctrl+C 停止服务器
echo.

REM Pass LAN IP to Flask
set SHARP_LAN_IP=%LOCAL_IP%

REM Set frontend mode
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

REM Skip SSL verification for networks with SSL proxy
set PYTHONHTTPSVERIFY=0
python app.py

pause

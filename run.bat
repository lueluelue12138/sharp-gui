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

REM 获取本机局域网 IP (使用 Python getaddrinfo)
for /f "delims=" %%i in ('python -c "import socket; ips=list(set(ip[4][0] for ip in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))); result=next((ip for ip in ips if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16<=int(ip.split('.')[1])<=31 and not ip.startswith('172.17.'))),None); print(result or next((ip for ip in ips if not ip.startswith('127.')),'127.0.0.1'))" 2^>nul') do set LOCAL_IP=%%i
if not defined LOCAL_IP set LOCAL_IP=127.0.0.1

REM 检查 HTTPS 证书状态
if exist "%SCRIPT_DIR%cert.pem" if exist "%SCRIPT_DIR%key.pem" (
    set PROTOCOL=https
    echo [HTTPS] 完整功能支持
) else (
    set PROTOCOL=http
    echo [HTTP] 陀螺仪功能仅本机可用
    echo 建议运行 python generate_cert.py 生成证书以启用 HTTPS
)
echo.
echo 访问地址:
echo   本机:   %PROTOCOL%://127.0.0.1:5050
echo   局域网: %PROTOCOL%://%LOCAL_IP%:5050
echo.
echo 按 Ctrl+C 停止服务器
echo.

REM 传递正确的 LAN IP 给 Flask
set SHARP_LAN_IP=%LOCAL_IP%

python app.py

pause

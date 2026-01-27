@echo off
REM ============================================================
REM Sharp GUI - 前端构建脚本 (Windows)
REM 构建 React 生产版本
REM ============================================================

setlocal
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo   Sharp GUI - 前端构建
echo ========================================
echo.

REM 检查 Node.js
where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Node.js
    echo 请先安装 Node.js 18+ 或运行 install.bat
    pause
    exit /b 1
)

REM 检查前端目录
if not exist "%SCRIPT_DIR%frontend" (
    echo [错误] frontend 目录不存在
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%frontend"

REM 安装依赖 (如果需要)
if not exist "node_modules" (
    echo [1/2] Installing dependencies...
    npm install
)

REM 构建
echo [2/2] Building React frontend...
npm run build

echo.
echo ============================================
echo   构建完成!
echo ============================================
echo.
echo 输出目录: frontend\dist\
echo 运行 run.bat 启动服务器
echo.

pause

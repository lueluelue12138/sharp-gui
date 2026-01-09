@echo off
REM ============================================================
REM Sharp GUI - Windows 一键安装脚本
REM 自动拉取 Apple ml-sharp 并部署 GUI
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Sharp GUI - Windows 安装脚本
echo   https://github.com/apple/ml-sharp
echo ========================================
echo.

set SHARP_REPO=https://github.com/apple/ml-sharp.git
set SHARP_DIR=ml-sharp
set SCRIPT_DIR=%~dp0

REM 检测 Python
echo [1/6] 检查 Python 环境...

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python！
    echo.
    echo 请从以下网址下载安装 Python 3.10+:
    echo   https://www.python.org/downloads/
    echo.
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] 找到 Python: %PYTHON_VERSION%

REM 检测 Git
echo.
echo [2/6] 检查 Git...

where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Git！
    echo.
    echo 请从以下网址下载安装 Git:
    echo   https://git-scm.com/download/win
    pause
    exit /b 1
)
echo [OK] Git 已安装

REM 检查 CUDA
echo.
echo [3/6] 检查 CUDA 环境...

where nvcc >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=5" %%i in ('nvcc --version ^| findstr release') do set CUDA_VERSION=%%i
    echo [OK] 找到 CUDA: !CUDA_VERSION!
) else (
    where nvidia-smi >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [警告] 找到 NVIDIA 驱动，但未安装 CUDA toolkit
    ) else (
        echo [警告] 未检测到 NVIDIA GPU，将使用 CPU 模式
    )
)

REM 拉取/更新 ml-sharp
echo.
echo [4/6] 获取 Apple ml-sharp...

if exist "%SCRIPT_DIR%%SHARP_DIR%" (
    echo [警告] ml-sharp 目录已存在
    set /p UPDATE="是否更新到最新版本? [Y/n] "
    if /i not "!UPDATE!"=="n" (
        cd /d "%SCRIPT_DIR%%SHARP_DIR%"
        git pull origin main 2>nul || git pull origin master 2>nul
        cd /d "%SCRIPT_DIR%"
        echo [OK] ml-sharp 已更新
    )
) else (
    echo 正在克隆 %SHARP_REPO% ...
    git clone --depth 1 "%SHARP_REPO%" "%SHARP_DIR%"
    echo [OK] ml-sharp 克隆完成
)

REM 创建虚拟环境
echo.
echo [5/6] 创建虚拟环境...

set VENV_DIR=%SCRIPT_DIR%venv

if exist "%VENV_DIR%" (
    echo [警告] 虚拟环境已存在
    set /p RECREATE="是否删除并重新创建? [y/N] "
    if /i "!RECREATE!"=="y" (
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo [OK] 使用现有虚拟环境
        goto install_deps
    )
)

python -m venv "%VENV_DIR%"
echo [OK] 虚拟环境创建完成

:install_deps
REM 安装依赖
echo.
echo [6/6] 安装 Python 依赖...

call "%VENV_DIR%\Scripts\activate.bat"

pip install --upgrade pip

echo 安装 Sharp 核心 (这可能需要几分钟)...
cd /d "%SCRIPT_DIR%%SHARP_DIR%"
pip install -r requirements.txt
cd /d "%SCRIPT_DIR%"

echo 安装 GUI 依赖...
pip install flask

echo [OK] 所有依赖安装完成

REM 创建目录
if not exist "%SCRIPT_DIR%inputs" mkdir "%SCRIPT_DIR%inputs"
if not exist "%SCRIPT_DIR%outputs" mkdir "%SCRIPT_DIR%outputs"

REM 测试安装
echo.
echo 测试安装...

sharp --help >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] Sharp CLI 安装失败
    pause
    exit /b 1
)
echo [OK] Sharp CLI 可用

python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import flask; print(f'Flask: {flask.__version__}')"

echo [OK] 安装测试通过

REM 完成
echo.
echo ============================================
echo   Sharp GUI 安装完成!
echo ============================================
echo.
echo 使用方法:
echo.
echo   1. 启动 GUI:
echo      run.bat
echo.
echo   2. 命令行推理:
echo      venv\Scripts\activate.bat
echo      sharp predict -i input.jpg -o outputs\
echo.
echo 首次运行会自动下载模型 (~500MB)
echo.

pause

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
echo [1/8] 检查 Python 环境...

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python！
    echo.
    echo ================================================================
    echo          请安装 Python 3.10+ (Install Python)
    echo ================================================================
    echo.
    echo   1. 从官网下载: https://www.python.org/downloads/
    echo.
    echo   2. 安装时务必勾选 "Add Python to PATH"！
    echo      (IMPORTANT: Check "Add Python to PATH")
    echo.
    echo   3. 安装完成后，关闭此窗口并重新运行 install.bat
    echo.
    echo ================================================================
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] 找到 Python: %PYTHON_VERSION%

REM 检查 Python 版本 >= 3.10
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)
if %PYTHON_MAJOR% LSS 3 (
    echo [错误] 需要 Python 3.10+，当前版本 %PYTHON_VERSION%
    pause
    exit /b 1
)
if %PYTHON_MAJOR% EQU 3 if %PYTHON_MINOR% LSS 10 (
    echo [错误] 需要 Python 3.10+，当前版本 %PYTHON_VERSION%
    pause
    exit /b 1
)

REM 检查 venv 模块
python -m venv --help >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] Python venv 模块不可用！
    echo 请重新安装 Python 并确保勾选 pip 和 venv 选项
    pause
    exit /b 1
)

REM 检测 Git
echo.
echo [2/8] 检查 Git...

where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Git！
    echo.
    echo ================================================================
    echo            请安装 Git (Install Git)
    echo ================================================================
    echo.
    echo   从官网下载: https://git-scm.com/download/win
    echo.
    echo   安装时使用默认设置即可
    echo.
    echo ================================================================
    pause
    exit /b 1
)
echo [OK] Git 已安装

REM 检查 CUDA
echo.
echo [3/8] 检查 CUDA 环境...

where nvcc >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=5" %%i in ('nvcc --version ^| findstr release') do set CUDA_VERSION=%%i
    echo [OK] 找到 CUDA: !CUDA_VERSION!
    set HAS_CUDA=true
) else (
    where nvidia-smi >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [警告] 找到 NVIDIA 驱动，但未安装 CUDA toolkit
        echo         视频渲染不可用，推理可正常工作
    ) else (
        echo [警告] 未检测到 NVIDIA GPU，将使用 CPU 模式
        echo         这没问题！3D 生成在 CPU 上也能正常运行
    )
    set HAS_CUDA=false
)

REM 检测 Node.js
echo.
echo [4/8] 检查 Node.js 环境...

where node >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%i in ('node --version') do echo [OK] 找到 Node.js: %%i
    set HAS_NODE=true
) else (
    echo [警告] 未找到 Node.js，跳过前端安装
    echo.
    echo   如需使用 React 版本，请安装 Node.js 18+:
    echo     https://nodejs.org/
    echo.
    echo   注意：预构建包已包含编译好的前端，无需安装 Node.js
    set HAS_NODE=false
)

REM 拉取/更新 ml-sharp
echo.
echo [5/8] 获取 Apple ml-sharp...

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
echo [6/8] 创建虚拟环境...

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
echo [7/8] 安装 Python 依赖...

call "%VENV_DIR%\Scripts\activate.bat"

pip install --upgrade pip

echo 安装 Sharp 核心 (这可能需要几分钟)...
cd /d "%SCRIPT_DIR%%SHARP_DIR%"
pip install -r requirements.txt
cd /d "%SCRIPT_DIR%"

echo 安装 GUI 依赖...
pip install flask

echo [OK] Python 依赖安装完成

REM 安装前端依赖
if "%HAS_NODE%"=="true" (
    echo.
    echo [8/8] 安装前端依赖...
    if exist "%SCRIPT_DIR%frontend" (
        cd /d "%SCRIPT_DIR%frontend"
        npm install
        cd /d "%SCRIPT_DIR%"
        echo [OK] 前端依赖安装完成
    ) else (
        echo [跳过] frontend 目录不存在
    )
) else (
    echo [跳过] 前端安装 (Node.js 不可用)
)

REM 创建目录
if not exist "%SCRIPT_DIR%inputs" mkdir "%SCRIPT_DIR%inputs"
if not exist "%SCRIPT_DIR%outputs" mkdir "%SCRIPT_DIR%outputs"

REM 生成 HTTPS 证书 (可选)
echo.
echo 生成 HTTPS 证书 (可选)...

where openssl >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python "%SCRIPT_DIR%generate_cert.py"
    if %ERRORLEVEL% equ 0 (
        echo [OK] HTTPS 证书已生成
    ) else (
        echo [警告] 证书生成失败，但不影响基本功能
        echo         HTTPS 不可用，陀螺仪功能仅限本机访问
        echo         可稍后手动运行: python generate_cert.py
    )
) else (
    echo [警告] 未找到 OpenSSL，跳过证书生成
    echo.
    echo   OpenSSL 随 Git for Windows 一起安装。
    echo   如已安装 Git，可尝试从 Git Bash 运行此脚本。
    echo.
    echo   或单独安装 OpenSSL: https://slproweb.com/products/Win32OpenSSL.html
    echo.
    echo   HTTPS 不可用，陀螺仪功能仅限本机访问
)

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
echo 使用方法 (Usage):
echo.
echo   1. 启动 GUI (Start GUI):
echo      run.bat
echo.
echo   2. 命令行推理 (CLI Inference):
echo      venv\Scripts\activate.bat
echo      sharp predict -i input.jpg -o outputs\
echo.
echo 首次运行会自动下载模型 (~500MB)
echo.

pause

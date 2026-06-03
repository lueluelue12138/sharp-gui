@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo ========================================
echo   Sharp GUI - Windows 安装脚本
echo   https://github.com/apple/ml-sharp
echo ========================================
echo.

set SHARP_REPO=https://github.com/apple/ml-sharp.git
set SHARP_DIR=ml-sharp
set SCRIPT_DIR=%~dp0

REM Version config - edit here to update dependency versions
set PYTHON_INSTALL_VERSION=3.12.8
set GIT_INSTALL_VERSION=2.47.1

REM PYTHON_CMD will hold the final python command to use
set "PYTHON_CMD=python"

REM Mainland-friendly mirrors. Set SHARP_USE_CHINA_MIRROR=0 to disable, or
REM set SHARP_PIP_INDEX_URL to your preferred PyPI-compatible mirror.
if not defined SHARP_USE_CHINA_MIRROR set SHARP_USE_CHINA_MIRROR=1
if "%SHARP_USE_CHINA_MIRROR%"=="1" (
    if not defined SHARP_PIP_INDEX_URL set "SHARP_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
    set "PIP_INDEX_URL=%SHARP_PIP_INDEX_URL%"
    set "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com pypi.org files.pythonhosted.org"
    set "PIP_DISABLE_PIP_VERSION_CHECK=1"
    if not defined SHARP_MODEL_SOURCE set "SHARP_MODEL_SOURCE=china"
    echo [INFO] Using PyPI mirror: %PIP_INDEX_URL%
)

REM Check if winget is available
set HAS_WINGET=false
where winget >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set HAS_WINGET=true
)

REM Detect AMD ROCm candidates before Python selection. Windows ROCm PyTorch
REM wheels currently require Python 3.12, so RDNA GPUs should not use 3.13 venvs.
set HAS_ROCM_CANDIDATE=false
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$n=(Get-CimInstance Win32_VideoController).Name -join '; '; if ($n -match 'Radeon RX 90|Radeon AI PRO R9700|Radeon PRO AI R9700|Radeon RX 79|Radeon PRO W7') { $n }" 2^>nul`) do (
    set HAS_ROCM_CANDIDATE=true
    echo [OK] Found AMD ROCm candidate GPU: %%i
)

REM ============================================================
REM  [1/6] Check Python
REM ============================================================
echo [1/6] 检查 Python 环境...

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [警告] 未找到 Python！
    echo.

    REM Try py launcher first (Windows Python Launcher)
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        py -3.12 --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=py -3.12"
            echo [OK] 通过 py launcher 找到 Python 3.12
            goto :python_version_ok
        )
        py -3.11 --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=py -3.11"
            echo [OK] 通过 py launcher 找到 Python 3.11
            goto :python_version_ok
        )
        py -3.10 --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=py -3.10"
            echo [OK] 通过 py launcher 找到 Python 3.10
            goto :python_version_ok
        )
    )

    if "!HAS_WINGET!"=="true" (
        echo ================================================================
        echo   可以自动安装 Python %PYTHON_INSTALL_VERSION%
        echo ================================================================
        echo.
        set /p INSTALL_PYTHON="是否自动安装? [Y/n] "
        if /i "!INSTALL_PYTHON!"=="n" (
            goto :ps_python
        )

        echo.
        echo 正在通过 winget 安装 Python...
        winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        if !ERRORLEVEL! equ 0 (
            echo.
            echo [OK] Python 安装完成，正在刷新环境变量...
            call :refresh_path
            where python >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                echo [OK] Python 已就绪！
                goto :python_found
            )
            REM Also try py launcher after install
            where py >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                py -3.12 --version >nul 2>&1
                if !ERRORLEVEL! equ 0 (
                    set "PYTHON_CMD=py -3.12"
                    echo [OK] 通过 py launcher 找到 Python 3.12
                    goto :python_version_ok
                )
            )
        )
        echo [警告] winget 安装未成功，尝试备用方案...
        echo.
    )

    :ps_python
    echo ================================================================
    echo   尝试自动下载并安装 Python %PYTHON_INSTALL_VERSION%
    echo ================================================================
    echo.
    set /p PS_INSTALL_PYTHON="是否自动下载安装 Python? [Y/n] "
    if /i "!PS_INSTALL_PYTHON!"=="n" (
        goto :manual_python
    )

    set "PYTHON_INSTALLER=%TEMP%\python-installer.exe"

    echo.
    echo [1/2] 正在下载 Python 安装包...
    call :download_file "https://registry.npmmirror.com/-/binary/python/%PYTHON_INSTALL_VERSION%/python-%PYTHON_INSTALL_VERSION%-amd64.exe" "!PYTHON_INSTALLER!"
    if !ERRORLEVEL! neq 0 (
        echo [警告] 镜像下载失败，尝试官方源...
        call :download_file "https://www.python.org/ftp/python/%PYTHON_INSTALL_VERSION%/python-%PYTHON_INSTALL_VERSION%-amd64.exe" "!PYTHON_INSTALLER!"
        if !ERRORLEVEL! neq 0 (
            echo [错误] 下载失败
            goto :manual_python
        )
    )

    echo.
    echo [2/2] 正在安装 Python...
    "!PYTHON_INSTALLER!" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_venv=1
    if !ERRORLEVEL! neq 0 (
        echo [警告] 静默安装失败，尝试交互式安装...
        echo 请在弹出的界面中勾选 "Add Python to PATH"
        "!PYTHON_INSTALLER!"
    )

    del "!PYTHON_INSTALLER!" 2>nul

    echo.
    echo 正在刷新环境变量...
    call :refresh_path

    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PATH=!PATH!;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"
    )
    if exist "C:\Python312\python.exe" (
        set "PATH=!PATH!;C:\Python312;C:\Python312\Scripts"
    )
    if exist "%ProgramFiles%\Python312\python.exe" (
        set "PATH=!PATH!;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"
    )

    where python >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        REM Try py launcher as last resort
        where py >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            py -3.12 --version >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                set "PYTHON_CMD=py -3.12"
                echo [OK] 通过 py launcher 找到 Python 3.12
                goto :python_version_ok
            )
        )
        echo [错误] 安装完成但仍然检测不到 Python
        echo         请关闭此窗口，重新打开命令提示符再运行 install.bat
        pause
        exit /b 1
    )
    echo [OK] Python 安装成功！
    goto :python_found
)

REM Python found via 'where python', check version compatibility
:python_found
set "PYTHON_CMD=python"
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] 找到 Python: %PYTHON_VERSION%

for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if "!HAS_ROCM_CANDIDATE!"=="true" if not "!PYTHON_MINOR!"=="12" (
    echo.
    echo [提示] 检测到 AMD ROCm 候选 GPU，Windows ROCm PyTorch 需要 Python 3.12
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        py -3.12 --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=py -3.12"
            for /f "tokens=2" %%i in ('py -3.12 --version 2^>^&1') do echo [OK] ROCm 路径将使用 Python %%i
            goto :python_version_ok
        )
    )
    goto :need_python_312
)

REM Check: Python version must be 3.10 ~ 3.13
set VERSION_OK=false
if %PYTHON_MAJOR% EQU 3 (
    if %PYTHON_MINOR% GEQ 10 if %PYTHON_MINOR% LEQ 13 (
        set VERSION_OK=true
    )
)

if "!VERSION_OK!"=="true" (
    goto :python_version_ok
)

REM Version not compatible, try py launcher for 3.12/3.11/3.10
echo.
echo [警告] 当前 Python %PYTHON_VERSION% 版本不兼容 (需要 3.10~3.13)
echo         正在查找兼容版本...

where py >nul 2>&1
if !ERRORLEVEL! equ 0 (
    py -3.12 --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py -3.12"
        for /f "tokens=2" %%i in ('py -3.12 --version 2^>^&1') do echo [OK] 找到兼容版本: Python %%i
        goto :python_version_ok
    )
    py -3.11 --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py -3.11"
        for /f "tokens=2" %%i in ('py -3.11 --version 2^>^&1') do echo [OK] 找到兼容版本: Python %%i
        goto :python_version_ok
    )
    py -3.10 --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py -3.10"
        for /f "tokens=2" %%i in ('py -3.10 --version 2^>^&1') do echo [OK] 找到兼容版本: Python %%i
        goto :python_version_ok
    )
)

REM No compatible version found, need to install 3.12
:need_python_312
echo [警告] 未找到兼容的 Python 版本
echo.
echo   当前系统的 Python %PYTHON_VERSION% 版本过新，部分依赖不支持
echo   需要额外安装 Python 3.12 (不会影响现有的 Python %PYTHON_VERSION%)
echo.

if "!HAS_WINGET!"=="true" (
    set /p INSTALL_312="是否自动安装 Python 3.12? [Y/n] "
    if /i "!INSTALL_312!"=="n" (
        goto :ps_python_compat
    )

    echo.
    echo 正在通过 winget 安装 Python 3.12...
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if !ERRORLEVEL! equ 0 (
        echo.
        echo [OK] Python 3.12 安装完成，正在刷新环境变量...
        call :refresh_path
        where py >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            py -3.12 --version >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                set "PYTHON_CMD=py -3.12"
                echo [OK] Python 3.12 已就绪！
                goto :python_version_ok
            )
        )
    )
    echo [警告] winget 安装未成功，尝试备用方案...
    echo.
)

:ps_python_compat
echo ================================================================
echo   尝试自动下载并安装 Python 3.12
echo   (不会影响现有的 Python %PYTHON_VERSION%)
echo ================================================================
echo.
set /p PS_INSTALL_312="是否自动下载安装? [Y/n] "
if /i "!PS_INSTALL_312!"=="n" (
    echo.
    echo [错误] 没有兼容的 Python 版本，无法继续安装
    echo         请手动安装 Python 3.12: https://www.python.org/downloads/
    echo         安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

set "PYTHON_INSTALLER=%TEMP%\python-installer.exe"

echo.
echo [1/2] 正在下载 Python 3.12 安装包...
call :download_file "https://registry.npmmirror.com/-/binary/python/%PYTHON_INSTALL_VERSION%/python-%PYTHON_INSTALL_VERSION%-amd64.exe" "!PYTHON_INSTALLER!"
if !ERRORLEVEL! neq 0 (
    echo [警告] 镜像下载失败，尝试官方源...
    call :download_file "https://www.python.org/ftp/python/%PYTHON_INSTALL_VERSION%/python-%PYTHON_INSTALL_VERSION%-amd64.exe" "!PYTHON_INSTALLER!"
    if !ERRORLEVEL! neq 0 (
        echo [错误] 下载失败
        echo         请手动安装 Python 3.12: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo.
echo [2/2] 正在安装 Python 3.12...
"!PYTHON_INSTALLER!" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_venv=1
if !ERRORLEVEL! neq 0 (
    echo [警告] 静默安装失败，尝试交互式安装...
    echo 请在弹出的界面中勾选 "Add Python to PATH"
    "!PYTHON_INSTALLER!"
)

del "!PYTHON_INSTALLER!" 2>nul
call :refresh_path

REM After installing 3.12, try py launcher
where py >nul 2>&1
if !ERRORLEVEL! equ 0 (
    py -3.12 --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py -3.12"
        echo [OK] Python 3.12 安装成功！
        goto :python_version_ok
    )
)

REM Try direct path - prepend to PATH instead of using full path (avoids spaces in path)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;!PATH!"
    set "PYTHON_CMD=python"
    echo [OK] Python 3.12 安装成功！
    goto :python_version_ok
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;!PATH!"
    set "PYTHON_CMD=python"
    echo [OK] Python 3.12 安装成功！
    goto :python_version_ok
)

echo [错误] 安装完成但仍然检测不到 Python 3.12
echo         请关闭此窗口，重新打开命令提示符再运行 install.bat
pause
exit /b 1

:python_version_ok
REM Show which python we are using
for /f "tokens=*" %%i in ('!PYTHON_CMD! --version 2^>^&1') do echo [OK] 将使用: %%i ^(!PYTHON_CMD!^)

REM Check venv module
!PYTHON_CMD! -m venv --help >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] Python venv 模块不可用！
    pause
    exit /b 1
)

goto :check_git

:manual_python
    echo.
    echo ================================================================
    echo   请手动安装 Python 3.12
    echo ================================================================
    echo.
    echo   1. 下载: https://www.python.org/downloads/release/python-3128/
    echo   2. 安装时勾选 "Add Python to PATH"
    echo   3. 安装后重新运行 install.bat
    echo.
    echo ================================================================
    pause
    exit /b 1

REM ============================================================
REM  [2/6] Check Git
REM ============================================================
:check_git
echo.
echo [2/6] 检查 Git...

where git >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [警告] 未找到 Git！
    echo.

    if "!HAS_WINGET!"=="true" (
        echo ================================================================
        echo   可以自动安装 Git
        echo ================================================================
        echo.
        set /p INSTALL_GIT="是否自动安装? [Y/n] "
        if /i "!INSTALL_GIT!"=="n" (
            goto :ps_git
        )

        echo.
        echo 正在通过 winget 安装 Git...
        winget install Git.Git --accept-source-agreements --accept-package-agreements
        if !ERRORLEVEL! equ 0 (
            echo.
            echo [OK] Git 安装完成，正在刷新环境变量...
            call :refresh_path
            if exist "C:\Program Files\Git\cmd" (
                set "PATH=!PATH!;C:\Program Files\Git\cmd"
            )
            where git >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                echo [OK] Git 已就绪！
                goto :git_found
            )
        )
        echo [警告] winget 安装未成功，尝试备用方案...
        echo.
    )

    :ps_git
    echo ================================================================
    echo   尝试自动下载并安装 Git %GIT_INSTALL_VERSION%
    echo ================================================================
    echo.
    set /p PS_INSTALL_GIT="是否自动下载安装 Git? [Y/n] "
    if /i "!PS_INSTALL_GIT!"=="n" (
        goto :manual_git
    )

    set "GIT_INSTALLER=%TEMP%\git-installer.exe"

    echo.
    echo [1/2] 正在下载 Git 安装包...
    call :download_file "https://registry.npmmirror.com/-/binary/git-for-windows/v%GIT_INSTALL_VERSION%.windows.1/Git-%GIT_INSTALL_VERSION%-64-bit.exe" "!GIT_INSTALLER!"
    if !ERRORLEVEL! neq 0 (
        echo [警告] 镜像下载失败，尝试官方源...
        call :download_file "https://github.com/git-for-windows/git/releases/download/v%GIT_INSTALL_VERSION%.windows.1/Git-%GIT_INSTALL_VERSION%-64-bit.exe" "!GIT_INSTALLER!"
        if !ERRORLEVEL! neq 0 (
            echo [错误] 下载失败
            goto :manual_git
        )
    )

    echo.
    echo [2/2] 正在安装 Git...
    "!GIT_INSTALLER!" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
    if !ERRORLEVEL! neq 0 (
        echo [警告] 静默安装失败，尝试交互式安装...
        "!GIT_INSTALLER!"
    )

    del "!GIT_INSTALLER!" 2>nul

    echo.
    echo 正在刷新环境变量...
    call :refresh_path

    if exist "C:\Program Files\Git\cmd" (
        set "PATH=!PATH!;C:\Program Files\Git\cmd"
    )

    where git >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [错误] 安装完成但仍然检测不到 Git
        echo         请关闭此窗口，重新打开命令提示符再运行 install.bat
        pause
        exit /b 1
    )
    echo [OK] Git 安装成功！
    goto :git_found
)

:git_found
echo [OK] Git 已安装

if exist "C:\Program Files\Git\usr\bin" (
    set "PATH=!PATH!;C:\Program Files\Git\usr\bin"
)

goto :check_cuda

:manual_git
    echo.
    echo ================================================================
    echo   请手动安装 Git
    echo ================================================================
    echo.
    echo   下载: https://git-scm.com/download/win
    echo   安装时使用默认设置即可
    echo.
    echo ================================================================
    pause
    exit /b 1

REM ============================================================
REM  [3/6] Check CUDA
REM ============================================================
:check_cuda
echo.
echo [3/6] 检查 CUDA 环境...

where nvcc >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "tokens=5" %%i in ('nvcc --version ^| findstr release') do set "CUDA_VERSION=%%~i"
    REM 去掉尾部逗号 (nvcc 输出格式: release 12.4, V12.4.131)
    set "CUDA_VERSION=!CUDA_VERSION:,=!"
    echo [OK] 找到 CUDA: !CUDA_VERSION!
    set HAS_CUDA=true
) else (
    where nvidia-smi >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo [警告] 找到 NVIDIA 驱动，但未安装 CUDA toolkit
    ) else (
        echo [警告] 未检测到 NVIDIA GPU，将使用 CPU 模式
    )
    set HAS_CUDA=false
)

REM ============================================================
REM  [4/6] Clone or update ml-sharp
REM ============================================================
echo.
echo [4/6] 获取 Apple ml-sharp...

if exist "%SCRIPT_DIR%%SHARP_DIR%" (
    echo ml-sharp 目录已存在
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

REM ============================================================
REM  [5/6] Create virtual environment (using PYTHON_CMD)
REM ============================================================
echo.
echo [5/6] 创建虚拟环境...

set VENV_DIR=%SCRIPT_DIR%venv

if exist "%VENV_DIR%" (
    echo 虚拟环境已存在
    set /p RECREATE="是否删除并重新创建? [y/N] "
    if /i "!RECREATE!"=="y" (
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo [OK] 使用现有虚拟环境
        goto :install_deps
    )
)

echo 使用 !PYTHON_CMD! 创建虚拟环境...
!PYTHON_CMD! -m venv "%VENV_DIR%"
if !ERRORLEVEL! neq 0 (
    echo [错误] 虚拟环境创建失败
    pause
    exit /b 1
)
echo [OK] 虚拟环境创建完成

:install_deps
REM ============================================================
REM  [6/6] Install dependencies
REM ============================================================
echo.
echo [6/6] 安装 Python 依赖...

call "%VENV_DIR%\Scripts\activate.bat"

python -m pip install --upgrade pip

REM Install ml-sharp requirements first. Its requirements.txt pins torch,
REM so the final CUDA/ROCm/CPU PyTorch build is selected and verified afterward.

:install_sharp_core_deps
echo 安装 Sharp 核心 (这可能需要几分钟)...
cd /d "%SCRIPT_DIR%%SHARP_DIR%"
pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    cd /d "%SCRIPT_DIR%"
    echo.
    echo [错误] Sharp 核心依赖安装失败！
    echo         可能原因: 当前 Python 版本与 PyTorch 不兼容
    echo         建议: 关闭此窗口，安装 Python 3.12 后重试
    echo         下载: https://www.python.org/downloads/release/python-3128/
    pause
    exit /b 1
)
cd /d "%SCRIPT_DIR%"

echo.
echo 检查并修复 PyTorch / CUDA / ROCm 运行环境...
python "%SCRIPT_DIR%tools\install_torch.py"
if !ERRORLEVEL! neq 0 (
    echo.
    echo [错误] PyTorch 安装或 CUDA/ROCm kernel 验证失败
    pause
    exit /b 1
)

echo 安装 GUI 依赖...
pip install flask

echo [OK] Python 依赖安装完成

if not exist "%SCRIPT_DIR%inputs" mkdir "%SCRIPT_DIR%inputs"
if not exist "%SCRIPT_DIR%outputs" mkdir "%SCRIPT_DIR%outputs"

REM ============================================================
REM  Download model
REM ============================================================
echo.
echo 下载推理模型...

python "%SCRIPT_DIR%tools\download_model.py"
if !ERRORLEVEL! neq 0 (
    echo.
    echo [警告] 模型下载失败，首次推理时会重试下载
    echo         也可稍后手动下载, 见下方提示
)

REM ============================================================
REM  Generate HTTPS certificate (optional)
REM ============================================================
echo.
echo 生成 HTTPS 证书...

where openssl >nul 2>&1
if !ERRORLEVEL! equ 0 (
    python "%SCRIPT_DIR%tools\generate_cert.py"
    if !ERRORLEVEL! equ 0 (
        echo [OK] HTTPS 证书已生成
    ) else (
        echo [警告] 证书生成失败，不影响基本功能
    )
) else (
    echo [警告] 未找到 OpenSSL，跳过证书生成
    echo   提示: Git for Windows 自带 OpenSSL
)

REM ============================================================
REM  Test installation
REM ============================================================
echo.
echo 测试安装...

sharp --help >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] Sharp CLI 安装失败
    pause
    exit /b 1
)
echo [OK] Sharp CLI 可用

python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import flask; print(f'Flask: {flask.__version__}')"

REM 显示 GPU 状态
python -c "import torch; cuda=torch.cuda.is_available(); hip=getattr(torch.version,'hip',None); mps=hasattr(torch.backends,'mps') and torch.backends.mps.is_available(); device='ROCm (AMD GPU)' if cuda and hip else ('CUDA (NVIDIA GPU)' if cuda else ('MPS (Apple GPU)' if mps else 'CPU')); print(f'推理设备: {device}')"

echo [OK] 安装测试通过

REM ============================================================
REM  Done
REM ============================================================
echo.
echo ============================================
echo   Sharp GUI 安装完成!
echo ============================================
echo.
echo 使用方法:
echo.
echo   1. 启动: run.bat
echo.
echo   2. 命令行: venv\Scripts\activate.bat
echo      sharp predict -i input.jpg -o outputs\
echo.
echo [提示] 如果推理时提示模型缺失或下载失败，可手动下载:
echo.
echo   下载地址 (任选其一):
echo     HuggingFace: https://huggingface.co/apple/Sharp/resolve/main/sharp_2572gikvuh.pt
echo     HF镜像(国内): https://hf-mirror.com/apple/Sharp/resolve/main/sharp_2572gikvuh.pt
echo.
echo   下载后放到:
python -c "import os; p=os.path.join(os.path.expanduser('~'),'.cache','torch','hub','checkpoints','sharp_2572gikvuh.pt'); print('    '+p)"
echo.

pause
exit /b 0

REM ============================================================
REM  Subroutines (must be below exit /b, never reached by flow)
REM ============================================================

:refresh_path
    set "SYS_PATH="
    set "USR_PATH="
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
    if defined SYS_PATH if defined USR_PATH (
        set "PATH=!SYS_PATH!;!USR_PATH!"
    ) else if defined SYS_PATH (
        set "PATH=!SYS_PATH!"
    )
    goto :eof

:download_file
    echo 正在下载: %~1
    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%~1' -OutFile '%~2' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    goto :eof

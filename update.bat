@echo off
chcp 65001 >nul 2>&1
setlocal

REM Sharp GUI verified code updater
REM   update.bat --channel stable --check
REM   update.bat --channel stable
REM   update.bat --channel latest

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE="

REM Portable Python is authoritative inside a complete Windows package.
if exist "%SCRIPT_DIR%python\python.exe" set "PYTHON_EXE=%SCRIPT_DIR%python\python.exe"
if not defined PYTHON_EXE if exist "%SCRIPT_DIR%venv\Scripts\python.exe" set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo [错误] 未找到可用 Python。便携包应包含 python\python.exe；源码安装请先运行 install.bat。
    if not defined SHARP_UPDATE_NO_PAUSE pause
    exit /b 1
)

"%PYTHON_EXE%" "%SCRIPT_DIR%tools\update.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not defined SHARP_UPDATE_NO_PAUSE pause
exit /b %EXIT_CODE%

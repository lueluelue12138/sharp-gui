@echo off
REM ============================================================
REM Sharp GUI - Release Build Script (Windows)
REM Creates pre-built release package
REM
REM Usage: release.bat [version]
REM   Example: release.bat v1.0.0
REM ============================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Get version
set VERSION=%1
if "%VERSION%"=="" (
    for /f "tokens=1-3 delims=/" %%a in ('date /t') do set VERSION=%%c%%a%%b
)

echo.
echo ========================================
echo   Sharp GUI - Release Build
echo   Version: %VERSION%
echo ========================================
echo.

REM 1. Build frontend using build.bat
echo [1/2] Building frontend...
call build.bat
if %ERRORLEVEL% neq 0 (
    echo [Error] Build failed
    pause
    exit /b 1
)

REM 2. Create release package
echo.
echo [2/2] Creating release package...
set RELEASE_DIR=%SCRIPT_DIR%.release-build
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

REM Copy core files
copy app.py "%RELEASE_DIR%\" >nul
copy generate_cert.py "%RELEASE_DIR%\" >nul
copy install.sh "%RELEASE_DIR%\" >nul
copy install.bat "%RELEASE_DIR%\" >nul
copy run.sh "%RELEASE_DIR%\" >nul
copy run.bat "%RELEASE_DIR%\" >nul
copy build.sh "%RELEASE_DIR%\" >nul
copy build.bat "%RELEASE_DIR%\" >nul
copy release.sh "%RELEASE_DIR%\" >nul 2>nul
copy release.bat "%RELEASE_DIR%\" >nul 2>nul
copy README.md "%RELEASE_DIR%\" >nul 2>nul
copy README.en.md "%RELEASE_DIR%\" >nul 2>nul
copy LICENSE "%RELEASE_DIR%\" >nul 2>nul

REM Copy directories
xcopy /E /I /Q templates "%RELEASE_DIR%\templates" >nul
xcopy /E /I /Q static "%RELEASE_DIR%\static" >nul
xcopy /E /I /Q frontend "%RELEASE_DIR%\frontend" >nul

REM Clean unnecessary files
rmdir /s /q "%RELEASE_DIR%\frontend\node_modules" 2>nul
rmdir /s /q "%RELEASE_DIR%\frontend\.vite" 2>nul
rmdir /s /q "%RELEASE_DIR%\frontend\src" 2>nul

REM Create zip
set OUTPUT_FILE=%SCRIPT_DIR%sharp-gui-%VERSION%.zip
if exist "%OUTPUT_FILE%" del "%OUTPUT_FILE%"
powershell -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%OUTPUT_FILE%'"

REM Cleanup
rmdir /s /q "%RELEASE_DIR%"

REM Done
echo.
echo ============================================
echo   Release package created!
echo ============================================
echo.
echo   File: sharp-gui-%VERSION%.zip
echo.
echo Next steps:
echo   1. Create GitHub Release
echo   2. Set tag: %VERSION%
echo   3. Upload sharp-gui-%VERSION%.zip
echo.

pause

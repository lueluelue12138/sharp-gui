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

for %%F in (version.txt update-manifest.json THIRD_PARTY_NOTICES.md LICENSE) do (
    if not exist "%SCRIPT_DIR%%%F" (
        echo [Error] Missing required release file: %%F
        exit /b 1
    )
)

REM Get version
set VERSION=%1
if "%VERSION%"=="" (
    for /f "usebackq delims=" %%v in ("%SCRIPT_DIR%version.txt") do if not defined VERSION set "VERSION=%%v"
)
set "SOURCE_VERSION="
for /f "usebackq delims=" %%v in ("%SCRIPT_DIR%version.txt") do if not defined SOURCE_VERSION set "SOURCE_VERSION=%%v"
if not "%VERSION%"=="%SOURCE_VERSION%" (
    echo [Error] version.txt ^(%SOURCE_VERSION%^) does not match requested release ^(%VERSION%^)
    exit /b 1
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
where git >nul 2>&1
if errorlevel 1 (
    echo [Error] Git is required to verify an exact release snapshot
    exit /b 1
)
set "DIRTY_RELEASE_TREE="
for /f "delims=" %%L in ('git status --porcelain --untracked-files^=all') do set "DIRTY_RELEASE_TREE=1"
if defined DIRTY_RELEASE_TREE (
    echo [Error] Frontend build or source tree differs from the committed revision. Commit the exact release snapshot first.
    git status --short
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
REM tools/ directory contains generate_cert.py, download_model.py, detect_cuda.py, update.py
copy install.sh "%RELEASE_DIR%\" >nul
copy install.bat "%RELEASE_DIR%\" >nul
copy run.sh "%RELEASE_DIR%\" >nul
copy run.bat "%RELEASE_DIR%\" >nul
copy build.sh "%RELEASE_DIR%\" >nul
copy build.bat "%RELEASE_DIR%\" >nul
copy update.sh "%RELEASE_DIR%\" >nul
copy update.bat "%RELEASE_DIR%\" >nul
copy release.sh "%RELEASE_DIR%\" >nul 2>nul
copy release.bat "%RELEASE_DIR%\" >nul 2>nul
copy README.md "%RELEASE_DIR%\" >nul 2>nul
copy README.en.md "%RELEASE_DIR%\" >nul 2>nul
copy LICENSE "%RELEASE_DIR%\" >nul 2>nul
copy THIRD_PARTY_NOTICES.md "%RELEASE_DIR%\" >nul 2>nul
copy update-manifest.json "%RELEASE_DIR%\" >nul
copy version.txt "%RELEASE_DIR%\" >nul

REM Copy directories
xcopy /E /I /Q backend "%RELEASE_DIR%\backend" >nul
xcopy /E /I /Q tools "%RELEASE_DIR%\tools" >nul
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

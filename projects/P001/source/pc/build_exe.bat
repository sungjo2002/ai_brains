@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Build 스마트인력관리365

if exist build_log.txt del /f /q build_log.txt >nul 2>nul

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 build_exe_helper.py
) else (
    python build_exe_helper.py
)

set BUILD_RESULT=%ERRORLEVEL%

if exist build_log.txt (
    echo.
    echo ===== build_log.txt =====
    type build_log.txt
    echo ===== end log =====
)

if not "%BUILD_RESULT%"=="0" (
    echo.
    echo [ERROR] Build failed. Check build_log.txt.
    pause
    exit /b %BUILD_RESULT%
)

echo.
echo [DONE] Build completed.
echo [DONE] Final folder: dist\스마트인력관리365
echo [DONE] Final exe: dist\스마트인력관리365\스마트인력관리365.exe
pause
exit /b 0

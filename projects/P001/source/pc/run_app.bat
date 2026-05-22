@echo off
setlocal
cd /d "%~dp0"
title Workforce PC Main

echo [INFO] Workforce PC Main
echo.

set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if defined PY_CMD goto py_found

where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto py_found

where python3 >nul 2>&1
if not errorlevel 1 set "PY_CMD=python3"
if defined PY_CMD goto py_found

echo [ERROR] Python was not found.
echo Install Python 3.11 or newer, then run this file again.
goto error_pause

:py_found
echo [INFO] Python command: %PY_CMD%
call %PY_CMD% -c "import PySide6" >nul 2>&1
if errorlevel 1 goto install_packages
goto run_app

:install_packages
echo [INFO] PySide6 not found. Installing required packages...
call %PY_CMD% -m pip install --upgrade pip
if errorlevel 1 goto install_error
call %PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto install_error
goto run_app

:run_app
echo [INFO] Starting app...
call %PY_CMD% main.py
if errorlevel 1 goto run_error
goto end

:install_error
echo.
echo [ERROR] Package installation failed.
echo Check internet connection, Python, pip, and permissions.
goto error_pause

:run_error
echo.
echo [ERROR] App execution failed.
echo Read the message above and send a screenshot if needed.
goto error_pause

:error_pause
echo.
pause

:end
endlocal

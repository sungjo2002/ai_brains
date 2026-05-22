@echo off
setlocal
cd /d "%~dp0"

set PYEXE=
where py >nul 2>nul
if not errorlevel 1 set PYEXE=py
if defined PYEXE goto runrestore
where python >nul 2>nul
if not errorlevel 1 set PYEXE=python
if defined PYEXE goto runrestore

echo Python 실행기를 찾을 수 없습니다.
pause
exit /b 1

:runrestore
%PYEXE% -m src.backup_cli restore-latest
if errorlevel 1 (
  echo 최신 백업 복원 중 문제가 발생했습니다.
  pause
  exit /b 1
)
echo 최신 백업을 data 폴더로 복원했습니다.
pause

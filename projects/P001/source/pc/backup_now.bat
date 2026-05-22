@echo off
setlocal
cd /d "%~dp0"

set PYEXE=
where py >nul 2>nul
if not errorlevel 1 set PYEXE=py
if defined PYEXE goto runbackup
where python >nul 2>nul
if not errorlevel 1 set PYEXE=python
if defined PYEXE goto runbackup

echo Python 실행기를 찾을 수 없습니다.
pause
exit /b 1

:runbackup
%PYEXE% -m src.backup_cli backup
if errorlevel 1 (
  echo 백업 생성 중 문제가 발생했습니다.
  pause
  exit /b 1
)
echo 백업이 완료되었습니다.
pause

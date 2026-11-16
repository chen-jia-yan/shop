@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 测试分析助手
set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo 没有找到 Python。请安装 Python 3.10 或更新版本，安装时勾选 Add python.exe to PATH。
  pause
  exit /b 1
)
%PY% scripts\ta.py open
echo.
pause

@echo off
cd /d "%~dp0"
rem 用 pythonw 在后台启动（没有命令行窗口）；这个窗口马上关闭
where pythonw >nul 2>nul && (start "" pythonw scripts\ta.py open & exit /b 0)
where pyw >nul 2>nul && (start "" pyw -3 scripts\ta.py open & exit /b 0)
chcp 65001 >nul
echo 没有找到 Python。请安装 Python 3.10 或更新版本，安装时勾选 Add python.exe to PATH。
pause

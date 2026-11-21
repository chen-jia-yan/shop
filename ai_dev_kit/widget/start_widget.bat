@echo off
rem Start the ai-dev-kit desktop widget without a console window.
set "WIDGET=%~dp0dev_widget.pyw"
if exist "%ProgramFiles%\Python312\pythonw.exe" (
    start "" "%ProgramFiles%\Python312\pythonw.exe" "%WIDGET%"
    goto :eof
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%WIDGET%"
    goto :eof
)
echo pythonw.exe not found. Edit this file and put the full path of pythonw.exe here.
pause

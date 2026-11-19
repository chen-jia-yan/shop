@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 文档对比助手：把文件夹拖进这个窗口，再按回车
echo.
set /p BASE=baseline 文件夹：
set /p NEW=新文件文件夹：
set /p RES=他已经跑好的结果文件夹（没有就直接回车，会重新对比）：
set BASE=%BASE:"=%
set NEW=%NEW:"=%
if defined RES set RES=%RES:"=%
echo.
if defined RES (
  python scripts\dca.py all --baseline-dir "%BASE%" --new-dir "%NEW%" --results-dir "%RES%"
) else (
  python scripts\dca.py all --baseline-dir "%BASE%" --new-dir "%NEW%"
)
if errorlevel 1 (
  echo.
  echo 出错了，请看上面的提示
  pause
  exit /b 1
)
for /f "delims=" %%d in ('dir /b /ad /o-n runs') do (
  start "" "runs\%%d\index.html"
  goto done
)
:done
pause

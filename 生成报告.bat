@echo off
rem Encoding: GBK (cp936) for Chinese Windows console
chcp 936 >nul
cd /d "%~dp0"
set "HAS_TEMPLATE_CONFIG="
for /f "delims=" %%F in ('dir /b "templates\*.json" 2^>nul ^| findstr /i /v /e "example.json"') do set "HAS_TEMPLATE_CONFIG=1"
if not defined HAS_TEMPLATE_CONFIG (
  echo 缺少模板配置：请重新下载仓库中的 templates 文件夹。
  pause
  exit /b 1
)
if not exist "profiles\profile.json" (
  echo 缺少 profiles\profile.json：请重新下载仓库中的 profiles 文件夹。
  pause
  exit /b 1
)
set /p GUIDE=请把指导书文件拖到本窗口，然后回车：
set GUIDE=%GUIDE:"=%
set /p EXP=实验编号（如 3 或 三，可留空）：
python -m lab_report --guide "%GUIDE%" --experiment "%EXP%"
if errorlevel 1 pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "templates\模电.json" (
  echo 首次使用：请先把 templates\模电.example.json 复制为 templates\模电.json，
  echo 并把 template_docx 改成你的 Word 模板路径。
  pause
  exit /b 1
)
if not exist "profiles\profile.json" (
  echo 首次使用：请先把 profiles\example.json 复制为 profiles\profile.json，
  echo 并填写姓名、学号、院系、专业。
  pause
  exit /b 1
)
set /p GUIDE=请把指导书文件拖到本窗口，然后回车：
set GUIDE=%GUIDE:"=%
set /p EXP=实验编号（如 3 或 三，可留空）：
python -m lab_report --guide "%GUIDE%" --experiment "%EXP%"
if errorlevel 1 pause

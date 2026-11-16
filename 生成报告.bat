@echo off
cd /d "%~dp0"
set "HAS_TEMPLATE_CONFIG="
for /f "delims=" %%F in ('dir /b "templates\*.json" 2^>nul ^| findstr /i /v /e "example.json"') do set "HAS_TEMPLATE_CONFIG=1"
if not defined HAS_TEMPLATE_CONFIG (
  echo First run: the template config is missing.
  echo Copy the example JSON in templates\ and set template_docx to your Word template.
  echo See README.md for the exact steps.
  pause
  exit /b 1
)
if not exist "profiles\profile.json" (
  echo First run: profiles\profile.json is missing.
  echo Copy profiles\example.json to profiles\profile.json and fill in your details.
  pause
  exit /b 1
)
set /p GUIDE=Drag the guide file into this window, then press Enter:
set GUIDE=%GUIDE:"=%
set /p EXP=Experiment number (e.g. 3, empty for the first experiment):
python -m lab_report --guide "%GUIDE%" --experiment "%EXP%"
if errorlevel 1 pause

@echo off
cd /d "%~dp0"
set "HAS_TEMPLATE_CONFIG="
for /f "delims=" %%F in ('dir /b "templates\*.json" 2^>nul ^| findstr /i /v /e "example.json"') do set "HAS_TEMPLATE_CONFIG=1"
if not defined HAS_TEMPLATE_CONFIG (
  echo The template config is missing or incomplete.
  echo Re-download the templates folder from the repository.
  pause
  exit /b 1
)
if not exist "profiles\profile.json" (
  echo profiles\profile.json is missing.
  echo Re-download the profiles folder from the repository.
  pause
  exit /b 1
)
set /p GUIDE=Drag the guide file into this window, then press Enter:
set GUIDE=%GUIDE:"=%
set /p EXP=Experiment number (e.g. 3, empty for the first experiment):
python -m lab_report --guide "%GUIDE%" --experiment "%EXP%"
if errorlevel 1 pause

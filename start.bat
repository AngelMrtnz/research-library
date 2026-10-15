@echo off
rem Research Library: double-click to start. It runs in the background; Quit in the app stops it.
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is needed. Install it with:  winget install Python.Python.3.12
  echo then double-click start.bat again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo First run: setting things up, this takes a minute...
  py -3 -m venv .venv
)
rem Install packages only when requirements.txt changed since the last run.
fc /b requirements.txt .venv\installed.txt >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
  copy /y requirements.txt .venv\installed.txt >nul
)
if not exist config.env copy config.env.example config.env >nul
.venv\Scripts\python -m app.check || (pause & exit /b 1)
start "" .venv\Scripts\pythonw.exe -m app.serve

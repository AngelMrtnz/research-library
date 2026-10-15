@echo off
rem Research Library launcher for Windows. Double-click to start.
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is needed. Install it with:  winget install Python.Python.3.12
  echo then double-click start.bat again.
  pause
  exit /b 1
)
if not exist .venv (
  echo First run: setting things up, this takes a minute...
  py -3 -m venv .venv
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
if not exist .env copy .env.local.example .env >nul
.venv\Scripts\python -m app.check || (pause & exit /b 1)
start "" http://localhost:8000/staging
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause

@echo off
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo [notchilppeon] Creating virtual env and installing packages. First run only, 1-2 min.
  python -m venv .venv || goto nopython
  .venv\Scripts\python -m pip install --upgrade pip > nul
  .venv\Scripts\python -m pip install -r requirements.txt || goto fail
)
if not exist .env copy .env.example .env > nul

start "" cmd /c "timeout /t 4 > nul & start http://127.0.0.1:8000"
.venv\Scripts\python run.py
goto :eof

:nopython
echo Python not found. Run this again from Anaconda Prompt, or install Python 3.10+.
pause
goto :eof

:fail
echo Package install failed. Check your internet connection.
pause

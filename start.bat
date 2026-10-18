@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
if not exist .venv\Scripts\python.exe (
  echo Creating local Python environment...
  %PY% -m venv .venv || goto :error
)
echo Installing or updating Indie Matchmaker dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
if not exist .env copy .env.example .env >nul
echo Starting server. Open http://127.0.0.1:8000/docs for the API.
.venv\Scripts\python.exe -m matchmaker
goto :eof
:error
echo Setup failed. Install Python 3.10 or newer and try again.
pause

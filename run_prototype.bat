@echo off
setlocal
echo =======================================================
echo          Starting EVA Prototype (Unified Server)
echo    Frontend + Backend + Guard (Sec-1 + Sec-2)
echo =======================================================
echo.

cd /d "%~dp0"

REM 1. Build frontend bundle
echo [1/3] Building frontend bundle...
cd agent\frontend
call npm run build
cd ..\..

REM 2. Run migrations to ensure database schema is up-to-date
echo [2/3] Checking database migrations...
set PYTHONPATH=%cd%;%cd%\guard;%cd%\contracts;%cd%\agent\backend
cd agent\backend
call ..\..\.venv\Scripts\alembic.exe upgrade head
cd ..\..

REM 3. Launch single combined server
echo [3/3] Starting connected EVA application...
echo.
echo =======================================================
echo  App URL:    http://localhost:8000
echo  API Docs:   http://localhost:8000/docs
echo  Health:     http://localhost:8000/api/health
echo.
echo  Default Login:
echo    Email:    admin@eva.local (or user@eva.local)
echo    Password: AdminPassword123! (or UserPassword123!)
echo =======================================================
echo.

call .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir agent/backend --host 127.0.0.1 --port 8000

endlocal

@echo off
REM SimpleChat Backend Startup Script (Production Mode)
REM This script starts the FastAPI backend in production mode without hot reload

chcp 65001 > nul

echo Starting SimpleChat Backend (Production Mode)...
echo.

REM Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo [WARNING] Virtual environment not detected!
    echo Please activate the virtual environment first:
    echo   cd backend
    echo   .\.venv\Scripts\activate
    echo.
    pause
    exit /b 1
)

echo [INFO] Virtual environment: %VIRTUAL_ENV%
echo [INFO] Mode: Production (No hot reload)
echo.

REM Start uvicorn without reload for production
uvicorn backend.main:app --host 0.0.0.0 --port 8000

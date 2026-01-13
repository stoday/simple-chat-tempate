@echo off
REM SimpleChat Backend Startup Script (Development Mode)
REM This script starts the FastAPI backend in development mode with hot reload

chcp 65001 > nul

echo Starting SimpleChat Backend (Development Mode)...
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
echo.

REM Start uvicorn with reload, excluding database and upload directories
echo [INFO] Starting Uvicorn with hot reload...
echo [INFO] Excluding: *.db, chat_uploads/*, rag_files/*
echo.

uvicorn backend.main:app --reload --reload-exclude "*.db" --reload-exclude "chat_uploads/*" --reload-exclude "rag_files/*" --reload-exclude "Knowledge/*" --host 0.0.0.0 --port 8000

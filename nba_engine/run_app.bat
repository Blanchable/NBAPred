@echo off
REM NBA Prediction Engine Launcher for Windows
REM Double-click this file to run the application

cd /d "%~dp0"

REM Check if virtual environment exists
if exist ".venv\Scripts\python.exe" (
    echo Starting NBA Prediction Engine...
    .venv\Scripts\python.exe app.py
) else (
    echo Virtual environment not found. Setting up...
    python -m venv .venv
    .venv\Scripts\pip.exe install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
    echo.
    echo Setup complete! Starting application...
    .venv\Scripts\python.exe app.py
)

pause

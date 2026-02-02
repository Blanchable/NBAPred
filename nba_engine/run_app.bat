@echo off
REM NBA Prediction Engine Launcher for Windows
REM Double-click this file to run the application

setlocal EnableDelayedExpansion

REM Change to the script's directory (handles paths with spaces)
cd /d "%~dp0"

echo ========================================
echo   NBA Prediction Engine Launcher
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment found.
    echo.
) else (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo.
)

REM Check if dependencies are installed by testing pandas import
".venv\Scripts\python.exe" -c "import pandas" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies... This may take a minute.
    echo.
    ".venv\Scripts\pip.exe" install --upgrade pip
    ".venv\Scripts\pip.exe" install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        echo Please check your internet connection and try again.
        pause
        exit /b 1
    )
    echo.
    echo Dependencies installed successfully!
    echo.
)

echo Starting NBA Prediction Engine...
echo.
".venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)

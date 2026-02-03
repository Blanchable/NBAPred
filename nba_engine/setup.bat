@echo off
REM NBA Prediction Engine - First Time Setup
REM Run this once to install all dependencies

setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ========================================
echo   NBA Prediction Engine Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.10+ from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, check the box that says
    echo "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Create virtual environment
echo Step 1/3: Creating virtual environment...
if exist ".venv" (
    echo Virtual environment already exists, recreating...
    rmdir /s /q .venv
)
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo Done.
echo.

REM Upgrade pip
echo Step 2/3: Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
echo Done.
echo.

REM Install dependencies
echo Step 3/3: Installing dependencies...
echo This may take 1-2 minutes...
echo.
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Please check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo You can now run the app by double-clicking:
echo   run_app.bat
echo.
echo Or to build a standalone .exe file, run:
echo   build_exe.bat
echo.
pause

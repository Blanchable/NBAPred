@echo off
REM NBA Prediction Engine - Build Standalone Executable
REM Creates a .exe file that can run without Python installed

setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ========================================
echo   Building NBA Predictor Executable
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

REM Check if pyinstaller is installed
".venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    ".venv\Scripts\pip.exe" install pyinstaller
)

echo Building executable... This may take a few minutes.
echo.

".venv\Scripts\pyinstaller.exe" --onefile --windowed --name "NBA_Predictor" --add-data "ingest;ingest" --add-data "model;model" app.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo Your executable is at:
echo   dist\NBA_Predictor.exe
echo.
echo You can copy this file anywhere and run it!
echo.
pause

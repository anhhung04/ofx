@echo off
REM Build OFX Windows executable
REM Usage: scripts\build-windows.bat
REM
REM Requirements:
REM   - Python 3.12+
REM   - pip install pyinstaller

setlocal enabledelayedexpansion

echo ==========================================
echo Building OFX Windows Executable
echo ==========================================

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Install PyInstaller if needed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Install OFX in development mode
echo Installing OFX dependencies...
pip install -e .

REM Run build script
echo Building executable...
python packaging\windows\build-exe.py

echo.
echo ==========================================
echo Build Complete!
echo ==========================================
echo.
echo Executable location:
dir /b dist\*.exe 2>nul || echo   (check dist/ directory)
echo.

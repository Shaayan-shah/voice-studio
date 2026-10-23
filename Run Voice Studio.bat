@echo off
setlocal
title Voice Studio
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Voice Studio for the first time...
    py -3 -m venv .venv
    if errorlevel 1 goto setup_error
)

".venv\Scripts\python.exe" -c "import edge_tts, pypdf, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
    echo Installing or repairing Voice Studio packages...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto setup_error
)

".venv\Scripts\python.exe" voice_studio.py
if errorlevel 1 (
    echo.
    echo Voice Studio stopped because of an error. See the message above.
    pause
)
exit /b

:setup_error
echo.
echo Setup could not complete. Check Python 3.10 or newer is installed and that your internet connection is available for first-time package installation.
pause
exit /b 1

@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ============================================
echo   AI Hedge Fund MOEX - Setup
echo ============================================
echo.

:: Use py launcher to find Python 3.11+
set PYCMD=py -3.11

%PYCMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.11 not found via py launcher.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('%PYCMD% --version 2^>^&1') do echo   Using Python %%v
echo.

:: Remove old venv if created with wrong Python version
if exist ".venv\Scripts\python.exe" (
    for /f "tokens=2 delims= " %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set VENVVER=%%v
    for /f "tokens=1,2 delims=." %%a in ("!VENVVER!") do (
        set VMAJOR=%%a
        set VMINOR=%%b
    )
    if !VMAJOR! lss 3 (
        echo [!] Existing venv uses Python !VENVVER! - removing...
        rmdir /s /q .venv
    ) else if !VMAJOR! equ 3 if !VMINOR! lss 11 (
        echo [!] Existing venv uses Python !VENVVER! - removing...
        rmdir /s /q .venv
    )
)

:: Create venv
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Creating virtual environment...
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo [1/3] Virtual environment already exists - skipping.
)

:: Install dependencies
echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.

:: Check .env
echo [3/3] Checking .env file...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo       Created .env from .env.example - fill in your API keys!
    ) else (
        echo       [WARNING] .env not found. Create it manually with your API keys.
    )
) else (
    echo       .env exists - OK.
)

echo.
echo ============================================
echo   Setup complete!
echo   Run run_gui.bat or run_cli.bat to start.
echo ============================================
pause
endlocal

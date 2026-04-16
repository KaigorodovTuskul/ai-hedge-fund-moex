@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ============================================
echo   AI Hedge Fund MOEX - Setup
echo ============================================
echo.

set PYTHON_VERSION=3.11.9
set PYTHON_DIR=python_portable
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip
set GETPIP_URL=https://bootstrap.pypa.io/get-pip.py

:: ---- Step 1: Download portable Python ----
if exist "%PYTHON_DIR%\python.exe" (
    for /f "tokens=2 delims= " %%v in ('"%PYTHON_DIR%\python.exe" --version 2^>^&1') do echo   Using Python %%v
    echo [1/3] Python portable already exists - skipping download.
    goto :install_deps
)

echo [1/3] Downloading Python %PYTHON_VERSION% portable...
powershell -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile 'python_portable.zip'"
if errorlevel 1 (
    echo [ERROR] Failed to download Python.
    if exist python_portable.zip del python_portable.zip
    pause
    exit /b 1
)

echo       Extracting...
powershell -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'python_portable.zip' -DestinationPath '%PYTHON_DIR%' -Force"
del python_portable.zip

echo       Configuring...
:: Enable site-packages and add Lib paths in embeddable Python
powershell -ExecutionPolicy Bypass -Command "$f = '%PYTHON_DIR%\python311._pth'; $c = (Get-Content $f) -replace '#import site', 'import site'; $c += 'Lib'; $c += 'Lib\site-packages'; Set-Content $f $c"

echo       Installing pip...
powershell -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%GETPIP_URL%' -OutFile 'get-pip.py'"
"%PYTHON_DIR%\python.exe" get-pip.py --no-warn-script-location
del get-pip.py
echo       Done.

:: ---- Step 2: Install dependencies ----
:install_deps
echo [2/3] Installing dependencies...
"%PYTHON_DIR%\python.exe" -m pip install --upgrade pip --quiet
"%PYTHON_DIR%\python.exe" -m pip install -r requirements.txt --quiet --no-warn-script-location
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.

:: ---- Step 3: Check .env ----
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

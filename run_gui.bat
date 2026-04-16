@echo off
chcp 65001 >nul
echo Starting AI Hedge Fund MOEX - Streamlit GUI...
echo.

if not exist "python_portable\python.exe" (
    echo [ERROR] Python portable not found. Run setup.bat first.
    pause
    exit /b 1
)

python_portable\python.exe -m streamlit run app_streamlit.py
pause

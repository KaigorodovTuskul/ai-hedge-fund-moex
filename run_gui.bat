@echo off
chcp 65001 >nul
echo Starting AI Hedge Fund MOEX - Streamlit GUI...
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
streamlit run app_streamlit.py
pause

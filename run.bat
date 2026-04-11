@echo off
REM GC Log Analyzer - Windows Run Script

cd /d "%~dp0"

REM Default port must match config.py (GC_ANALYZER_PORT)
if not defined GC_ANALYZER_PORT set GC_ANALYZER_PORT=5006

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
pip install -q -r requirements.txt

REM Open the app in the default browser after the server has time to bind
start "gc-analyzer-browser" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:%GC_ANALYZER_PORT%/ && exit"

REM Run the application
python app.py


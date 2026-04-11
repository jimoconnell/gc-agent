#!/bin/bash
# GC Log Analyzer - Run Script

cd "$(dirname "$0")"

# Default port must match config.py (GC_ANALYZER_PORT)
PORT="${GC_ANALYZER_PORT:-5006}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -q -r requirements.txt

# Open the app in the default browser after the server has time to bind
(
  sleep 2
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:${PORT}/"
  elif command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:${PORT}/"
  else
    python -c "import webbrowser; webbrowser.open(\"http://127.0.0.1:${PORT}/\")"
  fi
) &

# Run the application
python app.py


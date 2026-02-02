#!/bin/bash
# NBA Prediction Engine Launcher for Linux/macOS
# Make executable with: chmod +x run_app.sh
# Then double-click or run: ./run_app.sh

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ -f ".venv/bin/python" ]; then
    echo "Starting NBA Prediction Engine..."
    .venv/bin/python app.py
else
    echo "Virtual environment not found. Setting up..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    echo ""
    echo "Setup complete! Starting application..."
    .venv/bin/python app.py
fi

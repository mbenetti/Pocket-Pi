#!/bin/bash

# 1. Update the session explorer with the latest session logs
echo "Scanning session logs and updating dashboard..."
python3 update_explorer.py

if [ $? -ne 0 ]; then
    echo "Error: Failed to update session_explorer.html!"
    exit 1
fi

# 2. Open the session explorer in the default browser
echo "Opening Session Explorer in your default browser..."
if [ "$(uname)" == "Darwin" ]; then
    # macOS
    open session_explorer.html
elif [ "$(expr substr $(uname -s) 1 5)" == "Linux" ]; then
    # Linux
    xdg-open session_explorer.html
elif [ "$(expr substr $(uname -s) 1 10)" == "MINGW32_NT" ] || [ "$(expr substr $(uname -s) 1 10)" == "MINGW64_NT" ]; then
    # Windows (Git Bash)
    start session_explorer.html
else
    # Fallback
    echo "Could not detect OS to open browser automatically."
    echo "Please open session_explorer.html manually in your browser."
fi

#!/usr/bin/env bash
# Auto-start the Flask app whenever the Codespace boots.
# postStartCommand must return quickly, so we launch the server fully
# detached and let it run in the background.

set -e
cd "$(dirname "$0")/.."

# Stop any prior instance so a restart picks up code changes
pkill -f "python app.py" 2>/dev/null || true

# Ensure dependencies are present (cheap if already installed)
pip install -q -r requirements.txt

# Launch detached; logs go to /tmp/app.log
nohup python app.py > /tmp/app.log 2>&1 &
disown

echo "App launched on port 5000 — see /tmp/app.log for output"

#!/usr/bin/env bash
# ----------------------------------------------------------------
# Broker Agentic Challenge -- Codespace startup script
# Runs automatically via devcontainer.json postStartCommand
# ----------------------------------------------------------------
set -uo pipefail

echo ""
echo "==================================================="
echo "  Broker Agentic Challenge -- Codespace Start"
echo "==================================================="
echo ""

# -- 1. Kill any stale instance so restarts pick up code changes -
echo "-> Clearing port 5000..."
pkill -f "python app.py" 2>/dev/null || true
fuser -k 5000/tcp    2>/dev/null || true
sleep 1

# -- 2. Set port 5000 to public visibility via gh CLI -----------
#    Belt-and-suspenders alongside devcontainer.json "visibility".
#    The universal:2 image ships with gh pre-installed.
if [[ -n "${CODESPACE_NAME:-}" ]]; then
  echo "-> Setting port 5000 to public visibility..."
  gh codespace ports visibility 5000:public \
    --codespace "$CODESPACE_NAME" 2>/dev/null \
    && echo "   [OK] Port 5000 is now PUBLIC" \
    || echo "   [info] Visibility already managed by devcontainer.json"
else
  echo "   [info] Not in a Codespace -- skipping port visibility step"
fi

# -- 3. Start Flask app in the background -----------------------
echo "-> Launching python app.py..."
LOG=/tmp/ams-app.log
nohup python app.py > "$LOG" 2>&1 &
APP_PID=$!
disown

# Brief wait to confirm it did not immediately crash
sleep 2
if kill -0 "$APP_PID" 2>/dev/null; then
  echo "   [OK] Flask app running (PID $APP_PID) on :5000"
  echo "   Logs: tail -f $LOG"
else
  echo "   [ERR] Flask app failed to start -- check $LOG"
  tail -20 "$LOG" || true
  exit 1
fi

echo ""
echo "   Open the AMS UI --> port 5000 is forwarded & public"
echo ""

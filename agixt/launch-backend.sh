#!/bin/sh
echo "Starting AGiXT..."
sleep 15
python3 DB.py
sleep 5
if [ -n "$NGROK_TOKEN" ]; then
    echo "Starting ngrok..."
    python3 Tunnel.py
fi

echo "Starting task monitor..."
python3 TaskMonitor.py &
MONITOR_PID=$!

workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers &
API_PID=$!

# Handle shutdown gracefully
shutdown() {
    echo "Shutting down..."
    kill $MONITOR_PID
    kill $API_PID
    exit 0
}

trap shutdown SIGTERM SIGINT

# Keep the script running
wait $API_PID
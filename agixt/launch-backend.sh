#!/bin/sh
echo "Starting AGiXT..."
if [ "$DB_CONNECTED" = "true" ]; then
    sleep 5
    echo "Connecting to DB..."
    python3 DBConnection.py
fi
if [ -n "$NGROK_TOKEN" ]; then
    echo "Starting ngrok..."
    python3 Tunnel.py
fi
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers
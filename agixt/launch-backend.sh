#!/bin/sh
echo "Starting AGiXT..."
sleep 15
python3 DB.py
sleep 5
if [ -n "$NGROK_TOKEN" ]; then
    echo "Starting ngrok..."
    python3 Tunnel.py
fi
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers
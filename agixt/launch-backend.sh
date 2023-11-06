#!/bin/sh
if [ "$DB_CONNECTED" = "true" ]; then
  python3 DBConnection.py
  sleep 5
fi
echo "Starting AGiXT..."
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers
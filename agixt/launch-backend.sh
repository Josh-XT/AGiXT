#!/bin/sh
set -e
echo "Starting AGiXT..."
sleep 5
python3 DBConnection.py
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers
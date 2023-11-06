#!/bin/sh
set -e
python3 DBConnection.py
echo "Starting AGiXT..."
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers
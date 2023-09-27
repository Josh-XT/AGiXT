#!/bin/sh

set -e
set -a
if [ -f .env ]; then
  . .env
fi
if [ -f ../.env ]; then
  . ../.env
fi
set +a
# Check if $DB_CONNECTED is defined
if [ -z "$DB_CONNECTED" ]; then
  # Set defaults
  echo "No .env file found, setting defaults..."
  AGIXT_URI="http://localhost:7437"
  DB_CONNECTED="false"
  AGIXT_AUTO_UPDATE="true"
  AGIXT_API_KEY=""
  UVICORN_WORKERS="10"
  DATABASE_TYPE="sqlite"
  DATABASE_HOST="db"
  DATABASE_PORT="5432"
  DATABASE_NAME="agixt"
  DATABASE_USER="postgres"
  DATABASE_PASSWORD="postgres"
fi

workers="${UVICORN_WORKERS:-10}"

if [ "$DB_CONNECTED" = "true" ]; then
  python3 DBConnection.py
fi

echo "Starting AGiXT... Please wait until you see 'Applicaton startup complete' before opening Streamlit..."
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers

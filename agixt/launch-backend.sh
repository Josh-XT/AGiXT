#!/bin/sh

set -e

# Check if .env file exists and load it
if [ -f .env ]; then
  echo "Loading environment variables from .env file..."
  set -a # automatically export all variables
  . .env
  set +a # stop automatically exporting all variables
fi

# Check if .env file exists in the parent directory and load it
if [ -f ../.env ]; then
  echo "Loading environment variables from .env file in parent directory..."
  set -a # automatically export all variables
  . ../.env
  set +a # stop automatically exporting all variables
fi

# Check if $DB_CONNECTED is defined
if [ -z "$DB_CONNECTED" ]; then
  # Set defaults
  echo "No .env file found, setting defaults..."
  AGIXT_URI="http://localhost:7437"
  DB_CONNECTED="false"
  AGIXT_AUTO_UPDATE="true"
  AGIXT_HUB="AGiXT/light-hub"
  AGIXT_API_KEY=""
  UVICORN_WORKERS="4"
  GITHUB_USER=""
  GITHUB_TOKEN=""
  POSTGRES_SERVER="db"
  POSTGRES_PORT="5432"
  POSTGRES_DB="postgres"
  POSTGRES_USER="postgres"
  POSTGRES_PASSWORD="postgres"
fi


workers="${UVICORN_WORKERS:-4}"

if [ "$DB_CONNECTED" = "true" ]; then
  host="${POSTGRES_SERVER:-db}"
  port="${POSTGRES_PORT:-5432}"
  db="${POSTGRES_DB:-postgres}"  
  echo "Waiting for postgres server to start... $host:$port"
  sleep 15

  until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -p "$port" -U "$POSTGRES_USER" -c '\q'; do
    >&2 echo "Waiting for database... $host:$port"
    sleep 1
  done
  sleep 5
  # Check if the database exists, and create it if it doesn't
  PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -p "$port" -U "$POSTGRES_USER" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 || PGPASSWORD=$POSTGRES_PASSWORD createdb -h "$host" -p "$port" -U "$POSTGRES_USER" "$db"
  sleep 5
  python3 DBConnection.py
  sleep 10
fi
# Install AGiXT Hub
python3 Hub.py
echo "Starting AGiXT... Please wait until you see 'Applicaton startup complete' before opening Streamlit..."
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers

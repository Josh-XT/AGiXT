#!/bin/sh

set -e

# Check if .env file exists
if [ -f ".env" ]; then
  echo "Sourcing .env file..."
  source .env
elif [ -f "../.env" ]; then
  echo "Sourcing ../.env file..."
  source ../.env
else
  # Check if .env.example file exists in the current directory
  if [ -f ".env.example" ]; then
    echo "No .env file found, sourcing .env.example from current directory..."
    source .env.example
  else
    # Check if .env.example file exists in the parent directory
    if [ -f "../.env.example" ]; then
      echo "No .env or ../.env file found, sourcing .env.example from parent directory..."
      source ../.env.example
    else
      echo "No .env, ../.env, or .env.example file found!"
      exit 1
    fi
  fi
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

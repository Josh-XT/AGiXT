#!/bin/sh

set -e

host="${POSTGRES_SERVER:-db}"
port="${POSTGRES_PORT:-5432}"

until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -p "$port" -U "$POSTGRES_USER" -c '\q'; do
  >&2 echo "Waiting for database... $host:$port"
  sleep 1
done

>&2 echo "Database started. Starting AGiXT"

# Change into the agixt directory
cd /agixt

# Start the Uvicorn server
exec uvicorn app:app --host 0.0.0.0 --port 7437 --workers "$UVICORN_WORKERS" --proxy-headers

#!/bin/sh
# wait-for.sh

set -e

host="${POSTGRES_SERVER:-db}"
port="${POSTGRES_PORT:-5432}"
cmd="$@"

until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -p "$port" -U "$POSTGRES_USER" -c '\q'; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - executing command"
exec $cmd

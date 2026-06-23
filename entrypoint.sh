#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until python -c "
import os, sys
import psycopg
url = os.environ.get('DATABASE_URL', '')
try:
    psycopg.connect(url).close()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

echo "Running migrations..."
python manage.py migrate --noinput

exec "$@"

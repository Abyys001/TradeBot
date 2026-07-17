#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until python -c "
import os, sys
import psycopg
url = os.environ.get('DATABASE_URL', '')
# Enforce a short connect timeout so the startup script fails fast
# when the database is unreachable (e.g. Docker networking issues).
try:
    psycopg.connect(url, connect_timeout=5).close()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

echo "Waiting for Redis..."
until python -c "
import os, sys
try:
    import redis
    url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    r = redis.from_url(url, socket_connect_timeout=3)
    r.ping()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "Running migrations..."
  python manage.py migrate --noinput

  # Dev-only: bootstrap first login when the DB has no users yet.
  if [ "${CREATE_DEV_SUPERUSER:-False}" = "True" ] || [ "${DEBUG:-False}" = "True" ] || [ "${DEBUG:-false}" = "true" ]; then
    python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.dev'))
import django
django.setup()
from apps.accounts.models import User
if not User.objects.exists():
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@localhost')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin')
    User.objects.create_superuser(username, email, password)
    print(f'Created dev superuser: {username}')
"
  fi
fi

exec "$@"

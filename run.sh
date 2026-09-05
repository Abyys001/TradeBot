#!/usr/bin/env bash
#
# Run the whole platform without Docker.
#
# Exists because snap-packaged Docker on Debian/Kali cannot signal its own
# containers (AppArmor denies dockerd the "signal receive" permission on the
# docker-default profile), which makes `docker compose restart` impossible.
# This path needs only Python 3.12+ and Node 20+.
#
#   ./run.sh          start backend (:8000) and panel (:3000)
#   ./run.sh backend  backend only
#   ./run.sh panel    panel only
#   ./run.sh setup    install dependencies and create the admin user
#   ./run.sh demo     seed three paper accounts to try the fan-out
#   ./run.sh stop     stop whatever this script started

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"
RUNDIR="$ROOT/.run"
BACKEND_PORT="${BACKEND_PORT:-8000}"
PANEL_PORT="${PANEL_PORT:-3000}"

mkdir -p "$RUNDIR"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

ensure_env() {
  if [ ! -f "$ROOT/.env" ]; then
    say "creating .env"
    cp "$ROOT/.env.example" "$ROOT/.env"
  fi
  # A missing encryption key is fatal by design: the app refuses to store
  # credentials rather than writing them in plaintext (spec §7).
  if ! grep -qE '^CREDENTIAL_ENCRYPTION_KEYS=.+' "$ROOT/.env"; then
    say "generating a credential encryption key"
    local key
    key="$("$PY" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    sed -i "s|^CREDENTIAL_ENCRYPTION_KEYS=.*|CREDENTIAL_ENCRYPTION_KEYS=$key|" "$ROOT/.env"
  fi
  # This used to force USE_SQLITE=true on every start. There is no SQLite path
  # any more — a local run on a different engine to production is exactly the
  # gap this move closed — so the line is gone and `ensure_db` provisions a real
  # PostgreSQL instead. A leftover flag in an old .env is stripped so it cannot
  # look like it still does something.
  sed -i '/^USE_SQLITE=/d' "$ROOT/.env"
  # Outside a container the database is on this machine, not on a compose
  # service called `db`. Only rewritten when it still says `db`, so a host
  # deliberately pointed elsewhere is left alone.
  sed -i 's|^POSTGRES_HOST=db$|POSTGRES_HOST=127.0.0.1|' "$ROOT/.env"
  # Redis is only the channel layer; without it Channels falls back to
  # in-memory, which is fine for a single-process local run.
  sed -i 's|^REDIS_URL=.*|REDIS_URL=|' "$ROOT/.env"
}

# Read one key out of .env, without sourcing it (values contain '=' and '#').
env_value() {
  sed -n "s|^$1=||p" "$ROOT/.env" | tail -1
}

# Make sure the configured PostgreSQL exists and answers.
#
# The database is no longer a file that appears on demand, so this is the step
# that replaces "nothing to do". It provisions the role and database on a local
# server when one is installed, and otherwise says exactly what to install —
# never falls back to something that merely starts, because a local run that
# quietly differs from production is what this whole move was about.
ensure_db() {
  local host port db user pass
  host="$(env_value POSTGRES_HOST)"; host="${host:-127.0.0.1}"
  port="$(env_value POSTGRES_PORT)"; port="${port:-5432}"
  db="$(env_value POSTGRES_DB)";     db="${db:-walletmanager}"
  user="$(env_value POSTGRES_USER)"; user="${user:-walletmanager}"
  pass="$(env_value POSTGRES_PASSWORD)"

  if [ -n "$(env_value DATABASE_URL)" ]; then
    say "using DATABASE_URL from .env"
    return 0
  fi

  if PGPASSWORD="$pass" psql -h "$host" -p "$port" -U "$user" -d "$db" -tAc 'select 1' >/dev/null 2>&1; then
    say "database $db is up at $host:$port"
    return 0
  fi

  command -v psql >/dev/null || die "PostgreSQL is not installed. Install it with:
    sudo apt install postgresql postgresql-client"

  if ! pg_isready -h "$host" -p "$port" -q 2>/dev/null; then
    die "nothing is listening on $host:$port. Start the server with:
    sudo systemctl start postgresql
  Then re-run ./run.sh setup."
  fi

  # The server answers but our role or database is missing. Creating either
  # needs a superuser, which on a Debian/Kali package install is the `postgres`
  # peer account rather than anything reachable over TCP.
  say "creating role '$user' and database '$db'"
  if ! sudo -u postgres psql -p "$port" -v ON_ERROR_STOP=1 >/dev/null <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$user') THEN
    CREATE ROLE "$user" LOGIN PASSWORD '$pass';
  ELSE
    ALTER ROLE "$user" LOGIN PASSWORD '$pass';
  END IF;
END \$\$;
SQL
  then
    die "could not create the role. Do it by hand, then re-run ./run.sh setup:
    sudo -u postgres createuser --login --pwprompt $user
    sudo -u postgres createdb --owner $user $db"
  fi
  # CREATE DATABASE cannot run inside the DO block above, and re-running setup
  # must not fail on a database that already exists.
  sudo -u postgres psql -p "$port" -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 ||
    sudo -u postgres createdb -p "$port" --owner "$user" "$db"
  # pytest builds its own `test_<db>` and needs the right to do so.
  sudo -u postgres psql -p "$port" -qc "ALTER ROLE \"$user\" CREATEDB" >/dev/null

  PGPASSWORD="$pass" psql -h "$host" -p "$port" -U "$user" -d "$db" -tAc 'select 1' >/dev/null ||
    die "the database was created but still will not accept a connection from $user@$host:$port"
  say "database $db ready at $host:$port"
}

# Offer to carry a pre-Postgres db.sqlite3 across, once, into an empty target.
offer_sqlite_import() {
  [ -f "$BACKEND/db.sqlite3" ] || return 0
  local rows
  rows="$(cd "$BACKEND" && "$PY" manage.py shell -c "
from apps.trading.models import Trade
from apps.accounts.models import ConnectedAccount
print(Trade.objects.count() + ConnectedAccount.objects.count())
" 2>/dev/null | tail -1)"
  [ "${rows:-0}" = "0" ] || return 0

  say "found backend/db.sqlite3 and the PostgreSQL database is empty"
  (cd "$BACKEND" && "$PY" manage.py sqlite_to_postgres --dry-run)
  printf 'Copy these rows into PostgreSQL? [y/N] '
  local answer; read -r answer
  case "$answer" in
    y|Y|yes|YES) (cd "$BACKEND" && "$PY" manage.py sqlite_to_postgres) ;;
    *) say "skipped — run it later with: cd backend && .venv/bin/python manage.py sqlite_to_postgres" ;;
  esac
}

setup() {
  command -v python3 >/dev/null || die "python3 not found"
  command -v npm >/dev/null || die "npm not found"

  [ -d "$VENV" ] || { say "creating virtualenv"; python3 -m venv "$VENV"; }
  say "installing Python dependencies"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements-dev.txt"

  ensure_env
  ensure_db

  say "applying migrations"
  (cd "$BACKEND" && "$PY" manage.py migrate --noinput)

  offer_sqlite_import

  if ! (cd "$BACKEND" && "$PY" -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.contrib.auth.models import User
raise SystemExit(0 if User.objects.filter(is_staff=True).exists() else 1)
" 2>/dev/null); then
    say "create the panel admin user"
    (cd "$BACKEND" && "$PY" manage.py createsuperuser)
  fi

  [ -d "$FRONTEND/node_modules" ] || { say "installing panel dependencies"; (cd "$FRONTEND" && npm install --no-fund --no-audit); }
  say "setup complete — now run ./run.sh"
}

demo() {
  ensure_env
  say "seeding three paper accounts"
  (cd "$BACKEND" && "$PY" manage.py shell -c "
from decimal import Decimal
from apps.accounts.models import ConnectedAccount, Exchange
for label, balance in (('demo-small','10'),('demo-mid','50'),('demo-big','100')):
    ConnectedAccount.objects.update_or_create(
        label=label, exchange=Exchange.PAPER,
        defaults=dict(withdrawal_check_passed=True,
                      last_balance=Decimal(balance), last_balance_asset='USDT'))
print('paper accounts:', list(ConnectedAccount.objects.values_list('label','last_balance')))
")
}

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3<&-; return 0; } || return 1
}

check_port() {
  local port="$1" what="$2"
  port_in_use "$port" || return 0
  printf '\033[1;31mError:\033[0m port %s is already in use, so the %s cannot start.\n' "$port" "$what" >&2
  if docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null | grep -q ":$port->"; then
    cat >&2 <<EOF

A Docker container is holding it:
$(docker ps --format '  {{.Names}}  {{.Ports}}' 2>/dev/null | grep ":$port->")

If 'docker rm -f' fails with "permission denied", this is the snap-Docker
AppArmor bug — the daemon is not allowed to signal its own container. Kill the
process directly instead:

  sudo kill -9 \$(docker inspect -f '{{.State.Pid}}' <container-name>)
  docker rm -f <container-name>

Or pick another port:  BACKEND_PORT=8010 PANEL_PORT=3010 ./run.sh
EOF
  else
    echo "  Free it, or run: BACKEND_PORT=8010 PANEL_PORT=3010 ./run.sh" >&2
  fi
  exit 1
}

start_backend() {
  [ -x "$PY" ] || die "run ./run.sh setup first"
  check_port "$BACKEND_PORT" "backend"
  ensure_env
  # Not `ensure_db`: starting the panel is not the moment to be prompted for a
  # sudo password. This only waits, and says plainly what to run if there is
  # nothing to wait for.
  (cd "$BACKEND" && "$PY" manage.py wait_for_db --timeout 20) ||
    die "no database — run ./run.sh setup to create one"
  (cd "$BACKEND" && "$PY" manage.py migrate --noinput >/dev/null)
  say "backend on http://localhost:$BACKEND_PORT"
  (cd "$BACKEND" && exec "$VENV/bin/daphne" -b 0.0.0.0 -p "$BACKEND_PORT" config.asgi:application) \
    > "$RUNDIR/backend.log" 2>&1 &
  echo $! > "$RUNDIR/backend.pid"
}

start_panel() {
  [ -d "$FRONTEND/node_modules" ] || die "run ./run.sh setup first"
  check_port "$PANEL_PORT" "panel"
  say "panel on http://localhost:$PANEL_PORT"
  (cd "$FRONTEND" && \
    NUXT_PUBLIC_API_BASE="http://localhost:$BACKEND_PORT/api" \
    NUXT_API_PROXY_TARGET="http://localhost:$BACKEND_PORT/api" \
    NUXT_WS_PROXY_TARGET="ws://localhost:$BACKEND_PORT" \
    PORT="$PANEL_PORT" exec npx nuxt dev) > "$RUNDIR/panel.log" 2>&1 &
  echo $! > "$RUNDIR/panel.pid"
}

stop() {
  for name in backend panel; do
    local pidfile="$RUNDIR/$name.pid"
    if [ -f "$pidfile" ]; then
      local pid; pid="$(cat "$pidfile")"
      if kill -0 "$pid" 2>/dev/null; then
        say "stopping $name (pid $pid)"
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    fi
  done
}

wait_for() {
  local url="$1" tries=90
  until curl -sf --noproxy '*' -o /dev/null "$url" 2>/dev/null; do
    tries=$((tries - 1))
    [ "$tries" -le 0 ] && return 1
    sleep 1
  done
}

case "${1:-all}" in
  setup)   setup ;;
  demo)    demo ;;
  backend) start_backend; say "logs: tail -f .run/backend.log"; wait ;;
  panel)   start_panel;   say "logs: tail -f .run/panel.log"; wait ;;
  stop)    stop ;;
  all)
    trap stop EXIT INT TERM
    start_backend
    if wait_for "http://localhost:$BACKEND_PORT/api/accounts/auth/csrf/"; then
      say "backend ready"
    else
      die "backend did not start — see $RUNDIR/backend.log"
    fi
    start_panel
    wait_for "http://localhost:$PANEL_PORT/" && say "panel ready"
    echo
    say "open http://localhost:$PANEL_PORT   (Persian: /fa)"
    say "Ctrl-C to stop both"
    wait
    ;;
  *) die "unknown command: $1" ;;
esac

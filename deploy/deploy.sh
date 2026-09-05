#!/usr/bin/env bash
# Deploy the panel, and do not report success until the domain is serving again.
#
#   deploy/deploy.sh              # build, swap, verify
#   deploy/deploy.sh --check      # verify only, change nothing
#
# `docker compose up -d --build` on its own is the reason the panel has gone
# dark on six separate days: it exits as soon as the containers are *created*,
# which is a minute or so before the site actually answers, so a deploy that
# never came back looked exactly like a deploy that did. Everything below is
# in service of two things — keep the dark window as short as it can be, and
# refuse to call the deploy finished until a real request over the real domain
# comes back 200.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

URL="${DEPLOY_URL:-https://maxbot.cybercina.co.uk}"
COMPOSE="${DEPLOY_COMPOSE:-docker-compose.yml}"
DEADLINE="${DEPLOY_TIMEOUT:-300}"      # seconds to wait for the site to answer

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# A page and the API, because they fail independently: nginx can serve the
# panel while the backend behind it is still migrating.
probe() {
  local page api
  page=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$URL/" 2>/dev/null || echo 000)
  api=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$URL/api/health/" 2>/dev/null || echo 000)
  [[ "$page" == "200" && "$api" == "200" ]]
}

wait_for_site() {
  local start now waited
  start=$(date +%s)
  say "Waiting for $URL to answer"
  while :; do
    if probe; then
      now=$(date +%s); waited=$((now - start))
      printf '    up after %ss\n' "$waited"
      return 0
    fi
    now=$(date +%s); waited=$((now - start))
    if (( waited > DEADLINE )); then
      printf '\033[31m    still down after %ss\033[0m\n' "$waited"
      return 1
    fi
    printf '    down (%ss)\n' "$waited"
    sleep 3
  done
}

if [[ "${1:-}" == "--check" ]]; then
  say "Checking only"
  curl -sS -o /dev/null -w 'page   %{http_code}\n' --max-time 10 "$URL/" || true
  curl -sS -w 'health %{http_code}  ' -o /tmp/.dh --max-time 10 "$URL/api/health/" || true
  cat /tmp/.dh 2>/dev/null; echo
  probe && { echo "OK"; exit 0; } || { echo "NOT SERVING"; exit 1; }
fi

# 1. Build first. Nothing is taken down while this runs, so a build that fails
#    — a bad dependency, a type error — costs no downtime at all. This is the
#    step that must never be folded into `up --build`.
say "Building images (the running site is untouched)"
docker compose -f "$COMPOSE" build

# 2. The swap. This is the only part that is dark, and nginx now serves the
#    maintenance page through it rather than a bare 502.
say "Swapping containers"
docker compose -f "$COMPOSE" up -d --remove-orphans

# 3. Do not trust "Created". Ask the domain.
if ! wait_for_site; then
  say "Deploy did NOT come back — leaving everything running for inspection"
  docker compose -f "$COMPOSE" ps
  echo
  echo "Recent backend log:"
  docker compose -f "$COMPOSE" logs --tail 40 backend || true
  echo
  echo "Recent frontend log:"
  docker compose -f "$COMPOSE" logs --tail 40 frontend || true
  exit 1
fi

say "Deployed and serving"
docker compose -f "$COMPOSE" ps

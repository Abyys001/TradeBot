#!/usr/bin/env bash
# Deploy the latest `main` to the VPS, from here.
#
#   deploy/remote-deploy.sh           # pull + build + swap + verify
#   deploy/remote-deploy.sh --check   # ask the domain whether it is serving
#
# Connection details come from .env.vps, which is gitignored and holds a login
# to the server that routes live orders. This script is the only thing that
# reads it, it never prints it, and it stays inside $VPS_PATH — that box also
# hosts a dozen unrelated projects, and none of them are ours to touch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[[ -f .env.vps ]] || { echo "no .env.vps — copy .env.vps.example and fill it in" >&2; exit 1; }
set -a; . ./.env.vps; set +a

: "${VPS_HOST:?set VPS_HOST in .env.vps}"
: "${VPS_USER:?set VPS_USER in .env.vps}"

ssh_args=(-o StrictHostKeyChecking=accept-new -p "${VPS_PORT:-22}")
run() { ssh "${ssh_args[@]}" "$VPS_USER@$VPS_HOST" "$@"; }

if [[ -n "${VPS_KEY:-}" ]]; then
  ssh_args+=(-i "${VPS_KEY/#\~/$HOME}" -o IdentitiesOnly=yes)
elif [[ -n "${VPS_PASSWORD:-}" ]]; then
  # OpenSSH >= 8.4 will call SSH_ASKPASS with no tty when REQUIRE=force. That
  # is the whole reason sshpass is not a dependency here: installing it needs
  # sudo, and a deploy should not be gated on a second password.
  askpass="$(mktemp)"; chmod 700 "$askpass"
  trap 'rm -f "$askpass"' EXIT
  printf '#!/bin/sh\n. %q/.env.vps\nprintf "%%s\\n" "$VPS_PASSWORD"\n' "$ROOT" > "$askpass"
  ssh_args+=(-o PreferredAuthentications=password)
  run() { setsid -w env SSH_ASKPASS="$askpass" SSH_ASKPASS_REQUIRE=force DISPLAY=none \
            ssh "${ssh_args[@]}" "$VPS_USER@$VPS_HOST" "$@"; }
fi

# The build, swap and the "is it actually serving" wait all live in deploy.sh,
# which runs on the server. Duplicating any of it here is how the two drift.
run "cd ${VPS_PATH:-/root/walletManager} \
  && git pull --ff-only origin main \
  && DEPLOY_COMPOSE='${DEPLOY_COMPOSE:-docker-compose.yml}' \
     DEPLOY_URL='${DEPLOY_URL:-https://maxbot.cybercina.co.uk}' \
     deploy/deploy.sh ${1:-}"

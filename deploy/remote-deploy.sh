#!/usr/bin/env bash
# Deploy the latest `main` to the VPS, from here.
#
#   deploy/remote-deploy.sh           # pull + build + swap + verify
#   deploy/remote-deploy.sh --check   # ask the domain whether it is serving
#
# Connection details come from .env.vps, which is gitignored and holds a login
# to the server that routes live orders. This script is the only thing that
# reads it, it never prints it, and it stays inside $VPS_PATH — the rest of the
# box is somebody else's.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[[ -f .env.vps ]] || { echo "no .env.vps — copy .env.vps.example and fill it in" >&2; exit 1; }
set -a; . ./.env.vps; set +a

: "${VPS_HOST:?set VPS_HOST in .env.vps}"
: "${VPS_USER:?set VPS_USER in .env.vps}"

ssh_args=(-o StrictHostKeyChecking=accept-new -p "${VPS_PORT:-22}")
runner=(ssh)
if [[ -n "${VPS_PASSWORD:-}" ]]; then
  command -v sshpass >/dev/null || { echo "VPS_PASSWORD set but sshpass is not installed" >&2; exit 1; }
  runner=(sshpass -e ssh); export SSHPASS="$VPS_PASSWORD"
elif [[ -n "${VPS_KEY:-}" ]]; then
  ssh_args+=(-i "${VPS_KEY/#\~/$HOME}" -o IdentitiesOnly=yes)
fi

remote() { "${runner[@]}" "${ssh_args[@]}" "$VPS_USER@$VPS_HOST" "$@"; }

# The build, swap and the "is it actually serving" wait all live in deploy.sh,
# which runs on the server. Duplicating any of it here is how the two drift.
remote "cd ${VPS_PATH:-~/walletmanager} \
  && git pull --ff-only origin main \
  && DEPLOY_COMPOSE='${DEPLOY_COMPOSE:-docker-compose.prod.yml}' \
     DEPLOY_URL='${DEPLOY_URL:-https://maxbot.cybercina.co.uk}' \
     deploy/deploy.sh ${1:-}"

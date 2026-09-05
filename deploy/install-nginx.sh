#!/usr/bin/env bash
# Install the tracked host-nginx front for the panel.
#
#   sudo deploy/install-nginx.sh
#
# Copies deploy/nginx-host.conf into sites-available, links it, drops the
# maintenance page where the config expects it, and reloads — but only after
# `nginx -t` passes, so a bad edit is refused instead of taking every site on
# the box down with it. The previous config is kept alongside with a timestamp.
set -euo pipefail

SITE="maxbot.cybercina.co.uk"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AVAILABLE="/etc/nginx/sites-available/${SITE}"
ENABLED="/etc/nginx/sites-enabled/${SITE}"
WEBROOT="/var/www/maxbot"

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

# The page nginx serves while the containers are being swapped.
install -d -m 755 "$WEBROOT"
install -m 644 "$HERE/maintenance.html" "$WEBROOT/__maintenance.html"

if [[ -f "$AVAILABLE" ]]; then
  backup="${AVAILABLE}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -a "$AVAILABLE" "$backup"
  echo "previous config kept at $backup"
fi

install -m 644 "$HERE/nginx-host.conf" "$AVAILABLE"
ln -sfn "$AVAILABLE" "$ENABLED"

if ! nginx -t; then
  echo "nginx -t FAILED — restoring the previous config and leaving nginx alone" >&2
  [[ -n "${backup:-}" ]] && cp -a "$backup" "$AVAILABLE"
  exit 1
fi

nginx -s reload
echo "nginx reloaded for ${SITE}"

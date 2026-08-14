# Deploying the platform to a VPS

Launch topology for a fresh server owning the domain. TLS is automatic.

```
Browser ──(443)──> Caddy (auto Let's Encrypt, no certbot)
                        │
                        ├── /ws/** ──────────────────────┐   (WebSocket upgrade)
                        │                                │
                        └──> frontend (built Nuxt bundle, port 3000, internal)
                                  │ proxies /api/**      │
                                  └──> backend (Daphne, port 8000, internal)
                                             │            │
                                      Postgres 16     Redis 7
```

`/ws/**` bypasses the panel here as an optimisation, not a requirement. Caddy
hands the upgrade to Daphne directly, one hop fewer; the browser dials a
same-origin `wss://<domain>/ws/trading/` and knows nothing about the split. If
you front this stack with something other than the bundled `Caddyfile`, the
panel serves `/ws` itself (`frontend/server/routes/ws/[...].ts` relays it to
`NUXT_WS_PROXY_TARGET`) — so any proxy that forwards an `Upgrade` header to the
panel works without extra routing.

What still cannot carry it is a nitro **route rule**: `routeRules[].proxy` is
an h3 `proxyRequest`, which forwards the HTTP request and drops the upgrade.
That is the failure this section exists to prevent — the socket sits on
"connecting" and both latency readings stay blank.

Only Caddy publishes ports to the host (80/443). Backend and panel are on the
Docker network alone, so the Django API is never directly reachable from
outside — a stray `curl` to `:8000` cannot reach it.

## 1. DNS first

Create an `A` record on `cybercina.co.uk`:

| Type | Name | Value |
|---|---|---|
| A | `maxbot` | `<VPS public IP>` |

Verify before starting the stack — Caddy needs the domain resolvable to this
server to issue the certificate:

```bash
dig +short maxbot.cybercina.co.uk
```

## 2. Install Docker (official CE, not snap)

Use the Docker package from Docker's repo. Snap Docker cannot stop its own
containers (AppArmor) — see `docs/running.md` for the failure mode.

```bash
# Debian/Ubuntu — one-time:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # then log out and back in
```

Open ports 22, 80, 443 and nothing else (e.g. `ufw allow 22/80/443`).

## 3. Get the code and configure

```bash
git clone <repo-url> walletmanager && cd walletmanager
cp .env.production.example .env
```

Fill the three `change-me` values in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"    # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"    # POSTGRES_PASSWORD
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # CREDENTIAL_ENCRYPTION_KEYS
```

`CREDENTIAL_ENCRYPTION_KEYS` is required — without it the app refuses to store
credentials rather than writing them in plaintext (spec §7). Review the
trading-policy block too; every value maps to an open question in
`questions.md`, and each is decided by editing `.env`, not code.

## 4. Launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

The backend's boot command runs `collectstatic` then `migrate`, so first boot
takes a minute. Migrations run automatically on every boot; there is no manual
migrate step.

## 5. Verify

```bash
# TLS certificate issued and served:
curl -sI https://maxbot.cybercina.co.uk | head -1            # 200
# HTTP redirects to HTTPS:
curl -sI http://maxbot.cybercina.co.uk | grep -i location    # https://...
# Order routing refuses a stranger (403 is CORRECT — the CSRF check runs
# first, so a caller with no panel session never even reaches the auth gate):
curl -s -o /dev/null -w '%{http_code}\n' https://maxbot.cybercina.co.uk/api/trading/orders/open/ \
  -H 'Content-Type: application/json' -d '{"symbol":"BTCUSDT","side":"long","leverage":10}'

# The live channel reaches Channels and refuses a stranger (403 is CORRECT).
# This one check proves both halves: a 403 can only come from the consumer, so
# Caddy routed the upgrade to Daphne rather than serving it from the panel.
# A 404, or HTML, means /ws went to Nuxt and the socket will never connect.
curl -s -o /dev/null -w '%{http_code}\n' https://maxbot.cybercina.co.uk/ws/trading/ \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=='
```

Then in a browser: the panel at `/`, `/risk`, `/accounts`, `/history`, the
Persian build at `/fa`, and — before any real capital — every exchange adapter
on testnet per `docs/adapters.md`.

**Settings → Connection & data is the live-channel smoke test.** Signed in, it
must read `LIVE` with a panel latency in milliseconds, and an exchange latency
within about half a minute — the engine probes that itself now rather than
waiting for the chart to poll something.

Anything else names its own cause rather than sitting on `CONNECTING`:

| Reads | Means |
|---|---|
| `CONNECTING`, briefly | Handshake in flight. It resolves or becomes one of the below. |
| `OFFLINE · …did not complete the handshake` | The upgrade never reached Daphne. Check the `/ws/trading/` curl above; if you are not using the bundled Caddyfile, check your proxy forwards `Upgrade` to the panel. |
| `REFUSED · staff-only` | The socket reached the engine and the engine turned the session down. Sign in as a staff account. |
| `OFFLINE · engine answered …` | Reached the engine, which failed. `docker compose logs backend`. |

## 6. Day-to-day operations

| Task | Command |
|---|---|
| Logs | `docker compose -f docker-compose.prod.yml logs -f backend frontend caddy` |
| Update code | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Restart | `docker compose -f docker-compose.prod.yml restart` |
| Back up Postgres | `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U walletmanager walletmanager > backup.sql` |
| Inspect state | `docker compose -f docker-compose.prod.yml ps` |

`restart: unless-stopped` is on every service, so the stack comes back after a
server reboot. The emergency halt lives in the panel's top bar; `STOP_ALL=true`
in `.env` is the un-clearable pin (spec §7).

## 7. Security notes

- `.env` never enters git, and this repo is designed to hold trade-enabled,
  non-withdrawable keys (spec §7). Check the permission scope at connect time.
- Rotate `DJANGO_SECRET_KEY` by generating a new value and restarting the
  backend (sessions are invalidated — users log in again).
- Rotate `CREDENTIAL_ENCRYPTION_KEYS` by putting the new key FIRST and keeping
  old keys after it, comma separated, then restarting the backend.
- If the domain or the VPS changes, update `SITE_DOMAIN` and
  `DJANGO_ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` together — they must agree.
  `DJANGO_ALLOWED_HOSTS` now also gates the WebSocket: the live channel refuses
  any handshake whose `Origin` host is not in that list, so a domain missing
  from it shows as a panel that loads fine but never goes `LIVE`.
- The live channel is staff-only and same-origin-only. A WebSocket handshake is
  exempt from CORS, so without the origin check any page the admin visited
  could open one with their session cookie attached and stream balances,
  positions and failures. Both guards are pinned by tests in
  `backend/tests/test_consumer.py`; do not relax either to "make the socket
  work" — an ungated socket hands out everything the staff-only REST endpoints
  withhold.

# Deploying the platform to a VPS

A complete run from a bare server to a panel that routes orders — and, at each
step, the one command that proves it worked. Follow it top to bottom on a first
deploy; §7 onwards is what you come back for.

This stack holds **live, trade-enabled exchange credentials for other people's
capital**. Two rules that are not negotiable anywhere below: `.env` never enters
git, and every key you connect must be trade-only with withdrawal disabled
(spec §7 — the platform refuses a key that proves withdrawal rights, but it can
only check that where the exchange publishes a permissions endpoint, and four of
the eight do not).

## Topology

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

Only Caddy publishes ports to the host (80/443). Backend and panel sit on the
Docker network alone, so the Django API is never directly reachable — a stray
`curl` to `:8000` from outside cannot reach it.

There is **no Celery worker and no broker**. The fan-out is
`asyncio.gather` inside the ASGI process (a broker round trip does not fit the
per-leg deadline), and the history download runs in a background thread. Five
containers is the whole deployment.

### About `/ws`

`/ws/**` bypasses the panel here as an optimisation, not a requirement. Caddy
hands the upgrade to Daphne directly, one hop fewer; the browser dials a
same-origin `wss://<domain>/ws/trading/` and knows nothing about the split.

If you front this stack with something other than the bundled `Caddyfile`, the
panel serves `/ws` itself — `frontend/server/routes/ws/[...].ts` is a nitro
WebSocket handler that relays to `NUXT_WS_PROXY_TARGET`, forwarding the session
cookie so the staff check still happens at the consumer. Any proxy that
forwards an `Upgrade` header to the panel works with no extra routing.

The relay is why the `/ws/trading/` curl below can read **101 instead of 403**
behind such a proxy: the relay completes the handshake the moment it opens the
upstream, so the consumer's refusal arrives as a *post-handshake close frame*
(4403) that curl's HTTP-status check cannot see. That is relay-masking, not a
leak — the unauth socket is still refused, just one step later. Two options:

- **Accept 101 as the pass** behind the relay. The panel's own status line is
  the real check (Settings → Connection & data must read `REFUSED · staff-only`
  for a stranger, `LIVE` for the admin).
- **Route `/ws` past the relay to Daphne** so the check prints 403 again:
  add the `location /ws/` block from `deploy/nginx.conf` (upgrade headers +
  `proxy_read_timeout 3600s`), pointing at the backend. That requires the
  backend reachable from the proxy — nginx on the compose network, or the
  backend port published to the host. One hop fewer either way.

What cannot carry it is a nitro **route rule**: `routeRules[].proxy` is an h3
`proxyRequest`, which forwards the HTTP request and drops the upgrade. That is
the failure this section exists to prevent — the socket sits on "connecting"
and both latency readings stay blank.

Fronting the stack with nginx? `deploy/nginx.conf` is a drop-in that mirrors
this Caddyfile's split, upgrade headers included. The two things that break
every nginx front are the same two every debugging session here comes back to:
a `location /ws/` whose `proxy_pass` leaves out the `Upgrade`/`Connection`
headers (socket stuck on "connecting"), and a plain `location /` that forwards
`/api/` to the backend minus the `/api` prefix. This file handles both.

Two more nginx gotchas seen in the field, both covered in this file:

- **Idle sockets get reaped at nginx's default `proxy_read_timeout` (60s)** if
  your `location` does not say `proxy_read_timeout 3600s`. The panel pings every
  8s so a foreground tab survives anyway, but a throttled background tab can
  cross 60s and drop the channel. `deploy/nginx.conf` sets 3600s on `/ws`.
- **The relay needs the upgrade headers too.** If nginx forwards `/ws/` to the
  *panel* rather than splitting it off, a plain `proxy_pass` without
  `Upgrade`/`Connection` still strands the socket on "connecting" — the relay
  is an upgrade endpoint like any other.

## 0. What the server needs

| | Minimum | Comfortable |
|---|---|---|
| vCPU | 2 | 4 |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB | 40 GB+ |
| OS | Debian 12 / Ubuntu 22.04+ | same |

Disk is the one that surprises people: `BACKFILL_DAYS=365` across
`BACKFILL_PAIRS=50` at 1-minute resolution is roughly 500k rows per pair. Start
lower (§3) if you are on a 20 GB box.

**Outbound network matters as much as inbound.** The engine has to reach the
exchanges. A VPS that cannot open `api.hyperliquid.xyz` gives you a panel with
no prices, and with no price nothing sizes an order. Check before you build:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://api.hyperliquid.xyz/info \
  -H 'Content-Type: application/json' -d '{"type":"meta"}'      # 200
```

Not 200 → set `MARKET_DATA_PROXY` in §3, or pick a different region.

## 1. DNS first

Caddy provisions the TLS certificate at boot, so the name must resolve to this
server *before* the stack starts.

| Type | Name | Value |
|---|---|---|
| A | `maxbot` | `<VPS public IP>` |

```bash
dig +short maxbot.cybercina.co.uk        # must print this server's IP
```

## 2. Docker and the firewall

Use Docker's own package. Snap Docker cannot stop its own containers
(AppArmor) — see `docs/running.md` for that failure mode.

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"          # then log out and back in
docker compose version                   # v2, not docker-compose
```

Open 22, 80 and 443, nothing else:

```bash
sudo ufw allow 22,80,443/tcp && sudo ufw enable
```

Do **not** open 8000 or 3000. They are internal to the Docker network and
nothing outside needs them.

## 3. Get the code and configure

```bash
git clone <repo-url> walletmanager && cd walletmanager
cp .env.production.example .env
```

Generate the three secrets and paste them into `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
docker run --rm python:3.12-slim sh -c \
  "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                                                                # CREDENTIAL_ENCRYPTION_KEYS
```

`CREDENTIAL_ENCRYPTION_KEYS` is required. Without it the app refuses to store a
credential rather than writing it in plaintext (spec §7). Lose it and every
connected key becomes undecryptable — back it up somewhere that is not this
server.

Then set the domain in **three places that must agree**, or you get a panel
that loads and never goes `LIVE`:

```ini
SITE_DOMAIN=maxbot.cybercina.co.uk
DJANGO_ALLOWED_HOSTS=backend,localhost,127.0.0.1,maxbot.cybercina.co.uk
DJANGO_SECURE_SSL_REDIRECT=false
CORS_ALLOWED_ORIGINS=https://maxbot.cybercina.co.uk
```

`DJANGO_ALLOWED_HOSTS` also gates the WebSocket: the live channel refuses any
handshake whose `Origin` host is not listed.

`DJANGO_SECURE_SSL_REDIRECT=false` is not a security relaxation: TLS is
terminated by the proxy in front, which forwards `X-Forwarded-Proto: https`, so
browsers never hit Django over plaintext anyway. Left at the `true` default
(which `DJANGO_DEBUG=false` implies), the compose healthcheck — a plain `http://
127.0.0.1:8000` probe on the docker network with no forwarder header — gets a
301 and the backend never turns `healthy`, so `frontend` and `caddy` never
start. The prod compose pins it `false`; the line is here so the value is
visible in the source of truth.

### The settings that change how it trades

Every one of these is an open question in `questions.md` with **both branches
built**, so answering one is an `.env` edit and a restart, never a rewrite.
Decide before connecting real accounts.

| Setting | Default | What it decides |
|---|---|---|
| `BALANCE_FRACTION` | `0.99` | Share of each account's own USDT committed as margin. Rounded **down** to the exchange step, never up. |
| `MIN_LEVERAGE` / `MAX_LEVERAGE` | `1` / `10` | The band the ticket accepts. Leverage is identical on every account (spec §4); only dollar size differs. |
| `SLTP_BASIS` | `price` | Whether a typed percentage is a move in **price** or a fraction of the **margin** committed (Q5a). `/risk` in the panel shows both readings against real numbers. |
| `SLTP_REFERENCE` | `own_fill` | Which fill the percentage measures from: each account's own, or the admin's (Q5b/c). |
| `SLTP_AMEND_STRATEGY` | `place_then_cancel` | Mid-trade SL/TP change where the venue has no native amend (Q5d). The alternative leaves a moment unprotected instead of a moment double-protected. |
| `SLTP_FAILURE_POLICY` | `retry_then_close` | A leg that fills but whose stop will not attach (Q5e). The default closes it rather than leaving a position running unprotected at leverage. |
| `REJECT_SL_BEYOND_LIQUIDATION` | `true` | Refuses an order whose stop can never trigger because the position liquidates first. |
| `FANOUT_TIMEOUT_SECONDS` | `10.0` | Per-leg deadline (spec §4, **amended** — `questions.md` Q19). Was 1.0, which VPS exchange round trips blew on healthy orders. One slow exchange cannot hold up the others past this. A leg that fails *after* its order went out — deadline, HTTP read timeout, 5xx — is re-read from the exchange and reported as a fill when the position is there; raising this only makes that path rarer, it is not what makes the reporting correct. |
| `STOP_ALL` | `false` | `true` is an un-clearable halt pin. Leave `false` — the panel's own halt switch is the everyday control. |

### The settings that change what it shows

| Setting | Default | What it decides |
|---|---|---|
| `MARKET_DATA_PIN` | `hyperliquid` | Pins the feed to one venue. No hand-off behind it: that exchange answers or the panel says "no price feed". Also narrows the symbol picker to that venue's pairs, so the chart can price everything it offers. |
| `MARKET_DATA_PROVIDERS` | `hyperliquid,binance,bybit` | Only used when the pin is **cleared**: connected exchanges quote themselves first, these fall in behind. |
| `MARKET_DATA_PROXY` | empty | Egress proxy for price calls. Set where the VPS can only reach the exchange through one. A shell `socks://` URL is normalised; an unusable one is dropped rather than failing every call. |
| `MARKET_DATA_AUTO_SYNC` | `true` | Start the pair/history download by itself on first connect. |
| `BACKFILL_PAIRS` / `BACKFILL_DAYS` | `50` / `365` | How much scrollback the chart gets, and most of the disk footprint. |

**Hyperliquid is perpetuals only.** Under the default pin the spot chart has no
feed and says so. Clear `MARKET_DATA_PIN` if you need spot.

## 4. Launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First boot takes a few minutes: image build, then `collectstatic` and `migrate`
inside the backend's start command. Migrations run on **every** boot — there is
no manual migrate step, ever.

Wait for the stack to report itself healthy rather than guessing:

```bash
watch -n5 'docker compose -f docker-compose.prod.yml ps'
```

`backend` and `frontend` carry healthchecks, so `ps` shows `(healthy)` when
they are genuinely serving — not merely when the process started. Caddy will
not have a certificate until DNS resolves and port 80 is reachable.

Create the admin who trades:

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

Login refuses non-staff accounts outright, and the WebSocket refuses them
again at the consumer. A superuser is staff, so this is enough.

**Optional — the hidden-account viewer.** An account can be marked `hidden`: it
trades identically in every fan-out but is invisible to every operator except
the one username in `apps/accounts/visibility.py`. If you use that, create the
viewer now:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python manage.py ensure_hidden_viewer --password '<a real password>'
```

## 5. Prove it is up

One command for the stack:

```bash
curl -s https://maxbot.cybercina.co.uk/api/health/ | python3 -m json.tool
```

```json
{
  "status": "ok",
  "checks": {
    "database": true,
    "cache": true,
    "channel_layer_shared": true,
    "market_feed": true
  }
}
```

- `database` / `cache` false → 503, and the container is unhealthy. Logs.
- `channel_layer_shared` false → `REDIS_URL` did not reach the backend; the
  channel layer fell back to per-process memory and a halt flipped in one tab
  will not reach another.
- `market_feed` false on a cold boot is normal (nothing has priced yet). Still
  false a minute after opening the chart means outbound is blocked — go back
  to the §0 curl.

Then the edges the panel depends on:

```bash
# TLS issued and serving:
curl -sI https://maxbot.cybercina.co.uk | head -1              # 200
# HTTP redirects to HTTPS:
curl -sI http://maxbot.cybercina.co.uk | grep -i location      # https://...

# Order routing refuses a stranger (403 is CORRECT — the CSRF check runs first,
# so a caller with no panel session never even reaches the auth gate):
curl -s -o /dev/null -w '%{http_code}\n' https://maxbot.cybercina.co.uk/api/trading/orders/open/ \
  -H 'Content-Type: application/json' -d '{"symbol":"BTCUSDT","side":"long","leverage":10}'

# The live channel reaches Channels and refuses a stranger.
#
# With the bundled Caddyfile: 403 is CORRECT and proves both halves at once —
# only the consumer can produce it, so the upgrade reached Daphne.
#
# Behind some other proxy the panel's relay answers instead: it completes the
# handshake (101) and *then* closes with 4403 once the consumer refuses, which
# curl cannot see. 101 is a pass there; the panel's own status line is the
# check that distinguishes them.
#
# A 404, or HTML, means /ws never got there and the socket will not connect.
curl -s -o /dev/null -w '%{http_code}\n' https://maxbot.cybercina.co.uk/ws/trading/ \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=='
```

### Settings → Connection & data is the live-channel smoke test

Signed in, it must read `LIVE` with a panel latency in milliseconds, and an
exchange latency within about half a minute — the engine probes that itself
now rather than waiting for the chart to poll something.

Anything else names its own cause rather than sitting on `CONNECTING`:

| Reads | Means |
|---|---|
| `CONNECTING`, briefly | Handshake in flight. It resolves or becomes one of the below. |
| `OFFLINE · …did not complete the handshake` | The upgrade never reached Daphne. Check the `/ws/trading/` curl above; if you are not using the bundled Caddyfile, check your proxy forwards `Upgrade` to the panel (`deploy/nginx.conf` is the reference nginx front). |
| `REFUSED · staff-only` | The socket reached the engine and the engine turned the session down. Sign in as a staff account. |
| `OFFLINE · engine answered …` | Reached the engine, which failed. `docker compose logs backend`. |

Two latencies are shown and they are not interchangeable. **Panel** is the
browser's round trip to the engine — on a good link a few tens of ms, and it
says nothing about reaching an exchange. **Exchange** is the engine's measured
round trip to the price venue, which is the hop an order actually travels and
the one that spends the fan-out deadline.

## 6. Turn the whole thing on

Deployed is not the same as in use. In order:

1. **Connect an account** — `/accounts` → Connect. Every key must be
   trade-only with withdrawal **disabled**. The platform refuses a key that
   proves withdrawal rights at connect time, and `ConnectedAccount.clean()`
   blocks activating a credential that was never checked. Four venues
   (Hyperliquid, LBank, Gate, Toobit) publish no permission endpoint, so on
   those the check cannot run and the responsibility is yours at the exchange.
   Start with **one testnet account** — see `docs/adapters.md`; no adapter in
   this repo has been run against a live exchange yet.
2. **Watch the history download.** First connect kicks off the pair catalogue
   and the backfill in a background thread; `/accounts` shows the progress. A
   year across 50 pairs takes minutes to an hour. The chart can only pan back
   as far as this has stored.
3. **Check the chart** — `/chart`. The feed badge names the venue and whether
   prices    are **streamed** (pushed from the exchange socket) or **polled**.
   Under the default pin it reads `Hyperliquid · pinned`. "No price feed"
   means no provider answered; there is no synthetic series, by design.
4. **Set the policy from numbers, not taste** — `/risk` answers Q5a by showing
   what a percentage means under each basis against the balances you actually
   have connected.
5. **Build the watchlist** — the pairs you trade, stored in a cookie, quoted in
   one batched request.
6. **Route a first trade on testnet accounts.** `/chart` is the trading screen:
   ticket, chart and position bar all edit SL/TP and all write to one store, so
   one edit is one fan-out wherever it came from. Enter, drag the lines, amend
   mid-trade, close. Then `/dashboard` for per-account margin, live PnL marked
   to market, and what the fan-out actually cost. A leg below the
   exchange's minimum notional is **skipped with a persistent notification**,
   never rounded up — that is spec §5 working, not a bug.
7. **Test the halt.** Stop all in the top bar refuses new routing platform-wide
   and shows in every open panel; closing and amending keep working. Clear it
   again before you rely on the panel.
8. **Install the panel.** It is a PWA — Chrome/Edge offer Install, iOS Safari
   Add to Home Screen. HTTPS is what makes that offer appear, which you now
   have. The service worker never caches `/api` or `/ws`.
9. **Persian** — `/fa`, full RTL. English is the source language; both are
   complete.

## 7. Day-to-day operations

| Task | Command |
|---|---|
| State | `docker compose -f docker-compose.prod.yml ps` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f backend frontend caddy` |
| Health | `curl -s https://maxbot.cybercina.co.uk/api/health/` |
| Update | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Restart | `docker compose -f docker-compose.prod.yml restart` |
| Back up Postgres | `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U walletmanager walletmanager > backup-$(date +%F).sql` |
| Restore | `docker compose -f docker-compose.prod.yml exec -T db psql -U walletmanager walletmanager < backup.sql` |

`restart: unless-stopped` is on every service, so the stack returns after a
reboot.

**Back up `.env` separately from the database, and keep both.** The database
holds credentials encrypted with `CREDENTIAL_ENCRYPTION_KEYS`; a dump without
that key restores rows nobody can read.

**An update rebuilds images.** Dependencies move (the panel gained `ws` for the
WebSocket relay, for one), so `--build` is not optional on `git pull`.

## 8. When something is wrong

| Symptom | First thing to check |
|---|---|
| Panel loads, never goes `LIVE` | The domain in `DJANGO_ALLOWED_HOSTS`. The socket's origin check reads that list, so a missing domain is a page that works and a channel that refuses. |
| Backend stays `unhealthy`, `frontend`/`caddy` never start | `DJANGO_SECURE_SSL_REDIRECT` is unset (so `true`, given `DEBUG=false`): the healthcheck's plain HTTP probe gets a 301. Set it `false` — it is pinned in the compose and `env.production.example`. |
| `502` from Caddy | `docker compose ps` — the backend is probably still migrating on first boot. `start_period` is 90s. |
| `400 DisallowedHost` in the backend log | Same list. The panel forwards the browser's Host as `X-Forwarded-Host`. |
| CSRF failures on the ticket | `CORS_ALLOWED_ORIGINS` must carry the exact `https://` origin — it seeds `CSRF_TRUSTED_ORIGINS`. |
| No prices anywhere, `market_feed: false` | Outbound. The §0 curl, then `MARKET_DATA_PROXY`. |
| Chart empty for a pair the picker offered | Under a pin the picker only offers the pinned venue's pairs. If you cleared the pin, a pair may exist on one venue and not the quoting one. |
| Halt flips in one tab, not another | `channel_layer_shared: false` — Redis is not reaching the backend. |
| Certificate never issues | DNS, then port 80 reachable from the internet. Caddy needs both. |

## 9. Security notes

- `.env` never enters git. This stack holds trade-enabled keys for real partner
  capital.
- Keys are encrypted at rest, never logged, and **never sent to a browser** —
  not even masked. If you can read a key in a response, that is a bug.
- Rotate `DJANGO_SECRET_KEY` by generating a new value and restarting the
  backend. Sessions are invalidated; everyone logs in again.
- Rotate `CREDENTIAL_ENCRYPTION_KEYS` by putting the new key **first** and
  keeping the old ones after it, comma separated, then restarting.
- If the domain or the VPS changes, update `SITE_DOMAIN`,
  `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` together.
- The live channel is staff-only and same-origin-only. A WebSocket handshake is
  exempt from CORS, so without the origin check any page the admin visited
  could open one with their session cookie attached and stream balances,
  positions and per-leg failures. Both guards are pinned by
  `backend/tests/test_consumer.py`. Do not relax either to "make the socket
  work" — an ungated socket hands out everything the staff-only REST endpoints
  withhold.
- The routing endpoints enforce CSRF. They authenticate by session cookie and
  fan a leveraged entry across every connected account, so an exempt POST is
  one any page the admin has open can make.
- `/api/health/` is unauthenticated by necessity (a container healthcheck has
  no session) and answers in booleans only — no versions, hostnames, settings
  or counts. Keep it that way; the moment it carries a value instead of a
  verdict it is reconnaissance.

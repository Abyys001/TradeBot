# Running the platform

Two paths. Use the script on this machine — snap Docker is broken here, see
below.

## Option A — `./run.sh` (no Docker)

```bash
./run.sh setup     # venv, dependencies, migrations, admin user  (once)
./run.sh demo      # optional: seed three paper accounts
./run.sh           # start backend :8000 and panel :3000
```

Open <http://localhost:3000> — Persian at <http://localhost:3000/fa>.
Ctrl-C stops both. Logs land in `.run/backend.log` and `.run/panel.log`.

Other commands:

| Command | What |
|---|---|
| `./run.sh backend` | backend only |
| `./run.sh panel` | panel only |
| `./run.sh stop` | stop whatever the script started |
| `BACKEND_PORT=8010 PANEL_PORT=3010 ./run.sh` | different ports |

Uses SQLite and an in-memory channel layer, so no Postgres or Redis is needed.

## Option B — Docker

```bash
cp .env.example .env
# set CREDENTIAL_ENCRYPTION_KEYS — the file explains how
docker compose up -d --build
docker compose exec backend python manage.py createsuperuser
```

Runs Postgres and Redis too. Panel :3000, API :8000.

---

## ⚠️ Snap Docker cannot stop its own containers (this machine)

`docker stop` / `restart` / `compose up --force-recreate` all fail with:

```
Error response from daemon: cannot stop container <id>: permission denied
```

The kernel audit log shows why:

```
apparmor="DENIED" operation="signal" profile="docker-default"
comm="dockerd" denied_mask="receive" signal=kill peer="snap.docker.dockerd"
```

The container runs under the `docker-default` AppArmor profile, which does not
allow it to *receive* signals from the snap-confined `dockerd`. So Docker cannot
kill a container it started. Nothing to do with this project.

### Unsticking a container now

`sudo` works because a root shell is not under the snap profile being denied:

```bash
sudo kill -9 $(docker inspect -f '{{.State.Pid}}' walletmanager_copytrader-backend-1)
docker rm -f walletmanager_copytrader-backend-1
```

If a half-created container is holding the name after a failed recreate, remove
it too — `docker ps -a` shows it with a hash-prefixed name like
`c909e283e930_walletmanager_copytrader-backend-1`.

### Fixing it properly

Replace snap Docker with the official Docker CE packages:

```bash
sudo snap remove docker
# then install Docker CE from Docker's apt repository
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # log out and back in
```

Until then, `./run.sh` avoids the problem entirely.

## Verifying a run is healthy

The check that matters most — order routing must refuse anonymous callers:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/trading/orders/open/ \
  -H 'Content-Type: application/json' -d '{"symbol":"BTCUSDT","side":"long","leverage":10}'
```

**401 is correct.** A 200 means the process is serving stale pre-auth code —
stop it and start again.

Then the panel: `/` terminal, `/risk` the Q5a calculator, `/accounts`,
`/history`, and `/fa` for Persian (the page should come back with
`<html lang="fa" dir="rtl">`).

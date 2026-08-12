# WalletManager_CopyTrader

Multi-account order-routing platform. The admin trades once through a single
interface; every action — entry, SL/TP adjustment, close — is mirrored via API to
every connected account across up to ~10 exchanges, within one second, with each
account fully isolated from the others.

> **Status:** working end to end — order routing, all 8 exchange adapters,
> live chart with draggable order lines, mark-to-market PnL, watchlist,
> emergency halt, per-account history, installable bilingual panel.
> Every section of the spec is implemented. 117 backend tests pass.
> **No adapter has been run against a live exchange yet** — see
> [`docs/adapters.md`](docs/adapters.md) before connecting real capital.

```bash
./run.sh setup   # once: dependencies, migrations, admin user
./run.sh         # panel :3000, API :8000
```

Docker also works (`docker compose up -d --build`), but snap-packaged Docker
cannot stop its own containers — see [`docs/running.md`](docs/running.md).

## Where things are

| Path | What |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Project init — architecture, invariants, build path. **Start here.** |
| `backend/` | Django 5 + DRF + Channels + async fan-out engine |
| `frontend/` | Nuxt 3 + TypeScript + Tailwind + Pinia, EN/FA |
| [`questions.md`](questions.md) | Decisions taken + what is still open (Q5, Q10, Q11, Q12) |
| [`docs/spec/platform-spec.md`](docs/spec/platform-spec.md) | Authoritative requirements |
| [`docs/exchanges/coverage.md`](docs/exchanges/coverage.md) | All 8 exchanges: build order, testnet, blockers |
| [`docs/running.md`](docs/running.md) | How to run it, and the snap-Docker gotcha |
| [`docs/adapters.md`](docs/adapters.md) | Per-exchange status, caveats, go-live checklist |
| [`docs/frontend/tradingview.md`](docs/frontend/tradingview.md) | Chart setup — Lightweight Charts now, Charting Library later |
| [`reference/`](reference/README.md) | Read-only exchange docs & SDKs, one folder per exchange |

## First run

```bash
./run.sh setup   # venv, dependencies, migrations, prompts for an admin user
./run.sh demo    # optional: three paper accounts ($10 / $50 / $100)
./run.sh         # start both
```

Open <http://localhost:3000> (Persian: `/fa`). The paper accounts let you drive
the whole fan-out with no credentials and no money. Full detail, including the
snap-Docker workaround, in [`docs/running.md`](docs/running.md).

## Next step

1. Answer Q5 + Q12 in `questions.md` (`/risk` in the panel shows the numbers).
2. Start the two lead-time items: the TradingView Charting Library application
   and the LBank futures docs request.
3. Run every adapter on testnet per `docs/adapters.md` before real capital.

## Security

This repo is designed to hold live, trade-enabled exchange credentials for real
partner capital. Keys are encrypted at rest and must be non-withdrawable. Never
commit `.env`, key material, or logs containing signed requests. See
`CLAUDE.md` § Invariants.

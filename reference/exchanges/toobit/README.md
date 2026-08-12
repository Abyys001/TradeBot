# Toobit API docs

Downloaded 2026-08-11 from https://api-docs.toobit.com/api/ (VitePress site,
27 English pages) and converted to Markdown. Source is the live site, not a git
repo — re-download to refresh.

## Index — `api/`

**Start here:** `basic-information.md` (auth, signing, rate limits, error format)

| File | Contents |
|---|---|
| `introduction.md`, `quick-start.md`, `products.md` | Overview |
| `basic-information.md` | **Real auth**: base `https://api.toobit.com`, `X-BB-APIKEY` header, HMAC SHA256 over `totalParams`, lowercase hex, parameter order must match signature order |
| `authentication.md` | ⚠️ **Ignore this file** — it is unedited VitePress boilerplate (`api.example.com`, `sk_live_…`, Bearer tokens). It does not describe Toobit. Use `basic-information.md`. |
| `spot-*.md` | Spot: account & trading, market data, wallet, websockets, error codes, v2 API |
| `usdt-m-*.md` | USDT-M futures: account & trading, market data, websockets, error codes, v2 API |
| `copy-trading-leader.md`, `copy-trading-follower.md`, `copy-trading-example.md` | Copy-trading OpenAPI (`/api/v2/copy-trading/…`, requires `COPY_TRADING` account-type API key) |
| `code-examples.md`, `spot-example.md`, `usdt-m-example.md` | Signing + request examples |
| `agent.md`, `users.md`, `changelog.md` | Agent/broker, user mgmt, changelog |

## Notes for integration

- Auth is Binance-style (HMAC SHA256, `X-BB-APIKEY`), so the Binance adapter
  shape mostly transfers.
- Native SL/TP: `takeProfit` / `stopLoss` params accepted at order entry;
  separate `STOP_PROFIT_LOSS` order types exist for post-entry management.
- Leverage: `POST /api/v1/futures/leverage`.
- **No testnet found** in these docs. Per spec §9 handling, Toobit is expected
  to be flagged in the panel as "no test environment".
- The copy-trading endpoints are Toobit's *own* leader/follower product. This
  platform does **not** use them — we fan out independent orders per account.
  They are kept because they may be a cheaper path for Toobit specifically;
  decide per `questions.md`.

# Reference material (read-only)

Third-party exchange documentation and SDKs, vendored for offline lookup.
**Nothing here is imported by application code.** It exists so integration work
can consult the real API contracts without network access.

| Path | Exchange | What it is | Upstream |
|---|---|---|---|
| `exchanges/binance/rest-docs/` | Binance | Official Markdown API docs (REST, WS streams, user data stream, errors) | `binance-exchange/binance-official-api-docs` |
| `exchanges/bybit/v5-docs/` | Bybit | Official V5 docs site (Docusaurus source; content under `docs/v5/`) | `bybit-exchange/docs` |
| `exchanges/bybit/ai-trading-skill/` | Bybit | Bybit "AI Trading Skill" — endpoint cheatsheets per domain under `modules/` | `bybit-exchange/skills` |
| `exchanges/bybit/bybit.pdf` | Bybit | PDF export (provenance unknown — see `questions.md` Q6) | — |
| `exchanges/gateio/python-sdk/` | Gate.io | Official generated Python SDK, `gate-api` v7.1.8 (APIv4) | `gateio/gateapi-python` |
| `exchanges/kucoin/api-docs/` | KuCoin | Official API docs (Slate source under `source/`) | `Kucoin/kucoin-api-docs` |
| `exchanges/okx/ts-sdk/` | OKX | **Community** TypeScript SDK `okx-api` v3.2.1 + `llms.txt` API index | `tiagosiebler/okx-api` |
| `exchanges/hyperliquid/README.md` | Hyperliquid | Integration notes (auth, nonces, rate limits, TP/SL) — live docs via the `hyperliquid-docs` MCP server | hyperliquid.gitbook.io |
| `exchanges/lbank/api/` | LBank | Spot docs (complete) + contract docs (**public endpoints only** — see that folder's README) | www.lbank.com/docs/ |
| `exchanges/toobit/api/` | Toobit | 27 pages: spot, USDT-M futures, websockets, copy-trading | api-docs.toobit.com |
| `skills/frontend-design.SKILL.md` | — | The `frontend-design` skill — **design authority for the panel UI** (Q7) | — |

The LBank, Toobit, and Hyperliquid entries were downloaded and converted
2026-08-11 from live doc sites (no upstream git repo exists for them). Re-run the
download to refresh; each folder's README records its source URLs.

## Rules

- Treat everything under `reference/` as immutable. Do not edit, lint, format,
  or refactor it. Do not run its build scripts.
- Do not add these SDKs as project dependencies by copy-paste. If a vendored
  SDK (e.g. Gate.io Python) is actually wanted at runtime, install it from
  PyPI/npm and pin the version.
- Sizes are large (~48 MB total). Build artifacts inside it are gitignored.

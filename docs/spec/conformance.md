# Spec conformance — clause by clause

Every requirement in [`platform-spec.md`](platform-spec.md), where it is
implemented, and what proves it. Written so the claim "the spec is implemented"
can be *checked* rather than taken on faith.

Status key: **✅ done** · **⚠️ done, with a caveat you must read** · **➖ not required for v1**

Test commands: `cd backend && .venv/bin/python -m pytest` (119 tests) ·
`npx nuxi typecheck` · `npm run build` in `frontend/`.

---

## §2 Core architecture

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Up to ~10 exchanges | `apps/exchanges/registry.py` — 8 live adapters + paper | `tests/test_adapters.py` | ⚠️ built from vendored docs; **none run against a live exchange yet** (`docs/adapters.md`) |
| Multiple isolated accounts per exchange | `registry.build_adapter()` returns a fresh adapter, HTTP client and rate limiter per account | `tests/test_fanout.py` isolation cases | ✅ |
| One account's failure/rate limit never affects another | `apps/engine/fanout.py` — per-leg task, per-leg deadline, failure returned as data | `test_a_failing_account_is_recorded_and_notified_not_swallowed` | ✅ |
| Spot **and** futures | `sizing.size_order(market=...)` ignores leverage on spot; executor skips `set_leverage` | `tests/test_sizing.py` | ✅ |
| Admin's own account uses the same path | It is just another `ConnectedAccount`; no admin-only branch exists | — | ✅ |

## §3 Manual trading interface

| Requirement | Where | Status |
|---|---|---|
| Chart connected to TradingView | `composables/useChartAdapter.ts` — TradingView **Lightweight Charts** | ⚠️ Charting Library swaps in behind the same seam once TradingView grants access (`docs/frontend/tradingview.md`) |
| Market and limit orders | `components/terminal/Ticket.vue`, `order_views.open_position` | ✅ |
| Leverage 1–10x | `MIN_LEVERAGE`/`MAX_LEVERAGE`, slider in the ticket, validated server-side | ✅ |
| SL/TP set at order entry | `Ticket.vue` + presets | ✅ |
| SL/TP editable — (1) order entry | `Ticket.vue` | ✅ |
| SL/TP editable — (2) from the chart | `useChartAdapter` draggable lines; chart pan frozen during a drag, 14px grab band (28px touch) | ✅ |
| SL/TP editable — (3) position row under the chart | `components/terminal/PositionBar.vue` | ✅ |
| …all three agree | All three write `stores/order.ts`; one write path, one fan-out | ✅ |
| Positions panel: entry, liquidation, PnL, size, details | `PositionBar.vue` (aggregate) + `PositionsTable.vue` (per account). PnL computed server-side in Decimal by `/trading/positions/` | `test_positions_endpoint_marks_each_leg_to_market` ✅ |
| Close Position button, market, immediate | `PositionBar.vue` → `route_close` | ✅ |

Beyond the spec: the limit order's entry line is draggable too, and changing
pair or timeframe resets the view to the newest candle.

## §4 Execution & fan-out

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Identical leverage and SL/TP % on every account | One `TradeIntent` per fan-out; only sizing is per account | `test_open_persists_a_leg_per_account` (same leverage, 990/4950 margins) | ✅ |
| Mid-trade change propagates ≤ 1s | `fan_out(timeout=FANOUT_TIMEOUT_SECONDS)`, `route_amend` | `test_the_fanout_duration_is_recorded_for_audit` | ✅ |
| Entry dispatched to all accounts within ~1s | Single `asyncio.gather`, factories so nothing starts early | `tests/test_fanout.py` timing assertions | ✅ |
| Independent failure handling | `_run_leg` never raises; `return_exceptions=True` as a backstop | ✅ | ✅ |
| Failed-order notification, persistent, ~190×110, no auto-expire | `Notification` model + `components/app/NotificationCenter.vue` | `test_a_failing_account_is_recorded_and_notified_not_swallowed` | ⚠️ **amended**: moved from a docked card into the top bar because it covered the chart. Nothing auto-expires; dismissal is server-side. See `questions.md` Q16 |

## §5 Position sizing

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| 99% of available balance | `sizing.balance_fraction()` (`BALANCE_FRACTION=0.99`) | `tests/test_sizing.py`, margins 990/4950 | ✅ |
| Round down, never up; below minimum → skip with a notice | `floor_to_step`, `SizingRejection` | `tests/test_sizing.py` | ✅ |
| One open trade per account at a time | `eligible_accounts()` excludes accounts holding a filled, unclosed leg | `test_an_account_already_in_a_trade_sits_the_next_one_out` | ✅ |
| Identical leverage/SL%/TP%, only dollar size differs | As §4 | ✅ | ✅ |

## §6 Account management

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Admin adds each account manually | `components/accounts/ConnectForm.vue` → `ConnectedAccountViewSet.create` | ✅ | ✅ |
| Add button | `pages/accounts.vue` | ✅ | ✅ |
| Per-account Pause / Resume / Delete icons | `pages/accounts.vue`, colour-coded (amber / green / red) | ✅ | ✅ |
| No account joins a trade already in progress | `eligible_from` vs `trade.opened_at` | `test_an_account_connected_after_the_trade_does_not_join_it` | ✅ |
| A reconnected account waits for the next trade | `resume` sets `eligible_from = now` | `test_paused_accounts_are_excluded` | ✅ |
| Its existing exchange position is left as-is | Nothing force-closes on pause or delete | — | ✅ |
| Balance of every account visible **at all times** | 45s background refresh (`stores/accounts.ts`), rate-limited server-side, pushed to every panel over the WebSocket; stale figures marked amber | `test_balance_refresh_covers_paused_accounts`, `test_background_refresh_is_rate_limited_but_still_answers` | ✅ |

## §7 Security

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Keys must be non-withdrawable | `verify_credentials()` per adapter; a withdrawable key is **refused and the row deleted** (`accounts/views.py`) | `tests/test_adapters.py` | ⚠️ where an exchange exposes no permission endpoint the account is flagged "unverified" in the panel rather than silently passed. Hyperliquid agent-wallet rights still unverified (Q11) |
| Keys encrypted at rest, never in responses | `apps/core/crypto.py` (Fernet + rotation); serializers never expose them | `tests/test_crypto.py` | ✅ |
| Security first-class | Staff-gated routing endpoints, CSRF, no secrets in logs | `tests/test_auth.py` | ✅ |
| Emergency "stop all" | `apps/trading/killswitch.py`, `components/app/StopAll.vue` in every top bar | `tests/test_killswitch.py` (8 cases) | ✅ env pin cannot be cleared from the panel; closing still works while halted |

## §8 Trade history

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Per-account log: pair, date/time, PnL | `TradeLeg` + `pages/history.vue` with an account filter (`?account=`) | `test_close_records_pnl_per_account` | ✅ |

## §9 Testing

| Requirement | Where | Status |
|---|---|---|
| Demo/test mode exercising the full platform | `apps/exchanges/paper.py`, selectable as an exchange; `./run.sh demo` creates three paper accounts ($10 / $50 / $100) | ✅ |
| Per-exchange testnet honesty | `Capabilities.has_testnet` surfaced in Settings; no fake testnet toggle (Q9) | ✅ |

## §10 Open items

| Item | Resolution |
|---|---|
| Exact UI/UX layout | Built; responsive down to 320px, RTL-capable, installable (Q17) |
| Notification behaviour for **successful** trades | Transient toasts (`components/app/Toasts.vue`) — deliberately unlike failures, which never expire |
| Self-service partner onboarding | ➖ explicitly not required for v1 |
| Exchange-by-exchange API specifics | `docs/exchanges/coverage.md`, `docs/adapters.md`; LBank futures impossible (Q10) |

## §11 Legal note

Not a build requirement. Surfaced in the panel's Settings page rather than left
in a markdown file, because the person operating this should meet that sentence
before connecting real partner capital.

---

## What is genuinely not done

1. **No adapter has been run against a live exchange or testnet.** Every real
   adapter is unit-tested against a mocked transport. Do a testnet run before
   any real capital.
2. **LBank futures** cannot be implemented from public documentation; the
   adapter raises `NotSupported` rather than guessing (Q10).
3. **Hyperliquid agent-wallet withdrawal rights** unverified (Q11).
4. **TradingView Charting Library** pending their approval; Lightweight Charts
   is in place behind the same seam.
5. **Market data reachability** depends on the deployment's egress. Where no
   provider is reachable the panel serves labelled synthetic candles, and a
   synthetic price is never used to size an order (Q13).

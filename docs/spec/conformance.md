# Spec conformance — clause by clause

Every requirement in [`platform-spec.md`](platform-spec.md), where it is
implemented, and what proves it. Written so the claim "the spec is implemented"
can be *checked* rather than taken on faith.

Status key: **✅ done** · **⚠️ done, with a caveat you must read** · **➖ not required for v1**

Test commands: `cd backend && .venv/bin/python -m pytest` (183 tests) ·
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
| Hyperliquid sends the protection **with** the entry | `HyperliquidAdapter.place_order` builds the entry and both reduce-only triggers as one `bulk_orders` action under the `normalTpsl` grouping, so `native_sltp_on_entry` is now True for it. Attaching afterwards was a second signed round trip with a live leveraged position in between. `get_sltp` reads the flat `frontendOpenOrders` shape (it was parsing a nested one the API never sends, so placed protection read back as absent) and counts children riding on an unfilled parent | `test_hyperliquid_sends_the_entry_and_its_protection_in_one_action`, `test_hyperliquid_reads_back_protection_in_the_shape_the_api_returns`, `test_hyperliquid_counts_protection_riding_on_an_unfilled_entry` | ✅ doc-vs-code; still unrun against a live venue |
| SL/TP are **mandatory** on every entry and every amend, and are sent to the exchange | `order_views._percent` (400 without either), `executor._require_protection` (no account is touched), then real trigger prices per account: on the entry order where the venue accepts them (`native_sltp_on_entry`), placed and read back immediately after the fill where it does not (`executor._protect`) | `test_an_order_without_protection_is_refused`, `test_an_amend_without_protection_is_refused`, `test_an_intent_without_protection_never_reaches_an_exchange`, `test_paper_read_back_confirms_sl_and_tp_on_entry` | ✅ |
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
| Identical leverage and SL/TP % on every account | One `TradeIntent` per fan-out; only sizing is per account. An account whose exchange caps leverage below the admin's number **sits the trade out** (`executor._open_one`, code `leverage_capped`) instead of being silently clamped to a different leverage | `test_open_persists_a_leg_per_account`, `test_an_account_capped_below_the_asked_leverage_sits_out` | ✅ |
| Mid-trade change propagates ≤ 4s (Q19) | `fan_out(timeout=FANOUT_TIMEOUT_SECONDS)`, `route_amend` | `test_the_fanout_duration_is_recorded_for_audit` | ⚠️ **amended**: the 1s cap became `FANOUT_TIMEOUT_SECONDS` (default 10.0, via 4.0/3.0/5.0) after VPS round trips blew it on healthy orders. See `questions.md` Q19 |
| A mid-trade change replaces the old SL/TP rather than adding to it | Q5d strategy in `executor.apply_sltp`: snapshot `list_conditional_orders`, place, then `cancel_orders`. Only Bybit and paper amend in place; the other six place conditional orders and are cancelled around | `test_an_amend_leaves_exactly_one_pair_of_stops_alive`, `test_place_then_cancel_places_before_it_cancels`, `test_cancel_then_place_is_a_real_branch_not_dead_config` | ✅ `SLTP_AMEND_STRATEGY` is live config, both branches tested |
| Entry dispatched to all accounts within the configured deadline (Q19) | Single `asyncio.gather`, factories so nothing starts early; per-leg round trips fire together in `_open_one`; adapters kept warm between actions | `tests/test_fanout.py` timing assertions | ⚠️ **amended**: was ~1s; now `FANOUT_TIMEOUT_SECONDS` (default 10.0) — see Q19 |
| Independent failure handling | `_run_leg` never raises; `return_exceptions=True` as a backstop | ✅ | ✅ |
| A leg that fails after its order went out is re-read, not written off | `executor._reconcile*` runs for every `LegResult.unconfirmed` leg — anything whose code is not in `fanout.NEVER_SENT_CODES`, not just the deadline. A confirmed position is a `late_fill` | `test_a_timed_out_entry_that_filled_is_a_late_fill_not_a_failure`, `test_an_entry_that_failed_short_of_the_deadline_is_still_re_read` | ✅ Q19 |
| "The exchange holds nothing" and "the exchange will not answer" are different outcomes | `_reconcile_open` returns `not_filled` only on an affirmative empty answer to a market order; an unanswerable re-read keeps the failure and appends an explicit *not known* warning | `test_an_entry_the_exchange_holds_nothing_for_is_recorded_as_not_filled`, `test_a_leg_the_exchange_will_not_answer_says_it_is_unknown` | ✅ Q19 |
| A fill confirmed after the response is gone still becomes a position | `services.reconcile_open_trade()` off the positions poll, rate-limited; an unconfirmed account is not offered a new trade until it settles | `test_an_unconfirmed_leg_becomes_a_real_position_on_the_next_poll`, `test_an_unconfirmed_account_cannot_be_given_a_second_position` | ✅ Q19 |
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
| No account joins a trade already in progress | For an open trade, `eligible_accounts(trade)` returns the accounts **holding a filled, unclosed leg of it** — an account that connected or resumed later has no leg, so it cannot join | `test_an_account_connected_after_the_trade_does_not_join_it`, `test_an_account_connected_after_the_trade_still_cannot_join_an_amend` | ✅ |
| A reconnected account waits for the next trade | `resume` sets `eligible_from = now` | `test_paused_accounts_are_excluded` | ✅ |
| Its existing exchange position is left as-is | Nothing force-closes on pause or delete. Pause stops *new* orders only: an account still holding a leg stays in the amend/close fan-out, so its position can always be re-protected or flattened through the platform | `test_pausing_an_account_does_not_strand_its_open_position` | ✅ |
| Balance of every account visible **at all times** | 45s background refresh (`stores/accounts.ts`), rate-limited server-side, pushed to every panel over the WebSocket; stale figures marked amber | `test_balance_refresh_covers_paused_accounts`, `test_background_refresh_is_rate_limited_but_still_answers` | ✅ |

## §7 Security

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Keys must be non-withdrawable | `verify_credentials()` per adapter; a withdrawable key is **refused and the row deleted** (`accounts/views.py`). Re-checked on `verify` **and on `resume`** — a key that gained withdrawal rights while paused does not come back. `ConnectedAccount.clean()` refuses to activate an account whose check never ran (`withdrawal_checked_at`) | `tests/test_adapters.py`, `tests/test_accounts_api.py` | ⚠️ only Bybit, OKX, Binance and KuCoin publish key permissions; on the other four the adapter raises `NotSupported` after proving the key authenticates, so the account connects **paused and flagged "withdrawal unverified"** rather than silently passed — one Resume click activates it, on the admin's word that they checked the exchange dashboard. Binance and KuCoin keep that endpoint on their **spot** host, so a futures-only Binance key cannot reach it and is flagged, not refused. Hyperliquid agent-wallet rights still unverified (Q11) |
| Keys encrypted at rest, never in responses | `apps/core/crypto.py` (Fernet + rotation); serializers never expose them | `tests/test_crypto.py` | ✅ |
| Security first-class | Staff-gated routing endpoints, CSRF, no secrets in logs | `tests/test_auth.py` | ✅ |
| Close closes **every** open trade | `services.route_close_all` behind `POST /orders/close-all/` — the panel's close button. More than one trade can be open (accounts freed by a close take the next entry), and the per-id close left those live on the exchange while the panel read flat. `/positions/` also reports `other_open_trades` so a trade this panel does not draw is still visible | `test_close_all_closes_every_open_trade_not_just_the_newest`, `test_the_close_all_endpoint_closes_every_open_trade` | ✅ |
| Emergency "stop all" | `apps/trading/killswitch.py`, `components/app/StopAll.vue` in every top bar | `tests/test_killswitch.py` (10 cases) | ✅ env pin cannot be cleared from the panel; **both** closing *and* amending SL/TP keep working while halted (Q14), each with a test |

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
| Exchange-by-exchange API specifics | `docs/exchanges/coverage.md`, `docs/adapters.md`; LBank futures impossible (Q10) — LBank **spot** is a full round trip: buy, and `close_position` sells back at market |

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
5. **The symbol picker is a curated list of ten**, not the exchanges' own
   catalogues (`trading.market_views.SYMBOLS`), and the chart is served live on
   every request with no stored history. `ExchangeSymbol`, `StoredCandle` and
   `MarketDataSync` in `trading/models.py` are the tables shaped for that
   feature; **no code reads or writes them yet**, and their docstrings say so.
   Neither the catalogue nor stored history is a spec §3 requirement.
6. **Market data reachability** depends on the deployment's egress. Where no
   provider is reachable the API returns 503 and the panel shows an explicit
   "no price feed" state — there is no synthetic series, and with no price
   nothing sizes an order (Q13, amended 13 Aug 2026).

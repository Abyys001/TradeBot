# Gap analysis — WalletManager_CopyTrader

Audit against `docs/spec/platform-spec.md` (§1–§11), and the record of what was
done about it. **Every gap this audit found (G1–G10) is now closed** — the
original findings are kept below with the fix and the test that holds each one
shut, because "it was never broken" and "it was broken and is now covered" are
different states and the second one is worth being able to see.

Audit date: **Thu Aug 13 2026** · Fixes landed: **Thu Aug 13 2026**
Audit basis: `docs/spec/platform-spec.md`, `docs/spec/conformance.md`,
`questions.md` (Q1–Q17), full backend (`backend/apps/*` + `backend/tests/*`),
full frontend (`frontend/stores|components|pages|composables|layouts|middleware|server`).

Status key: **✅ conforms** · **⚠️ done but with a caveat** · **❌ non-conformant / bug**
· **🔶 not required for v1**.

## 1. Clause-by-clause status

| Spec | Requirement | Verdict | Evidence |
|---|---|---|---|
| §2 | Up to ~10 exchanges | ✅ 8 live + paper | `registry.py`, `docs/adapters.md` ⚠️ none live-tested (documented) |
| §2 | Multiple isolated accounts per exchange | ✅ fresh adapter/client/limiter per account | `registry.build_adapter` |
| §2 | One failure never blocks another | ✅ per-leg task + deadline, failures as data | `fanout.py` |
| §2 | Spot **and** futures | ✅ | `sizing.size_order`, executor skips `set_leverage` on spot |
| §2 | Admin uses same path as partners | ✅ admin is a `ConnectedAccount` | `accounts/models.py` |
| §3 | Chart (TradingView) | ⚠️ Lightweight Charts now, Charting Library later | `useChartAdapter.ts`, `docs/frontend/tradingview.md` |
| §3 | Market + limit orders | ✅ | `Ticket.vue`, `order_views.open_position` |
| §3 | Leverage 1–10x | ✅ | slider + `MIN/MAX_LEVERAGE`, server-validated |
| §3 | SL/TP at entry + editable from 3 places | ✅ single write path `stores/order.ts` | `order.ts`, `useChartAdapter` drag, `PositionBar.vue` |
| §3 | Positions panel + Close button | ✅ PnL server-side Decimal | `market_views.positions`, `PositionBar.vue` |
| §4 | Identical leverage & SL/TP % | ✅ **fixed (G6)** — an account capped below the asked leverage sits out instead of trading a different one; **fixed (G2)** — an amend replaces the old stops instead of stacking | `executor._open_one`, `executor.apply_sltp` |
| §4 | Mid-trade change within the deadline | ✅ **fixed (G1)** — amend works while halted. ⚠️ **amended in use (Q19)** — the 1s cap is now `FANOUT_TIMEOUT_SECONDS` (default 3.0, was briefly 4.0) after VPS round trips blew it on healthy orders; adapters are kept warm between actions | `executor.amend_sltp`, `test_sltp_can_still_be_amended_while_halted` |
| §4 | Entry fan-out within the deadline | ✅ ⚠️ **amended in use (Q19)** — same deadline change; legs now fire balance/leverage/rules round trips concurrently | `test_fanout.py` timing assertions |
| §4 | Independent failure handling | ✅ | `fanout._run_leg`, `return_exceptions=True` |
| §4 | Persistent failure notification, no auto-expire | ✅ **amended in use (Q16)**; **fixed (G7)** — a failed entry is no longer re-notified on every later action | `NotificationCenter.vue`, `test_an_account_that_never_entered_is_not_asked_to_close` |
| §5 | 99% margin, round down, skip below min | ✅ | `sizing.py`, `tests/test_sizing.py` |
| §5 | One open trade per account | ✅ | `services.accounts_in_open_trades` |
| §6 | Manual add / pause / resume / delete | ✅ **fixed (G4)** — pausing no longer strands an open position | `services.eligible_accounts`, `test_pausing_an_account_does_not_strand_its_open_position` |
| §6 | No joining a trade in progress; resume waits | ✅ now leg-based rather than clock-based | `test_an_account_connected_after_the_trade_still_cannot_join_an_amend` |
| §6 | Balance of every account at all times | ✅ 45s refresh, WS push, stale marked | `stores/accounts.ts` |
| §7 | Keys non-withdrawable, refuse if not | ✅ **fixed (G3)** — Binance's check reaches the spot host, so the refusal can fire; **fixed (G5)** — `resume` re-verifies and `clean()` gates on a check having run. ⚠️ Q11 Hyperliquid unverified (documented) | `binance_family.py`, `accounts/views.py`, `tests/test_accounts_api.py` |
| §7 | Keys encrypted at rest, never exposed | ✅ Fernet + rotation | `core/crypto.py`, serializers |
| §7 | Kill switch | ✅ close **and** amend work while halted, both tested | `test_killswitch.py` |
| §8 | Per-account history: pair, time, PnL | ✅ | `history.vue`, `_persist_close` PnL calc |
| §9 | Demo mode | ✅ paper adapter + `./run.sh demo` | `paper.py` |
| §10 | Open items | 🔶 self-service onboarding not required | |
| §11 | Legal note | 🔶 surfaced in Settings | `pages/settings.vue` |

Counts: **✅ ~24 · ⚠️ 2 (chart library, adapters not live-tested — both external) · ❌ 0 · 🔶 2**.

## 2. ❌ Gaps found, and how each was closed

### G1 — Kill switch blocked SL/TP amend → 500 · **fixed**

**Was:** `route_amend` → `amend_sltp` → `fan_out(...)` without
`respect_stop_all=False`, so the halt raised `StopAllActive` out of an endpoint
that catches nothing — HTTP 500 with a traceback, at the exact moment the admin
is trying to tighten a stop. This contradicted Q14, the `trading/views.py`
docstring and `StopAll.vue`'s own copy.

**Fix:** `amend_sltp` fans out with `respect_stop_all=False`, mirroring
`close_trade`; the docstring says why. Tests:
`test_stop_all_never_blocks_an_amend_either` (engine),
`test_sltp_can_still_be_amended_while_halted` (service),
`test_the_amend_endpoint_answers_while_halted` (HTTP 200, since 500 was the
actual symptom).

### G2 — `SLTP_AMEND_STRATEGY` was dead config; amends stacked conditional orders · **fixed**

**Was:** the setting was read nowhere; no adapter had a cancel method. Every
`set_sltp` on the six exchanges without in-place amend simply placed *another*
pair of reduce-only conditional orders. After the first SL/TP change the
position carried multiple live stops, and whichever triggered first won —
possibly at the price the admin had just replaced. OKX declared
`native_sltp_amend=True` while never calling `amend-algos`.

**Fix:** Q5d now lives in one place, `engine/executor.apply_sltp`, next to Q5e's
`_protect`:

1. snapshot the live protection with `adapter.list_conditional_orders(symbol)`,
2. place the new pair (`place_then_cancel`) or cancel first
   (`cancel_then_place`) — the setting picks, and both branches are tested,
3. cancel exactly the snapshot, so the orders just placed are never in it.

Two optional methods were added to the adapter seam
(`list_conditional_orders` / `cancel_orders`, both no-ops by default) and
implemented for Binance/Toobit, OKX, KuCoin, Gate.io and Hyperliquid; each
filters to *this platform's* protection orders so a partner's hand-placed
working order is never cancelled, and each tolerates an order that triggered
between snapshot and cancel. OKX's capability flag now says `False`, which is
what its code actually does. Endpoints per exchange are listed in
`docs/adapters.md`.

Tests: `test_an_amend_leaves_exactly_one_pair_of_stops_alive`,
`test_place_then_cancel_places_before_it_cancels`,
`test_cancel_then_place_is_a_real_branch_not_dead_config`,
`test_an_exchange_that_amends_in_place_is_left_alone`,
`test_the_first_attach_after_entry_also_clears_a_half_placed_pair`, plus
per-adapter list/cancel tests in `test_adapters.py`.

### G3 — Binance `verify_credentials` always failed · **fixed**

**Was:** `/sapi/v1/account/apiRestrictions` exists only on the spot host, but the
adapter's single client is bound to `fapi.binance.com`, so the request 4xx'd
every time → `AuthError` → every Binance account connected PAUSED and the §7
withdrawal refusal could never fire for Binance.

**Fix:** the permission call is made with an absolute URL to `api.binance.com`
(httpx ignores `base_url` for absolute URLs). A key with no spot access raises
`NotSupported` — "we cannot know", which flags the account — rather than
`AuthError`, which would claim the credential is broken; `verify_credentials`
now re-raises `NotSupported` instead of wrapping it, which also un-deadened
Toobit's careful message. The futures testnet has no `/sapi`, and says so.
`rest._handle` now carries the exchange's own error text on 401/403, because
"invalid key" and "this key lacks that permission" are the same status code.

Tests: `test_binance_asks_the_spot_host_for_key_permissions`,
`test_binance_refuses_a_withdrawable_key`,
`test_binance_says_so_when_the_key_cannot_reach_the_spot_host`,
`test_binance_testnet_does_not_pretend_to_check_permissions`.

### G4 — Pausing an account stranded its open position · **fixed**

**Was:** `pause` flipped the status, `eligible_accounts(trade)` filtered on
ACTIVE, and a resume moved `eligible_from` past the trade — so an open position
on a paused account could never be closed or re-protected through the platform.

**Fix:** for an open trade, eligibility is no longer "who is active" but **"who
holds a filled, unclosed leg of this trade"**. Pause still stops new orders;
flattening or re-protecting what is already live at leverage is a protection
action, like closing while halted. Spec §6's "no joining in progress" comes free
— an account that connected later has no leg to hold.

Test: `test_pausing_an_account_does_not_strand_its_open_position`.

### G5 — `resume()` never re-verified; `models.clean()` was dormant · **fixed**

**Was:** resume set ACTIVE without re-running `verify_account`, and `clean()`
was never called by any path. Worse, `clean()` as written demanded
`withdrawal_check_passed` — which five of the eight exchanges can never produce,
so calling it would have banned them.

**Fix:** a `withdrawal_checked_at` timestamp records *that the check ran*,
separately from its verdict. `clean()` now refuses to activate a non-paper
account whose check never ran, and `perform_create`/`resume` call `full_clean()`.
`resume` re-runs `verify_account`: proven withdrawable → refused, account stays
paused with the reason; unprovable → resumes flagged, which is what §7 actually
asks for. Migration `accounts/0002_connectedaccount_withdrawal_checked_at`.

Found while fixing this, and fixed with it: **KuCoin does publish key
permissions** (`GET /api/v1/user/api-key`, on the spot host — see the vendored
`reference/exchanges/kucoin/universal-sdk`). It was listed as "no permission
endpoint"; it now refuses a key carrying `Transfer`, taking §7's provable set
from three exchanges to four.

Tests: `tests/test_accounts_api.py` (6 cases).

## 3. ⚠️ Caveats that were raised, and what happened to them

- **G6 — silent leverage clamp vs §4 "identical leverage". Fixed.** The clamp is
  gone: an account whose exchange or symbol caps leverage below the admin's
  number now fails its leg with code `leverage_capped` and a persistent
  notification — the spec §5 treatment of an account that cannot comply. Trading
  one partner at 5x while the rest run at 10x is a different position for the
  same signal, and doing it silently is the part that made it a bug. The related
  mismatch is fixed too: an amend now computes margin from the exchange's own
  reported `position.leverage`, not the trade's requested number.
- **G7 — failed-entry legs re-fanned on amend/close. Fixed** by the same
  leg-based eligibility as G4: an account whose entry failed is never asked to
  close a position it never opened, so it stops minting a fresh persistent
  notification on every action. Test:
  `test_an_account_that_never_entered_is_not_asked_to_close`.
- **G8 — LBank spot was one-way. Fixed.** `close_position` sells the holding
  back at market instead of raising `NotSupported`, so the Q5e policy can
  actually flatten a spot leg. Found and fixed alongside it: the market **buy**
  was sending a base quantity where LBank documents a quote amount, which would
  have bought the wrong size. Remaining caveat, now documented in
  `questions.md` Q10 and `docs/adapters.md`: spot still has no SL/TP, so a spot
  leg with SL/TP set buys and immediately sells back under the default policy.
- **G9 — `sltp.py` docstring drift. Fixed.** It said liquidation sits ~1% away;
  it is 1/leverage, so 10% at 10x. The docstring now carries the correction and
  points at the test that asserts the numbers.
- **G10 — `conformance.md` overclaims. Fixed.** The §4 leverage row, the §4
  amend row (new), the §6 pause and mid-trade rows, and the §7 key and
  stop-all rows now say what the code does, with the tests that prove it.

## 4. What genuinely conforms (spot-checked this audit)

- Fan-out isolation, per-leg deadlines, failure-as-data (`fanout.py`); close
  **and amend** while halted, both tested; env-pinned `STOP_ALL` cannot be
  cleared from the panel; DB-down resolves to halted.
- One order store → three SL/TP surfaces cannot disagree (§3); chart drag
  converts to % off the admin's entry (Q5c) and can't disagree with the ticket.
- Sizing: 99% margin, floor to step, skip below minimum, spot ignores leverage,
  non-USDT surfaced not traded (Q4/Q12).
- PnL server-side in Decimal, synthetic prices labelled and never used for
  sizing (Q13).
- Q16 notification-centre amendment is recorded in the spec itself; nothing
  auto-expires; dismissal is server-side.
- Test suite: **162 pass**, `ruff` clean.

## 5. What is still open — and it is all external

None of these is a code gap; each needs something from outside the repo.

1. **No adapter has run against a live exchange or testnet** (`docs/adapters.md`
   has the checklist). The Q5d cancel paths are the newest code here and the
   first thing to check on testnet: amend twice, count the open orders, expect
   one stop and one take-profit.
2. **LBank futures** (Q10) — needs LBank to publish or send private docs.
3. **Hyperliquid agent-wallet withdrawal rights** (Q11) — needs a testnet check.
4. **TradingView Charting Library** — needs their approval.

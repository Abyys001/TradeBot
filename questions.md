# Questions & decisions — open

**Three are open: Q29, Q31 and Q32.** (Q30 was raised and answered in the same
pass; it is kept here rather than in `docs/decisions.md` only until the next
tidy.) Everything else this project has raised is answered and
recorded in **`docs/decisions.md`** (Q1–Q28), with the reasoning and the setting
or module that implements each. Code comments and `docs/spec/conformance.md`
cite them by number; the numbering is shared, so a Q-number means the same
decision wherever it appears.

Q11 and Q28 were answered by the admin on 2026-08-23, alongside bot mode's
Q20–Q27, and the spec §11 legal item is closed — the activity has been signed
off by a lawyer, and this repository is a technical one.

---

## Q29. Where do the `ta.*` golden values come from?

**Raised 2026-08-23, writing `docs/bot-plan.md`. Blocks Phase 2's fixture, not
its implementation.**

`docs/bot-mode.md` §2.3 requires every indicator in the v1 subset — `sma`,
`ema`, `rma`, `rsi`, `atr`, `macd`, `bb`, `stoch`, `cci`, `linreg`, the rest —
to be pinned by a golden test against a fixed BTCUSDT 1h window, to 8 decimal
places, and calls it "the only way to know you are right".

The trap it exists to catch is real and narrow: TradingView's `ta.rma` seeds the
first period with a simple average and only then goes recursive, so an RSI built
from the textbook recurrence is off by a few tenths **forever**. A few tenths is
enough to flip a `crossover`, and a flipped crossover is a trade that should not
have happened, at 99% of every partner's balance, once per bar.

The question is where the reference numbers come from, and the two answers are
not equivalent:

1. **Exported from TradingView by hand.** One sitting at a keyboard, one chart,
   one export per indicator, committed to `backend/tests/fixtures/pine/golden/`.
   This is an independent oracle — it can disagree with our implementation,
   which is the entire point of a golden test.
2. **Computed from the published Pine reference formulas and reviewed.** No
   admin time, and it does pin *regressions*. But it cannot catch a
   misunderstanding of the formula, because the same misunderstanding produces
   both the fixture and the code. That is exactly the weakness a golden test is
   supposed to remove.

The recommendation is (1) for the seeded family specifically — `rma`, `rsi`,
`atr`, and anything built on them — where the failure is silent and permanent,
and (2) for the arithmetically unambiguous ones (`sma`, `stdev`, `highest`,
`change`), whose formula has no room for a seeding choice. That is a small,
bounded ask: roughly six exports rather than thirty.

**Buildable meanwhile, and not waiting on this:** every indicator's incremental
`update()` implementation, its `na` warm-up behaviour, the per-call-site keying,
and the determinism test. Only the numbers the tests compare against are blocked.

---

## Q30. How does a script spell a percent exit?

**Raised 2026-08-25, implementing Phase 1. Answered in code; recorded here
because it is a deliberate difference from TradingView, not an omission.**

Q21 says a percent `strategy.exit` wins for that trade and a tick or point exit
is rejected. Pine's own `strategy.exit` spells both the same way: `loss=` and
`profit=` are **in ticks**, and `stop=`/`limit=` are absolute prices. There is no
percent argument to accept.

Reading `loss=10` as "10 percent" would give a TradingView script a different
meaning here without saying so — the exact failure Q24 exists to prevent, and
the more dangerous half of it, because a stop is the thing that limits the loss.

So: `loss`, `profit`, `stop`, `limit`, `trail_points`, `trail_offset` and
`trail_price` are **rejected by name**, each with its own message, and the
platform provides `loss_pct=` / `profit_pct=` instead. A script written for
TradingView therefore fails to load rather than trading a different stop, and the
error says which argument to change to what.

`apps/pine/subset.py` holds both halves — `EXIT_PERCENT_ARGS` and the five
`unsupported_exit_*` rejections — and `tests/test_pine_validate.py` proves each
message, line and column.

**Two narrowings recorded with it**, both in the same module's docstring:

- **Decorative constants** (`color.*`, `shape.*`, `location.*`, `size.*`,
  `plot.style_*`) are accepted *only* inside a visual call's argument list, where
  §1.3 says the call is recorded and never executed, and rejected by name
  anywhere else. Without this nearly every real script fails on its first
  `color=color.green`, over a value that cannot reach an order.
- **The Q27 read-surface carve-out.** Q27 forbids `apps/pine/` and `apps/bots/`
  from importing `accounts.visibility`, *and* requires every bot read surface to
  filter. Both cannot be literally true, so the import is permitted in exactly
  two modules — `apps/bots/views.py` and `apps/bots/serializers.py`, the read
  surfaces — and forbidden everywhere else. Enforced, not remembered:
  `tests/test_account_access.py` walks both packages' imports.

---

## Q31. Do passkeys replace the shared password, or sit beside it?

**Raised 2026-08-27, writing `docs/security-plan.md`. Blocks that plan's Phase
4 shape, not Phases 0–3.**

The plan adds an optional authenticator-app second factor (A1) with a
"remember this browser" companion (A2). A passkey is strictly better than both
— phishing-resistant by construction, and a tap instead of a typed code — so
the question is not whether to get there but what it does to the access model.

This platform's access model is deliberate and unusual: **one shared staff
login**, with the access list being `PanelSession` rows, one per browser, shown
in `components/dashboard/Sessions.vue`. That is the only place a second
participant is visible at all. A passkey is per-device by construction, which
gives two readings:

1. **Beside it.** Each participant enrols their own passkey against the same
   shared account. Nothing in the data model changes, `visibility.py` is
   untouched, and the Sessions list keeps meaning exactly what it means today.
   Buildable as written.
2. **Instead of it.** Per-person accounts, each with their own passkey. Better
   attribution in the audit log (B3) and no shared secret to leak — but it is a
   different product: `visibility.py`'s one hardcoded username, the profit
   split's three roles, and "who is signed in" all become per-person questions.

Reading 1 is the default and needs no answer to start. Reading 2 is the admin's
call, and is worth asking only if more than one person will hold the login
long-term.

---

## Q32. Is a WAF in front of the panel worth a hop on `/ws/`?

**Raised 2026-08-27, writing `docs/security-plan.md`. Blocks nothing; the plan
builds around either answer.**

A managed WAF (Cloudflare or equivalent) is the cheapest broad protection
available for a public panel — a DNS change, and it covers request floods and
the generic scanner traffic any exposed host gets.

But `docker-compose.prod.yml` has Caddy short-circuit `/ws/*` straight to
Channels *specifically* to save a hop, and the top bar shows the round-trip
that hop would lengthen. A proxying WAF puts it back, on the one connection
this platform treats as latency-critical.

The obvious compromise is to front the HTTP origin and leave the socket direct.
It is also a split configuration — two paths to the same host, only one
protected — so it is worth being a decision rather than a default.

---

## Adding one

New ambiguity found mid-task goes here, numbered from **Q33**, with the parts
that do not depend on the answer built in the meantime. Move it to
`docs/decisions.md` once it is answered, keeping its number.

A question belongs here only if it changes what gets built. A setting whose
default is already the decision does not — that is an answer, and it lives in
`docs/decisions.md` with its default named.

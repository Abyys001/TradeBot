# Questions & decisions — open

**One is open: Q29.** Everything else this project has raised is answered and
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

## Adding one

New ambiguity found mid-task goes here, numbered from **Q30**, with the parts
that do not depend on the answer built in the meantime. Move it to
`docs/decisions.md` once it is answered, keeping its number.

A question belongs here only if it changes what gets built. A setting whose
default is already the decision does not — that is an answer, and it lives in
`docs/decisions.md` with its default named.

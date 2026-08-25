# Golden indicator values — **empty on purpose** (Q29)

`docs/bot-mode.md` §2.3 wants every `ta.*` in the subset pinned to eight decimal
places against a fixed BTCUSDT 1h window exported from TradingView. Q29 is the
open question of where those numbers come from, and it is not a question code
can answer: an oracle computed from the same reference formulas the
implementation was written from shares any misreading of them.

Until the exports land, `tests/test_pine_ta.py` does two things that do **not**
need them:

* recomputes each indicator naively, straight from the code examples in
  `reference/pinescriptv6/reference/functions/ta.md`, and compares — which pins
  the incremental `update()` against the textbook definition;
* asserts the warm-up shape (`na` until the window fills) and the `rma` seeding,
  which is the specific trap Q29 exists to catch.

## Adding the exports

Drop one JSON file per indicator here:

```json
{
  "indicator": "rsi",
  "args": [14],
  "source": "close",
  "symbol": "BTCUSDT",
  "timeframe": "60",
  "bars": [{"time": 1690000000, "open": "…", "high": "…", "low": "…",
            "close": "…", "volume": "…"}],
  "expected": [null, null, "54.31842105", "…"]
}
```

`null` means `na`. Every number is a **string**, so it arrives as a `Decimal`
rather than as a float that lost the last two of those eight places on the way
in. `test_the_exported_golden_values` picks up every file in this directory the
moment one exists — nothing needs enabling.

# Strategy settings — properties and inputs

TradingView puts one dialog in front of a strategy with two tabs in it, and the
split between them is not cosmetic:

- **Properties** describe the *simulated broker* — capital, order size,
  commission, slippage, margin, the fill model. Change one and the **report**
  changes.
- **Inputs** are what the *script computes with* — lengths, multipliers, modes,
  toggles, dates, colours. Change one and the **signals** change, which on a
  live bot is a different trade rather than a different rendering of the same
  one.

This platform keeps that split and adds the consequence the platform has that
TradingView does not: a property stops at the backtest (spec §5 sizes every live
order at 99% of each account's own balance), while an input reaches the live
loop untouched. Every surface below says which of the two it is looking at.

Nothing here is written per strategy. The panel for any uploaded script is
derived from that script.

---

## 1. Architecture

```
source (.pine)
   │
   ├── lexer → parser → AST                      apps/pine/{lexer,parser,ast_nodes}.py
   │
   ├── validator — one walk                      apps/pine/validate.py
   │     ├── strategy() declaration  ─────────►  apps/pine/properties.py   (the broker half)
   │     └── every input.* call site ─────────►  InputSpec (the transcription)
   │
   └── analyser — the derivation                 apps/pine/inputs.py
         widget · category · dependency · groups
                   │
                   ▼
         InputSchema.as_dict()  ──stored──►  StrategyVersion.inputs_schema (JSON, immutable)
                   │
                   ├── GET /bots/versions/<id>/inputs/   the backtest form
                   └── GET /bots/bots/<id>/inputs/       the bot's own tab
                                   │
                                   ▼
                    InputsForm.vue — one row per input, drawn from the schema
                                   │
                        PATCH /bots/bots/<id>  { input_values }
                                   │
                     inputs.validate_values(schema, raw)
                                   │
                                   ▼
                    Bot.input_values ──► runtime._call_input ──► the bar loop
```

Two properties of that path matter more than the boxes:

**The schema is stored with the version, not re-derived.** A `StrategyVersion`
is immutable and a bot points at one. Re-parsing the source on every form load
would let a change in the analyser silently retitle, re-bound or drop a running
bot's settings. `InputSchema.from_data` also reads the bare field list older
rows hold, so nothing needs backfilling.

**`apps/pine/` stays stdlib-only.** The analyser imports no `django.*` and no
`apps.*` outside `apps.pine`, pinned by `tests/test_pine_purity.py`. That is
what makes the same object serve the backtest, the panel and the live loop.

---

## 2. Data model

| Where | What |
|---|---|
| `StrategyVersion.inputs_schema` | `InputSchema.as_dict()` — fields, groups, categories, defaults. Written once at save, immutable with the version. |
| `StrategyVersion.properties` / `.property_notes` | The broker half, same treatment (already in place). |
| `Bot.input_values` | **Overrides only**, `{name: value}`. Absent key = the script's own default. |
| `Bot.property_overrides` | The same, for the broker half. |
| `BacktestRun.input_values` | What that report was produced with, so a stored run stays readable. |
| `InputPreset` | `(strategy, name) → values`. On the **strategy**, not the version. |

### `InputSpec`

Transcribed from the call site:

`name` · `kind` · `default` · `title` · `minval` · `maxval` · `options` ·
`step` · `group` · `inline` · `tooltip`

Derived by `inputs.analyse`:

| Field | Meaning |
|---|---|
| `order` | Declaration order. TradingView's panel is in source order and so is this one. |
| `widget` | The control that edits it. `options=` makes any type a dropdown. |
| `category` | `risk` / `execution` / `backtest` / `logic` / `visual`. |
| `reason` | The sink that decided the category — the evidence, shown on the row. |
| `depends_on` | `[{controller, values}]` — advisory, never enforced. |
| `used` | False when nothing in the script reads it. |
| `choices` | `options=`, or the source list for `input.source`. |

**`name` is the identity, not `title`.** The variable an input is assigned to is
what the runtime keys on (`runtime._call_input`) and what the form submits, so
retitling an input keeps its configured value. This is also why the validator
refuses an `input.*` that is not assigned to a single name.

### Widget mapping

| Pine | Widget | Control |
|---|---|---|
| `input.bool` | `toggle` | checkbox |
| `input.int` | `number` | numeric, `step` = 1 unless declared |
| `input.float` | `number` | decimal, `step` from the declaration |
| `input.string` | `text` / `select` | dropdown when `options=` is present |
| `input.source` | `source` | the built-in series that exist |
| `input.color` | `color` | colour picker, `#RRGGBB[AA]` |
| `input.time` | `datetime` | date/time picker over epoch ms |
| `input.price` | `number` | numeric |
| `input.timeframe` | `timeframe` | text |
| `input.session` | `session` | text |
| `input.symbol` | `text` | text |
| `input.text_area` | `textarea` | multi-line |

`input.time` defaults are folded at validation — `timestamp("01 Jan 2026 …")`
becomes the number it is, using the runtime's own `timestamp`, so the field
shows a date rather than the word "timestamp".

---

## 3. Detection

### Groups

`group=` is the heading, taken as the string the script wrote — `"03. Targets /
Stop"` — because that string is the group's only identity and scripts number
their groups to force an order. Groups come back in first-appearance order,
each holding its inputs in source order. `inline=` runs become rows drawn on one
line. Ungrouped inputs keep their own bucket under the empty key rather than
being swept into the first heading.

A `group = G_TARGET` naming a top-level string constant resolves, which is how
every published strategy writes it.

### Classification — read off the sinks, never the name

`analyse` walks the AST twice.

**Pass one follows values.** Every assignment taints its target with the inputs
that flow into it, so `tp1Price = entry + tp1RR * risk` makes every use of
`tp1Price` a use of `tp1RR`. Arguments to user functions and methods taint their
parameters, and a field written on a method's receiver (`c.t1 := …`) is taken up
under the bare field name so the caller's `campaign.t1` finds it — without that
step a published strategy's most important settings read as unused.

**Pass two records where those values are consumed**, carrying the conditions in
force. The sink is pushed down to the leaf rather than resolved at the argument,
so `strategy.exit(stop = useAtr ? atrStop : swingStop)` records `atrStop` as a
risk input *guarded by* `useAtr`.

| Sink | Category |
|---|---|
| `strategy.*(loss_pct=, profit_pct=, qty_percent=, …)` | `risk` |
| `strategy.*(when=, oca_*=, disable_alert=)`, `alert()`, `alertcondition()` | `execution` |
| compared against `time` / `time_close` / `timestamp(...)` | `backtest` |
| any other `strategy.*` argument, or a condition guarding one | `logic` |
| `plot*`, `fill`, `bgcolor`, `barcolor`, `hline`, `label.*`, `line.*`, `box.*`, `table.*`, and `alert_message=`/`comment=` | `visual` |

Precedence is that order: a value reaching two sinks is filed under the more
consequential one. Two decisions in that table are worth naming:

- **A guard is `logic`, whichever call it guards — `strategy.exit` included.**
  Filing an exit's condition as risk read well for a take-profit toggle and
  badly for everything else, because the usual shape is one `if` holding both
  the entry and its exit, and every length in that condition came back as a risk
  setting.
- **`alert_message=` and `comment=` are `visual`.** They only *describe* an
  order. Counting them as execution files half a panel under Execution the
  moment an author builds an informative alert string, which every published
  strategy does.

An input with no sinks at all is marked `used: false` and falls to `visual` for
colours and free text, `logic` for everything else — the safe side, since a
number filed as decoration is a number nobody checks before going live.

### Dependencies

For each input, the guards over **every non-visual use** are intersected. A
dependency is claimed only when the same condition holds at all of them; one use
outside the guard drops it. Only shapes a form can act on survive the reduction:
a bool read, its negation, and an equality against one of a dropdown's options.
An unrecognised guard contributes nothing, which makes it *drop* a dependency
rather than invent one.

Visual uses are excluded from the intersection rather than from the analysis: a
target price plotted unconditionally and traded only when take-profit is on is
still gated, because a dependency here says "this changes nothing about the
orders", never "this changes nothing".

**It is advisory and it runs one way.** A gated row is dimmed with the reason
beside it and stays editable; its value is still submitted; nothing on the
execution path reads the flag. An input wrongly greyed out is a setting the
operator cannot reach on a live book, which is worse than one that stays bright
while it does nothing.

The call site's guards do **not** travel into a user function. A body is visited
once and cannot carry the conditions of every call, and inventing a gate is the
one error this analysis is arranged not to make.

---

## 4. Configuration management

`validate_values(schema, raw) → (clean, errors)`:

- **Only differences are kept.** A value equal to the script's own default is
  dropped, so "reset to default" is a deleted key rather than a copy of a number
  that then stops following the script.
- **A bad value is named, not dropped.** Somebody is looking at the field; a
  silently discarded value would come back as the default with nothing on screen
  to say the change never happened, and on this panel that change is a stop
  distance.
- Type, `minval`, `maxval` and `options` are enforced. `step` is a form
  affordance, not a refusal — TradingView treats it the same way, and rejecting
  a value that is inside the declared range for being off the step grid refuses
  a setting the script would have accepted.
- A name the script no longer has is reported by name. That is what a preset
  saved against an older version looks like on arrival.

`resolve_values(schema, overrides)` is the one merge rule — script default under
override — and it exists once, on the server, for the same reason
`properties.resolve` does: a browser recomputing it is a second place for "the
script chose 65" to become "the operator chose 65".

Values are checked at three doors: the bot serializer (`validate`, object-level
so a PATCH still finds the version), the backtest endpoint, and the runtime's
own coercion against the script's default shape.

### Presets

`InputPreset` is `(strategy, name) → values`. On the strategy and not the
version because an input is identified by its variable name and that survives an
edit: a preset called "Fast, tight stop" is about the settings, not the revision
they were first typed against. It stores values only — never a symbol, an
interval or a leverage, which live on the bot and would make "load" a way to
move a bot to another market by accident. Loading applies to the **draft**, so
it lands as unsaved changes somebody can read before committing them.

---

## 5. UI

| Surface | What |
|---|---|
| `components/bots/InputsForm.vue` | The rows. Groups collapse, `inline` runs draw on one line, a category filter narrows to one bucket, per-row and per-panel reset. Recomputes nothing. |
| `components/bots/StrategyInputs.vue` | The bot's Inputs tab: load, edit, save, presets. Carries the warning the Properties tab does not need — saving changes what the bot trades, and a running bot picks it up at the next start. |
| `components/bots/InputsDialog.vue` | The same form in front of a backtest, for a version with no bot behind it. Values are posted with the run and saved nowhere. |
| `pages/strategies/index.vue` | The editor's read-only table, now with the derived columns: the category, why, and what gates it. |
| `components/bots/PropertiesForm.vue` etc. | The broker half, unchanged. |

Titles, tooltips and option labels come out of the script and are shown as the
author wrote them, in whatever language that is. `i18n` covers the chrome around
them and never the settings themselves.

---

## 6. Flow, end to end

1. Paste or upload a script; the editor validates on every keystroke and draws
   the panel beside the underlines — a script with one mistake still has thirty
   inputs somebody is looking at.
2. Save a version: source, validation result, properties and **schema** are
   written together and never rewritten.
3. Backtest: open Inputs (and Properties), change what you mean to change, run.
   The values ride with the run and are stored on the report.
4. Create a bot from that version. Its Inputs tab starts at the script's
   defaults — no override rows at all — and shows which of them are risk, which
   are decoration and which are inert under the current toggles.
5. Save. The values are held to the schema and stored as differences.
6. Start. `supervisor` hands `bot.input_values` to the runtime, which resolves
   each `input.*` by variable name and falls back to the script's own default
   for anything absent.

---

## 7. What this deliberately does not do

- **No naming heuristics.** Nothing is classified because it is spelled
  "percent" or "color". The next uploaded strategy will not use this one's
  vocabulary.
- **No enforcement of dependencies.** See above — advisory, one direction.
- **No interprocedural guard tracking.** A function body is visited once, so a
  gate that exists only at one call site is not claimed.
- **No `step` refusals.** A form affordance, not a validation rule.
- **No preset that carries market or leverage.** Those are the bot's, not the
  strategy's.
- **Pyramiding, `calc_on_every_tick`, `fill_orders_on_standard_ohlc`** and the
  other properties the platform cannot honour are still reported rather than
  silently accepted — `properties.INERT` and `live_departures()`. Q20's rule is
  that parsed-and-dropped is only allowed out loud.

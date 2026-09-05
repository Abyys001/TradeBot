"""The v1 subset (Q24), as data.

One table for what is accepted and one for what is rejected, so that a rejection
cannot ship without the message its error must produce —
``tests/test_pine_validate.py`` parametrizes over ``REJECTIONS`` and asserts each
one's construct name, line and column come back.

Q24's rule is the one Q13 took for prices: **a script that loads and quietly
does not do what it says is worse than a script that will not load.** So nothing
outside this file is silently ignored. Two things are *accepted and reported*
rather than rejected — a script's ``qty`` (Q20) and a ``varip`` declaration
(Q23) — and both raise a warning the panel shows at upload time.

**User-defined types, methods and enums are in the subset** (``docs/decisions.md``
Q24, amended). ``type``/``method``/``enum`` used to be three rows here — "needs a
type system" — and now there is one: ``apps/pine/objects.py`` is that type
system. A ``type`` declares an object with typed fields, ``method f(T this, …)``
binds a function to it (dispatched and overloaded by receiver type), and ``enum``
is a closed set of named members. The validator checks the *definitions* fully
(unknown field type, duplicate name, unknown receiver, a cycle through methods)
and the *uses* as far as a lightweight ``var -> UDT`` inference reaches; anything
past that is a located runtime error on the first bar, never a silent ``na``.
Object field history — ``obj.field[n]`` — is still rejected by name, the same
way ``(a + b)[n]`` is: assign it to a variable first.

Three deliberate narrowings of "reject everything else" are recorded here rather
than left implicit:

  **Decorative constants, and the drawings they decorate.** ``plot``/
  ``plotshape`` and friends are recorded, never executed (§1.3). ``color.*``,
  ``shape.*``, ``line.style_*``, ``position.*`` and the rest of
  ``DECORATIVE_NAMESPACES`` are accepted **wherever a value is accepted** —
  originally only inside a visual call's argument list, which was one step too
  tight, because every real script names its colours on a line of their own
  first. The drawing namespaces (``line``, ``label``, ``box``, ``table``,
  ``polyline``, ``linefill``) are accepted the same way and draw nothing. The
  one thing refused out of all of it is ``DRAWING_READBACKS`` — ``line.get_price``
  and its family — because a coordinate read back out of a drawing *can* become
  a condition, and a condition becomes an order.

  **A partial close takes a percentage; a fixed ``qty`` is still refused.**
  ``strategy.close(qty_percent = 30)`` is a real scale-out here (Q33, answered):
  a percentage of the position is identical across accounts and only the dollar
  size differs, which is spec §5's existing rule applied to the exit rather than
  to the entry. ``qty = 2`` has no such reading — an absolute contract count is
  the platform's answer to give under Q20, and unlike a percentage there is
  nothing to translate it into across accounts of different sizes — so it stays
  an error rather than the warning ``strategy.entry(qty=)`` gets, where the
  platform's own sizing *is* a complete answer to the question asked.

  **``strategy.exit`` takes percent through ``loss_pct``/``profit_pct``.**
  Q21 says a percent exit wins and a tick/point exit is rejected, but Pine's own
  ``loss=``/``profit=`` are *in ticks*. Accepting those as percent would silently
  give a TradingView script a different meaning here — exactly what Q24 forbids
  — so they are rejected **by name** and a distinct percent spelling is provided.
  Recorded as Q30 in ``questions.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.pine.properties import (
    COMMISSION_CONSTANTS,
    CURRENCIES,
    PROPERTY_ARGS,
    QTY_CONSTANTS,
)

# --- accepted ---------------------------------------------------------------

#: Built-in series. Every one of these advances per bar and supports ``[n]``.
BUILTIN_SERIES = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "hl2",
        "hlc3",
        "ohlc4",
        "hlcc4",
        "time",
        "time_close",
        "bar_index",
    }
)

#: Scalars and namespaces that are values rather than calls.
BUILTIN_VALUES = frozenset(
    {"na", "last_bar_index", "last_bar_time", "timenow", "weekofyear"}
)

NAMESPACE_FUNCTIONS: dict[str, frozenset[str]] = {
    "ta": frozenset(
        {
            "sma",
            "ema",
            "rma",
            "wma",
            "vwma",
            "hma",
            "stdev",
            "variance",
            "rsi",
            "atr",
            "tr",
            "macd",
            "bb",
            "bbw",
            "stoch",
            "cci",
            "mom",
            "roc",
            "crossover",
            "crossunder",
            "cross",
            "change",
            "highest",
            "lowest",
            "highestbars",
            "lowestbars",
            "barssince",
            "valuewhen",
            "cum",
            "sum",
            "percentile_linear_interpolation",
            "linreg",
            "rising",
            "falling",
            "pivothigh",
            "pivotlow",
        }
    ),
    "math": frozenset(
        {
            "abs",
            "max",
            "min",
            "pow",
            "sqrt",
            "log",
            "log10",
            "exp",
            "round",
            "floor",
            "ceil",
            "sign",
            "avg",
            "sum",
            "random",
            "sin",
            "cos",
            "tan",
            "asin",
            "acos",
            "atan",
            "todegrees",
            "toradians",
            "round_to_mintick",
        }
    ),
    "str": frozenset(
        {
            "tostring",
            "tonumber",
            "format",
            "format_time",
            "length",
            "contains",
            "startswith",
            "endswith",
            "substring",
            "replace_all",
            "split",
            "trim",
            "upper",
            "lower",
            "repeat",
            "pos",
        }
    ),
    "input": frozenset(
        {
            "int",
            "float",
            "bool",
            "string",
            "source",
            "timeframe",
            "color",
            "time",
            "price",
            "session",
            "symbol",
            "text_area",
        }
    ),
    "strategy": frozenset({"entry", "close", "close_all", "exit"}),
    #: Colour arithmetic. Inert here for the same reason the constants are —
    #: nothing derived from a colour reaches a side, a price or a percent — but
    #: real functions rather than names, because ``color.new(c, 90)`` is written
    #: inline in every script that draws anything.
    "color": frozenset({"new", "rgb", "from_gradient", "r", "g", "b", "t"}),
    "timeframe": frozenset({"in_seconds"}),
}

#: Namespace members that are values, not calls.
NAMESPACE_VALUES: dict[str, frozenset[str]] = {
    "ta": frozenset({"tr"}),
    #: The performance figures TradingView's own dashboard is built from. The
    #: *driver* supplies every one of them (``Runtime.sync_position``) for the
    #: same reason it supplies ``position_size``: the exchange and the ledger
    #: are the source of truth, and a runtime keeping its own tally would be a
    #: second one. In a backtest they are the simulated account's; live they
    #: are the run's own closed trades.
    "strategy": frozenset(
        {
            "position_size",
            "position_avg_price",
            "position_entry_name",
            "opentrades",
            "closedtrades",
            "wintrades",
            "losstrades",
            "eventrades",
            "equity",
            "initial_capital",
            "netprofit",
            "netprofit_percent",
            "openprofit",
            "openprofit_percent",
            "grossprofit",
            "grossprofit_percent",
            "grossloss",
            "grossloss_percent",
            "max_drawdown",
            "max_drawdown_percent",
            "max_runup",
            "max_runup_percent",
            "avg_trade",
            "avg_trade_percent",
            "avg_winning_trade",
            "avg_losing_trade",
            "account_currency",
            "long",
            "short",
        }
    ),
    #: The symbol, as the platform knows it. Fed in at load from the bot's own
    #: pair and market (``SymbolInfo``) — never guessed, and never read from a
    #: clock or an environment, so a backtest and a live run see one answer.
    "syminfo": frozenset(
        {
            "ticker",
            "tickerid",
            "prefix",
            "currency",
            "basecurrency",
            "mintick",
            "minmove",
            "pricescale",
            "pointvalue",
            "type",
            "timezone",
            "session",
            "description",
            "root",
        }
    ),
    #: The bot's timeframe, likewise fed in rather than derived.
    "timeframe": frozenset(
        {
            "period",
            "multiplier",
            "isseconds",
            "isminutes",
            "isintraday",
            "isdaily",
            "isweekly",
            "ismonthly",
            "isdwm",
            "main_period",
        }
    ),
    #: Chart appearance. Constant here: this platform draws standard candles on
    #: one theme, so ``chart.is_heikinashi`` is *false* rather than unknown —
    #: which is what a strategy guarding against synthetic prices needs to read.
    "chart": frozenset(
        {
            "fg_color",
            "bg_color",
            "is_standard",
            "is_heikinashi",
            "is_renko",
            "is_kagi",
            "is_pnf",
            "is_linebreak",
            "is_range",
        }
    ),
    "barstate": frozenset(
        {"isfirst", "islast", "isconfirmed", "isnew", "ishistory", "isrealtime"}
    ),
    "math": frozenset({"pi", "e"}),
}

#: Callable without a namespace.
BARE_FUNCTIONS = frozenset(
    {
        "nz",
        "na",
        "fixnan",
        "input",
        "timestamp",
        "dayofweek",
        "hour",
        "minute",
        "second",
        "year",
        "month",
        "dayofmonth",
        "strategy",
        "max",
        "min",
        "abs",
        "weekofyear",
        #: Explicit casts. Pine has them as bare names shadowing the type
        #: keywords, and real scripts use `float(a + b)` to force a division to
        #: be a float one — refusing them fails on arithmetic, not on a feature.
        "int",
        "float",
        "bool",
        "string",
        "color",
    }
)

#: Recorded as annotations and never executed (§1.3). Their arguments cannot
#: reach an order, which is what licenses DECORATIVE_NAMESPACES below.
VISUAL_FUNCTIONS = frozenset(
    {
        "plot",
        "plotshape",
        "plotchar",
        "plotarrow",
        "plotcandle",
        "plotbar",
        "hline",
        "fill",
        "bgcolor",
        "barcolor",
        "alert",
        "alertcondition",
    }
)

#: Namespaces whose members are **inert constants**: a colour, a marker shape, a
#: line style, a table corner. Accepted wherever a value is accepted.
#:
#: This used to be "accepted only inside a plot() argument list", which was one
#: step too tight: every real script writes ``col = trendUp ? color.green :
#: color.red`` on its own line and passes ``col`` in later, and refusing that
#: rejects the script over a value that still cannot reach an order. The
#: property that licenses it is unchanged — a colour has no arithmetic that
#: produces a side, a price or a percent, and the two places a number *can*
#: leave the script (``strategy.exit`` percents and the intent's side) take
#: neither a colour nor a style.
DECORATIVE_NAMESPACES = frozenset(
    {
        "color",
        "shape",
        "location",
        "size",
        "plot",
        "display",
        "text",
        "font",
        "xloc",
        "yloc",
        "extend",
        "position",
        "format",
        "hline",
        "scale",
        "order",
        "adjustment",
        "barmerge",
        "alert",
    }
)

#: Drawing objects: ``line``, ``label``, ``box``, ``table``, ``polyline``,
#: ``linefill``.
#:
#: **Accepted, and drawn nowhere.** They used to be five rows in ``REJECTIONS``
#: whose message read "line.* has no execution effect here" — and then errored,
#: which is the one combination that cannot be right: a construct with no
#: execution effect is exactly the kind this file already accepts and records
#: (``plot``, ``plotshape``, ``bgcolor``). Half of a published strategy is its
#: chart furniture, so refusing it refuses the strategy over its decoration.
#:
#: ``line.new`` and friends return an opaque handle, the setters and ``delete``
#: are no-ops, and the panel draws none of it — the chart the admin looks at is
#: the platform's own, not the script's.
DRAWING_NAMESPACES = frozenset({"line", "label", "box", "table", "polyline", "linefill"})

#: Members of those namespaces that **read a value back out of a drawing**.
#: Refused by name, and this is the whole reason the split exists: a coordinate
#: read out of a line can become a condition, and a condition becomes an order.
#: Accepting these as no-ops would return ``na`` into live logic, which is Q24's
#: "loads and quietly does not do what it says".
DRAWING_READBACKS: frozenset[str] = frozenset(
    {
        "line.get_price",
        "line.get_x1",
        "line.get_x2",
        "line.get_y1",
        "line.get_y2",
        "label.get_text",
        "label.get_x",
        "label.get_y",
        "box.get_top",
        "box.get_bottom",
        "box.get_left",
        "box.get_right",
        "linefill.get_line1",
        "linefill.get_line2",
    }
)

#: The types those namespaces also name, so ``var line myLine = na`` declares.
DRAWING_TYPES = frozenset(DRAWING_NAMESPACES | {"chart.point"})

#: ``strategy.exit`` percent arguments (Q21, and see the module docstring).
EXIT_PERCENT_ARGS = frozenset({"loss_pct", "profit_pct"})

#: ``strategy.close`` arguments that name a **size** rather than a share.
#: ``qty_percent`` is not here: it is honoured (Q33). See the ``partial_close``
#: rejection below for why this one is an error where ``strategy.entry``'s own
#: ``qty`` is only a warning.
CLOSE_SIZE_ARGS = frozenset({"qty"})

#: ``strategy()`` arguments that carry no risk and are simply accepted.
#: The ``max_*_count`` family sizes TradingView's drawing pools; this platform
#: draws none of them, and a cap on nothing is not worth an error.
STRATEGY_ACCEPTED_ARGS = frozenset(
    {
        "title",
        "shorttitle",
        "overlay",
        "format",
        "precision",
        "max_bars_back",
        "scale",
        "max_lines_count",
        "max_labels_count",
        "max_boxes_count",
        "max_polylines_count",
        "explicit_plot_zorder",
        "behind_chart",
        "linktoseries",
        "close_entries_rule",
        "risk_free_rate",
        "calc_bars_count",
    }
)

#: TradingView's Properties tab. Honoured by the backtest, and reported wherever
#: one of them would describe a platform the bot will not run on.
#: ``apps.pine.properties`` owns what each means; this alias is so the validator
#: has one place to ask "is this a property?".
STRATEGY_PROPERTY_ARGS = PROPERTY_ARGS

#: Constants legal **only** inside the ``strategy()`` declaration:
#: ``strategy.percent_of_equity``, ``strategy.commission.percent``,
#: ``currency.USD``. They never reach the runtime — the declaration returns
#: ``na`` without evaluating its arguments — so accepting them is what lets a
#: TradingView strategy paste in unchanged.
DECLARATION_CONSTANTS: frozenset[str] = frozenset(
    set(QTY_CONSTANTS) | set(COMMISSION_CONSTANTS) | {f"currency.{c}" for c in CURRENCIES}
)


# --- rejected ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rejection:
    """One construct outside the subset, and the message its error must carry."""

    code: str
    #: What the validator matches on: a dotted prefix, a bare name, a keyword,
    #: or a ``strategy()`` / ``strategy.exit`` argument name.
    kind: str
    pattern: str
    message: str


REJECTIONS: tuple[Rejection, ...] = (
    Rejection(
        code="unsupported_security",
        kind="namespace",
        pattern="request",
        message=(
            "multi-timeframe is not supported yet — request.security() and its lookahead "
            "semantics are the single largest source of backtest/live divergence"
        ),
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="array",
        message="collections are not supported yet — array.* needs a runtime value model",
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="matrix",
        message="collections are not supported yet — matrix.* needs a runtime value model",
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="map",
        message="collections are not supported yet — map.* needs a runtime value model",
    ),
    Rejection(
        code="partial_close",
        kind="close_arg",
        pattern="qty",
        message=(
            "a close cannot name a number of contracts — every account is sized at 99% "
            "of its own balance (spec §5), so there is no one quantity that means the "
            "same thing on all of them. Use qty_percent=, which is a share of whatever "
            "each account is holding"
        ),
    ),
    Rejection(
        code="unsupported_strategy_risk",
        kind="namespace",
        pattern="strategy.risk",
        message=(
            "configure risk limits on the bot, not in the script — strategy.risk.* would "
            "overlap the bot's own auto-stop triggers (Q25) with no way to tell which won"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.order",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.cancel",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.cancel_all",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_import",
        kind="keyword",
        pattern="import",
        message=(
            "libraries are not supported — resolution, versioning and trust are all unsolved "
            "here"
        ),
    ),
    Rejection(
        code="unsupported_import",
        kind="keyword",
        pattern="export",
        message=(
            "libraries are not supported — resolution, versioning and trust are all unsolved "
            "here"
        ),
    ),
    Rejection(
        code="unsupported_exit_ticks",
        kind="exit_arg",
        pattern="loss",
        message=(
            "strategy.exit in ticks or points is rejected (Q21) — converting one needs the "
            "symbol's tick size, which the script cannot see. Use loss_pct= for percent"
        ),
    ),
    Rejection(
        code="unsupported_exit_ticks",
        kind="exit_arg",
        pattern="profit",
        message=(
            "strategy.exit in ticks or points is rejected (Q21) — converting one needs the "
            "symbol's tick size, which the script cannot see. Use profit_pct= for percent"
        ),
    ),
    Rejection(
        code="unsupported_exit_price",
        kind="exit_arg",
        pattern="stop",
        message=(
            "strategy.exit stop= is an absolute price and this platform's SL/TP is a "
            "percentage identical across accounts (§5). Use loss_pct="
        ),
    ),
    Rejection(
        code="unsupported_exit_price",
        kind="exit_arg",
        pattern="limit",
        message=(
            "strategy.exit limit= is an absolute price and this platform's SL/TP is a "
            "percentage identical across accounts (§5). Use profit_pct="
        ),
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_points",
        message="trailing stops are not supported yet — trail_points is in ticks (Q21)",
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_offset",
        message="trailing stops are not supported yet — trail_offset is in ticks (Q21)",
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_price",
        message="trailing stops are not supported yet — trail_price is an absolute price (Q21)",
    ),
)

REJECTED_NAMESPACES = {r.pattern: r for r in REJECTIONS if r.kind == "namespace"}
REJECTED_NAMES = {r.pattern: r for r in REJECTIONS if r.kind == "name"}
REJECTED_STRATEGY_ARGS = {r.pattern: r for r in REJECTIONS if r.kind == "strategy_arg"}
REJECTED_KEYWORDS = {r.pattern: r for r in REJECTIONS if r.kind == "keyword"}
REJECTED_EXIT_ARGS = {r.pattern: r for r in REJECTIONS if r.kind == "exit_arg"}
REJECTED_CLOSE_ARGS = {r.pattern: r for r in REJECTIONS if r.kind == "close_arg"}

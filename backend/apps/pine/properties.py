"""``strategy()``'s properties — TradingView's Properties tab, as data.

TradingView puts ten settings behind the strategy: initial capital, base
currency, order size, pyramiding, commission, limit-fill verification,
slippage, margin, recalculation and the fill model. They are the *backtest's*
model of a broker, and they are what makes one report comparable with another.

Three things about them here:

**They resolve in one direction.** Platform default → what ``strategy()``
declares → what the panel overrides. ``resolve()`` is the only place that order
exists, so a report and the form that produced it cannot disagree about which
number won. ``declared`` records which keys the *script* set, which is what lets
the panel show "from the script" beside a field instead of pretending the
author chose the default.

**A property that changes live sizing is a backtest property only.** Spec §5 is
an invariant: live margin is 99% of each account's own balance with leverage on
top, identical percentages everywhere, one open trade per account. So
``default_qty_type``/``default_qty_value`` and the margin pair describe the
simulated account and nothing else, and ``live_departures()`` names every one
that would make the backtest describe a different platform than the one the bot
will run on. Naming them is the point — Q20's rule is that parsed-and-dropped is
only allowed out loud.

``pyramiding`` is in that list without being honoured anywhere: a second entry
in a direction already held needs the multi-lot position model that
``questions.md`` Q33 carries, and simulating one in the backtest alone would
produce a curve live cannot reproduce. So it is reported and dropped, which is
the same treatment ``strategy.entry(qty=)`` gets and for the same reason.

**Two of them cannot be honoured at all here** and say so rather than being
accepted into silence: ``calc_on_every_tick`` needs tick data the platform
never stores (Q23 evaluates confirmed bars only), and
``fill_orders_on_standard_ohlc`` corrects Heikin Ashi candles, which this
platform does not draw.

Stdlib only, like the rest of ``apps.pine`` — the backtest and the live loop
both read the same object.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from apps.pine import ast_nodes as ast


class QtyType(StrEnum):
    """How the simulated account sizes an entry."""

    #: Spec §5, and the only one live routing implements: 99% of the balance
    #: as margin, leverage on top. Not a TradingView value — the platform's own.
    PLATFORM = "platform"
    FIXED = "fixed"  # strategy.fixed — a number of contracts
    CASH = "cash"  # strategy.cash — an amount of base currency
    PERCENT_OF_EQUITY = "percent_of_equity"  # strategy.percent_of_equity


class CommissionType(StrEnum):
    PERCENT = "percent"  # strategy.commission.percent
    CASH_PER_CONTRACT = "cash_per_contract"  # strategy.commission.cash_per_contract
    CASH_PER_ORDER = "cash_per_order"  # strategy.commission.cash_per_order


#: ``strategy.*`` and ``currency.*`` constants that are legal *only* inside the
#: ``strategy()`` declaration. They never reach the runtime — the declaration
#: returns ``na`` without evaluating its arguments — so accepting them here is
#: what lets a TradingView script paste in unchanged.
QTY_CONSTANTS: dict[str, QtyType] = {
    "strategy.fixed": QtyType.FIXED,
    "strategy.cash": QtyType.CASH,
    "strategy.percent_of_equity": QtyType.PERCENT_OF_EQUITY,
}

COMMISSION_CONSTANTS: dict[str, CommissionType] = {
    "strategy.commission.percent": CommissionType.PERCENT,
    "strategy.commission.cash_per_contract": CommissionType.CASH_PER_CONTRACT,
    "strategy.commission.cash_per_order": CommissionType.CASH_PER_ORDER,
}

#: Every ``currency.*`` constant, not only the shorter Base Currency dropdown:
#: a script writing ``currency.USDT`` is naming the one this platform actually
#: settles in, and rejecting it over a list copied from a stocks-era menu would
#: refuse the most correct declaration a crypto strategy can make.
#: ``currency.NONE`` is TradingView's "Default" — no conversion, the symbol's
#: own quote currency.
CURRENCIES: tuple[str, ...] = (
    "NONE",
    "AED",
    "ARS",
    "AUD",
    "BDT",
    "BHD",
    "BRL",
    "BTC",
    "CAD",
    "CHF",
    "CLP",
    "CNY",
    "COP",
    "CZK",
    "DKK",
    "EGP",
    "ETH",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "ISK",
    "JPY",
    "KES",
    "KRW",
    "KWD",
    "LKR",
    "MAD",
    "MXN",
    "MYR",
    "NGN",
    "NOK",
    "NZD",
    "PEN",
    "PHP",
    "PKR",
    "PLN",
    "QAR",
    "RON",
    "RSD",
    "RUB",
    "SAR",
    "SEK",
    "SGD",
    "THB",
    "TND",
    "TRY",
    "TWD",
    "USD",
    "USDT",
    "VES",
    "VND",
    "ZAR",
)

#: Every ``strategy()`` argument this module reads, mapped to how it is read.
#: ``validate`` uses the keys as the accepted set, so adding a property here is
#: the whole change on the language side.
PROPERTY_ARGS: frozenset[str] = frozenset(
    {
        "initial_capital",
        "currency",
        "default_qty_type",
        "default_qty_value",
        "pyramiding",
        "commission_type",
        "commission_value",
        "backtest_fill_limits_assumption",
        "slippage",
        "margin_long",
        "margin_short",
        "calc_on_order_fills",
        "calc_on_every_tick",
        "process_orders_on_close",
        "use_bar_magnifier",
        "fill_orders_on_standard_ohlc",
    }
)

#: Properties that describe the simulated account rather than the live one.
#: Each maps to the sentence the panel and the report show beside it.
BACKTEST_ONLY: dict[str, str] = {
    "default_qty_type": (
        "order size is a backtest property — live margin is 99% of each account's own "
        "balance with leverage on top (spec §5)"
    ),
    "default_qty_value": (
        "order size is a backtest property — live margin is 99% of each account's own "
        "balance with leverage on top (spec §5)"
    ),
    "pyramiding": (
        "pyramiding is not simulated at all — live commits 99% of the account on the "
        "first entry, so one open trade per account is all there is room for, and a "
        "backtest that scaled in would describe a platform that cannot (questions.md Q33)"
    ),
    "margin_long": (
        "margin is a backtest property — the live venue's own margin rules apply, not this number"
    ),
    "margin_short": (
        "margin is a backtest property — the live venue's own margin rules apply, not this number"
    ),
    "initial_capital": (
        "initial capital sizes the backtest's one notional account — live reads each "
        "account's real balance"
    ),
    "currency": (
        "base currency labels the report — the platform trades USDT-denominated accounts "
        "and reports an account that is not in USDT as unusable"
    ),
    "process_orders_on_close": (
        "filling on the signal bar's own close is what a backtest cannot do honestly and "
        "live cannot do at all — the bot routes after the bar has closed"
    ),
}

#: Properties with no effect here, and why. Reported at validation time.
INERT: dict[str, str] = {
    "calc_on_every_tick": (
        "this platform evaluates confirmed bars only (Q23) and stores no tick data, so "
        "recalculating on every tick has nothing to recalculate from"
    ),
    "fill_orders_on_standard_ohlc": (
        "this platform draws standard candles only, so there are no Heikin Ashi prices to correct"
    ),
    "backtest_fill_limits_assumption": (
        "limit entries are outside the subset (strategy.entry limit= is refused), so "
        "there is no limit fill to verify — carried for when they are not"
    ),
    "calc_on_order_fills": (
        "an extra evaluation after a fill needs intrabar prices; it is honoured only "
        "when the bar magnifier is on and lower-timeframe bars are archived"
    ),
}


@dataclass(frozen=True, slots=True)
class StrategyProperties:
    """One fully-resolved set. Every field concrete: nothing here means "ask again".

    The defaults are the *platform's*, not TradingView's, wherever the two
    differ — a report has to describe what this platform does. TradingView's own
    default is named in the docstring of each field that departs.
    """

    #: TradingView defaults to 1,000,000. A notional account this size makes
    #: percentage returns meaningless against real balances, so the platform
    #: sizes its one simulated account like a real one.
    initial_capital: Decimal = Decimal("10000")
    #: USDT, not TradingView's USD: every account this platform trades is
    #: USDT-denominated and one that is not is reported as unusable (§5).
    currency: str = "USDT"
    default_qty_type: QtyType = QtyType.PLATFORM
    #: Read only when ``default_qty_type`` is not ``PLATFORM``: contracts for
    #: ``FIXED``, currency for ``CASH``, percent for ``PERCENT_OF_EQUITY``.
    default_qty_value: Decimal = Decimal("100")
    pyramiding: int = 0
    commission_type: CommissionType = CommissionType.PERCENT
    #: Percent of the transacted value when the type is ``PERCENT``. Seeded from
    #: ``BACKTEST_FEE_BPS`` so an undeclared commission still costs what the
    #: platform assumes a taker fee costs.
    commission_value: Decimal = Decimal("0")
    backtest_fill_limits_assumption: int = 0
    #: Ticks, TradingView's unit. ``None`` leaves ``slippage_bps`` in force —
    #: the two are different units and averaging them would be a third model.
    slippage: int | None = None
    #: Percent of the position the account must fund. ``0`` is TradingView's
    #: "no margin requirement", and is the default here too.
    margin_long: Decimal = Decimal("0")
    margin_short: Decimal = Decimal("0")
    calc_on_order_fills: bool = False
    calc_on_every_tick: bool = False
    process_orders_on_close: bool = False
    use_bar_magnifier: bool = False
    fill_orders_on_standard_ohlc: bool = False

    #: Which keys the *script* set, and which the panel overrode. Display only —
    #: nothing branches on them, so a stale set cannot change a number.
    declared: frozenset[str] = field(default_factory=frozenset)
    overridden: frozenset[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict:
        return {
            "initial_capital": str(self.initial_capital),
            "currency": self.currency,
            "default_qty_type": self.default_qty_type.value,
            "default_qty_value": str(self.default_qty_value),
            "pyramiding": self.pyramiding,
            "commission_type": self.commission_type.value,
            "commission_value": str(self.commission_value),
            "backtest_fill_limits_assumption": self.backtest_fill_limits_assumption,
            "slippage": self.slippage,
            "margin_long": str(self.margin_long),
            "margin_short": str(self.margin_short),
            "calc_on_order_fills": self.calc_on_order_fills,
            "calc_on_every_tick": self.calc_on_every_tick,
            "process_orders_on_close": self.process_orders_on_close,
            "use_bar_magnifier": self.use_bar_magnifier,
            "fill_orders_on_standard_ohlc": self.fill_orders_on_standard_ohlc,
            "declared": sorted(self.declared),
            "overridden": sorted(self.overridden),
        }

    @property
    def max_entries(self) -> int:
        """Entries allowed in one direction. ``pyramiding`` counts *additional* ones."""
        return max(1, self.pyramiding + 1)

    def live_departures(self) -> list[str]:
        """What this set would simulate that the live platform does not do.

        Only the properties actually moved off their platform default appear:
        a script that declares ``pyramiding = 0`` is stating the platform's own
        behaviour, and warning about it would train the reader to skip the list.
        """
        lines: list[str] = []
        if self.default_qty_type is not QtyType.PLATFORM:
            lines.append(BACKTEST_ONLY["default_qty_type"])
        if self.pyramiding > 0:
            lines.append(BACKTEST_ONLY["pyramiding"])
        if self.margin_long > 0 or self.margin_short > 0:
            lines.append(BACKTEST_ONLY["margin_long"])
        if self.process_orders_on_close:
            lines.append(BACKTEST_ONLY["process_orders_on_close"])
        return lines

    def inert_here(self) -> list[str]:
        """The properties that are set and still do nothing. Same rule as above."""
        lines: list[str] = []
        if self.calc_on_every_tick:
            lines.append(INERT["calc_on_every_tick"])
        if self.fill_orders_on_standard_ohlc:
            lines.append(INERT["fill_orders_on_standard_ohlc"])
        if self.backtest_fill_limits_assumption:
            lines.append(INERT["backtest_fill_limits_assumption"])
        if self.calc_on_order_fills and not self.use_bar_magnifier:
            lines.append(INERT["calc_on_order_fills"])
        return lines


def resolve(
    *,
    platform: StrategyProperties | None = None,
    declared: dict | None = None,
    overrides: dict | None = None,
) -> StrategyProperties:
    """Platform default → script → panel, in that order and nowhere else.

    Unknown keys and unusable values are dropped rather than raising: this runs
    behind a validator that has already reported them by name, and a backtest
    that refuses to start because the panel posted a stray key would be hiding
    a report behind a typo.
    """
    base = platform or StrategyProperties()
    from_script = _clean(declared or {})
    from_panel = _clean(overrides or {})
    merged = {**from_script, **from_panel}
    return replace(
        base,
        **merged,
        declared=frozenset(from_script),
        overridden=frozenset(from_panel),
    )


def parse(call: ast.Call) -> tuple[dict, list[tuple[str, str, object]]]:
    """Read the properties off a ``strategy()`` call.

    Returns the declared values and a list of ``(arg, reason, span)`` notes for
    arguments that parsed but will not be honoured — the validator turns those
    into warnings so nothing is dropped silently (Q20).
    """
    values: dict = {}
    notes: list[tuple[str, str, object]] = []

    for arg in call.args:
        name = arg.name
        if not name or name not in PROPERTY_ARGS:
            continue
        parsed = _read(name, arg.value)
        if parsed is _UNREADABLE:
            notes.append(
                (
                    name,
                    f"{name} could not be read as a constant — a property that depends on a "
                    f"series is not a property, so the default stands",
                    arg.span,
                )
            )
            continue
        values[name] = parsed
        if not _departs(name, parsed):
            # Declared at its platform value. `pyramiding = 0` is this platform's
            # own behaviour written out, and warning about it would teach the
            # reader to skip the list the one time it matters.
            continue
        if name in INERT:
            notes.append((name, INERT[name], arg.span))
        elif name in BACKTEST_ONLY:
            notes.append((name, BACKTEST_ONLY[name], arg.span))

    return values, notes


def _departs(name: str, value: object) -> bool:
    """Whether this declared value actually changes anything from the default.

    ``initial_capital`` and ``currency`` never do in the sense that matters —
    they size and label the simulated account and cannot make it behave
    differently from live — so they carry a panel hint but no warning.
    """
    if name in ("initial_capital", "currency", "default_qty_value"):
        return False
    if name == "default_qty_type":
        return value is not QtyType.PLATFORM
    if name in _BOOL_ARGS:
        return bool(value)
    if name in ("pyramiding", "backtest_fill_limits_assumption"):
        return bool(value)
    if name in ("margin_long", "margin_short"):
        return isinstance(value, Decimal) and value > 0
    return False


# --- reading one argument ---------------------------------------------------

_UNREADABLE = object()

_BOOL_ARGS = frozenset(
    {
        "calc_on_order_fills",
        "calc_on_every_tick",
        "process_orders_on_close",
        "use_bar_magnifier",
        "fill_orders_on_standard_ohlc",
    }
)
_INT_ARGS = frozenset({"pyramiding", "backtest_fill_limits_assumption", "slippage"})
_DECIMAL_ARGS = frozenset(
    {"initial_capital", "default_qty_value", "commission_value", "margin_long", "margin_short"}
)


def _read(name: str, node: ast.Node) -> object:
    if name in _BOOL_ARGS:
        return _bool(node)
    if name in _INT_ARGS:
        return _int(node)
    if name in _DECIMAL_ARGS:
        return _decimal(node)
    if name == "default_qty_type":
        return QTY_CONSTANTS.get(ast.dotted_name(node) or "", _UNREADABLE)
    if name == "commission_type":
        return COMMISSION_CONSTANTS.get(ast.dotted_name(node) or "", _UNREADABLE)
    if name == "currency":
        return _currency(node)
    return _UNREADABLE


def _bool(node: ast.Node) -> object:
    return node.value if isinstance(node, ast.BoolLit) else _UNREADABLE


def _number(node: ast.Node) -> Decimal | None:
    if isinstance(node, ast.NumberLit):
        try:
            return Decimal(node.value)
        except InvalidOperation:
            return None
    if isinstance(node, ast.Unary) and node.op == "-":
        inner = _number(node.operand)
        return None if inner is None else -inner
    return None


def _int(node: ast.Node) -> object:
    value = _number(node)
    return _UNREADABLE if value is None else int(value)


def _decimal(node: ast.Node) -> object:
    value = _number(node)
    return _UNREADABLE if value is None else value


def _currency(node: ast.Node) -> object:
    """``currency.USD`` or the bare string ``"USD"`` — TradingView accepts both."""
    dotted = ast.dotted_name(node)
    if dotted and dotted.startswith("currency."):
        code = dotted.split(".", 1)[1]
        return code if code in CURRENCIES else _UNREADABLE
    if isinstance(node, ast.StringLit):
        code = node.value.upper()
        return code if code in CURRENCIES else _UNREADABLE
    return _UNREADABLE


def _clean(raw: dict) -> dict:
    """Coerce a wire/panel dict into the field types, dropping what will not fit."""
    out: dict = {}
    for key, value in raw.items():
        if key not in PROPERTY_ARGS or value is None:
            continue
        try:
            if key in _BOOL_ARGS:
                out[key] = _as_bool(value)
            elif key == "slippage":
                out[key] = int(value)
            elif key in _INT_ARGS:
                out[key] = max(0, int(value))
            elif key in _DECIMAL_ARGS:
                out[key] = Decimal(str(value))
            elif key == "default_qty_type":
                out[key] = QtyType(value)
            elif key == "commission_type":
                out[key] = CommissionType(value)
            elif key == "currency":
                code = str(value).upper()
                if code in CURRENCIES:
                    out[key] = code
        except (ValueError, TypeError, ArithmeticError):
            continue
    return out


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


# --- the Properties tab as a form -------------------------------------------
#
# The panel needs more than the values: it needs to know what kind of control
# each one is, which of TradingView's four groups it belongs in, and — the part
# that matters here — whether editing it changes the backtest only. All of that
# is a fact about the property, not about the page, so it lives here beside the
# rule it describes rather than being restated in TypeScript where it would
# drift the first time one of these sentences is rewritten.
#
# `docs/bots.md` calls this the panel's copy of the Properties tab. It is the
# same list TradingView shows, in the same order, minus nothing: a property this
# platform cannot honour is still *listed*, carrying the sentence that says so,
# because a field that silently vanishes reads as a platform that never heard of
# it (Q20 — parsed-and-dropped is only allowed out loud).


#: TradingView's own grouping, in TradingView's order.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("capital", "Capital & currency"),
    ("sizing", "Position sizing & scaling"),
    ("costs", "Risk, costs & margin"),
    ("execution", "Execution & recalculation"),
)


@dataclass(frozen=True, slots=True)
class PropertyField:
    """One row of the form. Everything the panel needs to draw and police it."""

    key: str
    category: str
    #: "decimal" | "int" | "bool" | "choice" | "currency"
    kind: str
    choices: tuple[str, ...] = ()
    #: Rendered after the input — "%", "ticks", "contracts".
    unit: str = ""
    minimum: Decimal | None = None
    #: Set when the field only ever describes the simulated account. The panel
    #: shows this beside the input, always — not only once it departs — because
    #: the question a reader has *while typing* is "will this reach live".
    backtest_only: str = ""
    #: Set when the field does nothing here at all, even in the backtest.
    inert: str = ""
    #: Read only while another field holds a particular value.
    enabled_when: tuple[str, tuple[str, ...]] | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "category": self.category,
            "kind": self.kind,
            "choices": list(self.choices),
            "unit": self.unit,
            "minimum": None if self.minimum is None else str(self.minimum),
            "backtest_only": self.backtest_only,
            "inert": self.inert,
            "enabled_when": (
                None
                if self.enabled_when is None
                else {"key": self.enabled_when[0], "values": list(self.enabled_when[1])}
            ),
        }


SCHEMA: tuple[PropertyField, ...] = (
    PropertyField(
        key="initial_capital",
        category="capital",
        kind="decimal",
        minimum=Decimal("0.01"),
        backtest_only=BACKTEST_ONLY["initial_capital"],
    ),
    PropertyField(
        key="currency",
        category="capital",
        kind="currency",
        choices=CURRENCIES,
        backtest_only=BACKTEST_ONLY["currency"],
    ),
    PropertyField(
        key="default_qty_type",
        category="sizing",
        kind="choice",
        choices=tuple(member.value for member in QtyType),
        backtest_only=BACKTEST_ONLY["default_qty_type"],
    ),
    PropertyField(
        key="default_qty_value",
        category="sizing",
        kind="decimal",
        minimum=Decimal("0"),
        backtest_only=BACKTEST_ONLY["default_qty_value"],
        # Meaningless under the platform's own sizing: there is no quantity to
        # state when margin is 99% of whatever the account actually holds.
        enabled_when=("default_qty_type", ("fixed", "cash", "percent_of_equity")),
    ),
    PropertyField(
        key="pyramiding",
        category="sizing",
        kind="int",
        unit="entries",
        minimum=Decimal("0"),
        backtest_only=BACKTEST_ONLY["pyramiding"],
    ),
    PropertyField(
        key="commission_type",
        category="costs",
        kind="choice",
        choices=tuple(member.value for member in CommissionType),
    ),
    PropertyField(
        key="commission_value",
        category="costs",
        kind="decimal",
        minimum=Decimal("0"),
    ),
    PropertyField(
        key="slippage",
        category="costs",
        kind="int",
        unit="ticks",
        minimum=Decimal("0"),
    ),
    PropertyField(
        key="margin_long",
        category="costs",
        kind="decimal",
        unit="%",
        minimum=Decimal("0"),
        backtest_only=BACKTEST_ONLY["margin_long"],
    ),
    PropertyField(
        key="margin_short",
        category="costs",
        kind="decimal",
        unit="%",
        minimum=Decimal("0"),
        backtest_only=BACKTEST_ONLY["margin_short"],
    ),
    PropertyField(
        key="process_orders_on_close",
        category="execution",
        kind="bool",
        backtest_only=BACKTEST_ONLY["process_orders_on_close"],
    ),
    PropertyField(key="use_bar_magnifier", category="execution", kind="bool"),
    PropertyField(
        key="calc_on_order_fills",
        category="execution",
        kind="bool",
        inert=INERT["calc_on_order_fills"],
    ),
    PropertyField(
        key="calc_on_every_tick",
        category="execution",
        kind="bool",
        inert=INERT["calc_on_every_tick"],
    ),
    PropertyField(
        key="fill_orders_on_standard_ohlc",
        category="execution",
        kind="bool",
        inert=INERT["fill_orders_on_standard_ohlc"],
    ),
    PropertyField(
        key="backtest_fill_limits_assumption",
        category="execution",
        kind="int",
        unit="ticks",
        minimum=Decimal("0"),
        inert=INERT["backtest_fill_limits_assumption"],
    ),
)

FIELDS: dict[str, PropertyField] = {row.key: row for row in SCHEMA}


def schema_as_data() -> dict:
    """The whole form, for the panel to draw. Static — no per-bot state in here."""
    return {
        "categories": [{"key": key, "label": label} for key, label in CATEGORIES],
        "fields": [row.as_dict() for row in SCHEMA],
    }


def validate_overrides(raw: object) -> tuple[dict, list[dict]]:
    """Clean a panel-supplied override set, reporting what it had to refuse.

    ``resolve`` drops a bad key in silence on purpose — it runs behind a
    validator that has already named it, and a backtest that refused to start
    over a stray key would hide a report behind a typo. A *form post* is the
    other case entirely: the person is looking at the field, so the rule here is
    the opposite one, and nothing is stored that could not be read back.

    Returns ``(clean, errors)``. ``clean`` is safe to hand to ``resolve``.
    """
    errors: list[dict] = []
    if raw in (None, ""):
        return {}, errors
    if not isinstance(raw, dict):
        return {}, [{"key": "", "message": "properties must be an object"}]

    clean: dict = {}
    for key, value in raw.items():
        field_spec = FIELDS.get(key)
        if field_spec is None:
            errors.append({"key": key, "message": f"{key} is not a strategy property"})
            continue
        # An override cleared in the panel comes back as null, and means "stop
        # overriding this" — the script's value, or the platform's, takes over
        # again. Storing it as an explicit null would pin the field to None.
        if value is None or value == "":
            continue

        # Range first, against what was *typed*. `_clean` floors the integer
        # properties at zero, so checking after it would turn "-3 entries" into
        # a silent 0 — which is the one outcome this function exists to prevent.
        if field_spec.kind in ("decimal", "int"):
            try:
                typed = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                errors.append({"key": key, "message": f"{value!r} is not a number"})
                continue
            if field_spec.minimum is not None and typed < field_spec.minimum:
                errors.append(
                    {"key": key, "message": f"{key} cannot be below {field_spec.minimum}"}
                )
                continue

        coerced = _clean({key: value})
        if key not in coerced:
            errors.append({"key": key, "message": f"{value!r} is not a usable value for {key}"})
            continue
        clean[key] = coerced[key]

    return clean, errors


def serialise_overrides(clean: dict) -> dict:
    """Overrides as JSON, for the column they are stored in.

    ``Decimal`` and ``StrEnum`` both survive a round trip through ``_clean``;
    neither survives ``JSONField``. Strings do, and ``_clean`` reads them back.
    """
    out: dict = {}
    for key, value in clean.items():
        if isinstance(value, Decimal):
            out[key] = str(value)
        elif isinstance(value, StrEnum):
            out[key] = value.value
        else:
            out[key] = value
    return out

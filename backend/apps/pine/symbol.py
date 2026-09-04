"""What the script may ask about the *instrument* and the *timeframe*.

``syminfo.mintick``, ``timeframe.period``, ``chart.is_heikinashi`` — the facts a
strategy reads to size a stop, to branch on the interval, or to refuse to run on
synthetic prices. None of them is a bar, so none belongs in ``Bar``; and none of
them may be *looked up* from in here, because ``apps.pine`` reads no settings, no
database and no clock (``bot-plan.md`` §1.1). They arrive as a value the driver
builds, which is also what makes a backtest and a live run see one answer.

Both types carry defaults derived from the strings the platform already has —
the bot's symbol and its interval — so a runtime constructed without them is
still describing the right instrument rather than a blank one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

#: The quote currencies the platform actually trades against, longest first so
#: ``BTCUSDT`` splits before ``USDT`` can be mistaken for ``USD``.
_QUOTES: tuple[str, ...] = ("USDT", "USDC", "BUSD", "TUSD", "USD", "BTC", "ETH", "EUR")

_INTERVAL_RE = re.compile(r"^\s*(\d+)\s*([smhdwM])\s*$")

#: Pine spells an interval as a bare number of minutes, or one of ``S``/``D``/
#: ``W``/``M``. A script comparing ``timeframe.period == "60"`` has to see the
#: same string TradingView would show it.
_PINE_UNITS: dict[str, str] = {"s": "S", "m": "", "h": "", "d": "D", "w": "W", "M": "M"}

_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "M": 2592000,
}


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """One instrument, as ``syminfo.*`` sees it.

    ``mintick`` is the field with teeth: ``math.round_to_mintick`` and any stop
    a script rounds itself go through it. It defaults to ``na``-ish precision
    rather than a guess — the driver passes the exchange's real tick size, and
    ``for_symbol`` leaves a placeholder that is deliberately coarse enough to be
    noticed rather than quietly wrong.
    """

    ticker: str = ""
    tickerid: str = ""
    prefix: str = ""
    currency: str = "USDT"
    basecurrency: str = ""
    mintick: Decimal = Decimal("0.01")
    pointvalue: Decimal = Decimal("1")
    type: str = "crypto"
    timezone: str = "UTC"
    session: str = "24x7"
    description: str = ""
    root: str = ""

    @property
    def minmove(self) -> Decimal:
        """Pine's ``minmove``/``pricescale`` pair, derived so the two agree."""
        return (self.mintick * self.pricescale).quantize(Decimal(1))

    @property
    def pricescale(self) -> Decimal:
        exponent = -self.mintick.normalize().as_tuple().exponent
        return Decimal(10) ** max(0, exponent)

    @classmethod
    def for_symbol(
        cls, symbol: str, *, market: str = "futures", mintick: Decimal | None = None
    ) -> SymbolInfo:
        upper = (symbol or "").upper()
        base, quote = _split_pair(upper)
        return cls(
            ticker=upper,
            tickerid=upper,
            currency=quote,
            basecurrency=base,
            mintick=mintick if mintick is not None else Decimal("0.01"),
            type="crypto",
            description=f"{base}/{quote}" if base and quote else upper,
            root=base,
            session="24x7",
            prefix="",
            timezone="UTC",
            pointvalue=Decimal("1"),
        )


@dataclass(frozen=True, slots=True)
class TimeframeInfo:
    """The bar interval, as ``timeframe.*`` sees it."""

    period: str = "60"
    multiplier: int = 1
    seconds: int = 3600

    @property
    def isseconds(self) -> bool:
        return self.seconds < 60

    @property
    def isminutes(self) -> bool:
        return 60 <= self.seconds < 86400

    @property
    def isintraday(self) -> bool:
        return self.seconds < 86400

    @property
    def isdaily(self) -> bool:
        return self.seconds == 86400

    @property
    def isweekly(self) -> bool:
        return self.seconds == 604800

    @property
    def ismonthly(self) -> bool:
        return self.seconds >= 2592000

    @property
    def isdwm(self) -> bool:
        return not self.isintraday

    @classmethod
    def for_interval(cls, interval: str) -> TimeframeInfo:
        """``"15m"`` → period ``"15"``; ``"1d"`` → ``"D"``. TradingView's spelling.

        An interval this cannot read falls back to one hour rather than raising:
        the feed has already validated it, and a strategy that branches on
        ``timeframe.period`` is reading a label, not deciding an order.
        """
        match = _INTERVAL_RE.match(interval or "")
        if match is None:
            return cls()
        count, unit = int(match.group(1)), match.group(2)
        seconds = count * _SECONDS[unit]
        if unit in ("m", "h"):
            period = str(seconds // 60)
            multiplier = seconds // 60
        else:
            period = f"{count}{_PINE_UNITS[unit]}" if count != 1 else _PINE_UNITS[unit]
            multiplier = count
        return cls(period=period, multiplier=multiplier, seconds=seconds)


def _split_pair(symbol: str) -> tuple[str, str]:
    for quote in _QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""

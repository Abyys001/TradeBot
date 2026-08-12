"""Market data and live position endpoints (spec §3).

The chart, the last price, and the open position's PnL all come from here.

PnL is computed **on this side** and shipped as a string. It could be done in
the browser from the mark price and each leg's fill, but then the formula would
exist twice — and the money invariant ("Decimal everywhere, no floats") only
holds on this side of the wire. One implementation, in Decimal, is the whole
reason this endpoint exists rather than a few extra fields on the trade.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.money import D
from apps.exchanges.base import MarketType, Side
from apps.exchanges.marketdata import (
    DEFAULT_LIMIT,
    INTERVALS,
    get_candles,
    get_ticker,
    normalise_interval,
    normalise_market,
)
from apps.trading.models import Trade, TradeStatus

#: Cap on a single watchlist request. The list is the admin's own and lives in
#: their browser; this only stops a hand-written URL from turning into a
#: hundred outbound calls.
MAX_WATCHLIST = 30

#: Symbols offered in the terminal's picker. A curated list rather than the
#: exchange's full catalogue: every connected account must be able to trade the
#: pair, and the intersection of ten exchanges is small and stable.
SYMBOLS = [
    {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"},
    {"symbol": "ETHUSDT", "base": "ETH", "quote": "USDT"},
    {"symbol": "SOLUSDT", "base": "SOL", "quote": "USDT"},
    {"symbol": "BNBUSDT", "base": "BNB", "quote": "USDT"},
    {"symbol": "XRPUSDT", "base": "XRP", "quote": "USDT"},
    {"symbol": "DOGEUSDT", "base": "DOGE", "quote": "USDT"},
    {"symbol": "ADAUSDT", "base": "ADA", "quote": "USDT"},
    {"symbol": "AVAXUSDT", "base": "AVAX", "quote": "USDT"},
    {"symbol": "LINKUSDT", "base": "LINK", "quote": "USDT"},
    {"symbol": "TONUSDT", "base": "TON", "quote": "USDT"},
]


@api_view(["GET"])
def candles(request):
    """OHLCV for the chart.

    Always answers 200 with data: when no provider is reachable the payload is
    synthetic and carries ``live: false``, which the panel renders as a
    placeholder badge. A chart that 500s tells the admin nothing; a chart that
    silently invents prices is worse than both.
    """
    try:
        interval = normalise_interval(request.query_params.get("interval"))
        market = normalise_market(request.query_params.get("market"))
        limit = int(request.query_params.get("limit") or DEFAULT_LIMIT)
    except (ValueError, TypeError) as exc:
        return Response({"detail": str(exc)}, status=400)

    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper()
    return Response(get_candles(symbol=symbol, interval=interval, market=market, limit=limit))


@api_view(["GET"])
def ticker(request):
    try:
        market = normalise_market(request.query_params.get("market"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper()
    return Response(get_ticker(symbol=symbol, market=market))


@api_view(["GET"])
def tickers(request):
    """Several quotes in one round trip, for the watchlist.

    One request per symbol would be ten requests every few seconds from every
    open panel. Each quote is individually cached, so this loop is cheap and a
    symbol shared with the chart costs nothing at all.
    """
    try:
        market = normalise_market(request.query_params.get("market"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)

    raw = (request.query_params.get("symbols") or "").upper()
    wanted = [s.strip() for s in raw.split(",") if s.strip()][:MAX_WATCHLIST]
    if not wanted:
        return Response({"tickers": []})

    return Response(
        {"tickers": [get_ticker(symbol=symbol, market=market) for symbol in wanted]}
    )


@api_view(["GET"])
def symbols(request):
    return Response({"symbols": SYMBOLS, "intervals": list(INTERVALS)})


@api_view(["GET"])
def positions(request):
    """The open trade, per account, marked to market (spec §3 positions panel).

    Entry price, liquidation price, size, margin, and current PnL — the fields
    the spec names — for every leg that actually filled, plus the totals the
    admin steers by.
    """
    trade = (
        Trade.objects.filter(status=TradeStatus.OPEN)
        .prefetch_related("legs__account")
        .first()
    )
    if trade is None:
        return Response({"trade": None, "legs": [], "totals": None, "mark": None})

    market = MarketType(trade.market)
    quote = get_ticker(symbol=trade.symbol, market=market)
    mark = D(quote["price"])
    direction = Decimal("1") if trade.side == Side.LONG.value else Decimal("-1")
    leverage = Decimal(trade.leverage or 1)

    rows = []
    total_pnl = Decimal("0")
    total_margin = Decimal("0")
    total_qty = Decimal("0")
    for leg in trade.legs.all():
        entry = leg.entry_price
        qty = leg.qty
        if not leg.ok or entry is None or qty is None:
            rows.append(
                {
                    "account": leg.account_id,
                    "account_label": leg.account.label,
                    "exchange": leg.account.exchange,
                    "ok": leg.ok,
                    "error": leg.error,
                    "error_code": leg.error_code,
                    "sltp_attached": leg.sltp_attached,
                    "qty": None,
                    "entry_price": None,
                    "margin": None,
                    "notional": None,
                    "stop_loss": None,
                    "take_profit": None,
                    "liquidation_price": None,
                    "pnl": None,
                    "pnl_pct": None,
                    "roe_pct": None,
                }
            )
            continue

        pnl = (mark - entry) * qty * direction
        margin = leg.margin or (entry * qty / leverage)
        notional = entry * qty
        # Isolated-margin approximation, the same one the ticket shows before
        # sending: the position is liquidated when the loss eats the margin.
        liq = entry * (Decimal("1") - direction / leverage)
        total_pnl += pnl
        total_margin += margin
        total_qty += qty
        rows.append(
            {
                "account": leg.account_id,
                "account_label": leg.account.label,
                "exchange": leg.account.exchange,
                "ok": True,
                "error": "",
                "error_code": "",
                "sltp_attached": leg.sltp_attached,
                "qty": _s(qty),
                "entry_price": _s(entry),
                "margin": _s(margin),
                "notional": _s(notional),
                "stop_loss": _s(leg.stop_loss),
                "take_profit": _s(leg.take_profit),
                "liquidation_price": _s(liq),
                "pnl": _s(pnl),
                # Against notional: how far price has moved in our favour.
                "pnl_pct": _s(pnl / notional * Decimal("100")) if notional else None,
                # Against margin: what the account actually gained or lost.
                "roe_pct": _s(pnl / margin * Decimal("100")) if margin else None,
            }
        )

    return Response(
        {
            "trade": {
                "id": trade.id,
                "symbol": trade.symbol,
                "side": trade.side,
                "market": trade.market,
                "leverage": trade.leverage,
                "sl_pct": _s(trade.sl_pct),
                "tp_pct": _s(trade.tp_pct),
                "sltp_basis": trade.sltp_basis,
                "admin_entry_price": _s(trade.admin_entry_price),
                "opened_at": trade.opened_at,
            },
            "mark": {**quote},
            "legs": rows,
            "totals": {
                "accounts": sum(1 for row in rows if row["ok"]),
                "failed": sum(1 for row in rows if not row["ok"]),
                "qty": _s(total_qty),
                "margin": _s(total_margin),
                "notional": _s(total_qty * mark),
                "pnl": _s(total_pnl),
                "roe_pct": _s(total_pnl / total_margin * Decimal("100")) if total_margin else None,
            },
        }
    )


def _s(value: Decimal | None) -> str | None:
    """Plain decimal string — never scientific notation, which the UI cannot parse."""
    if value is None:
        return None
    return f"{round(D(value), 8).normalize():f}"

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
    MarketDataError,
    get_candles,
    get_ticker,
    normalise_interval,
    normalise_market,
)
from apps.trading.models import Trade, TradeStatus

#: Returned when no exchange is reachable. 503, not 200-with-a-number: the panel
#: has to be able to tell "no feed" from "a price", and every price it draws has
#: to have come from an exchange.
FEED_DOWN = 503

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

    Real exchange data or a 503. There is no placeholder series: a chart that
    says "no feed" is honest, and one that invents candles is how someone reads
    a price that never existed.
    """
    try:
        interval = normalise_interval(request.query_params.get("interval"))
        market = normalise_market(request.query_params.get("market"))
        limit = int(request.query_params.get("limit") or DEFAULT_LIMIT)
    except (ValueError, TypeError) as exc:
        return Response({"detail": str(exc)}, status=400)

    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper()
    try:
        payload = get_candles(symbol=symbol, interval=interval, market=market, limit=limit)
    except MarketDataError as exc:
        return Response({"detail": str(exc), "live": False}, status=FEED_DOWN)
    return Response(payload)


@api_view(["GET"])
def ticker(request):
    try:
        market = normalise_market(request.query_params.get("market"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper()
    try:
        payload = get_ticker(symbol=symbol, market=market)
    except MarketDataError as exc:
        return Response({"detail": str(exc), "live": False}, status=FEED_DOWN)
    return Response(payload)


@api_view(["GET"])
def tickers(request):
    """Several quotes in one round trip, for the watchlist.

    One request per symbol would be ten requests every few seconds from every
    open panel. Each quote is individually cached, so this loop is cheap and a
    symbol shared with the chart costs nothing at all.

    A symbol nobody can quote is *omitted* rather than faked, and named in
    ``unavailable`` so the watchlist can grey that row instead of showing a
    price that was never real.
    """
    try:
        market = normalise_market(request.query_params.get("market"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)

    raw = (request.query_params.get("symbols") or "").upper()
    wanted = [s.strip() for s in raw.split(",") if s.strip()][:MAX_WATCHLIST]
    if not wanted:
        return Response({"tickers": [], "unavailable": []})

    quotes, missing = [], []
    for symbol in wanted:
        try:
            quotes.append(get_ticker(symbol=symbol, market=market))
        except MarketDataError:
            missing.append(symbol)
    return Response({"tickers": quotes, "unavailable": missing})


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
    # The position itself is a fact and is reported either way; only the
    # mark-to-market part needs a price. With no feed the sizes, entries and
    # margins still show and every PnL field is null — an unknown PnL reads as
    # unknown rather than as zero.
    try:
        quote = get_ticker(symbol=trade.symbol, market=market)
        mark = D(quote["price"])
        feed_error = ""
    except MarketDataError as exc:
        quote, mark, feed_error = None, None, str(exc)
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

        pnl = None if mark is None else (mark - entry) * qty * direction
        margin = leg.margin or (entry * qty / leverage)
        notional = entry * qty
        # Isolated-margin approximation, the same one the ticket shows before
        # sending: the position is liquidated when the loss eats the margin.
        liq = entry * (Decimal("1") - direction / leverage)
        if pnl is not None:
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
                "pnl_pct": (
                    _s(pnl / notional * Decimal("100"))
                    if pnl is not None and notional
                    else None
                ),
                # Against margin: what the account actually gained or lost.
                "roe_pct": (
                    _s(pnl / margin * Decimal("100")) if pnl is not None and margin else None
                ),
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
            "mark": None if quote is None else {**quote},
            "feed_error": feed_error,
            "legs": rows,
            "totals": {
                "accounts": sum(1 for row in rows if row["ok"]),
                "failed": sum(1 for row in rows if not row["ok"]),
                "qty": _s(total_qty),
                "margin": _s(total_margin),
                "notional": None if mark is None else _s(total_qty * mark),
                "pnl": None if mark is None else _s(total_pnl),
                "roe_pct": (
                    _s(total_pnl / total_margin * Decimal("100"))
                    if mark is not None and total_margin
                    else None
                ),
            },
        }
    )


def _s(value: Decimal | None) -> str | None:
    """Plain decimal string — never scientific notation, which the UI cannot parse."""
    if value is None:
        return None
    return f"{round(D(value), 8).normalize():f}"

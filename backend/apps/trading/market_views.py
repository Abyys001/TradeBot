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

from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.visibility import _check, _internal_exchanges
from apps.core.money import D
from apps.exchanges.base import MarketType, Side
from apps.exchanges.catalogue import (
    catalogue_sources,
    ensure_history,
    start_sync,
    sync_state,
)
from apps.exchanges.marketdata import (
    DEFAULT_LIMIT,
    INTERVALS,
    MarketDataError,
    get_candles,
    get_ticker,
    normalise_interval,
    normalise_market,
    pinned_provider,
)
from apps.trading.models import ExchangeSymbol, Trade, TradeStatus
from apps.trading.possync import sync_positions
from apps.trading.services import reconcile_open_trade

#: Returned when no exchange is reachable. 503, not 200-with-a-number: the panel
#: has to be able to tell "no feed" from "a price", and every price it draws has
#: to have come from an exchange.
FEED_DOWN = 503

#: Returned while a chart-driven download is running: the chart is *going* to
#: have history, it just does not yet. 503 would read as "permanently no feed"
#: and the panel would stop asking; 202 keeps it polling into the download.
HISTORY_DOWNLOADING = 202

#: Cap on a single watchlist request. The list is the admin's own and lives in
#: their browser; this only stops a hand-written URL from turning into a
#: hundred outbound calls.
MAX_WATCHLIST = 30

#: Returned when nothing has been downloaded yet. Not 200-with-a-list: the
#: picker used to offer ten pairs this platform had simply asserted were
#: tradeable. There is no catalogue until an exchange has been asked for one,
#: and no exchange can be asked without a connected account's API key.
NO_CATALOGUE = 409


@api_view(["GET"])
def candles(request):
    """OHLCV for the chart.

    Real exchange data or a 503. There is no placeholder series: a chart that
    says "no feed" is honest, and one that invents candles is how someone reads
    a price that never existed.

    When the feed is down and the pair has *no* stored history, the pair's own
    download is kicked off (see ``catalogue.ensure_history``) and this answers
    **202** until the worker has stored some bars — the chart is going to have
    history, it just does not yet. Every success carries the download's state
    in ``history`` so the chart can show progress and never re-ask.
    """
    try:
        interval = normalise_interval(request.query_params.get("interval"))
        market = normalise_market(request.query_params.get("market"))
        limit = int(request.query_params.get("limit") or DEFAULT_LIMIT)
        # `end` (UNIX seconds) asks for the window before that moment — how the
        # chart pans back into the downloaded year.
        raw_end = request.query_params.get("end")
        end = int(raw_end) if raw_end else None
    except (ValueError, TypeError) as exc:
        return Response({"detail": str(exc)}, status=400)

    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper()
    try:
        payload = get_candles(
            symbol=symbol, interval=interval, market=market, limit=limit, end=end
        )
    except MarketDataError as exc:
        history = ensure_history(market.value, symbol, interval)
        if history["state"] == "downloading":
            return Response(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "market": market.value,
                    "source": "",
                    "live": False,
                    "stored": False,
                    "pinned": pinned_provider(),
                    "provider_ms": None,
                    "feed_error": str(exc),
                    "candles": [],
                    "history": history,
                },
                status=HISTORY_DOWNLOADING,
            )
        return Response({"detail": str(exc), "live": False}, status=FEED_DOWN)
    payload["history"] = ensure_history(market.value, symbol, interval)
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
    """Every pair the connected exchanges list, as they list them.

    The union across exchanges, so nothing an admin could trade is hidden. Each
    row carries which venues have it — a pair only one exchange lists will skip
    the other accounts at sizing time, and the picker can say so up front.

    With nothing downloaded this answers 409 rather than a list: connect an
    account and its API key, and the catalogue arrives with it.
    """
    try:
        market = normalise_market(request.query_params.get("market"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)

    rows = (
        ExchangeSymbol.objects.filter(market=market.value, active=True)
        .values("symbol", "base", "quote", "exchange", "volume_24h")
        .order_by("symbol")
    )

    # The catalogue is downloaded from the connected exchanges, so a venue
    # reached *only* through a hidden account would otherwise appear in the
    # per-pair venue list. Strip those names, and drop a pair that has nothing
    # left — it exists solely because of a venue this reader must not know is
    # connected. Nothing here is dropped for the viewer, and nothing is dropped
    # for a venue anyone else already trades.
    masked = set() if _check(request.user) else _internal_exchanges()

    merged: dict[str, dict] = {}
    for row in rows:
        if row["exchange"] in masked:
            continue
        entry = merged.setdefault(
            row["symbol"],
            {
                "symbol": row["symbol"],
                "base": row["base"],
                "quote": row["quote"],
                "exchanges": [],
                "volume_24h": None,
            },
        )
        entry["exchanges"].append(row["exchange"])
        volume = row["volume_24h"]
        if volume is not None:
            current = entry["volume_24h"]
            entry["volume_24h"] = _s(volume if current is None else max(D(current), volume))

    if not merged:
        return Response(
            {
                "detail": (
                    "No exchange has been asked for its pairs yet. Connect the "
                    "first account with its API key — the pair list and price "
                    "feed are downloaded from that exchange."
                ),
                "needs_account": True,
                "symbols": [],
                "intervals": list(INTERVALS),
                "sync": sync_state(),
            },
            status=NO_CATALOGUE,
        )

    # Busiest first: what a chart is opened on, with the long tail behind it.
    ordered = sorted(
        merged.values(),
        key=lambda row: (-D(row["volume_24h"] or "0"), row["symbol"]),
    )
    return Response(
        {
            "symbols": ordered,
            "intervals": list(INTERVALS),
            "market": market.value,
            "needs_account": False,
            "sync": sync_state(),
        }
    )


@api_view(["GET", "POST"])
def market_sync(request):
    """Progress of the pair/history download — the bar on the accounts page.

    POST starts one (staff only, like every other write here). GET is the poll
    the bar runs on, and is readable by any signed-in admin.
    """
    if request.method == "POST":
        if not request.user.is_staff:
            return Response({"detail": "staff only"}, status=403)
        if not catalogue_sources():
            return Response(
                {
                    "detail": (
                        "Connect an account first: the pairs and their history "
                        "are downloaded from the exchange that account is on."
                    ),
                    "needs_account": True,
                },
                status=NO_CATALOGUE,
            )
        start_sync(request.data.get("exchange", "") or "", force=bool(request.data.get("force")))
    return Response(sync_state())


@api_view(["GET"])
def positions(request):
    """The open trade, per account, marked to market (spec §3 positions panel).

    Entry price, liquidation price, size, margin, and current PnL — the fields
    the spec names — for every leg that actually filled, plus the totals the
    admin steers by.

    Before reading, two reconciles run, both rate-limited across all pollers so
    ten open tabs are still one read per account:

    - any leg whose entry the exchange never confirmed is re-checked against
      that exchange (``services.reconcile_open_trade``, every
      ``UNCONFIRMED_RECHECK_INTERVAL`` seconds). That is what makes a position
      opened by a request that outran its deadline show up here as a position
      rather than as a failure notice;
    - every leg the platform believes in is checked against what the exchange
      actually holds (``possync.sync_positions``, every
      ``possync.SYNC_INTERVAL`` seconds), which is what keeps a stop that fired
      on the exchange from being drawn here as a live position — and a position
      the exchange holds but the platform had written off from being invisible.

    The panel's picture has to match the exchange's, and this endpoint is the
    picture.
    """
    async_to_sync(reconcile_open_trade)()
    async_to_sync(sync_positions)()
    open_trades = list(
        Trade.objects.filter(status=TradeStatus.OPEN).prefetch_related("legs__account")
    )
    trade = open_trades[0] if open_trades else None
    # This panel draws **one** trade — one symbol, one side, one set of lines.
    # More than one can be open (accounts freed by a close take the next entry
    # while the rest are still in the old trade), and drawing only the first
    # while the others run is the panel reporting flat on a live position. The
    # count says so out loud; the close button flattens all of them.
    others = max(0, len(open_trades) - 1)
    if trade is None:
        return Response(
            {"trade": None, "legs": [], "totals": None, "mark": None, "other_open_trades": 0}
        )

    # Hidden accounts are dropped here, before anything is priced or summed, so
    # the totals below are computed over the visible legs rather than trimmed
    # afterwards. A total that still counted a hidden account's margin would
    # give it away as surely as printing its label.
    legs = list(trade.legs.all())
    if not _check(request.user):
        legs = [leg for leg in legs if not leg.account.hidden]
    if not legs:
        # Every leg of the open trade belongs to an account this reader cannot
        # see, so as far as they are concerned there is no open trade — not an
        # empty one, which would still be an admission that something is running.
        return Response(
            {"trade": None, "legs": [], "totals": None, "mark": None, "other_open_trades": 0}
        )

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
    for leg in legs:
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
                    "sltp_verified": leg.sltp_verified,
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
                "sltp_verified": leg.sltp_verified,
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
            "other_open_trades": others,
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

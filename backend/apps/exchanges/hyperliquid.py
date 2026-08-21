"""Hyperliquid.

The odd one out on this platform. No API key/secret: actions are signed with an
**agent (API) wallet** private key using EIP-712. See
``reference/exchanges/hyperliquid/README.md`` for the constraints that shaped
this adapter.

Two decisions worth stating:

1. **The official SDK does the signing.** EIP-712 action hashing is easy to get
   subtly wrong and a wrong signature is a rejected order, so correctness beats
   a hand-rolled implementation here. The SDK is synchronous, so every call is
   pushed to a worker thread — a blocking call on the event loop would stall
   every other account's leg and blow the spec §4 budget.

2. **Queries use the master address, actions use the agent key.** Querying the
   agent address returns empty results; that pitfall is called out in the docs
   and is why ``wallet_address`` is a separate stored field.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.core.money import D, floor_to_step
from apps.exchanges.base import (
    AdapterError,
    AuthError,
    Balance,
    Capabilities,
    ClosedFill,
    ExchangeAdapter,
    MarketType,
    NotSupported,
    OrderResult,
    OrderType,
    Position,
    Side,
    SLTPState,
    SymbolRules,
)

logger = logging.getLogger(__name__)

MAINNET = "https://api.hyperliquid.xyz"
TESTNET = "https://api.hyperliquid-testnet.xyz"


def _sdk_timeout() -> float:
    """Per-request ceiling for the SDK, derived from the spec §4 deadline.

    Was a hardcoded 5s, which is longer than the whole per-leg budget: a hung
    request was killed by the fan-out with a bare "exceeded the deadline"
    instead of the SDK reporting what it was waiting for. Sitting just under
    the budget keeps the useful error.
    """
    from django.conf import settings

    return max(1.0, float(settings.TRADING["FANOUT_TIMEOUT_SECONDS"]) * 0.75)


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"
    capabilities = Capabilities(
        # Perpetuals only. Spot is a different asset namespace (@N indices, and
        # MAX_DECIMALS 8 rather than 6), and every spot path in this adapter
        # raises NotSupported — declaring SPOT here made the seam lie about it.
        markets=frozenset({MarketType.FUTURES}),
        has_testnet=True,
        # The entry and its TP/SL go out as one signed action (``normalTpsl``),
        # so a position is never live on the exchange without its protection.
        native_sltp_on_entry=True,
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,  # address-based; sub-accounts count separately
        wallet_based_auth=True,
    )

    def __init__(
        self,
        *,
        agent_private_key: str,
        account_address: str,
        testnet: bool = False,
        **_: Any,
    ) -> None:
        if not agent_private_key:
            raise AuthError("hyperliquid: no agent wallet private key configured")
        if not account_address:
            raise AuthError(
                "hyperliquid: the master account address is required — querying the "
                "agent address returns empty results"
            )
        self.account_address = account_address
        self.testnet = testnet
        self._url = TESTNET if testnet else MAINNET
        self._key = agent_private_key
        self._exchange: Any = None
        self._info: Any = None
        self._meta: dict[str, dict] = {}
        #: Serialises the one-time SDK construction. A leg opens with three
        #: concurrent calls (balance, rules, leverage), so without this a cold
        #: adapter builds the SDK three times over and downloads the asset
        #: metadata with it — the expensive thing this adapter now does once.
        self._build_lock = asyncio.Lock()
        #: SDK calls whose awaiter has been cancelled but whose worker thread is
        #: still running. See ``settle_inflight``.
        self._inflight: set[asyncio.Future] = set()

    # --- SDK plumbing -------------------------------------------------------

    def _build(self) -> None:
        """Construct the SDK clients, fetching the asset metadata exactly once.

        The obvious spelling — construct ``Info``, then construct ``Exchange`` —
        downloads that metadata **twice**: ``Info.__init__`` posts ``spotMeta``
        and ``meta`` to build its name→asset maps, and ``Exchange.__init__``
        builds an ``Info`` of its own, which does it again. Four blocking POSTs
        plus two cold TLS handshakes, and all of it inside the spec §4 per-leg
        deadline on the first action after a restart.

        Fetching the two payloads here and handing them to both constructors
        makes it two POSTs on one connection, and neither constructor then
        reaches the network at all. Combined with the adapter staying warm
        between actions (``apps.exchanges.pool``) it is paid once per process
        rather than once per order.
        """
        from eth_account import Account
        from hyperliquid.api import API
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info

        timeout = _sdk_timeout()
        wallet = Account.from_key(self._key)

        # One session, two calls. These are public /info reads — no signature,
        # no credentials — so nothing here touches the wallet.
        api = API(self._url, timeout)
        spot_meta = api.post("/info", {"type": "spotMeta"})
        meta = api.post("/info", {"type": "meta"})

        # positional args: (base_url, skip_ws, meta, spot_meta)
        self._info = Info(self._url, True, meta, spot_meta, timeout=timeout)
        self._exchange = Exchange(
            wallet=wallet,
            base_url=self._url,
            meta=meta,
            spot_meta=spot_meta,
            account_address=self.account_address,
            timeout=timeout,
        )

    async def _ensure_built(self) -> None:
        """Build the SDK once, however many callers arrive at the same moment."""
        if self._exchange is not None:
            return
        async with self._build_lock:
            if self._exchange is None:
                await asyncio.to_thread(self._build)

    async def warm(self) -> None:
        """Build the SDK now so no order pays for it inside the §4 deadline."""
        try:
            await self._ensure_built()
        except Exception as exc:  # noqa: BLE001 - warming is best effort
            logger.warning("hyperliquid: could not warm the client: %s", exc)

    async def _call(self, fn_name: str, *args, **kwargs) -> Any:
        """Run a synchronous SDK call off the event loop.

        Timed and logged because the SDK talks over ``requests``: unlike the
        public feed's httpx calls, nothing else leaves a trace of an order
        going out, so a leg that overran the deadline looked from the log like
        a leg that never sent anything. It is the opposite — see
        ``fanout.NEVER_SENT_CODES``.

        The call is **shielded**. ``asyncio.wait_for`` in the fan-out cancels
        the coroutine awaiting it, and that cancellation cannot reach the
        worker thread already inside ``requests`` — the signed order goes out
        regardless. Shielding keeps the running call reachable in
        ``_inflight`` instead of orphaning it, so ``settle_inflight`` can wait
        for the real answer rather than have the reconcile guess from a
        position read taken while the order was still on its way.
        """
        await self._ensure_built()
        target = self._exchange if hasattr(self._exchange, fn_name) else self._info
        fn = getattr(target, fn_name)
        started = time.perf_counter()
        call = asyncio.ensure_future(asyncio.to_thread(fn, *args, **kwargs))
        self._inflight.add(call)
        call.add_done_callback(self._settled)
        try:
            result = await asyncio.shield(call)
        except asyncio.CancelledError:
            # The deadline fired. The call is still running and still tracked;
            # nothing here may swallow the cancellation.
            raise
        except Exception as exc:  # SDK raises bare exceptions
            logger.warning(
                "hyperliquid %s failed after %.0fms: %s",
                fn_name,
                (time.perf_counter() - started) * 1000,
                exc,
                extra={"exchange": self.name},
            )
            raise AdapterError(f"hyperliquid: {exc}") from exc
        logger.info(
            "hyperliquid %s %.0fms",
            fn_name,
            (time.perf_counter() - started) * 1000,
            extra={"exchange": self.name},
        )
        return self._check(result)

    def _settled(self, call: asyncio.Future) -> None:
        """Drop a finished call, and read its exception so nobody warns about it.

        A call abandoned at the deadline usually finishes with no awaiter left;
        without this, one that raised would surface as "Task exception was
        never retrieved" from the loop's handler instead of the leg's own
        error, which is already recorded.
        """
        self._inflight.discard(call)
        if not call.cancelled():
            call.exception()

    async def settle_inflight(self, timeout: float) -> bool:
        pending = [call for call in self._inflight if not call.done()]
        if not pending:
            return True
        logger.info(
            "hyperliquid: waiting up to %.1fs for %d abandoned call(s) to finish",
            timeout,
            len(pending),
            extra={"exchange": self.name},
        )
        _, still_running = await asyncio.wait(pending, timeout=timeout)
        return not still_running

    def _check(self, result: Any) -> Any:
        if isinstance(result, dict) and result.get("status") == "err":
            raise AdapterError(f"hyperliquid: {result.get('response')}")
        if isinstance(result, dict):
            response = result.get("response", {})
            statuses = (response.get("data") or {}).get("statuses") or []
            for status in statuses:
                if isinstance(status, dict) and "error" in status:
                    raise AdapterError(f"hyperliquid: {status['error']}")
        return result

    async def close(self) -> None:
        # Both SDK clients own a ``requests.Session``. The pool closes adapters
        # when an account's credentials change or it is deleted; dropping the
        # references without closing the sessions leaks a pooled TLS connection
        # per rotation in a long-lived ASGI process.
        for client in (self._exchange, self._info):
            session = getattr(client, "session", None)
            if session is not None:
                session.close()
        self._exchange = None
        self._info = None

    @staticmethod
    def _statuses(result: Any) -> list:
        return ((result.get("response") or {}).get("data") or {}).get("statuses") or []

    @staticmethod
    def _order_id(statuses: list) -> str:
        """The exchange's ``oid`` out of an order response.

        Hyperliquid reports one status per order, shaped ``{"filled": {...}}``
        or ``{"resting": {...}}``, each carrying its own ``oid``. This used to
        return ``str(statuses)`` — the whole list stringified — which is not an
        identifier and cannot be handed back to ``cancel``.
        """
        for status in statuses:
            if not isinstance(status, dict):
                continue
            for leg in status.values():
                if isinstance(leg, dict) and leg.get("oid") is not None:
                    return str(leg["oid"])
        return ""

    @staticmethod
    def _cloid(client_order_id: str | None) -> Any:
        """Map an engine order id onto Hyperliquid's 16-byte client id.

        The engine's ids are arbitrary strings; a Cloid must be exactly 16 bytes
        of hex. Digesting is what makes the mapping deterministic, which is the
        only property that matters here — the same engine id must produce the
        same Cloid so a retried leg is deduplicated rather than doubled.
        """
        if not client_order_id:
            return None
        from hyperliquid.utils.types import Cloid

        digest = hashlib.blake2b(client_order_id.encode(), digest_size=16).digest()
        return Cloid.from_int(int.from_bytes(digest, "big"))

    def _coin(self, symbol: str) -> str:
        """BTCUSDT -> BTC. Hyperliquid perps are named by base asset alone."""
        upper = symbol.upper()
        for quote in ("USDT", "USDC", "USD"):
            if upper.endswith(quote):
                return upper[: -len(quote)]
        return upper

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        state = await self._call("user_state", self.account_address)
        if not isinstance(state, dict) or "marginSummary" not in state:
            raise AuthError(
                "hyperliquid: could not read the account state. Check that the "
                "master address is correct and the agent wallet is approved."
            )
        # The state read proves the agent is approved for this master account.
        # It proves nothing about withdrawal rights: the docs do not state
        # whether an agent wallet can sign a withdrawal (questions.md Q11).
        # Returning normally would mark the account "§7 verified" off a check
        # that never ran, so report the gap — the account connects, flagged.
        logger.warning(
            "hyperliquid: agent-wallet withdrawal rights are unverified (questions.md Q11); "
            "account %s connected without a spec §7 permission check",
            self.account_address,
        )
        raise NotSupported(
            "hyperliquid: the agent wallet is approved, but whether an agent can "
            "sign withdrawals is not documented (questions.md Q11), so §7 cannot "
            "be proven. Verify on testnet before connecting real capital."
        )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        # Hyperliquid perps are USDC-margined. It is reported as USDT to the
        # sizing layer because it is the account's dollar collateral, but the
        # real asset name is surfaced so the dashboard can show the truth.
        state = await self._call("user_state", self.account_address)
        summary = state.get("marginSummary", {})
        withdrawable = D(str(state.get("withdrawable", "0")))
        return Balance(
            asset="USDT",
            available=withdrawable,
            total=D(str(summary.get("accountValue", "0"))),
        )

    async def _load_meta(self) -> None:
        meta = await self._call("meta")
        for entry in meta.get("universe", []):
            self._meta[entry["name"]] = entry

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported("hyperliquid: this adapter covers perpetuals only")
        coin = self._coin(symbol)
        if not self._meta:
            await self._load_meta()
        entry = self._meta.get(coin)
        if entry is None:
            raise AdapterError(f"hyperliquid: unknown coin {coin}")
        # szDecimals fixes the size grid; prices carry at most 5 significant
        # figures and (6 - szDecimals) decimal places.
        size_decimals = int(entry.get("szDecimals", 3))
        return SymbolRules(
            symbol=symbol,
            price_tick=D(1).scaleb(-(6 - size_decimals)),
            qty_step=D(1).scaleb(-size_decimals),
            min_qty=D(1).scaleb(-size_decimals),
            # Documented minimum order value; orders below it are rejected with
            # minTradeNtlRejected.
            min_notional=D("10"),
            max_leverage=int(entry.get("maxLeverage", 10)),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        mids = await self._call("all_mids")
        coin = self._coin(symbol)
        if coin not in mids:
            raise AdapterError(f"hyperliquid: no mid price for {coin}")
        return D(str(mids[coin]))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._call("update_leverage", leverage, self._coin(symbol), True)

    async def place_order(
        self,
        *,
        symbol: str,
        market: MarketType,
        side: Side,
        qty: Decimal,
        order_type: OrderType,
        limit_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> OrderResult:
        coin = self._coin(symbol)
        rules = await self.get_symbol_rules(symbol, market)
        size = floor_to_step(qty, rules.qty_step)
        if size <= 0:
            raise AdapterError(f"hyperliquid: size {qty} rounds to zero")

        is_buy = side is Side.LONG
        if order_type is OrderType.MARKET:
            # There is no market order type — an aggressive IOC limit is the
            # documented equivalent. 5% crossing matches the SDK default.
            mid = await self.get_mark_price(symbol)
            price = self._crossed(mid, is_buy, rules)
            hl_type = {"limit": {"tif": "Ioc"}}
        else:
            if limit_price is None:
                raise AdapterError("hyperliquid: limit order needs a price")
            price = limit_price
            hl_type = {"limit": {"tif": "Gtc"}}

        entry: dict[str, Any] = {
            "coin": coin,
            "is_buy": is_buy,
            "sz": float(size),
            "limit_px": float(self._round_price(price, rules)),
            "order_type": hl_type,
            "reduce_only": reduce_only,
        }
        cloid = self._cloid(client_order_id)
        if cloid is not None:
            entry["cloid"] = cloid

        # The protection rides **with the entry**, in the same signed action,
        # under the ``normalTpsl`` grouping — the OCO form the Hyperliquid order
        # form itself sends. Attaching afterwards was a second signed round trip
        # with a live leveraged position in between: anything that stopped it
        # (the §4 deadline cancelling the leg, a rejection, a dropped
        # connection) left the position on the exchange with no stop at all.
        # One action cannot land half, so there is no such window.
        #
        # Hyperliquid places the children when the parent fully fills — which is
        # what an IOC market entry does — and holds them tied to the parent
        # while a limit order rests. ``get_sltp`` reads both states back, and
        # the executor still verifies: this removes the window, it does not
        # replace the read-back.
        children = self._tpsl_requests(
            coin=coin,
            exit_is_buy=not is_buy,
            size=size,
            rules=rules,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        result = await self._call("bulk_orders", [entry, *children], None, "normalTpsl")

        statuses = self._statuses(result)
        # One status per request, in order: the parent first, then the children.
        # Only the parent's fill describes the entry — a child's resting oid is
        # not this order's id and its size is not a fill.
        parent = statuses[:1]
        for kind, status in zip(
            [request["order_type"]["trigger"]["tpsl"] for request in children],
            statuses[1:],
            strict=False,
        ):
            if isinstance(status, dict) and "error" in status:
                raise AdapterError(
                    f"hyperliquid: entry accepted but the {kind} order was rejected: "
                    f"{status['error']}",
                    code="sltp_rejected",
                )

        filled = size
        avg = price
        for status in parent:
            if isinstance(status, dict) and "filled" in status:
                filled = D(str(status["filled"].get("totalSz", size)))
                avg = D(str(status["filled"].get("avgPx", price)))
            elif isinstance(status, dict) and "error" in status:
                raise AdapterError(f"hyperliquid: order rejected: {status['error']}")
        return OrderResult(
            order_id=self._order_id(parent), filled_qty=filled, avg_price=avg, raw=result
        )

    def _tpsl_requests(
        self,
        *,
        coin: str,
        exit_is_buy: bool,
        size: Decimal,
        rules: SymbolRules,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> list[dict[str, Any]]:
        """The reduce-only trigger orders for one position, as bulk requests.

        Shared by the entry attach (``normalTpsl``, tied to the parent order)
        and the standalone attach (``positionTpsl``, tied to the position) so
        the two cannot describe the protection differently.
        """
        requests: list[dict[str, Any]] = []
        for price, kind in ((stop_loss, "sl"), (take_profit, "tp")):
            if price is None:
                continue
            trigger = float(self._round_price(price, rules))
            requests.append(
                {
                    "coin": coin,
                    "is_buy": exit_is_buy,
                    "sz": float(size),
                    # The trigger fires a *market* exit, and on Hyperliquid that
                    # is still a limit order under the hood. Priced at the
                    # trigger it can fire and sit unfilled — the stop that does
                    # not stop. Cross by the same 5% ``place_order`` uses.
                    "limit_px": float(self._crossed(D(str(trigger)), exit_is_buy, rules)),
                    "order_type": {
                        "trigger": {"triggerPx": trigger, "isMarket": True, "tpsl": kind}
                    },
                    "reduce_only": True,
                }
            )
        return requests

    def _round_price(self, price: Decimal, rules: SymbolRules) -> Decimal:
        """Snap a price onto Hyperliquid's grid, or it is tickRejected.

        Hyperliquid has **no uniform tick size**. A price is valid when it has
        at most 5 significant figures and no more than ``6 - szDecimals``
        decimal places (perps: ``MAX_DECIMALS`` = 6); integer prices are valid
        regardless of significant figures. The old reading — floor to a
        ``10 ** -(6 - szDecimals)`` grid — passed 63016.4 for BTC
        (6 significant figures, tick 0.1) and the exchange rejected it.

        ``qty_step`` carries ``10 ** -szDecimals``, so the size grid names the
        price rule too. This mirrors the official SDK's ``rounding.py``: above
        100k round to an integer, otherwise round to the tighter of the two
        bounds (half-up; any mode lands on the grid, the SDK's rounding is
        nearest).
        """
        price = D(price)
        if price > D("100000"):
            return price.to_integral_value(rounding=ROUND_HALF_UP)
        size_decimals = -rules.qty_step.as_tuple().exponent
        sig_fig_dp = max(0, 4 - price.adjusted())
        decimal_places = min(sig_fig_dp, 6 - size_decimals)
        return price.quantize(D(1).scaleb(-decimal_places), rounding=ROUND_HALF_UP)

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        """Resting reduce-only trigger orders on this coin (Q5d snapshot).

        ``frontendOpenOrders`` rather than ``openOrders``: only the former
        carries ``isTrigger``/``reduceOnly``, and without those a plain resting
        limit order the partner placed would look like protection and be
        cancelled on the next SL/TP change.

        Top-level rows only, deliberately: a child riding on an unfilled parent
        has not been placed and has nothing to cancel — cancelling the parent is
        what removes it, and that is the entry, not the protection.
        """
        coin = self._coin(symbol)
        orders = await self._call("frontend_open_orders", self.account_address)
        return [
            str(order["oid"])
            for order in orders or []
            if isinstance(order, dict)
            if order.get("coin") == coin
            and order.get("isTrigger")
            and order.get("reduceOnly")
            and order.get("oid") is not None
        ]

    async def get_sltp(self, symbol: str) -> SLTPState:
        """The trigger orders Hyperliquid actually holds for this coin.

        ``frontendOpenOrders`` is also what ``list_conditional_orders`` uses, so
        the read-back sees exactly the set the Q5d strategy would cancel — the
        two cannot disagree about what "resting protection" means. A trigger
        Hyperliquid silently dropped is a missing leg here, which is the whole
        point of the read-back.

        **Children are included.** A TP/SL sent with the entry under
        ``normalTpsl`` is placed outright once the parent fills, and until then
        rides on the parent as a child row. Both are protection the exchange is
        holding, and a read-back that saw only the first would report a resting
        limit order as unprotected — which under the Q5e policy closes a
        perfectly good position at market.

        The row shape is the flat one ``frontendOpenOrders`` documents
        (``triggerPx``/``orderType`` at the top level, ``children`` alongside),
        not the nested ``{"order": {...}}`` of an order-status response. Reading
        the nested shape was why this returned an empty state for every account:
        placed protection read back as absent, and the leg failed — or worse,
        was closed — with the stop and target sitting on the exchange the whole
        time.
        """
        coin = self._coin(symbol)
        orders = await self._call("frontend_open_orders", self.account_address)
        stop_loss = take_profit = None
        for order in self._flatten(orders):
            if order.get("coin") != coin or not order.get("isTrigger"):
                continue
            price = self._trigger_price(order)
            if price is None:
                continue
            kind = self._tpsl_kind(order)
            if kind == "sl":
                stop_loss = price
            elif kind == "tp":
                take_profit = price
        return SLTPState(stop_loss=stop_loss, take_profit=take_profit)

    @staticmethod
    def _flatten(orders: Any) -> list[dict]:
        """Frontend order rows plus the children hanging off them, one flat list."""
        flat: list[dict] = []
        for order in orders or []:
            if not isinstance(order, dict):
                continue
            flat.append(order)
            flat.extend(child for child in order.get("children") or [] if isinstance(child, dict))
        return flat

    @staticmethod
    def _tpsl_kind(order: dict) -> str | None:
        """Which half of the protection a trigger row is.

        ``frontendOpenOrders`` names it in ``orderType`` — "Stop Market",
        "Take Profit Limit" and so on — rather than carrying the ``tpsl`` tag
        the *order request* uses. Both spellings are read: the tag when a
        response happens to carry it, the order type otherwise.
        """
        tag = order.get("tpsl") or ((order.get("order") or {}).get("tpsl"))
        if tag in ("sl", "tp"):
            return tag
        order_type = str(order.get("orderType") or "").lower()
        if "take profit" in order_type:
            return "tp"
        if "stop" in order_type:
            return "sl"
        return None

    @staticmethod
    def _trigger_price(order: dict) -> Decimal | None:
        """``triggerPx`` out of a frontend order row, if it is a real price.

        Hyperliquid writes ``"0.0"`` on rows that are not triggers, so a zero is
        "no trigger here", not a trigger at zero.
        """
        raw = order.get("triggerPx")
        if raw is None:
            trigger = (order.get("order") or {}).get("trigger")
            raw = trigger.get("triggerPx") if isinstance(trigger, dict) else None
        if raw is None:
            return None
        price = D(str(raw))
        return price or None

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        """The whole stale set in **one** signed action.

        ``Exchange.cancel`` is a one-element ``bulk_cancel``, so a loop over it
        was N sequential round trips inside the spec §4 per-leg deadline — on a
        venue answering in ~1s that is what pushed an amend past the deadline
        and left the leg on its previous stop. One action, N ids.
        """
        if not order_ids:
            return
        coin = self._coin(symbol)
        try:
            await self._call(
                "bulk_cancel", [{"coin": coin, "oid": int(order_id)} for order_id in order_ids]
            )
        except (AdapterError, ValueError) as exc:
            # "Order was never placed, already canceled, or filled" — the
            # trigger fired between the snapshot and this call.
            if "never placed" not in str(exc).lower():
                raise

    async def set_sltp(
        self,
        *,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
        position: Position | None = None,
    ) -> None:
        """Places new trigger orders. Hyperliquid has no amend for these, so the
        previous pair is cancelled by ``executor.apply_sltp`` (Q5d).

        **Both legs go out in one signed action** (``bulk_orders`` with the
        ``positionTpsl`` grouping — what the Hyperliquid position form itself
        sends). The obvious spelling, one ``order`` call per leg, was two signed
        round trips inside the spec §4 per-leg deadline, and it failed in the
        worst possible shape: the stop went out first, so anything that stopped
        the second call — the fan-out deadline cancelling the leg mid-attach, a
        rejection, a dropped connection — left the position on the exchange with
        a stop and **no take profit**, which is exactly the state reported from
        the live stack. One action cannot land half.

        ``positionTpsl`` also ties the pair to the position rather than to a
        fixed size, so the two cannot drift apart from what is actually held.
        """
        coin = self._coin(symbol)
        # Neither read depends on the other, and this runs inside the §4 per-leg
        # deadline with a signed L1 action still to come — a serial pair here was
        # a whole round trip out of the budget for nothing. A ``position`` the
        # amend path already read drops the ``user_state`` call entirely; the
        # rules read is served from the cached asset metadata.
        rules_call = self.get_symbol_rules(symbol, MarketType.FUTURES)
        if position is None:
            position, rules = await asyncio.gather(self.get_position(symbol), rules_call)
        else:
            rules = await rules_call
        if position is None:
            raise AdapterError(
                f"hyperliquid: no open position on {symbol}", code="no_position"
            )
        # Exit side is the opposite of the position.
        is_buy = position.side is Side.SHORT

        requests = self._tpsl_requests(
            coin=coin,
            exit_is_buy=is_buy,
            size=position.size,
            rules=rules,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        kinds = [request["order_type"]["trigger"]["tpsl"] for request in requests]
        if not requests:
            return

        result = await self._call("bulk_orders", requests, None, "positionTpsl")
        statuses = ((result.get("response") or {}).get("data") or {}).get("statuses") or []
        for kind, status in zip(kinds, statuses, strict=False):
            if isinstance(status, dict) and "error" in status:
                raise AdapterError(f"hyperliquid: {kind} order rejected: {status['error']}")

    def _crossed(self, price: Decimal, is_buy: bool, rules: SymbolRules) -> Decimal:
        """A price aggressive enough that a triggered market exit actually fills."""
        return self._round_price(price * (D("1.05") if is_buy else D("0.95")), rules)

    async def get_position(self, symbol: str) -> Position | None:
        coin = self._coin(symbol)
        state = await self._call("user_state", self.account_address)
        for entry in state.get("assetPositions", []):
            position = entry.get("position", {})
            if position.get("coin") != coin:
                continue
            size = D(str(position.get("szi", "0")))
            if size == 0:
                continue
            leverage = position.get("leverage", {})
            return Position(
                symbol=symbol,
                side=Side.LONG if size > 0 else Side.SHORT,
                size=abs(size),
                entry_price=D(str(position.get("entryPx") or "0")),
                liquidation_price=D(str(position.get("liquidationPx") or "0")) or None,
                unrealized_pnl=D(str(position.get("unrealizedPnl", "0"))),
                leverage=int(leverage.get("value", 1)) if isinstance(leverage, dict) else 1,
            )
        return None

    async def get_closed_pnl(self, symbol: str, since: datetime) -> ClosedFill | None:
        """Rebuild the exit from the venue's own fills (``userFillsByTime``).

        A stop or liquidation on Hyperliquid leaves nothing behind except the
        fills, and those carry ``closedPnl`` per fill — the exchange's realised
        PnL, computed against its own entry basis, which is why it is preferred
        over ``(exit - entry) * qty`` here. ``closedPnl`` is gross, so the fees
        on the same fills are subtracted to get what the account actually kept.

        Only reducing fills count. Anything that opened or added to the
        position has ``closedPnl`` of zero and an ``Open``/``Buy`` direction,
        and averaging its price into the exit would move the exit toward the
        entry.
        """
        coin = self._coin(symbol)
        start_ms = int(since.timestamp() * 1000)
        fills = await self._call("user_fills_by_time", self.account_address, start_ms)
        if not isinstance(fills, list):
            return None

        notional = D("0")
        qty = D("0")
        pnl = D("0")
        fees = D("0")
        last_ms = 0
        for fill in fills:
            if not isinstance(fill, dict) or fill.get("coin") != coin:
                continue
            direction = str(fill.get("dir", ""))
            if not ("Close" in direction or "Liquidat" in direction or ">" in direction):
                continue
            size = D(str(fill.get("sz", "0")))
            if size <= 0:
                continue
            qty += size
            notional += size * D(str(fill.get("px", "0")))
            pnl += D(str(fill.get("closedPnl", "0")))
            fees += D(str(fill.get("fee", "0")))
            last_ms = max(last_ms, int(fill.get("time", 0)))

        if qty <= 0:
            return None
        return ClosedFill(
            exit_price=notional / qty,
            qty=qty,
            realised_pnl=pnl - fees,
            fees=fees,
            closed_at=datetime.fromtimestamp(last_ms / 1000, UTC) if last_ms else None,
        )

    async def close_position(self, symbol: str) -> OrderResult:
        position = await self.get_position(symbol)
        if position is None:
            # Coded, because "already flat" is the outcome a close wanted, not a
            # failure that should keep the trade open in the panel.
            raise AdapterError(
                f"hyperliquid: no open position to close on {symbol}", code="no_position"
            )
        coin = self._coin(symbol)
        rules = await self.get_symbol_rules(symbol, MarketType.FUTURES)
        # Exit direction: opposite of the position side.
        is_buy = position.side is Side.SHORT
        mid = await self.get_mark_price(symbol)
        # Aggressive IOC limit: 5% crossing, same as place_order for MARKET.
        price = float(self._crossed(mid, is_buy, rules))
        result = await self._call(
            "order",
            coin,
            is_buy,
            float(position.size),
            price,
            {"limit": {"tif": "Ioc"}},
            True,  # reduce_only
        )
        filled = position.size
        avg = mid
        statuses = self._statuses(result)
        for status in statuses:
            if isinstance(status, dict) and "filled" in status:
                filled = D(str(status["filled"].get("totalSz", position.size)))
                avg = D(str(status["filled"].get("avgPx", mid)))
        return OrderResult(
            order_id=self._order_id(statuses),
            filled_qty=filled,
            avg_price=avg,
            raw=result,
        )

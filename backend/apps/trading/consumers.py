"""WebSocket channel to the admin panel.

Carries live position/balance updates and — the one that matters for spec §4 —
per-leg failure notifications the moment a leg fails, rather than after the
whole fan-out settles.
"""

from __future__ import annotations

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.visibility import _check
from apps.trading import streamhub

GROUP = "trading"

logger = logging.getLogger(__name__)


@sync_to_async
def _hidden_ids() -> set[int]:
    """Accounts this socket must never mention.

    Read per broadcast rather than captured at connect: an account hidden while
    a panel is already open must vanish from that panel's next update, not at
    its next reload. The query is a single indexed lookup and every caller runs
    *after* a fan-out has settled, so it is nowhere near the spec §4 budget.
    """
    from apps.accounts.visibility import _internal_ids

    return _internal_ids()


@sync_to_async
def _exchange_latency() -> dict:
    """Last measured engine→exchange round trip, straight from the cache.

    Read, never measured, because this sits on the pong path: an outbound HTTP
    call here would land inside the round trip the browser is timing and the
    *panel* latency would report the exchange's slowness as the admin's own.
    """
    from apps.exchanges.marketdata import provider_latency

    return provider_latency()


@sync_to_async
def _probe_exchange_latency() -> None:
    """Measure one real round trip, off the pong path, only when it is stale.

    The reading used to be a by-product of whatever the panel happened to be
    polling, which broke in exactly the case that matters: once bars stream
    over a WebSocket the REST polls drop to one every two minutes, the cached
    round trip expires, and "Exchange latency" goes blank on a deployment where
    everything is working. A settings page that never opens the chart measured
    nothing at all.

    `probe_latency` is debounced platform-wide, so however many panels are
    connected this costs one ticker call every 25 seconds — and the answer it
    caches is a real quote the chart would have fetched anyway.
    """
    from apps.exchanges.marketdata import probe_latency

    try:
        probe_latency()
    except Exception:  # noqa: BLE001 - a diagnostic must never break the channel
        logger.debug("exchange latency probe failed", exc_info=True)


#: Strong references to in-flight warm-ups. A bare ``create_task`` can be
#: garbage collected mid-build; this is the documented way to keep it alive.
_warmups: set[asyncio.Task] = set()


def _kick_warmup() -> None:
    """Build the exchange clients in the background, off the order path.

    Fire and forget on purpose: the panel must connect at the speed of the
    handshake, not at the speed of the slowest venue, and a warm-up that fails
    costs nothing — the next real call builds the client as it always did.
    """
    from apps.trading.services import warm_adapters

    async def run() -> None:
        try:
            await warm_adapters()
        except Exception:  # noqa: BLE001 - warming must never break the channel
            logger.debug("adapter warm-up failed", exc_info=True)

    task = asyncio.create_task(run())
    _warmups.add(task)
    task.add_done_callback(_warmups.discard)


class TradingConsumer(AsyncJsonWebsocketConsumer):
    #: The market room this socket is watching, or "" for none. An instance
    #: attribute rather than a lazily-set one so `disconnect` can rely on it
    #: even when the socket is refused before ever subscribing.
    market_room = ""

    #: The in-flight latency probe, so a socket that closes mid-probe does not
    #: leave a task measuring an exchange for nobody.
    _probe: asyncio.Task | None = None

    #: Whether this socket may be told about hidden accounts. Decided once, from
    #: the authenticated session, and never from anything the client sends.
    #: Defaults to False so a code path that forgets to set it fails closed.
    sees_hidden = False

    async def connect(self) -> None:
        # Same gate as the REST side (`IsAdminUser`, and login itself refuses a
        # non-staff account). This channel carries balances, open positions,
        # per-leg failures and the halt state, so an ungated socket would hand
        # out everything the staff-only endpoints withhold — and it used to,
        # accepting any connection that reached it. The origin check in
        # config.asgi is the other half; this one is what stops a *logged-out*
        # or non-staff session.
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_staff:
            await self.close(code=4403)
            return

        self.sees_hidden = _check(user)

        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})
        # The navbar's Live/Offline flap has no server-side trail otherwise:
        # Daphne/Channels never write their own connect/disconnect to the log
        # table, and container stdout does not survive a redeploy. One row per
        # socket, on the events that are already rare, is what makes a future
        # recurrence diagnosable from LogEntry instead of requiring SSH access
        # at the exact moment it happens.
        logger.info("trading websocket connected", extra={"category": "SYSTEM"})
        # The admin has the panel open; the first order is seconds to minutes
        # away. Build the exchange clients now so that order is not the one
        # paying for it inside the spec §4 deadline.
        _kick_warmup()

    async def disconnect(self, code: int) -> None:
        logger.info(
            "trading websocket disconnected (code=%s)", code, extra={"category": "SYSTEM"}
        )
        if self._probe is not None and not self._probe.done():
            self._probe.cancel()
        # Leave the market room first: a socket that goes away without dropping
        # its viewer count would hold an exchange subscription open forever.
        await self._leave_market()
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def _leave_market(self) -> None:
        key = getattr(self, "market_room", "")
        if not key:
            return
        self.market_room = ""
        await self.channel_layer.group_discard(key, self.channel_name)
        await streamhub.leave(key)

    async def _subscribe_market(self, content: dict) -> None:
        """Follow one pair live. One room at a time — the panel shows one chart.

        Re-subscribing is how the symbol picker and the timeframe buttons work,
        so the previous room is always left first; without that, switching
        timeframe five times would leave five exchange subscriptions running.
        """
        from apps.exchanges.marketdata import normalise_interval, normalise_market

        symbol = str(content.get("symbol") or "").upper()
        if not symbol:
            return
        try:
            interval = normalise_interval(content.get("interval"))
            market = normalise_market(content.get("market"))
        except ValueError:
            return

        await self._leave_market()
        key = await streamhub.join(symbol=symbol, interval=interval, market=market)
        self.market_room = key
        await self.channel_layer.group_add(key, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("type") == "subscribe_market":
            await self._subscribe_market(content)
            return
        if content.get("type") == "unsubscribe_market":
            await self._leave_market()
            return
        if content.get("type") == "ping":
            # The pong carries both halves of the real path: the browser times
            # its own round trip to the engine, and the engine reports the last
            # measured round trip to the exchange. Neither is a constant.
            latency = await _exchange_latency()
            await self.send_json(
                {
                    "type": "pong",
                    "exchange_ms": latency["ms"],
                    "exchange": latency["provider"],
                }
            )
            # Refresh the exchange reading *after* answering, so the probe can
            # never be charged to the browser's own round trip. Fire-and-forget
            # on purpose: a slow or unreachable venue must not delay a pong,
            # and the next keepalive picks up whatever this measured.
            if latency["ms"] is None:
                self._probe = asyncio.create_task(_probe_exchange_latency())

    # --- group event handlers ---------------------------------------------
    #
    # Everything below fans out from one channel-layer group, so each socket
    # receives every event and decides for itself what to forward. Filtering
    # here rather than splitting the group in two is the safer shape: a new
    # broadcaster cannot forget to pick the right group, because there is only
    # one, and a handler that forwards nothing is the failure mode instead of a
    # handler that forwards everything.

    async def leg_result(self, event: dict) -> None:
        payload = event["payload"]
        if not self.sees_hidden:
            hidden = await _hidden_ids()
            legs = [leg for leg in payload.get("legs", []) if leg.get("account_id") not in hidden]
            if not legs:
                # Every leg belonged to a hidden account. Sending the envelope
                # with an empty list would still hand over a trade id and the
                # fact that a fan-out just happened.
                return
            payload = {**payload, "legs": legs}
        await self.send_json({"type": "leg_result", **payload})

    async def notification(self, event: dict) -> None:
        payload = event["payload"]
        if not self.sees_hidden and payload.get("account_id") in await _hidden_ids():
            return
        # Spec §4: persistent until dismissed — the client must not auto-expire it.
        await self.send_json({"type": "notification", "persistent": True, **payload})

    async def positions_changed(self, event: dict) -> None:
        """The position sync corrected the record; the panel's copy is stale.

        Account ids only, and hidden ones are stripped before they leave — the
        detail rides on ``/positions/`` and the notification, both of which
        already filter. What this carries is "re-read", which the panel acts on
        immediately rather than at the next poll tick: the row it is drawing may
        be a position that no longer exists.
        """
        payload = event["payload"]
        if not self.sees_hidden:
            hidden = await _hidden_ids()
            payload = {
                **payload,
                "closed": [i for i in payload.get("closed", []) if i not in hidden],
                "adopted": [i for i in payload.get("adopted", []) if i not in hidden],
                "drifted": [i for i in payload.get("drifted", []) if i not in hidden],
                # "<account id>:<symbol>", so the id is the part before the colon.
                "untracked": [
                    row
                    for row in payload.get("untracked", [])
                    if int(str(row).split(":", 1)[0]) not in hidden
                ],
            }
            # A reopen is caused by exactly one account holding a position the
            # platform had closed. Keeping the trade id would announce that a
            # hidden account did so, so it goes; the trade itself reaches this
            # reader through /positions/, which filters properly.
            payload.pop("reopened", None)
            if not any(payload[key] for key in ("closed", "adopted", "drifted", "untracked")):
                # Everything this sweep touched belongs to accounts this reader
                # cannot see. "Something changed" is itself the leak.
                return
        await self.send_json({"type": "positions_changed", **payload})

    async def balances(self, event: dict) -> None:
        rows = event["payload"]
        if not self.sees_hidden:
            hidden = await _hidden_ids()
            rows = [row for row in rows if row.get("id") not in hidden]
        await self.send_json({"type": "balances", "accounts": rows})

    async def stop_all(self, event: dict) -> None:
        # Spec §7: a halt flipped in one tab must show in every open panel.
        await self.send_json({"type": "stop_all", **event["payload"]})

    async def market_bar(self, event: dict) -> None:
        await self.send_json({"type": "market_bar", **event["payload"]})

    async def market_stream_down(self, event: dict) -> None:
        # Not an error to show the admin — the polled feed is still real. It
        # tells the panel to stop expecting pushes and go back to asking.
        await self.send_json({"type": "market_stream_down", **event["payload"]})

    async def market_stream_up(self, event: dict) -> None:
        await self.send_json({"type": "market_stream_up", **event["payload"]})

    # --- bot mode ---------------------------------------------------------
    # Same group, same staff-only same-origin gate. The per-account filtering
    # is the part that needs care: a bot's action payload carries fan-out legs,
    # which name accounts, and Q27 says every bot read surface filters.

    async def bot_state(self, event: dict) -> None:
        await self.send_json({"type": "bot_state", **event["payload"]})

    async def bot_bar(self, event: dict) -> None:
        # A bar carries no account data at all — it is public market data the
        # panel already has on the chart.
        await self.send_json({"type": "bot_bar", **event["payload"]})

    async def bot_intent(self, event: dict) -> None:
        await self.send_json({"type": "bot_intent", **event["payload"]})

    async def bot_action(self, event: dict) -> None:
        payload = event["payload"]
        if not self.sees_hidden:
            hidden = await _hidden_ids()
            actions = []
            for action in payload.get("actions", []):
                legs = [
                    leg
                    for leg in action.get("legs", [])
                    if leg.get("account_id") not in hidden
                ]
                actions.append({**action, "legs": legs})
            payload = {**payload, "actions": actions}
        await self.send_json({"type": "bot_action", **payload})

    async def bot_stopped(self, event: dict) -> None:
        # Why a bot stopped is never account-specific, and it is exactly the
        # thing nobody must miss — Q25's whole premise is that nobody is
        # watching at 03:00.
        await self.send_json({"type": "bot_stopped", "persistent": True, **event["payload"]})

    async def system_log_entry(self, event: dict) -> None:
        entry = event["entry"]
        if not self.sees_hidden:
            # The live tail is a read surface like any other. A fan-out leg that
            # times out on a hidden account logs a warning naming that account's
            # id, and the REST list already strips it — a socket that pushed it
            # anyway would make the log page the one place the account leaks.
            # Trade-level rows are left to the REST filter: the id alone reaches
            # nothing here, and a channel-layer handler must not run a join.
            if entry.get("account_id") is not None and entry["account_id"] in await _hidden_ids():
                return
        await self.send_json({"type": "system_log", **entry})

    @classmethod
    async def encode_json(cls, content) -> str:
        # Async because Channels awaits this hook (channels>=4). A sync override
        # here raised TypeError inside connect(), which closed the socket
        # immediately after accept — the panel flapped Live/Offline forever.
        return json.dumps(content, default=str)

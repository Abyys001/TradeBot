"""Shared REST plumbing for HMAC-style exchanges.

Every adapter gets its own httpx client, its own rate limiter, and its own
credentials — the structural half of the isolation guarantee in spec §2.
Subclasses supply signing and endpoint shapes; this class owns transport,
timeouts, error mapping, and never letting a raw exception escape untyped.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from apps.exchanges.base import (
    AdapterError,
    AuthError,
    ExchangeAdapter,
    ExchangeUnavailable,
    RateLimited,
)
from apps.exchanges.ratelimit import TokenBucket

logger = logging.getLogger(__name__)

# Below the fan-out's per-leg deadline so a slow exchange fails inside the
# deadline rather than being killed by it — the error message is then useful.
# A floor rather than the value: ``default_timeout()`` derives the real one from
# the configured deadline, and this is what a deployment that sets an absurdly
# small deadline still gets.
DEFAULT_TIMEOUT = 0.8

#: How long an idle connection is kept for reuse. Adapters are pooled per
#: account (``apps.exchanges.pool``) and the balance poll touches every account
#: every 20s, so this is what turns that poll into a free keepalive: the trade
#: that follows finds a connection already open and skips the TCP+TLS handshake
#: that used to be the largest single item in a leg's time.
KEEPALIVE_EXPIRY = 300.0

_LIMITS = httpx.Limits(
    max_keepalive_connections=8,
    max_connections=16,
    keepalive_expiry=KEEPALIVE_EXPIRY,
)


def default_timeout() -> float:
    """Per-request ceiling, derived from the spec §4 per-leg deadline.

    Hardcoding 0.8s was wrong in both directions: too tight for a VPS whose
    round trip to the venue is 200ms and a signed request takes two of them,
    and unrelated to the deadline it is supposed to sit under — raising
    ``FANOUT_TIMEOUT_SECONDS`` bought a leg no extra patience at all, which is
    part of why a healthy order still came back as a timeout.

    Three quarters of the budget: long enough that a real answer is waited for,
    short enough that ``ExchangeUnavailable: request timed out`` (which names
    the venue) beats the fan-out's generic deadline message.
    """
    from django.conf import settings

    budget = float(settings.TRADING["FANOUT_TIMEOUT_SECONDS"])
    return max(DEFAULT_TIMEOUT, budget * 0.75)


def _httpx_timeout(total: float) -> httpx.Timeout:
    """Read patience and connect patience are not the same thing.

    A venue that is answering slowly deserves the full budget. A host that is
    unreachable — DNS gone, port blocked, the wrong proxy — should fail fast so
    the leg reports it instead of burning the whole deadline discovering it.
    """
    return httpx.Timeout(total, connect=min(total, 2.0))


def exchange_proxy() -> str | None:
    """The proxy signed trading calls should use, or None for a direct connection.

    **Only** ``EXCHANGE_PROXY`` is honoured. The ambient shell proxy is
    deliberately ignored, which is why every client below sets
    ``trust_env=False``:

    * These requests carry signed order instructions for real partner capital.
      Routing them through whatever ``ALL_PROXY`` a shell happens to export,
      without anyone having said so, is not a decision to make implicitly.
    * It breaks anyway. This machine exports ``ALL_PROXY=socks://…``, a scheme
      httpx rejects outright, and ``HTTPS_PROXY=http://…`` pointing at a SOCKS
      port — so an inherited proxy fails every call for reasons that look
      nothing like a proxy problem.

    ``socks://`` is normalised to ``socks5://`` (shells commonly write the
    former, httpx wants the latter), and an unusable value is dropped with a
    warning rather than taking every account offline.
    """
    candidate = (os.getenv("EXCHANGE_PROXY") or "").strip()
    if not candidate:
        return None
    if candidate.startswith("socks://"):
        candidate = "socks5://" + candidate[len("socks://") :]
    try:
        httpx.Proxy(candidate)
    except Exception as exc:  # noqa: BLE001 - a bad proxy must not kill every account
        logger.warning("ignoring unusable EXCHANGE_PROXY %r: %s", candidate, exc)
        return None
    return candidate


class RestAdapter(ExchangeAdapter):
    """Base for API-key exchanges. Subclasses implement ``_sign`` and the verbs."""

    base_url: str = ""
    testnet_url: str = ""
    #: Requests per second and burst, per account.
    rate: float = 8.0
    burst: int = 20

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        testnet: bool = False,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self._url = (self.testnet_url or self.base_url) if testnet else self.base_url
        self._limiter = TokenBucket(self.rate, self.burst)
        self._timeout = default_timeout() if timeout is None else timeout
        #: An injected client answers for *every* host — that is what makes the
        #: adapter tests offline. Only a real adapter opens a second one.
        self._injected = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=self._url,
            timeout=_httpx_timeout(self._timeout),
            headers={"User-Agent": "TradeBot/1.0"},
            # Adapters outlive an action (apps.exchanges.pool), so this pool is
            # what carries a warm connection into the next order.
            limits=_LIMITS,
            # Explicit, never ambient: see exchange_proxy.
            trust_env=False,
            proxy=exchange_proxy(),
        )
        self._extra_clients: dict[str, httpx.AsyncClient] = {}

    def host_client(self, url: str) -> httpx.AsyncClient:
        """A client for a second host of the same exchange, made once per adapter.

        Binance and KuCoin both keep their key-permission endpoint on the spot
        host while everything else this platform does lives on the futures host.
        The extra client still belongs to this adapter instance and this
        account, so spec §2 isolation is unaffected — and it is closed with the
        rest in ``close()``.
        """
        if self._injected:
            return self._client
        if url not in self._extra_clients:
            self._extra_clients[url] = httpx.AsyncClient(
                base_url=url,
                timeout=_httpx_timeout(self._timeout),
                headers={"User-Agent": "TradeBot/1.0"},
                limits=_LIMITS,
                trust_env=False,
                proxy=exchange_proxy(),
            )
        return self._extra_clients[url]

    async def close(self) -> None:
        await self._client.aclose()
        for client in self._extra_clients.values():
            await client.aclose()
        self._extra_clients.clear()

    # --- signing hook -------------------------------------------------------

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | list | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        """Return (headers, query params, request content) for a signed request."""
        raise NotImplementedError

    # --- transport ----------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        # A few endpoints take a JSON *array* as the whole body (OKX cancel-algos).
        body: dict | list | None = None,
        signed: bool = True,
        weight: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> Any:
        """One signed or public call.

        ``client`` overrides the transport for exchanges that split their API
        across two hosts under one credential: Binance serves ``/sapi`` only
        from the spot host, KuCoin serves the key-permission endpoint only from
        the spot host. The override is still a client owned by *this* adapter
        instance for *this* account, so spec §2 isolation is unaffected.
        """
        if not await self._limiter.acquire(weight, timeout=0.5):
            # Coded, because "not sent" is a fact the engine acts on: this is
            # one of the few failures that provably left no order behind, so it
            # skips the post-deadline re-read (fanout.NEVER_SENT_CODES).
            raise RateLimited(
                f"{self.name}: local rate limit reached, request not sent",
                code="rate_limit_local",
            )

        if signed:
            headers, query, content = self._sign(method, path, params, body)
        else:
            headers, query, content = {}, params, None

        try:
            response = await (client or self._client).request(
                method,
                path,
                params=query,
                content=content,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise ExchangeUnavailable(f"{self.name}: request timed out") from exc
        except httpx.HTTPError as exc:
            raise ExchangeUnavailable(f"{self.name}: {exc}") from exc

        return self._handle(response)

    def _handle(self, response: httpx.Response) -> Any:
        if response.status_code == 429:
            raise RateLimited(f"{self.name}: rate limited by the exchange")
        if response.status_code in (401, 403):
            # Carry the exchange's own wording: "invalid key" and "this key has
            # no permission for that endpoint" are the same status code and very
            # different problems (see BinanceAdapter._get_account_permissions).
            raise AuthError(
                f"{self.name}: credentials rejected ({response.status_code})"
                f"{self._detail(response)}",
                code="auth",
            )
        if response.status_code >= 500:
            raise ExchangeUnavailable(f"{self.name}: exchange error {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterError(f"{self.name}: non-JSON response ({response.status_code})") from exc

        if response.status_code >= 400:
            raise AdapterError(f"{self.name}: {self._error_message(payload)}")
        return self.unwrap(payload)

    def unwrap(self, payload: Any) -> Any:
        """Strip the exchange's envelope and raise on in-band error codes."""
        return payload

    def _detail(self, response: httpx.Response) -> str:
        """The exchange's error text, when it sent one. Never the request body."""
        try:
            payload = response.json()
        except ValueError:
            return ""
        message = self._error_message(payload)
        return f" — {message}" if message else ""

    def _error_message(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("msg", "message", "error", "retMsg", "sMsg", "label"):
                if payload.get(key):
                    return str(payload[key])
        return str(payload)[:200]

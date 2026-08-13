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

# Below the fan-out's 1s budget so a slow exchange fails inside the deadline
# rather than being killed by it — the error message is then useful.
DEFAULT_TIMEOUT = 0.8


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
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self._url = (self.testnet_url or self.base_url) if testnet else self.base_url
        self._limiter = TokenBucket(self.rate, self.burst)
        self._timeout = timeout
        #: An injected client answers for *every* host — that is what makes the
        #: adapter tests offline. Only a real adapter opens a second one.
        self._injected = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=self._url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
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
                timeout=httpx.Timeout(self._timeout),
                headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
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
            raise RateLimited(f"{self.name}: local rate limit reached, request not sent")

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
                f"{self._detail(response)}"
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

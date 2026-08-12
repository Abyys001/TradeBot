"""Shared REST plumbing for HMAC-style exchanges.

Every adapter gets its own httpx client, its own rate limiter, and its own
credentials — the structural half of the isolation guarantee in spec §2.
Subclasses supply signing and endpoint shapes; this class owns transport,
timeouts, error mapping, and never letting a raw exception escape untyped.
"""

from __future__ import annotations

import logging
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
        self._client = client or httpx.AsyncClient(
            base_url=self._url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    # --- signing hook -------------------------------------------------------

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
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
        body: dict | None = None,
        signed: bool = True,
        weight: int = 1,
    ) -> Any:
        if not await self._limiter.acquire(weight, timeout=0.5):
            raise RateLimited(f"{self.name}: local rate limit reached, request not sent")

        if signed:
            headers, query, content = self._sign(method, path, params, body)
        else:
            headers, query, content = {}, params, None

        try:
            response = await self._client.request(
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
            raise AuthError(f"{self.name}: credentials rejected ({response.status_code})")
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

    def _error_message(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("msg", "message", "error", "retMsg", "sMsg", "label"):
                if payload.get(key):
                    return str(payload[key])
        return str(payload)[:200]

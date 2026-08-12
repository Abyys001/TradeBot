"""Adapter registry and per-account factory.

The only place that maps an exchange name to a class. Everything above it —
engine, services, views — stays exchange-agnostic (see the seam note in
``base.py``).

Every call to ``build_adapter`` returns a **fresh instance with its own HTTP
client and rate limiter**. Adapters are never cached or shared between accounts;
that is the structural half of the spec §2 isolation guarantee.
"""

from __future__ import annotations

from apps.accounts.models import ConnectedAccount, Exchange
from apps.exchanges.base import Capabilities, ExchangeAdapter
from apps.exchanges.binance_family import BinanceAdapter, ToobitAdapter
from apps.exchanges.bybit import BybitAdapter
from apps.exchanges.gateio import GateioAdapter
from apps.exchanges.hyperliquid import HyperliquidAdapter
from apps.exchanges.kucoin import KucoinAdapter
from apps.exchanges.lbank import LbankAdapter
from apps.exchanges.okx import OkxAdapter
from apps.exchanges.paper import PaperAdapter

ADAPTERS: dict[str, type[ExchangeAdapter]] = {
    Exchange.HYPERLIQUID: HyperliquidAdapter,
    Exchange.BYBIT: BybitAdapter,
    Exchange.BINANCE: BinanceAdapter,
    Exchange.OKX: OkxAdapter,
    Exchange.GATEIO: GateioAdapter,
    Exchange.KUCOIN: KucoinAdapter,
    Exchange.TOOBIT: ToobitAdapter,
    Exchange.LBANK: LbankAdapter,
    Exchange.PAPER: PaperAdapter,
}


class UnknownExchange(Exception):
    pass


def adapter_class(exchange: str) -> type[ExchangeAdapter]:
    try:
        return ADAPTERS[exchange]
    except KeyError as exc:
        raise UnknownExchange(f"no adapter for exchange {exchange!r}") from exc


def capabilities_for(exchange: str) -> Capabilities:
    return adapter_class(exchange).capabilities


def build_adapter(account: ConnectedAccount) -> ExchangeAdapter:
    """Live adapter for one account. Credentials are decrypted here and nowhere else."""
    cls = adapter_class(account.exchange)

    if account.exchange == Exchange.PAPER:
        from apps.core.money import D

        # state_key keeps the simulated position alive between actions, since
        # there is no exchange holding it for us.
        return PaperAdapter(
            balance=D(account.last_balance or "1000"),
            state_key=f"account-{account.id}",
        )

    if account.exchange == Exchange.HYPERLIQUID:
        # The agent private key is stored in the passphrase column; the master
        # address is separate because /info queries must not use the agent.
        return HyperliquidAdapter(
            agent_private_key=account.api_passphrase or account.api_secret,
            account_address=account.wallet_address,
            testnet=account.testnet,
        )

    return cls(  # type: ignore[call-arg]
        api_key=account.api_key,
        api_secret=account.api_secret,
        passphrase=account.api_passphrase,
        testnet=account.testnet,
    )


def testnet_support() -> list[dict]:
    """Spec §9 / Q9: what the panel shows about test environments per exchange."""
    rows = []
    for value, label in Exchange.choices:
        capabilities = capabilities_for(value)
        rows.append(
            {
                "exchange": value,
                "label": label,
                "has_testnet": capabilities.has_testnet,
                "note": capabilities.testnet_note,
                "markets": sorted(m.value for m in capabilities.markets),
                "native_sltp_amend": capabilities.native_sltp_amend,
                "per_key_rate_limits": capabilities.per_key_rate_limits,
                "wallet_based_auth": capabilities.wallet_based_auth,
            }
        )
    return rows

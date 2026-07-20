"""Standalone EIP-712 signer for Hyperliquid L1 agent-signed actions.

Implements the phantom-agent signing protocol used by Hyperliquid without
any dependency on hyperliquid-python-sdk signing internals.

Signing protocol (L1 actions):
  1. msgpack-serialize the action dict (same encoding as the SDK).
  2. Append nonce as 8-byte big-endian uint64.
  3. Append vault flag: 0x00 if no vault, else 0x01 + 20-byte vault address.
  4. keccak256 the result → connectionId (bytes32).
  5. EIP-712 sign an Agent struct {source, connectionId}.

Chain IDs:
  mainnet → 42161 (Arbitrum One)
  testnet → 421614 (Arbitrum Sepolia)
"""
from __future__ import annotations

import logging
from typing import Any

import msgpack
from eth_account import Account
from eth_utils import keccak

logger = logging.getLogger(__name__)

_CHAIN_IDS: dict[str, int] = {
    "mainnet": 42161,
    "testnet": 421614,
}

_SOURCES: dict[str, str] = {
    "mainnet": "a",
    "testnet": "b",
}

_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
]

_AGENT_TYPE = [
    {"name": "source", "type": "string"},
    {"name": "connectionId", "type": "bytes32"},
]


def _msgpack_encode(obj: Any) -> bytes:
    return msgpack.packb(obj, use_bin_type=True)


def _action_hash(action: dict, vault_address: str | None, nonce: int) -> bytes:
    """keccak256(msgpack(action) || nonce_u64_be || vault_flag) → bytes32."""
    data = _msgpack_encode(action)
    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        raw = vault_address[2:] if vault_address.startswith("0x") else vault_address
        data += b"\x01" + bytes.fromhex(raw)
    return keccak(primitive=data)


class AgentSigner:
    """EIP-712 signer for Hyperliquid L1 agent-authorized actions.

    The agent private key is decrypted once at construction and held in memory
    only for the lifetime of this object. It is never logged or serialized.

    Usage::

        signer = AgentSigner(credential)
        sig = signer.sign_l1_action(action_dict, nonce=nonce)

    For SDK-managed order placement where the SDK handles signing internally,
    call ``build_exchange_client()`` to get a compatible Exchange object.
    """

    def __init__(self, credential) -> None:
        from apps.credentials.models import ExchangeCredential

        if not isinstance(credential, ExchangeCredential):
            raise TypeError("credential must be an ExchangeCredential instance")

        self._wallet = Account.from_key(credential.get_agent_key())
        self.master_address: str = credential.wallet_address
        self._network: str = credential.network
        self._chain_id: int = _CHAIN_IDS.get(credential.network, 42161)
        self._source: str = _SOURCES.get(credential.network, "a")
        self._strategy_id: int | None = None

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def sign_l1_action(
        self,
        action: dict,
        *,
        vault_address: str | None = None,
        nonce: int,
    ) -> str:
        """Sign a Hyperliquid L1 action.

        Returns the 65-byte EIP-712 signature as a 0x-prefixed hex string.
        The signature covers a phantom Agent struct whose ``connectionId`` is
        keccak256(msgpack(action) || nonce_u64_be || vault_flag).

        Args:
            action: The action dict (e.g. ``{"type": "order", ...}``).
            vault_address: Optional vault/sub-account address. Pass ``None``
                for standard agent-key signing.
            nonce: Monotonically increasing nonce (usually ms timestamp).
        """
        connection_id = _action_hash(action, vault_address, nonce)

        signed = self._wallet.sign_typed_data(
            domain_data={
                "name": "Exchange",
                "version": "1",
                "chainId": self._chain_id,
            },
            message_types={"Agent": _AGENT_TYPE},
            message_data={
                "source": self._source,
                "connectionId": connection_id,
            },
        )
        sig = "0x" + signed.signature.hex()
        self._audit("l1_action", action.get("type", "unknown"), sig)
        return sig

    def sign_user_signed_action(self, action: dict, *, nonce: int) -> str:
        """Sign a user-signed (off-chain) action with the same phantom-agent pattern."""
        return self.sign_l1_action(action, vault_address=None, nonce=nonce)

    def build_exchange_client(self):
        """Return an SDK Exchange client for SDK-managed order placement.

        The SDK manages its own EIP-712 signing internally. Use ``sign_l1_action``
        directly when you need explicit control (custom endpoints, auditing).
        """
        from apps.exchange.constants import network_url
        from hyperliquid.exchange import Exchange

        return Exchange(
            self._wallet,
            network_url(self._network),
            account_address=self.master_address,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _audit(self, action_type: str, subtype: str, sig: str) -> None:
        try:
            from apps.execution.models import ExecutionLog

            ExecutionLog.objects.create(
                strategy_id=self._strategy_id,
                level=ExecutionLog.Level.DEBUG,
                event="eip712.signed",
                payload={
                    "action_type": action_type,
                    "subtype": subtype,
                    "network": self._network,
                    "signer": self.master_address,
                    "sig_prefix": sig[:12],
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("eip712 audit log skipped (non-critical)")

"""Hyperliquid client factory: agent signing, verify, emergency actions."""
from __future__ import annotations

import logging

import eth_account
from django.utils import timezone

from .hl_constants import network_url, normalize_coin

logger = logging.getLogger(__name__)


def build_info(network: str, *, skip_ws: bool = True):
    from hyperliquid.info import Info

    return Info(network_url(network), skip_ws=skip_ws)


def build_exchange(cred):
    """Construct an Exchange client signed with the stored agent key."""
    from hyperliquid.exchange import Exchange

    wallet = eth_account.Account.from_key(cred.get_agent_key())
    return Exchange(
        wallet,
        network_url(cred.network),
        account_address=cred.wallet_address,
    )


def verify_credential(cred) -> tuple[bool, str]:
    """Validate master wallet reachability and agent key format."""
    try:
        info = build_info(cred.network)
        state = info.user_state(cred.wallet_address)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Credential %s verify failed: %s", cred.pk, type(exc).__name__)
        cred.is_active = False
        cred.save(update_fields=["is_active"])
        return False, f"request failed: {type(exc).__name__}"

    if state is None:
        cred.is_active = False
        cred.save(update_fields=["is_active"])
        return False, "no user state for wallet"

    try:
        agent = eth_account.Account.from_key(cred.get_agent_key())
    except Exception as exc:  # noqa: BLE001
        cred.is_active = False
        cred.save(update_fields=["is_active"])
        return False, f"invalid agent key: {type(exc).__name__}"

    cred.agent_address = agent.address
    cred.is_active = True
    cred.last_verified_at = timezone.now()
    cred.permissions = {"agent": agent.address, "network": cred.network}
    cred.save(update_fields=["is_active", "last_verified_at", "agent_address", "permissions"])
    return True, "verified"


def cancel_all_orders(cred) -> dict:
    """Cancel all open orders for the master account (best-effort)."""
    try:
        info = build_info(cred.network)
        exchange = build_exchange(cred)
        address = cred.wallet_address
        open_orders = info.open_orders(address) or []
        if not open_orders:
            return {"ok": True, "cancelled": 0}

        requests = [{"coin": o.get("coin"), "oid": o.get("oid")} for o in open_orders if o.get("oid")]
        if not requests:
            return {"ok": True, "cancelled": 0}

        if len(requests) == 1:
            r = requests[0]
            resp = exchange.cancel(r["coin"], r["oid"])
        else:
            resp = exchange.bulk_cancel(requests)
        return {"ok": True, "cancelled": len(requests), "response": resp}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cancel_all_orders failed for cred %s: %s", cred.pk, type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def close_all_positions(cred) -> dict:
    """Cancel open orders and close all perp positions + spot balances (best-effort)."""
    results = {"ok": True, "cancelled": cancel_all_orders(cred), "closed": []}
    try:
        info = build_info(cred.network)
        exchange = build_exchange(cred)
        state = info.user_state(cred.wallet_address) or {}
        for item in state.get("assetPositions") or []:
            pos = item.get("position") or {}
            coin = pos.get("coin")
            szi = pos.get("szi", "0")
            try:
                sz = float(szi)
            except (TypeError, ValueError):
                continue
            if not coin or sz == 0:
                continue
            resp = exchange.market_close(coin=normalize_coin(coin), sz=None)
            results["closed"].append({"coin": coin, "response": resp})

        spot_state = info.spot_user_state(cred.wallet_address) or {}
        for bal in spot_state.get("balances") or []:
            coin = bal.get("coin")
            total = bal.get("total", "0")
            try:
                sz = float(total)
            except (TypeError, ValueError):
                continue
            if not coin or sz <= 0 or coin in ("USDC", "USD"):
                continue
            try:
                resp = exchange.market_open(name=coin, is_buy=False, sz=sz, px=None)
                results["closed"].append({"coin": coin, "market": "spot", "response": resp})
            except Exception as exc:  # noqa: BLE001
                results["closed"].append({"coin": coin, "error": type(exc).__name__})
    except Exception as exc:  # noqa: BLE001
        logger.warning("close_all_positions failed for cred %s: %s", cred.pk, type(exc).__name__)
        results["ok"] = False
        results["error"] = type(exc).__name__
    return results

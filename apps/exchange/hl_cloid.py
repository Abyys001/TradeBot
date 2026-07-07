"""Map Pine strategy order ids to Hyperliquid client order ids (cloid)."""
from __future__ import annotations

import hashlib

from hyperliquid.utils.types import Cloid


def pine_oid_to_cloid(oid: str) -> Cloid:
    """Deterministic 128-bit cloid from a Pine order id string."""
    digest = hashlib.sha256(str(oid).encode()).digest()[:16]
    return Cloid.from_str("0x" + digest.hex())

"""Per-exchange credential verification dispatch.

Routes a credential to the right verifier based on its ``exchange`` so the
verify view/task stay exchange-agnostic. Each verifier persists
``is_active``/``last_verified_at`` and returns ``(ok, detail)``.
"""
from __future__ import annotations

from .models import Exchange


def verify_credential(cred) -> tuple[bool, str]:
    if cred.exchange == Exchange.TABDEAL:
        from apps.exchange.tabdeal_futures import verify_tabdeal_credential

        return verify_tabdeal_credential(cred)
    # Hyperliquid verification removed
    return False, "Hyperliquid credentials are no longer supported"

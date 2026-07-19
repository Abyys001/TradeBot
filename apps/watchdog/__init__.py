"""Watchdog app — Node D (Master Plan §6).

Independent process that monitors Node B health, manages position protection,
and enforces the kill switch. Cannot open positions — only close/flatten.

Three response tiers:
- **Tier 1** (T_self): B is slow → attach SL if not already attached.
- **Tier 2** (T_dead): B is dead → confirm SL, hold up to max_blind_hold, then flatten.
- **Tier 3** (daily loss breach): flatten + kill switch.
"""

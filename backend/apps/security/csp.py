"""The Content-Security-Policy the panel serves, and which header carries it.

The value is deliberately one constant rather than something composed per
request: a policy assembled from settings is a policy nobody can read, and this
one has to be readable to be trusted.

``'unsafe-inline'`` is present for scripts and styles because Nuxt hydrates
from an inline payload script and Tailwind's critical CSS is inlined at build
time. Removing it means per-request nonces threaded through the Nitro renderer,
which is a real piece of work and not this switch's job — the switch is here so
the report-only pass can start today.

Served from an endpoint rather than baked into the Nuxt build because the whole
point is that it can be turned on, watched, and turned off again from the panel
without a redeploy.
"""

from __future__ import annotations

VALUE = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        # The panel is not embeddable. It holds live positions behind a session
        # cookie, so a frame around it is a clickjack waiting to happen.
        "frame-ancestors 'none'",
        "img-src 'self' data: blob:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        # Same-origin everywhere, the WebSocket included — see the note on
        # NUXT_PUBLIC_WS_BASE in CLAUDE.md.
        "connect-src 'self' ws: wss:",
        "form-action 'self'",
        "frame-src 'none'",
    )
)

ENFORCE_HEADER = "Content-Security-Policy"
REPORT_HEADER = "Content-Security-Policy-Report-Only"


def header_for(mode: str) -> tuple[str, str] | None:
    """``(header, value)`` for the mode, or ``None`` when the switch is off."""
    if mode == "enforce":
        return ENFORCE_HEADER, VALUE
    if mode == "report":
        return REPORT_HEADER, VALUE
    return None

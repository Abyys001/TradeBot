import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from apps.trading.routing import websocket_urlpatterns  # noqa: E402  (needs apps loaded)

# `AllowedHostsOriginValidator` is the WebSocket half of a same-origin policy,
# and it is not optional now that Caddy exposes /ws on the public domain.
#
# A WebSocket handshake is not subject to CORS: any page the admin happens to
# visit can open one to this host, and the browser attaches the session cookie
# for it. Without this check that page would receive the live channel — live
# balances, positions, per-leg failures — from an authenticated session it does
# not own. The origin's host is matched against ALLOWED_HOSTS, so production
# (which pins the domain) is locked down while a dev default of "*" stays
# permissive.
_router = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)


async def application(scope, receive, send):
    """The router, plus one-time bot resumption on the first request.

    Bots run as asyncio tasks in this process, alongside the fan-out — their
    actions go through ``services.route_*``, which is async, and a broker hop
    would spend the spec §4 per-leg budget before the first exchange call.

    Resumed here rather than at import time because an asyncio task needs a
    running loop, and because a management command that merely imports this
    module must not start trading. The first act of every resumed bot is warm-up
    and reconciliation, never an order — see ``apps.bots.supervisor``.
    """
    await _resume_bots_once()
    return await _router(scope, receive, send)


_resumed = False


async def _resume_bots_once() -> None:
    global _resumed
    if _resumed:
        return
    _resumed = True

    from django.conf import settings

    if not settings.BOT["SUPERVISOR_IN_ASGI"]:
        # The `bots` compose service owns them instead.
        return
    try:
        from apps.bots.supervisor import resume_all

        resumed = await resume_all()
    except Exception:  # noqa: BLE001 - a bot that cannot resume must not take the API down
        import logging

        logging.getLogger(__name__).exception("could not resume bots")
        return
    if resumed:
        import logging

        logging.getLogger(__name__).warning("resumed %d bot(s) on process start", len(resumed))

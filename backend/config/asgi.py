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
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)

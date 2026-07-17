"""WSGI entrypoint (sync). ASGI (config/asgi.py) is the primary entrypoint."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()

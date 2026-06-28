"""Development settings with SQLite (no Postgres needed)."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

import os

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "dev.db"),
    }
}

# Remove daphne + channels so manage.py runserver uses standard WSGI server
# (Daphne/ASGI hangs on POST request bodies under Python 3.14)
INSTALLED_APPS = [a for a in INSTALLED_APPS if a not in ("daphne", "channels")]
CHANNEL_LAYERS = {}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

HL_API_URL = "https://api.hyperliquid-testnet.xyz"
HL_NETWORK = "testnet"
HL_API_BASE_URL = "https://api.hyperliquid-testnet.xyz"

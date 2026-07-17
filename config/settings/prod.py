"""Production settings.

Layers 2/3 of the multi-layer credential protection live here:
  - TLS in transit (SECURE_* + DB sslmode)
  - Postgres at-rest encryption is configured at the DB/disk level (infra),
    not in app code; documented in README.
"""
from .base import *  # noqa: F401,F403

DEBUG = False

# Security hardening — HTTPS / TLS in transit.
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True

# Explicit cookie hardening.
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True

# Require TLS to PostgreSQL (DATABASE_URL may also set sslmode).
DATABASES["default"].setdefault("OPTIONS", {})  # noqa: F405
DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")  # noqa: F405

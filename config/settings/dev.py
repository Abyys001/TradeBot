"""Development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True

# Relaxed for local dev only.
ALLOWED_HOSTS = ["*"]

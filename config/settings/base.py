"""Base settings shared by all environments.

Secrets and environment-specific values are read from the environment / .env
via django-environ. See .env.example for the required variables.
"""
from pathlib import Path

import environ

# BASE_DIR = repo root (two levels up from this file: config/settings/base.py)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Read .env if present (dev convenience; prod injects real env vars).
environ.Env.read_env(BASE_DIR / ".env")

# --- Core ---
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# AES-256 master key for credential encryption (base64 urlsafe, 32 raw bytes).
CREDENTIAL_ENC_KEY = env("CREDENTIAL_ENC_KEY")

# --- Applications ---
DJANGO_APPS = [
    "daphne",  # must precede staticfiles so its ASGI runserver takes over
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "corsheaders",
    "rest_framework",
    "channels",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.credentials",
    "apps.strategies",
    "apps.execution",
    "apps.exchange",
    "apps.transpiler",
    "apps.dashboard",
    "apps.risk",
    "apps.paper",
    "apps.optimizer",
    "apps.pro",
    "apps.integrations",
    "apps.telegram",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Both WSGI (sync) and ASGI (Channels) entrypoints exist; ASGI is primary.
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---
DATABASES = {"default": env.db("DATABASE_URL")}

# --- Redis: cache + Channels layer + Celery (see celery.py) ---
REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "dashboard-health-heartbeat": {
        "task": "dashboard.health_heartbeat",
        "schedule": 5.0,
    },
    "execution-reconcile-orders": {
        "task": "execution.reconcile_orders",
        "schedule": 60.0,
    },
    "exchange-sync-active-accounts": {
        "task": "exchange.sync_active_accounts",
        "schedule": 30.0,
    },
    "exchange-collect-open-interest": {
        "task": "exchange.collect_open_interest",
        "schedule": 3600.0,
    },
    "exchange-sync-history-incremental": {
        "task": "exchange.sync_history_incremental",
        "schedule": float(env.int("HISTORY_SYNC_INTERVAL_SECONDS", default=3600)),
    },
}

# Coins polled for forward open-interest history collection (no HL OI history API).
OI_COLLECT_COINS = ["BTC", "ETH", "SOL", "HYPE"]
OI_COLLECT_NETWORK = "mainnet"

# Scheduled incremental history sync (public API, no keys required).
HISTORY_SYNC_ASSETS = env.list("HISTORY_SYNC_ASSETS", default=["BTC", "ETH", "SOL", "HYPE"])
HISTORY_SYNC_TIMEFRAMES = env.list("HISTORY_SYNC_TIMEFRAMES", default=["1m", "5m", "15m", "1h"])
HISTORY_SYNC_NETWORK = env("HISTORY_SYNC_NETWORK", default="mainnet")
HISTORY_SYNC_INTERVAL_SECONDS = env.int("HISTORY_SYNC_INTERVAL_SECONDS", default=3600)
HISTORY_DOWNLOAD_WORKERS = env.int("HISTORY_DOWNLOAD_WORKERS", default=2)
HISTORY_FUNDING_COOLDOWN_SEC = env.float("HISTORY_FUNDING_COOLDOWN_SEC", default=1.5)
DOWNLOAD_TRADES = env.bool("DOWNLOAD_TRADES", default=False)

# --- Auth ---
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# --- i18n / tz ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS / CSRF (SPA dev) ---
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)

# --- Live engine (Phase 3) ---
LIVE_WINDOW_BUFFER = env.int("LIVE_WINDOW_BUFFER", default=50)
LIVE_SESSION_KEY_PREFIX = env("LIVE_SESSION_KEY_PREFIX", default="live:session")

# --- Telegram ---
TELEGRAM_ALERT_ENABLED = env.bool("TELEGRAM_ALERT_ENABLED", default=False)

# --- Hyperliquid ---
HL_NETWORK = env("HL_NETWORK", default="testnet")
HL_API_URL = env("HL_API_URL", default="")
HL_CANDLE_CHANNEL_PREFIX = env("HL_CANDLE_CHANNEL_PREFIX", default="hl:candles")
HL_META_CACHE_TTL = env.int("HL_META_CACHE_TTL", default=300)
HL_WS_PING_INTERVAL = env.int("HL_WS_PING_INTERVAL", default=55)
HL_MIN_FREE_MARGIN_USD = env.int("HL_MIN_FREE_MARGIN_USD", default=50)

# Local OHLCV history store (offline backtesting). Default: <repo>/data/candles.
CANDLE_DATA_DIR = env(
    "CANDLE_DATA_DIR", default=str(BASE_DIR / "data" / "candles")
)

# Do not leak secrets in logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

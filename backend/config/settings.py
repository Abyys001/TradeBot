"""Django settings. Dev defaults are safe; production values come from the environment."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-do-not-use-in-production")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "channels",
    "apps.accounts",
    "apps.trading",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves Django's static files (the admin UI) once DEBUG=false and
    # `collectstatic` has run — the launch command in docker-compose.prod.yml
    # does both. Development is unaffected: runserver takes over under DEBUG.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

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
            ]
        },
    }
]

# Tests always use SQLite, whatever .env says. Without this, switching the
# compose stack to Postgres breaks the suite — and worse, a local test run could
# point at a database holding real connected accounts.
RUNNING_TESTS = "pytest" in sys.modules

if RUNNING_TESTS or env_bool("USE_SQLITE", True):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "walletmanager"),
            "USER": os.getenv("POSTGRES_USER", "walletmanager"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }

# Same reasoning as the database: tests must not need a Redis to be running,
# and must never publish test events onto a real channel layer.
REDIS_URL = "" if RUNNING_TESTS else os.getenv("REDIS_URL", "")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Redis when there is one, per-process memory otherwise. The cache holds market
# data (cheap to lose) and the spec §7 kill-switch flag (not cheap to lose) —
# which is why `apps.trading.killswitch` re-reads the row on a cache miss and
# treats an unreadable switch as halted rather than trusting an empty cache.
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "walletmanager",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{v}"}
    for v in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("fa", "Persian")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Absolute: with the relative "static/" the admin at /admin/ would resolve its
# assets to /admin/static/... and whitenoise (production) and runserver (dev)
# would both 404 them.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
CORS_ALLOW_CREDENTIALS = True

# The panel proxies /api through its own origin, so a POST arrives with the
# browser's Origin (the panel) but this server's Host. Django's CSRF check
# compares the two and rejects the mismatch unless the origin is trusted here.
CSRF_TRUSTED_ORIGINS = [
    origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith(("http://", "https://"))
]

# --- Credential encryption (spec §7) ---------------------------------------
# Fernet key, base64 urlsafe 32 bytes. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Never commit a real value. Rotation: put the new key first, old keys after.
CREDENTIAL_ENCRYPTION_KEYS = [
    k.strip() for k in os.getenv("CREDENTIAL_ENCRYPTION_KEYS", "").split(",") if k.strip()
]

# --- Trading policy ---------------------------------------------------------
# Each of these encodes an open question in questions.md. Both/all branches are
# implemented; flipping the setting changes behaviour with no code change.
TRADING = {
    # Q12 / spec §5. Fraction of available balance committed as margin.
    "BALANCE_FRACTION": os.getenv("BALANCE_FRACTION", "0.99"),
    # Q5a: "price" -> SL% is a move in price. "margin" -> SL% is a loss of margin.
    "SLTP_BASIS": os.getenv("SLTP_BASIS", "price"),
    # Q5b/Q5c: "own_fill" -> each account uses its own fill price as the anchor.
    #          "admin_price" -> every account gets the admin's absolute price.
    "SLTP_REFERENCE": os.getenv("SLTP_REFERENCE", "own_fill"),
    # Q5d: how to amend SL/TP when the exchange cannot amend in place.
    "SLTP_AMEND_STRATEGY": os.getenv("SLTP_AMEND_STRATEGY", "place_then_cancel"),
    # Q5e: what to do when the entry filled but SL/TP placement failed.
    "SLTP_FAILURE_POLICY": os.getenv("SLTP_FAILURE_POLICY", "retry_then_close"),
    "SLTP_FAILURE_RETRIES": int(os.getenv("SLTP_FAILURE_RETRIES", "2")),
    # Q5a guard: refuse an SL that sits at or beyond the liquidation price.
    "REJECT_SL_BEYOND_LIQUIDATION": env_bool("REJECT_SL_BEYOND_LIQUIDATION", True),
    # Spec §4 (amended, Q19). Hard per-account deadline for a fan-out leg, in
    # seconds. Started at 1.0; a VPS's exchange round trips (balance, leverage,
    # order, then SL/TP) routinely landed at 1–2s. The setup cost that made that
    # true is gone — adapters are kept warm between actions (see
    # apps/exchanges/pool.py), so a leg no longer pays a TCP+TLS handshake, and
    # on Hyperliquid no longer re-downloads the asset metadata, before its first
    # real call. 5.0 is the default: comfortably above a healthy VPS leg, so the
    # deadline stays a tripwire for genuinely stuck exchanges rather than a
    # speed bump healthy legs trip on. A leg that overruns is abandoned, not
    # awaited — and then re-read from the exchange, because abandoned is not the
    # same as failed (see apps/engine/executor.py: _reconcile*). A request that
    # already reached the exchange may have executed even though we stopped
    # listening for the reply.
    "FANOUT_TIMEOUT_SECONDS": float(os.getenv("FANOUT_TIMEOUT_SECONDS", "5.0")),
    # Spec §3. Leverage bounds offered by the UI.
    "MIN_LEVERAGE": int(os.getenv("MIN_LEVERAGE", "1")),
    "MAX_LEVERAGE": int(os.getenv("MAX_LEVERAGE", "10")),
    # Spec §7 recommendation: platform-wide kill switch. This is the *pin* —
    # true here means the halt cannot be cleared from the panel. The everyday
    # switch is the KillSwitch row (see apps/trading/killswitch.py).
    "STOP_ALL": env_bool("STOP_ALL", False),
}

# --- Market data (spec §3) --------------------------------------------------
# Public price feeds only: no credentials, no signing, never per account.
# Providers are tried in order. When none answers the API returns 503 and the
# panel says the feed is down — there is no synthetic fallback, because a chart
# that invents candles is how someone reads a price that never existed. Set
# ENABLED=false only in an air-gapped deployment, where the panel then shows no
# prices at all rather than made-up ones.
MARKET_DATA = {
    # Same reasoning as the database and channel layer above: the suite must
    # never reach out to a real exchange, so it is off unless a test stubs the
    # transport and opts in explicitly.
    "ENABLED": False if RUNNING_TESTS else env_bool("MARKET_DATA_ENABLED", True),
    # Pin the outbound proxy for price calls. Empty means "use the shell's
    # HTTPS_PROXY/ALL_PROXY if httpx can speak it, else go direct" — see
    # marketdata.resolve_proxy. Set explicitly where the exchange is only
    # reachable through a proxy.
    "PROXY": os.getenv("MARKET_DATA_PROXY", ""),
    # Fallbacks *behind* the connected exchanges. The venue an account is on is
    # always tried first (see marketdata._configured_providers), so these only
    # matter before the first connect or when that exchange is unreachable.
    #
    # Hyperliquid leads: it is the flagged-important venue, so when the feed has
    # to fall back it should still quote the exchange the admin actually trades
    # rather than dropping to Binance/Bybit for a chart that is then compared
    # against Hyperliquid fills.
    "PROVIDERS": [
        p.strip()
        for p in os.getenv("MARKET_DATA_PROVIDERS", "hyperliquid,binance,bybit").split(",")
        if p.strip()
    ],
    # Pin the feed to exactly one venue, overriding both the connected-exchange
    # preference and the fallback list above.
    #
    # The default arrangement quotes whichever exchange the accounts sit on,
    # which means the chart can silently change venue when an account is added.
    # For a desk that reads Hyperliquid's book and sizes against it, that is a
    # correctness problem rather than a convenience: a Binance mark compared
    # against a Hyperliquid fill is a different number. Pinning makes the venue
    # a deployment decision, and the panel keeps naming it in the feed badge.
    #
    # There is no fallback under a pin — that is the point. A pinned venue that
    # cannot answer returns 503 and the panel says "no price feed", exactly as
    # it does when every provider is down. Note Hyperliquid is perpetuals only,
    # so pinning it leaves the spot chart with no feed.
    #
    # Hyperliquid by default because it is the flagged-important venue and the
    # one this desk reads. Set MARKET_DATA_PIN empty to restore the
    # connected-exchange-first behaviour with the fallbacks above.
    "PIN": os.getenv("MARKET_DATA_PIN", "hyperliquid").strip(),
    # --- history download (accounts page progress bar) ---------------------
    # Every timeframe the chart offers, for the busiest pairs, one year back.
    # A year of 1m bars is ~525k rows per pair: dial these down where storage
    # or first-connect time matters more than intraday scrollback.
    "BACKFILL_INTERVALS": [
        i.strip()
        for i in os.getenv("BACKFILL_INTERVALS", "1m,5m,15m,1h,4h,1d").split(",")
        if i.strip()
    ],
    "BACKFILL_PAIRS": int(os.getenv("BACKFILL_PAIRS", "50")),
    "BACKFILL_DAYS": int(os.getenv("BACKFILL_DAYS", "365")),
    # Start the download by itself when the first account connects.
    "AUTO_SYNC": False if RUNNING_TESTS else env_bool("MARKET_DATA_AUTO_SYNC", True),
    # --- on-demand chart history --------------------------------------------
    # The chart's own download for a pair the bulk backfill never reached: at
    # least this many days of bars, on every timeframe, fetched in a background
    # thread the moment the pair's chart is opened (see catalogue.ensure_history).
    "CHART_BACKFILL_DAYS": int(os.getenv("CHART_BACKFILL_DAYS", "1")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

# --- Production hardening ---------------------------------------------------
# The launch topology: Caddy terminates TLS, the Nuxt panel forwards the
# browser's scheme and host as X-Forwarded-Proto / X-Forwarded-Host, and Django
# is reachable only from the panel over the Docker network (no host port is
# published). Those headers cannot be spoofed from outside, so trusting them is
# safe here. Everything defaults OFF under DEBUG and ON in production; each can
# be overridden explicitly from the environment.
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_REFERRER_POLICY = "same-origin"

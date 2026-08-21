"""Django settings. Dev defaults are safe; production values come from the environment."""

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured
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
    # No models of its own — it is here so its management commands
    # (wait_for_db, sqlite_to_postgres, backup_db) are discoverable.
    "apps.core",
    "apps.accounts",
    "apps.trading",
    "apps.logging",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "apps.logging.middleware.RequestLoggingMiddleware",
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
    # After AuthenticationMiddleware: it needs `request.user` to know whose
    # session it is looking at.
    "apps.accounts.sessions.panel_session_middleware",
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

# PostgreSQL, everywhere, including the test suite. There is no SQLite branch any
# more and no `USE_SQLITE` flag: the two engines disagree in exactly the places
# this application is sensitive to — NUMERIC handling, concurrent writers (the
# candle archive has three background threads writing it), and the semantics of
# `bulk_create(ignore_conflicts=True)` — so a suite that passes on one proves
# little about the other. Set up a local server with `./run.sh setup`.
RUNNING_TESTS = "pytest" in sys.modules


def database_config() -> dict:
    """One database, from ``DATABASE_URL`` when set, else the discrete vars.

    The URL form is what a hosted Postgres hands you and is the single value a
    deployment has to get right; the ``POSTGRES_*`` vars stay because both
    compose stacks pin ``POSTGRES_HOST: db`` on the service and a URL would have
    to be reassembled there for no gain.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        parts = urlsplit(url)
        if parts.scheme not in {"postgres", "postgresql"}:
            raise ImproperlyConfigured(
                f"DATABASE_URL must be a postgres:// URL, got {parts.scheme or 'nothing'}://"
            )
        config = {
            "NAME": unquote(parts.path.lstrip("/")) or "walletmanager",
            "USER": unquote(parts.username or ""),
            "PASSWORD": unquote(parts.password or ""),
            "HOST": parts.hostname or "127.0.0.1",
            "PORT": str(parts.port or 5432),
        }
    else:
        config = {
            "NAME": os.getenv("POSTGRES_DB", "walletmanager"),
            "USER": os.getenv("POSTGRES_USER", "walletmanager"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            # 127.0.0.1 is the host-run default; both compose files set `db`
            # explicitly on the service, so this never applies in a container.
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }

    config["ENGINE"] = "django.db.backends.postgresql"
    # Reconnecting per request used to be free; it is not now that the chart
    # poll writes archived bars on the way past.
    config["CONN_MAX_AGE"] = int(os.getenv("DB_CONN_MAX_AGE", "60"))
    config["CONN_HEALTH_CHECKS"] = True
    # Names the connection in pg_stat_activity, so the background threads that
    # write candles are distinguishable from the request path when one blocks.
    config["OPTIONS"] = {"application_name": os.getenv("DB_APPLICATION_NAME", "walletmanager")}

    if RUNNING_TESTS:
        # The suite runs on Postgres, but never on the deployment's database.
        # pytest-django derives the test database as `test_<NAME>`; pinning the
        # name here as well means a stray `--reuse-db` or a hand-run
        # `manage.py test` cannot land on a database holding real credentials.
        config["TEST"] = {"NAME": f"test_{config['NAME']}"}
    return config


DATABASES = {"default": database_config()}

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
    # real call. 10.0 is the default: far above a healthy VPS leg, so the
    # deadline stays a tripwire for genuinely stuck exchanges rather than a
    # speed bump healthy legs trip on. A leg that overruns is abandoned, not
    # awaited — and then re-read from the exchange, because abandoned is not the
    # same as failed (see apps/engine/executor.py: _reconcile*). A request that
    # already reached the exchange may have executed even though we stopped
    # listening for the reply. The same is true of every *other* way a leg can
    # fail after the order went out — an HTTP read timeout, a 5xx, a dropped
    # connection — so the re-read covers all of them, not only the deadline.
    "FANOUT_TIMEOUT_SECONDS": float(os.getenv("FANOUT_TIMEOUT_SECONDS", "10.0")),
    # Spec §3. Leverage bounds offered by the UI.
    "MIN_LEVERAGE": int(os.getenv("MIN_LEVERAGE", "1")),
    "MAX_LEVERAGE": int(os.getenv("MAX_LEVERAGE", "10")),
    # Spec §7 recommendation: platform-wide kill switch. This is the *pin* —
    # true here means the halt cannot be cleared from the panel. The everyday
    # switch is the KillSwitch row (see apps/trading/killswitch.py).
    "STOP_ALL": env_bool("STOP_ALL", False),
}

# --- Financial ledger (deposits, withdrawals, PnL) --------------------------
# The keys are trade-only (spec §7), so no exchange API can report a transfer.
# What the platform *can* do is subtract: equity moved by X, the closed legs it
# placed itself explain Y, the recorded cash flows explain Z, and the remainder
# is a deposit or a withdrawal nobody wrote down. That remainder is proposed for
# review, never booked — apps/accounts/detection.py.
LEDGER = {
    "DETECT_ENABLED": env_bool("LEDGER_DETECT_ENABLED", True),
    # Fees, funding and exchange rounding move equity without anyone moving
    # money. A proposal needs to clear the larger of a flat floor and a share of
    # the account, so a $50 account is not swamped and a $500k one is not buried
    # in dust. Both in USDT / percent, parsed as Decimal at the point of use.
    "DETECT_MIN_USDT": os.getenv("LEDGER_DETECT_MIN_USDT", "1"),
    "DETECT_MIN_PCT": os.getenv("LEDGER_DETECT_MIN_PCT", "0.25"),
    # --- telling a trade result from somebody's cash (apps/accounts/classify) --
    "CLASSIFY_ENABLED": env_bool("LEDGER_CLASSIFY_ENABLED", True),
    # off  — classify nothing, every change waits for a person (the old behaviour)
    # safe — act on the confident rules; only a genuinely ambiguous change queues
    # all  — act on everything, the standing "it was the trade" default included
    "AUTO_RESOLVE": os.getenv("LEDGER_AUTO_RESOLVE", "safe"),
    # How close to a trade a balance change has to be for the trade to be a
    # candidate explanation at all. Money that moves while nothing has traded
    # for this long came from outside. Default 15 minutes: "a few minutes after
    # the trade" is still the trade's neighbourhood, an hour later is not.
    "TRADE_WINDOW_SECONDS": os.getenv("LEDGER_TRADE_WINDOW_SECONDS", "900"),
    # A leftover this small next to the trade's own PnL is fees, funding and the
    # exchange's rounding — the trade, not a transfer.
    "TRADE_TOLERANCE_PCT": os.getenv("LEDGER_TRADE_TOLERANCE_PCT", "10"),
    # What counts as an emptied account. Exchanges leave dust behind on a full
    # withdrawal, and nobody trades to exactly zero.
    "EMPTY_PCT": os.getenv("LEDGER_EMPTY_PCT", "2"),
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
    # Pairs that are always backfilled regardless of 24h volume ranking.
    # These are base asset names (e.g. "BTC", "SOL") — the backfill system
    # resolves them to the full symbol (e.g. "BTCUSDT") during queue build.
    "BACKFILL_PRIORITY_PAIRS": [
        p.strip().upper()
        for p in os.getenv(
            "BACKFILL_PRIORITY_PAIRS",
            "VVV,BTC,HYPE,PUMP,SOL,ZEC,LINK,KAITO,BNB,WLD,LIT",
        ).split(",")
        if p.strip()
    ],
    # Start the download by itself when the first account connects.
    "AUTO_SYNC": False if RUNNING_TESTS else env_bool("MARKET_DATA_AUTO_SYNC", True),
    # --- the candle archive --------------------------------------------------
    # Write every *closed* bar the platform sees to `StoredCandle`, whatever
    # brought it in: the chart's REST poll and the exchange WebSocket, not only
    # the two backfill jobs. This is what makes the chart's scrollback deepen on
    # its own while the panel is simply open, and nothing ever prunes the table.
    #
    # Off under pytest for the same reason ENABLED is: a test that stubs the
    # transport must not silently gain rows in a table other tests assert on.
    # Tests that mean to exercise the archive opt in with override_settings.
    "ARCHIVE": False if RUNNING_TESTS else env_bool("MARKET_DATA_ARCHIVE", True),
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
    "filters": {"not_library_noise": {"()": "apps.logging.handlers.NoiseFilter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "database": {
            "class": "apps.logging.handlers.DatabaseHandler",
            "level": "INFO",
            # The database handler is what the admin reads in /logs, and it hangs
            # off the root logger — so without this filter it collects every
            # library's INFO chatter (one httpx line per market-data poll, whose
            # URL carries a Binance signature). The console keeps all of it.
            "filters": ["not_library_noise"],
        },
    },
    "root": {
        "handlers": ["console", "database"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
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

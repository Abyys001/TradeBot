# System Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, queryable, live-tailable system log that captures every event across the stack — trade errors, exchange failures, HTTP access, internal errors — accessible via a new "System Log" sidebar link with filtering and real-time WebSocket tail.

**Architecture:** New `apps.logging` Django app with a `LogEntry` model, a custom `DatabaseHandler` that hooks into Python's logging module (zero-change catch-all), a `system_log()` helper for structured entries, an HTTP access middleware, a REST API with filtering/pagination, WebSocket broadcast via the existing `"trading"` channel group, and a full frontend page with filter bar, auto-scrolling log table, and live/paused toggle.

**Tech Stack:** Django 5 + DRF + Channels (backend), Nuxt 3 + TypeScript + Pinia + Tailwind (frontend), existing `TradingConsumer` WebSocket consumer, existing `useNavigation` composable for sidebar.

## Global Constraints

- `Decimal` everywhere for money (not relevant here, but project-wide)
- Hidden accounts: `apps.accounts.visibility` never imported from `apps.engine/` or `apps.trading/services.py`
- WebSocket is staff-only and same-origin-only, gated in `TradingConsumer.connect()`
- All frontend strings through `useI18n()` — English first, Persian second
- Existing logging pattern: `logger = logging.getLogger(__name__)` in every module
- Existing notification pattern: `Notification` model + `_broadcast("notification", payload)` + WebSocket consumer handler
- Existing broadcast pattern: `channel_layer.group_send("trading", {"type": event, "payload": payload})`

---

### Task 1: Create the `apps.logging` Django app — model + migration

**Files:**
- Create: `backend/apps/logging/__init__.py`
- Create: `backend/apps/logging/apps.py`
- Create: `backend/apps/logging/models.py`
- Create: `backend/apps/logging/migrations/__init__.py`
- Modify: `backend/config/settings.py:21-34` (INSTALLED_APPS)

**Interfaces:**
- Consumes: `apps.accounts.ConnectedAccount` (FK), `apps.trading.Trade` (FK)
- Produces: `LogEntry` model with `Level` and `Category` TextChoices, indexed on `(level, timestamp)`, `(category, timestamp)`, `(account, timestamp)`

- [ ] **Step 1: Create `backend/apps/logging/__init__.py`**

```python
# empty file
```

- [ ] **Step 2: Create `backend/apps/logging/apps.py`**

```python
from django.apps import AppConfig


class LoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.logging"
    label = "logging"

    def ready(self) -> None:
        from django.db.models.signals import post_delete

        from apps.accounts.models import ConnectedAccount
        from apps.exchanges.pool import evict

        def _retire(sender, instance, **kwargs):  # noqa: ANN001, ARG001
            evict(instance.id)

        post_delete.connect(
            _retire, sender=ConnectedAccount, dispatch_uid="exchanges.pool.retire"
        )
```

- [ ] **Step 3: Create `backend/apps/logging/models.py`**

```python
from django.db import models


class Level(models.TextChoices):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Category(models.TextChoices):
    TRADE = "TRADE"
    EXCHANGE = "EXCHANGE"
    SYSTEM = "SYSTEM"
    AUTH = "AUTH"
    MARKET_DATA = "MARKET_DATA"
    ENGINE = "ENGINE"
    ADMIN = "ADMIN"


class LogEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=8, choices=Level.choices)
    category = models.CharField(max_length=16, choices=Category.choices)
    source = models.CharField(max_length=200)
    message = models.TextField()
    account = models.ForeignKey(
        "accounts.ConnectedAccount",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_entries",
    )
    trade = models.ForeignKey(
        "trading.Trade",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_entries",
    )
    exchange = models.CharField(max_length=20, null=True, blank=True)
    error_code = models.CharField(max_length=60, null=True, blank=True)
    context = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["level", "timestamp"]),
            models.Index(fields=["category", "timestamp"]),
            models.Index(fields=["account", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.timestamp:%Y-%m-%d %H:%M:%S} {self.source}: {self.message[:80]}"
```

- [ ] **Step 4: Create `backend/apps/logging/migrations/__init__.py`**

```python
# empty file
```

- [ ] **Step 5: Register the app in `backend/config/settings.py:21-34`**

Add `"apps.logging"` after `"apps.trading"` in INSTALLED_APPS:

```python
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
    "apps.logging",
]
```

- [ ] **Step 6: Generate and run the migration**

Run: `cd backend && python manage.py makemigrations logging && python manage.py migrate`

Expected: `Migrations for 'logging': ... 0001_initial.py` then `Apply all` successful.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/logging/ backend/config/settings.py
git commit -m "feat(logging): add LogEntry model with level, category, account/trade FKs, indexes"
```

---

### Task 2: DatabaseHandler — capture all Python logging to DB

**Files:**
- Create: `backend/apps/logging/handlers.py`
- Create: `backend/apps/logging/tests/test_handler.py`
- Modify: `backend/config/settings.py:294-300` (LOGGING config)

**Interfaces:**
- Consumes: `LogEntry` model (from Task 1)
- Produces: `DatabaseHandler` class — `logging.Handler` subclass that writes to DB and broadcasts to channel layer

- [ ] **Step 1: Write the failing test**

Create `backend/apps/logging/__init__.py` is already done. Create the test file:

```python
# backend/apps/logging/tests/__init__.py
# empty
```

```python
# backend/apps/logging/tests/test_handler.py
import logging

from apps.logging.handlers import DatabaseHandler
from apps.logging.models import LogEntry


def test_handler_creates_log_entry(db):
    """Handler emits a LogEntry when a logger call is made."""
    handler = DatabaseHandler()
    logger = logging.getLogger("apps.engine.fanout_test")
    logger.addHandler(handler)
    try:
        logger.warning("test leg failed")
        assert LogEntry.objects.count() == 1
        entry = LogEntry.objects.first()
        assert entry.level == "WARNING"
        assert entry.category == "ENGINE"
        assert entry.message == "test leg failed"
        assert entry.source == "apps.engine.fanout_test"
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_handler_ignores_debug(db):
    """DEBUG messages are not persisted."""
    handler = DatabaseHandler()
    logger = logging.getLogger("apps.debug_test")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        logger.debug("should not appear")
        assert LogEntry.objects.count() == 0
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_handler_category_derivation(db):
    """Category is derived from logger name prefix."""
    handler = DatabaseHandler()
    cases = [
        ("apps.engine.fanout", "ENGINE"),
        ("apps.exchanges.binance", "EXCHANGE"),
        ("apps.trading.services", "TRADE"),
        ("apps.accounts.views", "ADMIN"),
        ("django.request", "SYSTEM"),
        ("some.other.logger", "SYSTEM"),
    ]
    for logger_name, expected_category in cases:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        try:
            logger.info(f"test {logger_name}")
            entry = LogEntry.objects.order_by("-timestamp").first()
            assert entry.category == expected_category, f"{logger_name} -> {entry.category}"
        finally:
            logger.removeHandler(handler)


def test_handler_extracts_extras(db):
    """Structured extras are persisted in the entry."""
    handler = DatabaseHandler()
    logger = logging.getLogger("apps.extras_test")
    logger.addHandler(handler)
    try:
        logger.error(
            "order failed",
            extra={
                "account_id": 42,
                "trade_id": 7,
                "exchange": "binance",
                "error_code": "RateLimited",
                "context": {"retry_after": 5},
            },
        )
        entry = LogEntry.objects.first()
        assert entry.account_id == 42
        assert entry.trade_id == 7
        assert entry.exchange == "binance"
        assert entry.error_code == "RateLimited"
        assert entry.context == {"retry_after": 5}
    finally:
        logger.removeHandler(handler)
        handler.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest apps/logging/tests/test_handler.py -v`
Expected: FAIL with `ImportError: cannot import name 'DatabaseHandler'`

- [ ] **Step 3: Implement DatabaseHandler**

```python
# backend/apps/logging/handlers.py
"""Custom logging handler that persists log entries to the database and
broadcasts them over the WebSocket for live tail."""

from __future__ import annotations

import logging
import traceback
from typing import Any

LEVEL_MAP = {
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

CATEGORY_PREFIXES = {
    "apps.engine": "ENGINE",
    "apps.exchanges": "EXCHANGE",
    "apps.trading": "TRADE",
    "apps.accounts": "ADMIN",
    "apps.logging": "SYSTEM",
    "django": "SYSTEM",
}

EXTRA_ATTRS = ("account_id", "trade_id", "exchange", "error_code", "context", "request_id")


def _derive_category(name: str) -> str:
    for prefix, category in CATEGORY_PREFIXES.items():
        if name.startswith(prefix):
            return category
    return "SYSTEM"


class DatabaseHandler(logging.Handler):
    """Emit log records as LogEntry rows and broadcast to WebSocket group."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = LEVEL_MAP.get(record.levelno)
            if level is None:
                return

            extra: dict[str, Any] = {}
            for attr in EXTRA_ATTRS:
                val = getattr(record, attr, None)
                if val is not None:
                    extra[attr] = val

            account = None
            if "account_id" in extra:
                try:
                    from apps.accounts.models import ConnectedAccount

                    account = ConnectedAccount.objects.get(pk=extra["account_id"])
                except Exception:  # noqa: BLE001
                    pass

            trade = None
            if "trade_id" in extra:
                try:
                    from apps.trading.models import Trade

                    trade = Trade.objects.get(pk=extra["trade_id"])
                except Exception:  # noqa: BLE001
                    pass

            entry_data = {
                "level": level,
                "category": _derive_category(record.name),
                "source": record.name,
                "message": record.getMessage(),
                "account": account,
                "trade": trade,
                "exchange": extra.get("exchange"),
                "error_code": extra.get("error_code"),
                "context": extra.get("context"),
                "request_id": extra.get("request_id"),
            }

            from apps.logging.models import LogEntry

            entry = LogEntry.objects.create(**entry_data)

            self._broadcast(entry)
        except Exception:  # noqa: BLE001 — a logging handler must never raise
            self.handleError(record)

    def _broadcast(self, entry) -> None:
        """Fire-and-forget broadcast to the trading WebSocket group."""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            if layer is None:
                return
            async_to_sync(layer.group_send)(
                "trading",
                {
                    "type": "system_log.entry",
                    "entry": {
                        "id": entry.id,
                        "timestamp": entry.timestamp.isoformat(),
                        "level": entry.level,
                        "category": entry.category,
                        "source": entry.source,
                        "message": entry.message,
                        "account_id": entry.account_id,
                        "trade_id": entry.trade_id,
                        "exchange": entry.exchange,
                        "error_code": entry.error_code,
                        "context": entry.context,
                    },
                },
            )
        except Exception:  # noqa: BLE001 — broadcast failure must not break logging
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest apps/logging/tests/test_handler.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Register handler in Django LOGGING config**

Modify `backend/config/settings.py:294-300`:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "database": {
            "class": "apps.logging.handlers.DatabaseHandler",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console", "database"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}
```

- [ ] **Step 6: Run full test suite to ensure no regressions**

Run: `cd backend && python -m pytest -x -q`
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/logging/handlers.py backend/apps/logging/tests/ backend/config/settings.py
git commit -m "feat(logging): DatabaseHandler captures all Python logging to LogEntry"
```

---

### Task 3: system_log() helper + HTTP access middleware

**Files:**
- Create: `backend/apps/logging/utils.py`
- Create: `backend/apps/logging/middleware.py`
- Create: `backend/apps/logging/tests/test_middleware.py`
- Create: `backend/apps/logging/tests/test_utils.py`
- Modify: `backend/config/settings.py:36-48` (MIDDLEWARE)

**Interfaces:**
- Consumes: `DatabaseHandler` (Task 2) via the standard logging module
- Produces: `system_log(level, category, message, **kwargs)` helper; `RequestLoggingMiddleware` class

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/logging/tests/test_utils.py
from apps.logging.models import LogEntry
from apps.logging.utils import system_log


def test_system_log_creates_entry(db):
    system_log("error", "TRADE", "fan-out failed", exchange="binance", error_code="timeout")
    assert LogEntry.objects.count() == 1
    entry = LogEntry.objects.first()
    assert entry.level == "ERROR"
    assert entry.category == "TRADE"
    assert entry.message == "fan-out failed"
    assert entry.exchange == "binance"
    assert entry.error_code == "timeout"


def test_system_log_with_account(db, connected_account):
    system_log(
        "warning",
        "ENGINE",
        "leg slow",
        account_id=connected_account.id,
        trade_id=None,
        context={"ms": 3000},
    )
    entry = LogEntry.objects.first()
    assert entry.account_id == connected_account.id
    assert entry.context == {"ms": 3000}
```

```python
# backend/apps/logging/tests/test_middleware.py
from unittest.mock import MagicMock

from apps.logging.models import LogEntry
from apps.logging.middleware import RequestLoggingMiddleware


def _make_request(path="/api/trading/policy/", method="GET", status_code=200, user=None):
    request = MagicMock()
    request.path = path
    request.method = method
    request.META = {}
    if user:
        request.user = user
    return request


def _make_response(status_code=200):
    response = MagicMock()
    response.status_code = status_code
    return response


def test_middleware_logs_request(db):
    middleware = RequestLoggingMiddleware(lambda r: _make_response(200))
    request = _make_request()
    middleware(request)
    # At least one entry for the request
    assert LogEntry.objects.filter(category="SYSTEM").exists()


def test_middleware_skips_health(db):
    middleware = RequestLoggingMiddleware(lambda r: _make_response(200))
    request = _make_request(path="/api/health/")
    middleware(request)
    assert LogEntry.objects.count() == 0


def test_middleware_logs_5xx_as_error(db):
    def view(request):
        resp = _make_response(500)
        return resp

    middleware = RequestLoggingMiddleware(view)
    request = _make_request()
    middleware(request)
    entry = LogEntry.objects.first()
    assert entry.level == "ERROR"


def test_middleware_logs_4xx_as_warning(db):
    def view(request):
        resp = _make_response(404)
        return resp

    middleware = RequestLoggingMiddleware(view)
    request = _make_request()
    middleware(request)
    entry = LogEntry.objects.first()
    assert entry.level == "WARNING"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest apps/logging/tests/test_utils.py apps/logging/tests/test_middleware.py -v`
Expected: FAIL with `ImportError: cannot import name 'system_log'` / `ImportError: cannot import name 'RequestLoggingMiddleware'`

- [ ] **Step 3: Implement system_log() helper**

```python
# backend/apps/logging/utils.py
"""Convenience wrapper for structured system log entries."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.logging.system")


def system_log(level: str, category: str, message: str, **kwargs: Any) -> None:
    """Log a structured entry that gets persisted and broadcast.

    Extra kwargs are filtered to known attributes and attached as ``extra=``
    to the underlying logger call.  The DatabaseHandler picks them up and
    writes them to the LogEntry columns.
    """
    known = ("account_id", "trade_id", "exchange", "error_code", "context", "request_id")
    extra = {k: v for k, v in kwargs.items() if k in known and v is not None}
    getattr(logger, level)(message, extra=extra)
```

- [ ] **Step 4: Implement RequestLoggingMiddleware**

```python
# backend/apps/logging/middleware.py
"""Middleware that logs every HTTP request/response to the system log."""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger("apps.logging.http")

_SKIP_PATHS = frozenset({"/api/health/"})


class RequestLoggingMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request) -> object:
        path = request.path
        if path in _SKIP_PATHS:
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        status = response.status_code
        user = getattr(request, "user", None)
        username = getattr(user, "username", None) if user and user.is_authenticated else None

        extra: dict = {
            "context": {
                "method": request.method,
                "path": path,
                "status": status,
                "duration_ms": duration_ms,
                "user": username,
            }
        }

        if status >= 500:
            logger.error("%s %s %d %sms", request.method, path, status, duration_ms, extra=extra)
        elif status >= 400:
            logger.warning("%s %s %d %sms", request.method, path, status, duration_ms, extra=extra)
        else:
            logger.info("%s %s %d %sms", request.method, path, status, duration_ms, extra=extra)

        return response
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest apps/logging/tests/test_utils.py apps/logging/tests/test_middleware.py -v`
Expected: All tests PASS

- [ ] **Step 6: Register middleware in settings.py**

Add `"apps.logging.middleware.RequestLoggingMiddleware"` at the end of the MIDDLEWARE list in `backend/config/settings.py:36-48`:

```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.logging.middleware.RequestLoggingMiddleware",
]
```

- [ ] **Step 7: Commit**

```bash
git add backend/apps/logging/utils.py backend/apps/logging/middleware.py backend/apps/logging/tests/test_utils.py backend/apps/logging/tests/test_middleware.py backend/config/settings.py
git commit -m "feat(logging): system_log() helper and HTTP access logging middleware"
```

---

### Task 4: REST API — LogEntryViewSet + serializer + URLs

**Files:**
- Create: `backend/apps/logging/serializers.py`
- Create: `backend/apps/logging/views.py`
- Create: `backend/apps/logging/urls.py`
- Create: `backend/apps/logging/tests/test_api.py`
- Modify: `backend/config/urls.py:6-14`

**Interfaces:**
- Consumes: `LogEntry` model (Task 1)
- Produces: `/api/logging/` (list), `/api/logging/{id}/` (detail), `/api/logging/prune/` (DELETE action)

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/logging/tests/test_api.py
import datetime

from django.urls import reverse
from rest_framework.test import APIClient

from apps.logging.models import LogEntry


def _create_entries(count=3, **overrides):
    entries = []
    for i in range(count):
        data = {
            "level": "INFO",
            "category": "SYSTEM",
            "source": "test",
            "message": f"test message {i}",
        }
        data.update(overrides)
        entries.append(LogEntry.objects.create(**data))
    return entries


def test_list_logs(db, admin_client):
    _create_entries(3)
    resp = admin_client.get(reverse("logentry-list"))
    assert resp.status_code == 200
    assert resp.data["count"] == 3


def test_filter_by_level(db, admin_client):
    _create_entries(2, level="INFO")
    _create_entries(1, level="ERROR")
    resp = admin_client.get(reverse("logentry-list") + "?level=ERROR")
    assert resp.data["count"] == 1


def test_filter_by_category(db, admin_client):
    _create_entries(2, category="TRADE")
    _create_entries(1, category="ENGINE")
    resp = admin_client.get(reverse("logentry-list") + "?category=ENGINE")
    assert resp.data["count"] == 1


def test_search(db, admin_client):
    _create_entries(1, message="timeout on binance")
    _create_entries(1, message="order filled")
    resp = admin_client.get(reverse("logentry-list") + "?search=timeout")
    assert resp.data["count"] == 1


def test_prune(db, admin_client):
    old = LogEntry.objects.create(
        level="INFO",
        category="SYSTEM",
        source="test",
        message="old",
        timestamp=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31),
    )
    recent = LogEntry.objects.create(
        level="INFO",
        category="SYSTEM",
        source="test",
        message="recent",
    )
    resp = admin_client.delete(reverse("logentry-prune"))
    assert resp.status_code == 200
    assert not LogEntry.objects.filter(pk=old.pk).exists()
    assert LogEntry.objects.filter(pk=recent.pk).exists()


def test_requires_admin(db, client):
    resp = client.get(reverse("logentry-list"))
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest apps/logging/tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.logging.views'`

- [ ] **Step 3: Implement serializer**

```python
# backend/apps/logging/serializers.py
from rest_framework import serializers

from apps.logging.models import LogEntry


class LogEntrySerializer(serializers.ModelSerializer):
    account_label = serializers.CharField(source="account.label", read_only=True, default=None)

    class Meta:
        model = LogEntry
        fields = [
            "id",
            "timestamp",
            "level",
            "category",
            "source",
            "message",
            "account",
            "account_label",
            "trade",
            "exchange",
            "error_code",
            "context",
            "request_id",
        ]
        read_only_fields = fields
```

- [ ] **Step 4: Implement viewset**

```python
# backend/apps/logging/views.py
import datetime

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.logging.models import LogEntry
from apps.logging.serializers import LogEntrySerializer


class LogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LogEntrySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = LogEntry.objects.select_related("account").all()

        level = self.request.query_params.get("level")
        if level:
            qs = qs.filter(level=level)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source__icontains=source)

        account = self.request.query_params.get("account")
        if account:
            qs = qs.filter(account_id=account)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(message__icontains=search) | Q(error_code__icontains=search))

        start = self.request.query_params.get("start")
        if start:
            qs = qs.filter(timestamp__gte=start)

        end = self.request.query_params.get("end")
        if end:
            qs = qs.filter(timestamp__lte=end)

        return qs

    @action(detail=False, methods=["delete"])
    def prune(self, request):
        cutoff = timezone.now() - datetime.timedelta(days=30)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)
```

- [ ] **Step 5: Implement URLs**

```python
# backend/apps/logging/urls.py
from rest_framework.routers import DefaultRouter

from apps.logging.views import LogEntryViewSet

router = DefaultRouter()
router.register("logs", LogEntryViewSet, basename="logentry")

urlpatterns = router.urls
```

- [ ] **Step 6: Register in config/urls.py**

Modify `backend/config/urls.py:6-14`:

```python
from django.contrib import admin
from django.urls import include, path

from apps.core.health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/trading/", include("apps.trading.urls")),
    path("api/logging/", include("apps.logging.urls")),
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest apps/logging/tests/test_api.py -v`
Expected: All 6 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/apps/logging/serializers.py backend/apps/logging/views.py backend/apps/logging/urls.py backend/apps/logging/tests/test_api.py backend/config/urls.py
git commit -m "feat(logging): REST API for log entries with filtering, search, and prune"
```

---

### Task 5: WebSocket broadcast — consumer handler

**Files:**
- Modify: `backend/apps/trading/consumers.py:174-230` (add `system_log_entry` handler)

**Interfaces:**
- Consumes: `system_log.entry` channel layer event from `DatabaseHandler._broadcast()` (Task 2)
- Produces: `system_log_entry()` handler on `TradingConsumer` that forwards to client with hidden-account filtering

- [ ] **Step 1: Add the consumer handler**

In `backend/apps/trading/consumers.py`, add after the `market_stream_up` handler (around line 223), before the `encode_json` classmethod:

```python
    async def system_log_entry(self, event: dict) -> None:
        """Forward a system log entry, filtering hidden accounts."""
        entry = event["entry"]
        if not self.sees_hidden and entry.get("account_id"):
            hidden = await _hidden_ids()
            if entry["account_id"] in hidden:
                return
        await self.send_json({"type": "system_log", "entry": entry})
```

- [ ] **Step 2: Run existing consumer tests**

Run: `cd backend && python -m pytest apps/trading/tests/test_consumer.py -v`
Expected: All existing tests still pass.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/trading/consumers.py
git commit -m "feat(logging): WebSocket system_log_entry handler with hidden-account filtering"
```

---

### Task 6: Log cleanup management command

**Files:**
- Create: `backend/apps/logging/management/__init__.py`
- Create: `backend/apps/logging/management/commands/__init__.py`
- Create: `backend/apps/logging/management/commands/prune_logs.py`
- Create: `backend/apps/logging/tests/test_prune.py`

**Interfaces:**
- Consumes: `LogEntry` model (Task 1)
- Produces: `python manage.py prune_logs` command

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/logging/tests/test_prune.py
import datetime

from django.core.management import call_command

from apps.logging.models import LogEntry


def test_prune_removes_old_entries(db):
    old = LogEntry.objects.create(
        level="INFO", category="SYSTEM", source="test", message="old",
        timestamp=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31),
    )
    recent = LogEntry.objects.create(
        level="INFO", category="SYSTEM", source="test", message="recent",
    )
    call_command("prune_logs")
    assert not LogEntry.objects.filter(pk=old.pk).exists()
    assert LogEntry.objects.filter(pk=recent.pk).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest apps/logging/tests/test_prune.py -v`
Expected: FAIL with `CommandNotFoundError` or similar

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p backend/apps/logging/management/commands
touch backend/apps/logging/management/__init__.py
touch backend/apps/logging/management/commands/__init__.py
```

- [ ] **Step 4: Implement the command**

```python
# backend/apps/logging/management/commands/prune_logs.py
"""Delete log entries older than 30 days."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.logging.models import LogEntry


class Command(BaseCommand):
    help = "Prune log entries older than 30 days."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(f"Pruned {deleted} log entries older than 30 days")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest apps/logging/tests/test_prune.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/apps/logging/management/
git commit -m "feat(logging): prune_logs management command for 30-day retention"
```

---

### Task 7: Frontend — Pinia store for system log

**Files:**
- Create: `frontend/stores/systemLog.ts`

**Interfaces:**
- Consumes: `useApi()` (existing), `useAccountsStore()` (existing), WebSocket `system_log` messages from `live.ts`
- Produces: `useSystemLogStore` — state, hydrate(), receive(), loadMore(), clearFilters(), toggleLiveTail()

- [ ] **Step 1: Create the store**

```typescript
// frontend/stores/systemLog.ts
import { defineStore } from 'pinia'

export interface LogEntry {
  id: number
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  category: string
  source: string
  message: string
  account: number | null
  accountLabel: string | null
  trade: number | null
  exchange: string | null
  error_code: string | null
  context: Record<string, any> | null
}

export interface LogFilters {
  level: string
  category: string
  source: string
  account: string
  search: string
  start: string
  end: string
}

const PAGE_SIZE = 50

export const useSystemLogStore = defineStore('systemLog', {
  state: () => ({
    entries: [] as LogEntry[],
    filters: {
      level: '',
      category: '',
      source: '',
      account: '',
      search: '',
      start: '',
      end: '',
    } as LogFilters,
    liveTail: true,
    loading: false,
    page: 1,
    total: 0,
  }),

  actions: {
    async hydrate() {
      this.loading = true
      try {
        const params = new URLSearchParams()
        if (this.filters.level) params.set('level', this.filters.level)
        if (this.filters.category) params.set('category', this.filters.category)
        if (this.filters.source) params.set('source', this.filters.source)
        if (this.filters.account) params.set('account', this.filters.account)
        if (this.filters.search) params.set('search', this.filters.search)
        if (this.filters.start) params.set('start', this.filters.start)
        if (this.filters.end) params.set('end', this.filters.end)
        params.set('page', String(this.page))
        params.set('page_size', String(PAGE_SIZE))

        const data = await useApi().logs(params.toString())
        this.entries = data.results.map(this._enrich)
        this.total = data.count
      } catch {
        // keep existing entries on network failure
      } finally {
        this.loading = false
      }
    },

    async loadMore() {
      if (this.loading) return
      this.loading = true
      try {
        const params = new URLSearchParams()
        if (this.filters.level) params.set('level', this.filters.level)
        if (this.filters.category) params.set('category', this.filters.category)
        if (this.filters.source) params.set('source', this.filters.source)
        if (this.filters.account) params.set('account', this.filters.account)
        if (this.filters.search) params.set('search', this.filters.search)
        if (this.filters.start) params.set('start', this.filters.start)
        if (this.filters.end) params.set('end', this.filters.end)
        this.page++
        params.set('page', String(this.page))
        params.set('page_size', String(PAGE_SIZE))

        const data = await useApi().logs(params.toString())
        this.entries.push(...data.results.map(this._enrich))
        this.total = data.count
      } catch {
        this.page--
      } finally {
        this.loading = false
      }
    },

    receive(entry: Omit<LogEntry, 'accountLabel'>) {
      const enriched = this._enrich(entry)
      // Apply current filters client-side
      if (this.filters.level && enriched.level !== this.filters.level) return
      if (this.filters.category && enriched.category !== this.filters.category) return
      if (this.filters.source && !enriched.source.includes(this.filters.source)) return
      if (this.filters.account && String(enriched.account) !== this.filters.account) return
      if (
        this.filters.search &&
        !enriched.message.toLowerCase().includes(this.filters.search.toLowerCase()) &&
        !(enriched.error_code ?? '').toLowerCase().includes(this.filters.search.toLowerCase())
      )
        return
      this.entries.unshift(enriched)
      this.total++
    },

    clearFilters() {
      this.filters = { level: '', category: '', source: '', account: '', search: '', start: '', end: '' }
      this.page = 1
      this.hydrate()
    },

    toggleLiveTail() {
      this.liveTail = !this.liveTail
    },

    _enrich(entry: any): LogEntry {
      const accounts = useAccountsStore()
      return {
        ...entry,
        accountLabel: entry.account ? accounts.labelFor(entry.account) : null,
      }
    },
  },
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/stores/systemLog.ts
git commit -m "feat(logging): Pinia store for system log with filtering and live tail"
```

---

### Task 8: Frontend — API client method for logs

**Files:**
- Modify: `frontend/composables/useApi.ts:106-117` (add `logs` and `pruneLogs` methods)

**Interfaces:**
- Consumes: `request()` helper (existing)
- Produces: `useApi().logs(params)` and `useApi().pruneLogs()`

- [ ] **Step 1: Add the API methods**

In `frontend/composables/useApi.ts`, add after the `ledgerSplit` / `saveLedgerSplit` methods (around line 116), before the closing `}`:

```typescript
    // --- system log ---
    logs: (params: string) =>
      request<{ count: number; results: any[] }>(`/logging/logs/?${params}`),
    pruneLogs: () => request<{ deleted: number }>('/logging/logs/prune/', { method: 'DELETE' }),
```

- [ ] **Step 2: Commit**

```bash
git add frontend/composables/useApi.ts
git commit -m "feat(logging): API client methods for system log endpoints"
```

---

### Task 9: Frontend — WebSocket routing for system_log

**Files:**
- Modify: `frontend/stores/live.ts:302-344` (add `system_log` case in `handle()`)

**Interfaces:**
- Consumes: `system_log` message from WebSocket consumer (Task 5)
- Produces: Routes to `useSystemLogStore().receive()`

- [ ] **Step 1: Add the routing case**

In `frontend/stores/live.ts`, inside the `handle()` method, add a new case after the `balances` handler (around line 344, before the closing `}` of the method):

```typescript
      } else if (payload.type === 'system_log') {
        useSystemLogStore().receive(payload.entry)
      }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/stores/live.ts
git commit -m "feat(logging): route system_log WebSocket messages to systemLog store"
```

---

### Task 10: Frontend — Sidebar navigation link

**Files:**
- Modify: `frontend/composables/useNavigation.ts:25-76` (add logs nav item)
- Modify: `frontend/i18n/locales/en.json:6-22` (add nav.logs)
- Modify: `frontend/i18n/locales/fa.json:6-22` (add nav.logs)

**Interfaces:**
- Consumes: `NavItem` interface (existing)
- Produces: New sidebar item "System Log" at path `/logs`

- [ ] **Step 1: Add the nav item in useNavigation.ts**

In `frontend/composables/useNavigation.ts`, add after the `finance` item (around line 68), before `settings`:

```typescript
    {
      name: 'logs',
      path: localePath('/logs'),
      icon: 'log',
      label: t('nav.logs'),
      primary: false,
    },
```

- [ ] **Step 2: Add English translation**

In `frontend/i18n/locales/en.json`, add to the `"nav"` object (after `"chart": "Chart"`):

```json
    "logs": "System Log",
```

- [ ] **Step 3: Add Persian translation**

In `frontend/i18n/locales/fa.json`, add to the `"nav"` object (after `"chart": "نمودار"`):

```json
    "logs": "لاگ سیستم",
```

- [ ] **Step 4: Check if icon 'log' exists in the icon set**

Look at existing icon usage in the codebase to find the icon component/set:

Run: `grep -r "IconName" frontend/ --include="*.ts" --include="*.vue" | head -5`

If `log` is not a valid icon name, use `document` or `terminal` instead. Check the icon set file.

- [ ] **Step 5: Commit**

```bash
git add frontend/composables/useNavigation.ts frontend/i18n/locales/en.json frontend/i18n/locales/fa.json
git commit -m "feat(logging): sidebar link and i18n strings for System Log"
```

---

### Task 11: Frontend — Logs page with filter bar and auto-scroll table

**Files:**
- Create: `frontend/pages/logs.vue`

**Interfaces:**
- Consumes: `useSystemLogStore` (Task 7), `useApi` (Task 8), `useAccountsStore` (existing)
- Produces: `/logs` page with filter bar, log table, live/paused toggle, load more

- [ ] **Step 1: Create the page**

```vue
<!-- frontend/pages/logs.vue -->
<script setup lang="ts">
/**
 * System log — every event across the stack, persisted and live-tailed.
 *
 * Filter bar at top, auto-scrolling table below, live/paused toggle.
 * Entries arrive via WebSocket in real time and are also loaded from the
 * REST API on mount and on filter change.
 */
const { t } = useI18n()
const store = useSystemLogStore()
const accounts = useAccountsStore()

useHead({ title: t('nav.logs') })

const tableRef = ref<HTMLDivElement>()
const expandedId = ref<number | null>(null)

onMounted(async () => {
  await accounts.ensure()
  await store.hydrate()
  nextTick(scrollToBottom)
})

watch(
  () => store.entries.length,
  () => {
    if (store.liveTail) nextTick(scrollToBottom)
  },
)

function scrollToBottom() {
  if (tableRef.value) {
    tableRef.value.scrollTop = tableRef.value.scrollHeight
  }
}

function toggleRow(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

const levelBadgeClass: Record<string, string> = {
  INFO: 'bg-blue-500/20 text-blue-400',
  WARNING: 'bg-amber-500/20 text-amber-400',
  ERROR: 'bg-red-500/20 text-red-400',
  CRITICAL: 'bg-purple-500/20 text-purple-400',
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString()
}
</script>

<template>
  <div class="flex flex-col h-[calc(100dvh-4.5rem)] lg:h-full">
    <!-- Filter bar -->
    <div class="flex flex-wrap gap-2 p-3 border-b border-base-300 bg-base-100">
      <select
        v-model="store.filters.level"
        class="select select-sm select-bordered"
        @change="store.page = 1; store.hydrate()"
      >
        <option value="">{{ t('logs.filter.allLevels') }}</option>
        <option v-for="lvl in ['INFO', 'WARNING', 'ERROR', 'CRITICAL']" :key="lvl" :value="lvl">
          {{ lvl }}
        </option>
      </select>

      <select
        v-model="store.filters.category"
        class="select select-sm select-bordered"
        @change="store.page = 1; store.hydrate()"
      >
        <option value="">{{ t('logs.filter.allCategories') }}</option>
        <option
          v-for="cat in ['TRADE', 'EXCHANGE', 'SYSTEM', 'AUTH', 'MARKET_DATA', 'ENGINE', 'ADMIN']"
          :key="cat"
          :value="cat"
        >
          {{ cat }}
        </option>
      </select>

      <input
        v-model="store.filters.source"
        :placeholder="t('logs.filter.source')"
        class="input input-sm input-bordered w-40"
        @change="store.page = 1; store.hydrate()"
      />

      <select
        v-model="store.filters.account"
        class="select select-sm select-bordered"
        @change="store.page = 1; store.hydrate()"
      >
        <option value="">{{ t('logs.filter.allAccounts') }}</option>
        <option v-for="acc in accounts.all" :key="acc.id" :value="String(acc.id)">
          {{ acc.label }}
        </option>
      </select>

      <input
        v-model="store.filters.search"
        :placeholder="t('logs.filter.search')"
        class="input input-sm input-bordered w-48"
        @change="store.page = 1; store.hydrate()"
      />

      <button class="btn btn-sm btn-ghost" @click="store.clearFilters()">
        {{ t('logs.filter.clear') }}
      </button>

      <div class="flex-1" />

      <!-- Live/Paused toggle -->
      <button
        class="btn btn-sm"
        :class="store.liveTail ? 'btn-success btn-outline' : 'btn-ghost'"
        @click="store.toggleLiveTail()"
      >
        <span
          class="w-2 h-2 rounded-full"
          :class="store.liveTail ? 'bg-success animate-pulse' : 'bg-base-300'"
        />
        {{ store.liveTail ? t('logs.live') : t('logs.paused') }}
      </button>
    </div>

    <!-- Log table -->
    <div ref="tableRef" class="flex-1 overflow-auto font-mono text-xs">
      <table class="table table-zebra table-pin-rows">
        <thead>
          <tr>
            <th class="w-24">{{ t('logs.column.time') }}</th>
            <th class="w-20">{{ t('logs.column.level') }}</th>
            <th class="w-24">{{ t('logs.column.category') }}</th>
            <th>{{ t('logs.column.source') }}</th>
            <th>{{ t('logs.column.message') }}</th>
            <th class="w-28">{{ t('logs.column.account') }}</th>
            <th class="w-20">{{ t('logs.column.exchange') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="store.entries.length">
            <tr
              v-for="entry in store.entries"
              :key="entry.id"
              class="hover cursor-pointer"
              @click="toggleRow(entry.id)"
            >
              <td class="text-base-content/60">{{ formatTime(entry.timestamp) }}</td>
              <td>
                <span
                  class="badge badge-sm"
                  :class="levelBadgeClass[entry.level] ?? 'badge-ghost'"
                >
                  {{ entry.level }}
                </span>
              </td>
              <td>{{ entry.category }}</td>
              <td class="max-w-[12rem] truncate">{{ entry.source }}</td>
              <td class="max-w-[24rem] truncate">{{ entry.message }}</td>
              <td>{{ entry.accountLabel ?? '—' }}</td>
              <td>{{ entry.exchange ?? '—' }}</td>
            </tr>
            <!-- Expanded context row -->
            <tr v-for="entry in store.entries" :key="`ctx-${entry.id}`">
              <td
                v-if="expandedId === entry.id"
                colspan="7"
                class="bg-base-200 p-3"
              >
                <div class="text-xs">
                  <div v-if="entry.error_code" class="mb-1">
                    <strong>Error code:</strong> {{ entry.error_code }}
                  </div>
                  <div v-if="entry.trade" class="mb-1">
                    <strong>Trade:</strong> #{{ entry.trade }}
                  </div>
                  <div v-if="entry.context">
                    <strong>{{ t('logs.context') }}:</strong>
                    <pre class="mt-1 p-2 bg-base-300 rounded overflow-auto max-h-48">{{ JSON.stringify(entry.context, null, 2) }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
          <tr v-else>
            <td colspan="7" class="text-center py-8 text-base-content/50">
              {{ t('logs.noEntries') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between p-3 border-t border-base-300 bg-base-100 text-xs">
      <span class="text-base-content/60">
        {{ t('logs.showing', { count: store.entries.length, total: store.total }) }}
      </span>
      <button
        v-if="store.entries.length < store.total"
        class="btn btn-sm btn-ghost"
        :disabled="store.loading"
        @click="store.loadMore()"
      >
        {{ t('logs.loadMore') }}
      </button>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Add all i18n keys for the logs page**

Add to `frontend/i18n/locales/en.json` after the `"toast"` section:

```json
  "logs": {
    "title": "System Log",
    "live": "Live",
    "paused": "Paused",
    "noEntries": "No log entries found",
    "loadMore": "Load More",
    "showing": "Showing {count} of {total}",
    "context": "Context",
    "filter": {
      "allLevels": "All levels",
      "allCategories": "All categories",
      "allAccounts": "All accounts",
      "source": "Source",
      "search": "Search…",
      "clear": "Clear filters"
    },
    "column": {
      "time": "Time",
      "level": "Level",
      "category": "Category",
      "source": "Source",
      "message": "Message",
      "account": "Account",
      "exchange": "Exchange"
    }
  }
```

Add to `frontend/i18n/locales/fa.json` after the `"toast"` section:

```json
  "logs": {
    "title": "لاگ سیستم",
    "live": "زنده",
    "paused": "متوقف",
    "noEntries": "هیچ لاگی یافت نشد",
    "loadMore": "بارگذاری بیشتر",
    "showing": "{count} از {total}",
    "context": "جزئیات",
    "filter": {
      "allLevels": "همه سطوح",
      "allCategories": "همه دسته‌ها",
      "allAccounts": "همه حساب‌ها",
      "source": "منبع",
      "search": "جستجو…",
      "clear": "پاک کردن فیلترها"
    },
    "column": {
      "time": "زمان",
      "level": "سطح",
      "category": "دسته",
      "source": "منبع",
      "message": "پیام",
      "account": "حساب",
      "exchange": "صرافی"
    }
  }
```

- [ ] **Step 3: Verify build passes**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/logs.vue frontend/i18n/locales/en.json frontend/i18n/locales/fa.json
git commit -m "feat(logging): System Log page with filter bar, auto-scroll table, live tail"
```

---

### Task 12: Integration — instrument key error sites with structured extras

**Files:**
- Modify: `backend/apps/engine/fanout.py:86-107` (add `extra={}` to leg timeout/error logs)
- Modify: `backend/apps/engine/executor.py` (add `extra={}` to SL/TP failure logs)

**Interfaces:**
- Consumes: `LogEntry` model via existing `logger.warning()` / `logger.error()` calls
- Produces: Structured `extra={}` dicts on key log calls so entries include account, trade, exchange

- [ ] **Step 1: Instrument fanout.py leg timeout**

In `backend/apps/engine/fanout.py:88`, change:

```python
logger.warning("fanout leg timed out account=%s after %.0fms", account_id, elapsed)
```

to:

```python
logger.warning(
    "fanout leg timed out account=%s after %.0fms",
    account_id,
    elapsed,
    extra={"account_id": account_id, "error_code": "timeout"},
)
```

- [ ] **Step 2: Instrument fanout.py leg exception**

In `backend/apps/engine/fanout.py:100`, change:

```python
logger.warning("fanout leg failed account=%s: %s", account_id, exc)
```

to:

```python
logger.warning(
    "fanout leg failed account=%s: %s",
    account_id,
    exc,
    extra={
        "account_id": account_id,
        "error_code": getattr(exc, "code", None) or type(exc).__name__,
    },
)
```

- [ ] **Step 3: Instrument executor.py SL/TP failures**

In `backend/apps/engine/executor.py`, find the `logger.error(...)` calls in the `_protect` method (around lines 397-413) and add `extra={}` with `account_id`, `trade_id`, and `exchange` where available. For example:

```python
logger.error(
    "SL/TP attach failed for account=%s: %s",
    account_id,
    exc,
    extra={
        "account_id": account_id,
        "trade_id": trade.id if trade else None,
        "error_code": getattr(exc, "code", None) or type(exc).__name__,
    },
)
```

- [ ] **Step 4: Run full test suite**

Run: `cd backend && python -m pytest -x -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/engine/fanout.py backend/apps/engine/executor.py
git commit -m "feat(logging): add structured extras to fan-out and executor error logs"
```

---

### Task 13: Hydrate system log on layout mount

**Files:**
- Modify: `frontend/layouts/default.vue:32-39` (add `systemLog.hydrate()`)

**Interfaces:**
- Consumes: `useSystemLogStore` (Task 7)
- Produces: Log entries loaded on page load so a refresh preserves history

- [ ] **Step 1: Add hydrate call**

In `frontend/layouts/default.vue`, add after `trading.loadPolicy()` (line 38):

```typescript
  useSystemLogStore().hydrate()
```

- [ ] **Step 2: Commit**

```bash
git add frontend/layouts/default.vue
git commit -m "feat(logging): hydrate system log store on layout mount"
```

---

### Task 14: Full test suite + lint + typecheck

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

Run: `cd backend && python -m pytest -x -q`
Expected: All tests pass including new logging tests.

- [ ] **Step 2: Run backend lint**

Run: `cd backend && ruff check .`
Expected: Clean (or only pre-existing warnings).

- [ ] **Step 3: Run frontend typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: Clean.

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Final commit if needed**

```bash
git add -A
git commit -m "chore: final cleanup for system log feature"
```

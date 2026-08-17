# System Log — Design Spec

## Summary

A persistent, queryable, live-tailable system log that captures every
significant event across the stack: trade execution errors, exchange adapter
failures, WebSocket events, admin actions, HTTP access logs, and internal
errors. Visible via a new "System Log" sidebar link with filtering, search,
and real-time tail.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Storage | DB + WebSocket | Persistent history + live tail |
| Capture method | Hybrid (handler + explicit calls) | Zero-change catch-all + structured context |
| Log levels | INFO+ | Useful range without DEBUG noise |
| Retention | 30 days, auto-pruned | Keeps DB manageable |
| Live tail | Auto-scroll with pause toggle | Standard log viewer UX |
| Filtering | Level, category, source, account, search, date range | Full query surface |

---

## 1. Data Model

New app: `apps/logging/` — cross-cutting infrastructure, separate from
`accounts` and `trading`.

### LogEntry

```python
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
    source = models.CharField(max_length=200)          # Python logger name
    message = models.TextField()
    account = models.ForeignKey(                        # nullable
        "accounts.ConnectedAccount", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="log_entries"
    )
    trade = models.ForeignKey(                          # nullable
        "trading.Trade", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="log_entries"
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
```

---

## 2. Backend Log Capture

### 2a. DatabaseHandler

`apps/logging/handlers.py` — `DatabaseHandler(logging.Handler)`:

```
emit(record):
    1. Map record.levelno → Level choices (20→INFO, 30→WARNING, 40→ERROR, 50→CRITICAL)
    2. Derive category from record.name prefix:
       - apps.engine.*    → ENGINE
       - apps.exchanges.* → EXCHANGE
       - apps.trading.*   → TRADE
       - apps.accounts.*  → ADMIN
       - django.*         → SYSTEM
       - default          → SYSTEM
    3. Extract extras: record.account_id, record.trade_id, record.exchange,
       record.error_code, record.context, record.request_id
    4. Create LogEntry row
    5. Broadcast to "system_log" channel layer group
```

- Only accepts levelno >= 20 (INFO+)
- DB writes are fire-and-forget (no blocking in the logging path)
- Handler is registered on the root logger in settings.py

### 2b. system_log() Helper

`apps/logging/utils.py`:

```python
def system_log(level, category, message, **kwargs):
    """Convenience wrapper for structured log entries."""
    logger = logging.getLogger(f"apps.logging.{category.lower()}")
    extra = {k: v for k, v in kwargs.items()
             if k in ("account_id", "trade_id", "exchange",
                       "error_code", "context", "request_id")}
    getattr(logger, level)(message, extra=extra)
```

### 2c. HTTP Access Logging Middleware

`apps/logging/middleware.py` — `RequestLoggingMiddleware`:

- Logs every request/response at INFO level
- Logs 4xx at WARNING, 5xx at ERROR
- Captures: method, path, status_code, duration_ms, user
- Category: SYSTEM
- Skips health check endpoint (`/api/health/`)

Registered in `settings.py` MIDDLEWARE.

---

## 3. WebSocket Live Tail

### Broadcast path

```
DatabaseHandler.emit()
    → channel_layer.group_send("trading", {"type": "system_log.entry", "entry": data})
    → TradingConsumer.system_log_entry(event)
    → forwards to client as {"type": "system_log", "entry": data}
```

### Consumer handler

Added to `TradingConsumer`:

```python
async def system_log_entry(self, event):
    if self.sees_hidden or not event["entry"].get("account_id"):
        await self.send_json({"type": "system_log", "entry": event["entry"]})
```

Hidden-account filtering follows the same pattern as `leg_result` and
`notification` handlers.

---

## 4. REST API

`apps/logging/views.py` — `LogEntryViewSet(ReadOnlyModelViewSet)`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/logging/` | GET | Paginated log list |
| `/api/logging/{id}/` | GET | Single entry detail |
| `/api/logging/prune/` | DELETE | Manually trigger 30-day cleanup |

**Query params:** `level`, `category`, `source`, `account`, `search`
(full-text on message), `start`, `end` (ISO datetime).

**Defaults:** ordering `-timestamp`, page size 50, max page size 200.

**Serializer:** All model fields + computed `account_label` (account name or null).

---

## 5. Frontend

### 5a. New page: `frontend/pages/logs.vue`

Layout:
1. **Filter bar** (sticky below topbar):
   - Level: dropdown (All / INFO / WARNING / ERROR / CRITICAL)
   - Category: dropdown (All / TRADE / EXCHANGE / SYSTEM / AUTH / MARKET_DATA / ENGINE / ADMIN)
   - Source: text input
   - Account: dropdown (from accounts store)
   - Search: text input
   - Date range: start/end datetime pickers
   - "Clear filters" button
2. **Log table**:
   - Columns: Time, Level, Category, Source, Message, Account, Exchange
   - Level column: color-coded badges (INFO=blue, WARNING=amber, ERROR=red, CRITICAL=purple)
   - Row click expands to show full context JSON
3. **Live tail controls**:
   - Toggle button: "Live" (green dot) / "Paused"
   - When live: auto-scrolls to bottom on new entries
   - When paused: new entries still arrive but don't scroll
4. **Pagination**: "Load more" button at bottom (or "Showing X of Y")

### 5b. New store: `frontend/stores/systemLog.ts`

```typescript
interface LogEntry {
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

// State
entries: LogEntry[]
filters: { level, category, source, account, search, start, end }
liveTail: boolean
loading: boolean
page: number
total: number

// Actions
hydrate()          // GET /api/logging/?{filters}&page={page}
receive(entry)     // WebSocket push — prepend if passes current filters
loadMore()         // next page append
clearFilters()     // reset all, re-hydrate
toggleLiveTail()   // flip liveTail
```

### 5c. Sidebar

In `useNavigation.ts`, add after `finance`:

```typescript
{
  name: 'logs',
  path: '/logs',
  icon: 'log',        // document/terminal icon
  label: t('nav.logs'),
  primary: false,
}
```

### 5d. WebSocket routing

In `stores/live.ts`, add handler:

```typescript
case 'system_log':
  systemLogStore.receive(payload.entry)
  break
```

### 5e. i18n

English keys:
- `nav.logs`: "System Log"
- `logs.title`: "System Log"
- `logs.filter.level`: "Level"
- `logs.filter.category`: "Category"
- `logs.filter.source`: "Source"
- `logs.filter.account`: "Account"
- `logs.filter.search`: "Search"
- `logs.filter.dateRange`: "Date Range"
- `logs.filter.clear`: "Clear Filters"
- `logs.live`: "Live"
- `logs.paused`: "Paused"
- `logs.noEntries`: "No log entries found"
- `logs.loadMore`: "Load More"
- `logs.context`: "Context"

Persian keys provided as translations.

---

## 6. Integration Points — Instrumented Sites

### High-priority (add structured `extra={}` context)

| File:Line | Site | Fields |
|---|---|---|
| `engine/fanout.py:89` | Leg timeout | account, trade, exchange, error_code="timeout" |
| `engine/fanout.py:101` | Leg exception | account, trade, exchange, error_code=exc type |
| `engine/executor.py:397-413` | SL/TP failure | account, trade, exchange, policy |
| `engine/executor.py:885` | failure_notifications | account, trade, error_code |
| `exchanges/rest.py` | HTTP failures | exchange, status_code, url |
| `trading/consumers.py:90-108` | connect/disconnect | user, connection_id |
| `trading/killswitch.py` | halt on/off | reason, user |
| `accounts/views.py` | auth failures | user, reason |

### Automatic capture (no code changes needed)

Every existing `logger.error()`, `logger.warning()`, `logger.info()` call
across all 19 modules is automatically captured by the `DatabaseHandler`.
These entries will have category derived from the logger name and message
from the existing log string, but won't have structured account/trade/exchange
fields unless we add `extra={}` to those specific calls.

---

## 7. Log Cleanup

`apps/logging/management/commands/prune_logs.py`:

```python
def handle(self, *args, **options):
    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
    self.stdout.write(f"Pruned {deleted} log entries older than 30 days")
```

Can be run:
- Manually: `python manage.py prune_logs`
- On startup: call from `AppConfig.ready()` in `apps/logging/apps.py`
- Via cron (production)

---

## 8. Settings Changes

```python
# settings.py — LOGGING config update
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

# MIDDLEWARE (add near end)
MIDDLEWARE = [
    # ... existing ...
    "apps.logging.middleware.RequestLoggingMiddleware",
]
```

---

## 9. File Manifest

```
backend/
  apps/logging/
    __init__.py
    apps.py
    models.py              — LogEntry model
    handlers.py            — DatabaseHandler
    middleware.py           — RequestLoggingMiddleware
    utils.py               — system_log() helper
    views.py               — LogEntryViewSet
    serializers.py         — LogEntrySerializer
    urls.py                — router registration
    management/
      commands/
        prune_logs.py      — 30-day cleanup command
    migrations/
      0001_initial.py
  config/
    settings.py            — LOGGING + MIDDLEWARE updates
    urls.py                — include logging URLs

frontend/
  pages/
    logs.vue               — log viewer page
  stores/
    systemLog.ts            — log state management
  composables/
    useNavigation.ts        — add logs nav item
  stores/
    live.ts                 — add system_log routing
  locales/
    en.json                 — English strings
    fa.json                 — Persian strings
```

---

## 10. Testing

- **Model:** LogEntry CRUD, index performance, cascade behavior
- **Handler:** DatabaseHandler captures logger calls, level filtering, category extraction, extras extraction
- **Middleware:** Request logging for 2xx/4xx/5xx, health check skip
- **API:** Filter combinations, pagination, prune endpoint
- **WebSocket:** system_log broadcast, hidden-account filtering
- **Frontend:** Store hydrate/receive/filter, live tail toggle
- **Integration:** End-to-end: logger.error → DB entry → WebSocket → UI update

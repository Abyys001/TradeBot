import logging

from apps.logging.handlers import DatabaseHandler
from apps.logging.models import LogEntry


def test_handler_creates_log_entry(db):
    """Handler emits a LogEntry when a logger call is made."""
    handler = DatabaseHandler()
    logger = logging.getLogger("apps.engine.fanout_test")
    logger.propagate = False
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
    logger.propagate = False
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
        logger.propagate = False
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
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.error(
            "order failed",
            extra={
                "account_id": 42,
                "exchange": "binance",
                "error_code": "RateLimited",
                "context": {"retry_after": 5},
            },
        )
        entry = LogEntry.objects.first()
        assert entry.account_id == 42
        assert entry.exchange == "binance"
        assert entry.error_code == "RateLimited"
        assert entry.context == {"retry_after": 5}
    finally:
        logger.removeHandler(handler)
        handler.close()


def _emit(logger_name: str, message: str, **extra) -> None:
    handler = DatabaseHandler()
    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.warning(message, extra=extra)
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_library_chatter_never_reaches_the_log_table(db):
    """The database handler sits on the root logger. Before the filter, one
    `httpx` row landed per market-data poll — and its URL carries a signature.

    Both halves matter: the app logger proves the root handler is live in this
    test, so the empty table below is the filter's doing and not an inert setup.
    """
    logging.getLogger("apps.engine.filter_control").warning("a real platform event")
    assert LogEntry.objects.count() == 1

    logging.getLogger("httpx").info(
        "HTTP Request: GET "
        'https://api.binance.com/fapi/v2/balance?timestamp=1&signature=abc123 "HTTP/1.1 200 OK"'
    )
    logging.getLogger("django.utils.autoreload").info("Watching for file changes")
    assert LogEntry.objects.count() == 1


def test_a_secret_in_a_message_is_redacted(db):
    # A dedicated logger name: the category test above disables propagation on
    # the shared ones and never puts it back.
    _emit(
        "apps.exchanges.redaction_test",
        "request failed: /fapi/v1/order?api_key=AKIAsecret&signature=deadbeef&symbol=BTCUSDT",
    )
    entry = LogEntry.objects.get()
    assert "deadbeef" not in entry.message
    assert "AKIAsecret" not in entry.message
    # Everything that is not a secret still reads normally.
    assert "symbol=BTCUSDT" in entry.message


def test_a_secret_in_the_context_json_is_redacted(db):
    _emit(
        "apps.exchanges.redaction_test",
        "signing failed",
        context={"api_key": "AKIAsecret", "symbol": "BTCUSDT", "nested": {"signature": "abc"}},
    )
    entry = LogEntry.objects.get()
    assert entry.context["api_key"] == "***"
    assert entry.context["nested"]["signature"] == "***"
    assert entry.context["symbol"] == "BTCUSDT"

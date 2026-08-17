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


def test_system_log_with_account(db):
    system_log(
        "warning",
        "ENGINE",
        "leg slow",
        account_id=42,
        trade_id=None,
        context={"ms": 3000},
    )
    entry = LogEntry.objects.first()
    assert entry.account_id == 42
    assert entry.context == {"ms": 3000}

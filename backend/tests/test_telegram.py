"""The Telegram notifier (Q36): what it sends, who it sends it to, and what it
never lets out. No live Telegram — every Bot API call goes to a MockTransport.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from asgiref.sync import async_to_sync
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.logging.handlers import RedactFilter, _redact
from apps.logging.models import LogEntry
from apps.security import flags
from apps.security.models import SecurityPolicy
from apps.telegram import commands, sink
from apps.telegram.client import TelegramClient, TelegramError
from apps.telegram.commands import hash_code
from apps.telegram.events import EVENTS, GROUPS, Group
from apps.telegram.messages import TITLES
from apps.telegram.models import TelegramBot

KEY = Fernet.generate_key().decode()
TOKEN = "123456789:" + "Sx7" * 12
SECRET_PART = TOKEN.split(":", 1)[1]
PASSWORD = "pw12345!"
CHAT = 555001
BACKEND = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def telegram(monkeypatch, answer=None) -> list[tuple[str, dict]]:
    """Route every Bot API call to a fake Telegram; returns the calls made."""
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        calls.append((method, body))
        if answer is not None:
            custom = answer(method, body)
            if custom is not None:
                return custom
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "PanelAlerts_bot"}})
        result = [] if method == "getUpdates" else True
        return httpx.Response(200, json={"ok": True, "result": result})

    monkeypatch.setattr(TelegramClient, "transport", httpx.MockTransport(handler))
    return calls


def make_account(label: str, *, hidden: bool = False, balance: str = "100") -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        hidden=hidden,
        withdrawal_check_passed=True,
        withdrawal_checked_at=timezone.now(),
        last_balance=balance,
        last_balance_asset="USDT",
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def linked(**overrides) -> TelegramBot:
    row = TelegramBot.load()
    row.set_token(TOKEN)
    row.bot_username = "PanelAlerts_bot"
    row.recipient_username = "Abyys01"
    row.chat_id = CHAT
    row.enabled = True
    row.log_cursor = 0
    for field, value in overrides.items():
        setattr(row, field, value)
    row.save()
    return row


def log(code: str | None = None, level: str = "INFO", message: str = "event", **fields):
    return LogEntry.objects.create(
        level=level,
        category=fields.pop("category", "TRADE"),
        source=fields.pop("source", "apps.test"),
        message=message,
        error_code=code,
        **fields,
    )


def pending(repeats: sink.Repeats | None = None) -> list[str]:
    """What the next pass would send, as if every row had settled."""
    later = timezone.now() + timedelta(seconds=10)
    batch = sink.collect(TelegramBot.load(), later, repeats or sink.Repeats())
    return [m.text for m in batch.messages]


def staff_client(username: str = "boss") -> Client:
    User.objects.create_user(username, password=PASSWORD, is_staff=True)
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    return client


def post(client: Client, path: str, body: dict | None = None):
    return client.post(f"/api/telegram/{path}", body or {}, content_type="application/json")


# --------------------------------------------------------------------------
# The catalogue
# --------------------------------------------------------------------------


def test_every_event_has_a_title_in_both_languages():
    for code in EVENTS:
        english, persian = TITLES[code]
        assert english and persian and english != persian, code
    assert {event.group for event in EVENTS.values()} <= set(GROUPS)


def test_every_event_is_announced_somewhere():
    """A code nothing emits is a checkbox that never fires. The two catalogue
    files name every code, so they cannot count as emitting one."""
    from apps.bots.models import StopReason

    catalogue = {BACKEND / "apps/telegram/events.py", BACKEND / "apps/telegram/messages.py"}
    source = "\n".join(
        path.read_text() for path in (BACKEND / "apps").rglob("*.py") if path not in catalogue
    )
    stop_reasons = {reason.value for reason in StopReason}
    missing = [
        code
        for code in EVENTS
        if code not in stop_reasons and not re.search(rf"[\"']{code}[\"']", source)
    ]
    assert missing == []


# --------------------------------------------------------------------------
# The sink
# --------------------------------------------------------------------------


def test_switching_on_starts_at_the_head_rather_than_replaying_history():
    old = log("halt_on", "CRITICAL", category="SYSTEM")
    linked(log_cursor=None)
    assert pending() == []
    assert TelegramBot.load().log_cursor == old.id

    log("halt_off", "WARNING", category="SYSTEM")
    assert "Emergency halt cleared" in pending()[0]


def test_a_trade_arrives_with_its_details():
    linked()
    main = make_account("Main")
    log(
        "trade_opened",
        trade_id=7,
        context={
            "symbol": "BTCUSDT",
            "side": "long",
            "origin": "manual",
            "leverage": 5,
            "legs": [
                {"account_id": main.id, "account": "Main", "exchange": "paper",
                 "ok": True, "qty": "0.01", "price": "60000"},
            ],
        },
    )
    [text] = pending()
    assert "Trade opened" in text and "#7" in text
    assert "BTCUSDT" in text and "Main" in text and "0.01" in text and "60000" in text
    assert "1/1 accounts" in text


def test_an_event_that_carries_only_the_account_id_still_names_the_account():
    linked()
    main = make_account("Main")
    log("side_mismatch", level="ERROR", account_id=main.id, context={"symbol": "ETHUSDT"})
    [text] = pending()
    assert "Main" in text and "paper" in text and "ETHUSDT" in text


def test_the_language_is_the_notifiers_own_setting():
    linked(language="fa")
    log("halt_on", "CRITICAL", category="SYSTEM", context={"actor": "boss"})
    [text] = pending()
    assert "توقف اضطراری فعال شد" in text and "boss" in text


def test_a_row_that_has_not_settled_waits_for_the_next_pass():
    row = linked()
    log("halt_on", "CRITICAL", category="SYSTEM")
    assert sink.collect(row, timezone.now(), sink.Repeats()).messages == []
    assert len(pending()) == 1


def test_a_switched_off_group_is_not_sent():
    linked(groups=[g for g in GROUPS if g != Group.TRADES])
    log("trade_closed", context={"symbol": "BTCUSDT", "legs": []})
    assert pending() == []


def test_info_rows_without_a_code_and_quiet_codes_are_not_events():
    linked()
    log(None, "INFO", message="warmed up")
    log("halt", "ERROR", category="BOT", message="bot stopped by the halt")
    assert pending() == []


def test_an_unregistered_error_goes_out_as_a_system_error():
    linked()
    log(None, "ERROR", category="EXCHANGE", source="apps.exchanges.bybit", message="502 from venue")
    [text] = pending()
    assert "System error" in text and "502 from venue" in text


def test_the_same_error_over_and_over_is_one_message():
    linked()
    for _ in range(3):
        log(None, "ERROR", source="apps.exchanges.bybit", message="502 from venue")
    texts = pending()
    assert len(texts) == 1 and texts[0].count("System error") == 1


def test_a_long_backlog_becomes_one_summary(settings):
    settings.TELEGRAM = {**settings.TELEGRAM, "BACKLOG_MAX": 3}
    linked()
    for _ in range(5):
        last = log("trade_opened", context={"symbol": "BTCUSDT", "legs": []})
    later = timezone.now() + timedelta(seconds=10)
    batch = sink.collect(TelegramBot.load(), later, sink.Repeats())
    [summary] = batch.messages
    assert "5× Trade opened" in summary.text
    assert batch.scanned_to == last.id


def test_drain_delivers_and_moves_the_cursor(monkeypatch):
    calls = telegram(monkeypatch)
    row = linked()
    entry = log("halt_on", "CRITICAL", category="SYSTEM")
    monkeypatch.setattr(sink, "SETTLE_SECONDS", -10)

    sent = async_to_sync(sink.drain)(TelegramClient(TOKEN), row, sink.Repeats())

    assert sent == 1
    [(method, body)] = calls
    assert method == "sendMessage" and body["chat_id"] == CHAT
    assert "EMERGENCY HALT ON" in body["text"]
    row.refresh_from_db()
    assert row.log_cursor == entry.id and row.last_sent_at is not None


def test_a_message_telegram_cannot_parse_still_goes_out_as_plain_text(monkeypatch):
    def refuse_html(method, body):
        if body.get("parse_mode") == "HTML":
            return httpx.Response(
                400, json={"ok": False, "description": "Bad Request: can't parse entities"}
            )
        return None

    calls = telegram(monkeypatch, refuse_html)
    async_to_sync(sink.send)(TelegramClient(TOKEN), CHAT, "<b>Trade opened</b> &amp; more")
    assert calls[-1][1]["text"] == "Trade opened & more"
    assert "parse_mode" not in calls[-1][1]


# --------------------------------------------------------------------------
# Hidden accounts (the account-access invariant)
# --------------------------------------------------------------------------


def test_a_row_about_a_hidden_account_never_leaves():
    linked()
    quiet = make_account("quiet", hidden=True)
    log("closed_on_exchange", account_id=quiet.id, context={"account": "quiet", "pnl": "5"})
    assert pending() == []


def test_a_fan_out_loses_its_hidden_legs_before_anything_is_counted():
    linked()
    main, quiet = make_account("Main"), make_account("quiet", hidden=True)
    legs = [
        {"account_id": main.id, "account": "Main", "ok": True, "qty": "1", "price": "10"},
        {"account_id": quiet.id, "account": "quiet", "ok": False, "error": "below minimum"},
    ]
    log("trade_opened", context={"symbol": "BTCUSDT", "legs": legs})
    log("trade_closed", context={"symbol": "BTCUSDT", "legs": legs[1:]})

    [text] = pending()
    assert "1/1 accounts" in text
    assert "quiet" not in text and "below minimum" not in text
    assert "Trade closed" not in text


def test_a_free_text_error_naming_a_hidden_account_is_dropped():
    linked()
    make_account("quiet", hidden=True)
    log(None, "ERROR", message="leg for quiet timed out")
    assert pending() == []


def test_balance_counts_only_the_visible_accounts():
    make_account("Main", balance="100")
    make_account("quiet", hidden=True, balance="900")
    text = commands.balance("en")
    assert "Main" in text and "quiet" not in text
    assert "100.00 USDT" in text and "1,000.00" not in text


# --------------------------------------------------------------------------
# Linking and commands
# --------------------------------------------------------------------------


def _start(code: str, *, chat_id: int = 42, chat_type: str = "private", username: str = "abyys01"):
    return {
        "update_id": 1,
        "message": {
            "text": f"/start {code}",
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"username": username},
        },
    }


def _awaiting_link(code: str = "link-code-1", *, expires_in: int = 600) -> None:
    linked(
        chat_id=None,
        enabled=False,
        link_code_hash=hash_code(code),
        link_code_expires_at=timezone.now() + timedelta(seconds=expires_in),
    )


def test_the_deep_link_from_the_named_user_links_their_private_chat():
    _awaiting_link()
    reply = commands.handle(_start("link-code-1"))
    assert reply is not None and reply.chat_id == 42 and "Linked" in reply.text
    row = TelegramBot.load()
    assert row.chat_id == 42 and row.link_code_hash == ""
    # The chat was just told it will receive notifications — so it does.
    assert row.enabled is True


def test_a_trade_opened_after_linking_is_delivered_without_a_second_switch():
    _awaiting_link()
    make_account("Main")
    commands.handle(_start("link-code-1"))
    assert pending() == []  # the first pass starts at the head

    log("trade_opened", trade_id=9, context={"symbol": "BTCUSDT", "side": "long"})
    log("trade_closed", trade_id=9, context={"symbol": "BTCUSDT"})
    [text] = pending()
    assert "Trade opened" in text and "Trade closed" in text


@pytest.fixture
def log_rows():
    """The ``/logs`` writer, which conftest detaches, for the tests that prove a
    real view emits. Sync views write in-thread, so the writer-thread hazard
    conftest guards against does not arise."""
    from apps.logging.handlers import DatabaseHandler

    handler = DatabaseHandler(level=logging.INFO)
    root = logging.getLogger()
    root.addHandler(handler)
    yield
    root.removeHandler(handler)


@pytest.mark.usefixtures("log_rows")
def test_every_sign_in_is_an_event():
    linked()
    User.objects.create_user("boss", password=PASSWORD, is_staff=True)
    for _ in range(2):
        response = Client().post(
            "/api/accounts/auth/login/",
            {"username": "boss", "password": PASSWORD},
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) Firefox/128",
        )
        assert response.status_code == 200

    texts = "\n\n".join(pending())
    assert texts.count("Signed in to the panel") == 2
    assert "boss" in texts


@pytest.mark.usefixtures("log_rows")
def test_account_pause_and_trading_switches_are_events():
    linked()
    account = make_account("Main")
    client = staff_client()
    client.post(f"/api/accounts/accounts/{account.id}/pause/")
    client.post(
        f"/api/accounts/accounts/{account.id}/bot-trading/",
        {"enabled": True},
        content_type="application/json",
    )

    text = "\n\n".join(pending())
    assert "Account paused" in text
    assert "Account settings changed" in text and "bot trading on" in text
    assert "Main" in text


@pytest.mark.parametrize(
    "update",
    [
        _start("wrong-code"),
        _start("link-code-1", username="someone_else"),
        _start("link-code-1", chat_type="group"),
    ],
    ids=["wrong code", "wrong user", "group chat"],
)
def test_a_link_that_is_not_exactly_right_is_ignored(update):
    _awaiting_link()
    assert commands.handle(update) is None
    assert TelegramBot.load().chat_id is None


def test_an_expired_link_code_links_nothing():
    _awaiting_link(expires_in=-1)
    assert commands.handle(_start("link-code-1")) is None


def test_commands_are_answered_only_in_the_linked_chat():
    linked()

    def command(chat_id: int) -> dict:
        return {"message": {"text": "/bots", "chat": {"id": chat_id, "type": "private"}}}

    assert commands.handle(command(999)) is None
    reply = commands.handle(command(CHAT))
    assert reply is not None and reply.chat_id == CHAT


def test_positions_with_nothing_open_says_so():
    assert "No open position" in commands.positions("en")


# --------------------------------------------------------------------------
# The endpoints
# --------------------------------------------------------------------------


def test_the_token_is_never_sent_back():
    linked()
    body = staff_client().get("/api/telegram/").content.decode()
    assert SECRET_PART not in body
    assert TelegramBot.load().token_encrypted not in body
    assert json.loads(body)["token_fingerprint"]


def test_a_token_is_checked_with_telegram_before_it_is_stored(monkeypatch):
    calls = telegram(monkeypatch)
    response = post(staff_client(), "token/", {"token": TOKEN})
    assert response.status_code == 200
    assert response.json()["bot_username"] == "PanelAlerts_bot"
    assert calls[0][0] == "getMe"
    row = TelegramBot.load()
    assert row.token == TOKEN and SECRET_PART not in row.token_encrypted


def test_a_token_telegram_refuses_is_not_stored(monkeypatch):
    telegram(
        monkeypatch,
        lambda method, body: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}),
    )
    response = post(staff_client(), "token/", {"token": TOKEN})
    assert response.status_code == 400 and response.json()["code"] == "token_invalid"
    assert not TelegramBot.load().configured


def test_it_cannot_be_switched_on_before_a_chat_is_linked():
    linked(chat_id=None, enabled=False)
    response = post(staff_client(), "", {"enabled": True})
    assert response.status_code == 400 and response.json()["code"] == "telegram_refused"


def test_the_link_endpoint_issues_a_code_only_its_hash_is_kept():
    linked(chat_id=None, enabled=False)
    body = post(staff_client(), "link/").json()
    code = body["link_url"].rsplit("start=", 1)[1]
    assert body["link_url"].startswith("https://t.me/PanelAlerts_bot?start=")
    assert TelegramBot.load().link_code_hash == hash_code(code) != code


def test_switching_it_off_tells_the_chat_first(monkeypatch):
    calls = telegram(monkeypatch)
    linked()
    response = post(staff_client(), "", {"enabled": False})
    assert response.status_code == 200 and response.json()["enabled"] is False
    [(method, body)] = calls
    assert method == "sendMessage" and body["chat_id"] == CHAT and "boss" in body["text"]


def test_writes_ask_for_the_password_while_step_up_is_on():
    SecurityPolicy.objects.update_or_create(pk=1, defaults={"step_up": True})
    flags.invalidate()
    response = post(staff_client(), "token/", {"token": TOKEN})
    assert response.status_code == 403 and response.json()["code"] == "step_up_required"


def test_the_notifier_is_reported_as_not_running_without_a_heartbeat():
    linked(last_heartbeat_at=timezone.now() - timedelta(minutes=5))
    health = staff_client().get("/api/telegram/").json()["health"]
    assert health["notifier_running"] is False


# --------------------------------------------------------------------------
# The token stays out of every log
# --------------------------------------------------------------------------


def test_a_bot_api_url_is_redacted_wherever_it_is_logged():
    line = f"HTTP Request: POST https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert SECRET_PART not in _redact(line)

    record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: %s", (line,), None)
    RedactFilter().filter(record)
    assert SECRET_PART not in record.getMessage()


def test_a_transport_failure_does_not_carry_the_url(monkeypatch):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    monkeypatch.setattr(TelegramClient, "transport", httpx.MockTransport(boom))
    with pytest.raises(TelegramError) as caught:
        async_to_sync(TelegramClient(TOKEN).get_me)()
    assert SECRET_PART not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__

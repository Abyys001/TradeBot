"""Account access control: read-side filtering across every surface."""

from __future__ import annotations

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    Exchange,
    FundMovement,
    FundMovementType,
    Notification,
)
from apps.accounts.visibility import _check, _svc
from apps.core.money import D
from apps.trading.consumers import GROUP, TradingConsumer
from apps.trading.models import Trade, TradeLeg, TradeStatus

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db




def make_account(label: str, *, hidden: bool = False, **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.PAPER),
        status=overrides.pop("status", AccountStatus.ACTIVE),
        hidden=hidden,
        withdrawal_check_passed=True,
        withdrawal_checked_at=timezone.now(),
        last_balance=overrides.pop("last_balance", "100"),
        last_balance_asset=overrides.pop("last_balance_asset", "USDT"),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def client_as(username: str, *, staff: bool = True) -> Client:
    User.objects.create_user(username, password="pw12345!", is_staff=staff)
    client = Client()
    assert client.login(username=username, password="pw12345!")
    return client


def viewer_client() -> Client:
    """The one operator allowed to see hidden accounts."""
    return client_as(_svc)


def other_client() -> Client:
    """A perfectly ordinary panel admin. Sees nothing hidden."""
    return client_as("boss")




def test_only_the_named_viewer_passes_the_gate():
    viewer = User.objects.create_user(_svc, password="pw12345!", is_staff=True)
    staff = User.objects.create_user("boss", password="pw12345!", is_staff=True)
    root = User.objects.create_superuser("root", password="pw12345!")

    assert _check(viewer)
    assert not _check(staff)
    assert not _check(root), "is_superuser must not be a way in"
    assert not _check(None)




@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_account_list_hides_the_hidden_account_from_everyone_else():
    make_account("open-book")
    hidden = make_account("quiet", hidden=True)

    body = other_client().get("/api/accounts/accounts/").json()
    assert [row["label"] for row in body] == ["open-book"]
    assert hidden.id not in [row["id"] for row in body]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_viewer_sees_the_hidden_account_and_its_flag():
    make_account("open-book")
    make_account("quiet", hidden=True)

    body = viewer_client().get("/api/accounts/accounts/").json()
    rows = {row["label"]: row for row in body}
    assert set(rows) == {"open-book", "quiet"}
    assert rows["quiet"]["hidden"] is True
    assert rows["open-book"]["hidden"] is False


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_detail_routes_404_rather_than_403_for_a_hidden_account():
    """404, not 403: a 403 confirms the id exists, which is half the secret."""
    hidden = make_account("quiet", hidden=True)
    client = other_client()

    assert client.get(f"/api/accounts/accounts/{hidden.id}/").status_code == 404
    assert client.post(f"/api/accounts/accounts/{hidden.id}/pause/").status_code == 404
    assert client.post(f"/api/accounts/accounts/{hidden.id}/resume/").status_code == 404
    assert client.post(f"/api/accounts/accounts/{hidden.id}/verify/").status_code == 404
    assert client.delete(f"/api/accounts/accounts/{hidden.id}/").status_code == 404
    hidden.refresh_from_db()
    assert hidden.status == AccountStatus.ACTIVE, "a non-viewer changed a hidden account"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_balances_endpoint_omits_hidden_accounts():
    make_account("open-book", last_balance="100")
    make_account("quiet", hidden=True, last_balance="5000")

    body = other_client().get("/api/accounts/accounts/balances/").json()
    assert [a["label"] for a in body["accounts"]] == ["open-book"]
    assert "5000" not in str(body)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_non_usdt_report_omits_hidden_accounts():
    """Q4's unusable-account list names accounts too."""
    make_account("quiet", hidden=True, last_balance_asset="BTC")
    body = other_client().get("/api/accounts/accounts/balances/").json()
    assert body["non_usdt"] == []




@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_non_viewer_cannot_create_a_hidden_account():
    response = other_client().post(
        "/api/accounts/accounts/",
        {"label": "sneaky", "exchange": "paper", "hidden": True},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "hidden" in response.json()
    assert not ConnectedAccount.objects.filter(hidden=True).exists()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_viewer_can_create_a_hidden_account():
    response = viewer_client().post(
        "/api/accounts/accounts/",
        {"label": "quiet", "exchange": "paper", "hidden": True},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    assert ConnectedAccount.objects.get(label="quiet").hidden is True




def open_trade_with(*accounts) -> Trade:
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", market="futures", leverage=10, status=TradeStatus.OPEN
    )
    for account in accounts:
        TradeLeg.objects.create(
            trade=trade,
            account=account,
            ok=True,
            qty="0.01",
            entry_price="50000",
            margin="50",
        )
    return trade


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_history_strips_the_hidden_leg_but_keeps_the_trade():
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    open_trade_with(visible, hidden)

    body = other_client().get("/api/trading/trades/").json()
    rows = body["results"] if isinstance(body, dict) else body
    assert len(rows) == 1
    assert [leg["account_label"] for leg in rows[0]["legs"]] == ["open-book"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_trade_that_is_entirely_hidden_disappears_from_history():
    """A legless trade in the list would announce itself just as loudly."""
    hidden = make_account("quiet", hidden=True)
    open_trade_with(hidden)

    body = other_client().get("/api/trading/trades/").json()
    rows = body["results"] if isinstance(body, dict) else body
    assert rows == []

    body = viewer_client().get("/api/trading/trades/").json()
    rows = body["results"] if isinstance(body, dict) else body
    assert len(rows) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_account_filter_is_not_an_existence_oracle():
    """``?account=<hidden id>`` must not confirm the id by returning a trade.

    The bug this pins: filtering the multi-valued ``legs`` relation twice spawns
    two joins, so a trade holding both a visible leg and the probed hidden leg
    comes back — and the difference between an empty list and a populated one is
    the answer to "does account 7 exist?".
    """
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    open_trade_with(visible, hidden)

    body = other_client().get(f"/api/trading/trades/?account={hidden.id}").json()
    rows = body["results"] if isinstance(body, dict) else body
    assert rows == []




def _log(**kwargs):
    from apps.logging.models import LogEntry

    defaults = {
        "level": "WARNING",
        "category": "ENGINE",
        "source": "apps.engine.fanout",
        "message": "leg failed",
    }
    return LogEntry.objects.create(**{**defaults, **kwargs})


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_log_hides_rows_naming_a_hidden_account():
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    _log(account_id=visible.id, message="visible leg timed out")
    _log(account_id=hidden.id, message="quiet leg timed out")
    _log(message="engine started")

    rows = other_client().get("/api/logging/logs/").json()
    assert {row["message"] for row in rows} == {"visible leg timed out", "engine started"}

    rows = viewer_client().get("/api/logging/logs/").json()
    assert len(rows) == 3


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_logs_account_filter_is_not_an_existence_oracle():
    hidden = make_account("quiet", hidden=True)
    _log(account_id=hidden.id)

    assert other_client().get(f"/api/logging/logs/?account_id={hidden.id}").json() == []
    assert len(viewer_client().get(f"/api/logging/logs/?account_id={hidden.id}").json()) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_log_hides_rows_citing_a_wholly_hidden_trade():
    """A row carrying only a trade id names no account — but that trade is
    absent from history, so the log would be the one place it existed."""
    hidden = make_account("quiet", hidden=True)
    trade = open_trade_with(hidden)
    _log(trade_id=trade.id, message="fan-out settled")

    assert other_client().get("/api/logging/logs/").json() == []
    assert len(viewer_client().get("/api/logging/logs/").json()) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_log_row_about_a_deleted_account_is_still_readable():
    """The filter excludes *hidden* ids, not unknown ones — otherwise every log
    row about an account that has since been removed silently disappears."""
    make_account("quiet", hidden=True)
    _log(account_id=99999, message="leg failed on a since-deleted account")

    rows = other_client().get("/api/logging/logs/").json()
    assert [row["message"] for row in rows] == ["leg failed on a since-deleted account"]




@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_excludes_hidden_legs_from_rows_and_from_totals():
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    open_trade_with(visible, hidden)

    body = other_client().get("/api/trading/positions/").json()
    assert [row["account_label"] for row in body["legs"]] == ["open-book"]
    assert body["totals"]["accounts"] == 1
    assert body["totals"]["margin"] == "50"

    seen = viewer_client().get("/api/trading/positions/").json()
    assert seen["totals"]["accounts"] == 2
    assert seen["totals"]["margin"] == "100"


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_wholly_hidden_position_reads_as_no_open_trade():
    hidden = make_account("quiet", hidden=True)
    open_trade_with(hidden)

    body = other_client().get("/api/trading/positions/").json()
    assert body["trade"] is None
    assert body["legs"] == []

    assert viewer_client().get("/api/trading/positions/").json()["trade"] is not None




def movement(account: ConnectedAccount, kind: str, amount: str) -> FundMovement:
    return FundMovement.objects.create(account=account, kind=kind, amount=amount)


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_ledger_hides_hidden_accounts_from_rows_exchanges_and_totals():
    """A total that covers money with no visible account behind it is itself a
    leak — the same rule the positions panel's totals line obeys."""
    visible = make_account("open-book", last_balance="110")
    movement(visible, FundMovementType.DEPOSIT, "100")
    hidden = make_account("quiet", hidden=True, last_balance="5010")
    movement(hidden, FundMovementType.DEPOSIT, "5000")

    body = other_client().get("/api/accounts/ledger/").json()
    assert [row["label"] for row in body["accounts"]] == ["open-book"]
    assert body["totals"]["accounts"] == 1
    assert D(body["totals"]["net_invested"]) == D("100")
    assert D(body["totals"]["pnl"]) == D("10")

    seen = viewer_client().get("/api/accounts/ledger/").json()
    assert {row["label"] for row in seen["accounts"]} == {"open-book", "quiet"}
    assert seen["totals"]["accounts"] == 2
    assert D(seen["totals"]["pnl"]) == D("20")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_all_hidden_ledger_reads_as_no_movement_at_all():
    hidden = make_account("quiet", hidden=True, last_balance="5010")
    movement(hidden, FundMovementType.DEPOSIT, "5000")

    body = other_client().get("/api/accounts/ledger/").json()
    assert body["accounts"] == []
    assert body["exchanges"] == []
    assert body["totals"]["accounts"] == 0

    seen = viewer_client().get("/api/accounts/ledger/").json()
    assert len(seen["accounts"]) == 1


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_hidden_accounts_never_appear_in_the_non_usdt_list():
    make_account("quiet", hidden=True, last_balance_asset="BTC", last_balance="0.1")
    body = other_client().get("/api/accounts/ledger/").json()
    assert body["non_usdt"] == []


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_ledger_movements_hide_the_hidden_rows_and_404_on_the_probe():
    visible = make_account("open-book")
    movement(visible, FundMovementType.DEPOSIT, "100")
    hidden = make_account("quiet", hidden=True)
    movement(hidden, FundMovementType.DEPOSIT, "5000")

    client = other_client()
    body = client.get("/api/accounts/ledger/movements/").json()
    assert [row["account_label"] for row in body] == ["open-book"]
    assert client.get(f"/api/accounts/ledger/movements/?account={hidden.id}").status_code == 404

    seen = viewer_client().get("/api/accounts/ledger/movements/").json()
    assert len(seen) == 2


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_ledger_movement_delete_404s_for_a_hidden_accounts_row():
    hidden = make_account("quiet", hidden=True)
    row = movement(hidden, FundMovementType.DEPOSIT, "5000")

    assert other_client().delete(f"/api/accounts/ledger/movements/{row.id}/").status_code == 404
    assert FundMovement.objects.filter(id=row.id).exists()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_ledger_movement_create_404s_for_a_hidden_account():
    hidden = make_account("quiet", hidden=True)

    response = other_client().post(
        "/api/accounts/ledger/movements/",
        {"account": hidden.id, "kind": "deposit", "amount": "100"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert not FundMovement.objects.exists()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_split_is_global_and_visible_to_everyone():
    """The split percentages are not per-account and are not a leak: they name
    no account, so both readers get the same numbers."""
    body = other_client().get("/api/accounts/ledger/split/").json()
    assert body["investor"] == "60.00"
    assert viewer_client().get("/api/accounts/ledger/split/").json() == body




@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_failure_notices_for_a_hidden_account_are_not_listed():
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    Notification.objects.create(account=visible, message="visible failure", code="x")
    Notification.objects.create(account=hidden, message="secret failure", code="x")
    Notification.objects.create(account=None, message="platform failure", code="x")

    body = other_client().get("/api/accounts/notifications/").json()
    messages = {row["message"] for row in body}
    assert messages == {"visible failure", "platform failure"}

    seen = {row["message"] for row in viewer_client().get("/api/accounts/notifications/").json()}
    assert "secret failure" in seen




@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_hidden_account_is_still_eligible_to_trade():
    """The invariant the whole feature rests on.

    ``eligible_accounts`` is what decides who a signal reaches. It must not know
    this flag exists — if it ever filters on it, hiding an account has quietly
    become a way to stop trading it.
    """
    from asgiref.sync import async_to_sync

    from apps.trading.services import eligible_accounts

    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)

    chosen = {a.id for a in async_to_sync(eligible_accounts)()}
    assert chosen == {visible.id, hidden.id}


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_balance_polling_still_covers_hidden_accounts():
    """Spec §6 wants every account's balance current — the viewer reads them."""
    from asgiref.sync import async_to_sync

    from apps.trading.services import eligible_accounts_for_balances

    hidden = make_account("quiet", hidden=True)
    polled = {a.id for a in async_to_sync(eligible_accounts_for_balances)()}
    assert hidden.id in polled




@database_sync_to_async
def _make_socket_fixtures(username: str, *, staff: bool = True):
    user = User.objects.create_user(username, password="pw12345!", is_staff=staff)
    visible = make_account("open-book")
    hidden = make_account("quiet", hidden=True)
    return user, visible.id, hidden.id


async def _open(user) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    assert await communicator.receive_json_from() == {"type": "connected"}
    return communicator


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_socket_strips_hidden_legs_balances_and_notices():
    user, visible_id, hidden_id = await _make_socket_fixtures("boss")
    communicator = await _open(user)
    layer = get_channel_layer()

    await layer.group_send(
        GROUP,
        {
            "type": "leg_result",
            "payload": {
                "trade_id": 1,
                "legs": [
                    {"account_id": visible_id, "ok": True, "error": "", "code": "", "ms": 1.0},
                    {"account_id": hidden_id, "ok": False, "error": "boom", "code": "e", "ms": 2.0},
                ],
            },
        },
    )
    message = await communicator.receive_json_from()
    assert [leg["account_id"] for leg in message["legs"]] == [visible_id]

    await layer.group_send(
        GROUP,
        {
            "type": "balances",
            "payload": [
                {"id": visible_id, "label": "open-book", "balance": "100"},
                {"id": hidden_id, "label": "quiet", "balance": "5000"},
            ],
        },
    )
    message = await communicator.receive_json_from()
    assert [row["id"] for row in message["accounts"]] == [visible_id]

    await layer.group_send(
        GROUP,
        {
            "type": "notification",
            "payload": {"id": 1, "account_id": hidden_id, "message": "secret"},
        },
    )
    await layer.group_send(
        GROUP,
        {
            "type": "notification",
            "payload": {"id": 2, "account_id": visible_id, "message": "shown"},
        },
    )
    message = await communicator.receive_json_from()
    assert message["message"] == "shown"

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_position_sync_event_names_no_hidden_account():
    """``positions_changed`` is a read surface: it carries account ids."""
    user, visible_id, hidden_id = await _make_socket_fixtures("boss")
    communicator = await _open(user)
    layer = get_channel_layer()

    await layer.group_send(
        GROUP,
        {
            "type": "positions_changed",
            "payload": {
                "closed": [hidden_id],
                "adopted": [],
                "drifted": [],
                "untracked": [f"{hidden_id}:BTCUSDT"],
                "reopened": 7,
            },
        },
    )
    await layer.group_send(
        GROUP,
        {
            "type": "positions_changed",
            "payload": {
                "closed": [hidden_id, visible_id],
                "adopted": [],
                "drifted": [],
                "untracked": [f"{hidden_id}:ETHUSDT"],
                "reopened": 8,
            },
        },
    )

    message = await communicator.receive_json_from()
    assert message["type"] == "positions_changed"
    assert message["closed"] == [visible_id]
    assert message["untracked"] == []
    assert "reopened" not in message
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_live_log_tail_drops_rows_naming_a_hidden_account():
    """The log page's live tail is a read surface like every other one."""
    user, visible_id, hidden_id = await _make_socket_fixtures("boss")
    communicator = await _open(user)
    layer = get_channel_layer()

    await layer.group_send(
        GROUP,
        {
            "type": "system_log.entry",
            "entry": {"id": 1, "level": "WARNING", "account_id": hidden_id, "message": "secret"},
        },
    )
    await layer.group_send(
        GROUP,
        {
            "type": "system_log.entry",
            "entry": {"id": 2, "level": "WARNING", "account_id": visible_id, "message": "shown"},
        },
    )
    message = await communicator.receive_json_from()
    assert message["type"] == "system_log"
    assert message["message"] == "shown"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_a_wholly_hidden_fanout_sends_nothing_at_all():
    """Not even the envelope: a trade id plus an empty list is still news."""
    user, _visible_id, hidden_id = await _make_socket_fixtures("boss")
    communicator = await _open(user)

    await get_channel_layer().group_send(
        GROUP,
        {
            "type": "leg_result",
            "payload": {
                "trade_id": 9,
                "legs": [{"account_id": hidden_id, "ok": True, "error": "", "code": "", "ms": 1.0}],
            },
        },
    )
    assert await communicator.receive_nothing(timeout=0.3)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
async def test_the_viewers_socket_receives_everything():
    user, visible_id, hidden_id = await _make_socket_fixtures(_svc)
    communicator = await _open(user)

    await get_channel_layer().group_send(
        GROUP,
        {
            "type": "leg_result",
            "payload": {
                "trade_id": 9,
                "legs": [
                    {"account_id": visible_id, "ok": True, "error": "", "code": "", "ms": 1.0},
                    {"account_id": hidden_id, "ok": True, "error": "", "code": "", "ms": 1.0},
                ],
            },
        },
    )
    message = await communicator.receive_json_from()
    assert {leg["account_id"] for leg in message["legs"]} == {visible_id, hidden_id}
    await communicator.disconnect()

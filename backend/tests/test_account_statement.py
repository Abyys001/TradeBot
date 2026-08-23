"""The downloadable statement: one account between two dates.

The per-account page answers "everything, ever" and is checked in
``test_account_report``. This file exists because a *window* introduces a
different way to be wrong: a figure that covers the account's whole life
printed under a heading that names one month is a lie that whoever receives the
PDF cannot detect. So what is pinned here is the boundary — which legs and
which cash flows fall inside the period, which whole-life figures deliberately
do not move, and that an inclusive end date really includes that whole day.

The rendering itself is pinned only as far as it can be: the route returns a
real PDF, named after the period, for a window with trades in it and for one
with nothing in it at all — an empty table is exactly where a report generator
falls over.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
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
)
from apps.accounts.report import statement_report
from apps.accounts.statement import Statement, build_statement_pdf, statement_filename
from apps.accounts.views import statement_window
from apps.trading.models import Trade, TradeLeg

KEY = Fernet.generate_key().decode()
pytestmark = pytest.mark.django_db

NOW = timezone.now()
#: The window every test below asks about: the seven days ending yesterday.
START = NOW - timedelta(days=7)
END = NOW - timedelta(days=1)


def make_account(label="partner-a", **overrides) -> ConnectedAccount:
    account = ConnectedAccount(
        label=label,
        exchange=overrides.pop("exchange", Exchange.BYBIT),
        status=overrides.pop("status", AccountStatus.ACTIVE),
        withdrawal_check_passed=True,
        withdrawal_checked_at=NOW,
        last_balance=overrides.pop("last_balance", Decimal("1200")),
        last_balance_asset=overrides.pop("last_balance_asset", "USDT"),
        **overrides,
    )
    account.set_credentials(api_key="k", api_secret="s")
    account.save()
    return account


def add_leg(account, *, opened, closed=None, pnl=None, ok=True, symbol="BTCUSDT"):
    """A leg with both of its instants chosen. ``opened_at`` is ``auto_now_add``,
    so it can only be set after the row exists."""
    trade = Trade.objects.create(symbol=symbol, side="long", leverage=10)
    leg = TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=ok,
        error="" if ok else "rejected: below minimum notional",
        error_code="" if ok else "below_min",
        qty=Decimal("0.01"),
        entry_price=Decimal("50000"),
        exit_price=Decimal("51000") if closed else None,
        margin=Decimal("100"),
        pnl=None if pnl is None else Decimal(pnl),
        closed_at=closed,
    )
    TradeLeg.objects.filter(pk=leg.pk).update(opened_at=opened)
    leg.refresh_from_db()
    return leg


def add_movement(account, *, when, amount, kind=FundMovementType.DEPOSIT):
    return FundMovement.objects.create(
        account=account, kind=kind, amount=Decimal(amount), occurred_at=when
    )


# --- the window ----------------------------------------------------------


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_leg_belongs_to_the_period_it_was_realised_in():
    """Money moves when the position closes, not when it opens.

    A leg opened before the window and closed inside it is this period's
    result; one opened inside it and closed after is the *next* period's, and
    counting it here would credit the account twice over two statements.
    """
    account = make_account()
    add_leg(account, opened=START - timedelta(days=3), closed=START + timedelta(days=1), pnl="40")
    add_leg(account, opened=START + timedelta(days=2), closed=END + timedelta(days=2), pnl="99")
    add_leg(account, opened=START - timedelta(days=9), closed=START - timedelta(days=8), pnl="500")

    data = statement_report(account, start=START, end=END)

    assert [Decimal(row["pnl"]) for row in data["closed"]] == [Decimal("40")]
    assert Decimal(data["trading"]["realised_pnl"]) == Decimal("40")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_position_still_open_returns_nothing_yet():
    """Listed, because the reader has to know it is there. Not summed, because
    an unrealised number on a receipt is a promise, not a result."""
    account = make_account()
    add_leg(account, opened=START + timedelta(days=1), closed=None)
    add_leg(account, opened=START + timedelta(days=2), closed=END - timedelta(hours=1), pnl="12")

    data = statement_report(account, start=START, end=END)

    assert len(data["open"]) == 1
    assert data["open"][0]["open"] is True
    assert len(data["closed"]) == 1
    assert Decimal(data["trading"]["realised_pnl"]) == Decimal("12")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_leg_closed_after_the_window_is_open_as_far_as_this_statement_knows():
    """The statement describes the period, not the moment it was printed.

    A position that was running when the window ended is reported as running,
    even though by now it has closed — otherwise reprinting last month's
    statement today would produce a different last month.
    """
    account = make_account()
    add_leg(account, opened=START + timedelta(days=1), closed=END + timedelta(days=3), pnl="75")

    data = statement_report(account, start=START, end=END)

    assert data["closed"] == []
    assert len(data["open"]) == 1
    assert Decimal(data["trading"]["realised_pnl"]) == Decimal("0")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_failed_leg_is_listed_as_a_failure_not_a_flat_trade():
    """An order that never reached the exchange returned nothing. Folding it
    into the results would drag the win rate toward a trade that never was."""
    account = make_account()
    add_leg(account, opened=START + timedelta(days=1), closed=None, ok=False)
    add_leg(account, opened=START + timedelta(days=1), closed=END - timedelta(days=1), pnl="20")

    data = statement_report(account, start=START, end=END)

    assert len(data["failed"]) == 1
    assert data["failed"][0]["error_code"] == "below_min"
    assert data["open"] == []
    assert Decimal(data["trading"]["realised_pnl"]) == Decimal("20")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_cash_flows_are_windowed_and_netted():
    account = make_account()
    add_movement(account, when=START + timedelta(days=1), amount="1000")
    add_movement(
        account,
        when=START + timedelta(days=2),
        amount="250",
        kind=FundMovementType.WITHDRAWAL,
    )
    add_movement(account, when=START - timedelta(days=5), amount="9999")
    add_movement(account, when=END + timedelta(hours=2), amount="7777")

    flows = statement_report(account, start=START, end=END)["flows"]

    assert flows["count"] == 2
    assert Decimal(flows["deposits"]) == Decimal("1000")
    assert Decimal(flows["withdrawals"]) == Decimal("250")
    assert Decimal(flows["net"]) == Decimal("750")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_lifetime_figures_are_carried_through_unwindowed():
    """Balance and PnL-since-inception cannot be cut to a period — the account
    is worth what it is worth. They ride along whole; the PDF labels them."""
    account = make_account(last_balance=Decimal("1200"))
    add_movement(account, when=START - timedelta(days=40), amount="1000")

    data = statement_report(account, start=START, end=END)

    assert Decimal(data["ledger"]["net_invested"]) == Decimal("1000")
    assert Decimal(data["ledger"]["pnl"]) == Decimal("200")
    assert data["flows"]["count"] == 0


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_no_window_is_the_whole_life():
    account = make_account()
    add_leg(account, opened=START - timedelta(days=90), closed=START - timedelta(days=89), pnl="5")
    add_movement(account, when=START - timedelta(days=90), amount="100")

    data = statement_report(account)

    assert len(data["closed"]) == 1
    assert data["flows"]["count"] == 1
    assert data["period"] == {"start": None, "end": None}


# --- the route -----------------------------------------------------------


def staff_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


class _FakeRequest:
    """``statement_window`` reads one attribute, and a whole DRF request to pin
    an off-by-one would be more setup than the thing under test."""

    def __init__(self, params):
        self.query_params = params


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_end_date_includes_that_whole_day():
    """``end=2026-03-31`` means the 31st, all of it.

    The operator types a calendar day; the server turns it into the exclusive
    midnight after it. Off by one here silently drops the last day's trades
    from every month-end statement.
    """
    account = make_account()
    day = (NOW - timedelta(days=3)).astimezone(timezone.get_current_timezone())
    stamp = day.strftime("%Y-%m-%d")
    add_leg(
        account,
        opened=day - timedelta(days=1),
        closed=day.replace(hour=23, minute=59, second=0, microsecond=0),
        pnl="33",
    )

    start, end = statement_window(_FakeRequest({"start": stamp, "end": stamp}))
    data = statement_report(account, start=start, end=end)

    assert [Decimal(row["pnl"]) for row in data["closed"]] == [Decimal("33")]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_route_returns_a_named_pdf():
    account = make_account(label="Partner A")
    add_leg(account, opened=START + timedelta(days=1), closed=END - timedelta(days=1), pnl="42")

    response = staff_client().get(
        f"/api/accounts/accounts/{account.id}/statement/",
        {"start": START.strftime("%Y-%m-%d"), "end": END.strftime("%Y-%m-%d")},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "no-store"
    assert response.content.startswith(b"%PDF-")
    assert int(response["Content-Length"]) == len(response.content)
    disposition = response["Content-Disposition"]
    assert disposition.startswith("attachment; filename=")
    assert START.strftime("%Y-%m-%d") in disposition


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_period_with_nothing_in_it_still_produces_a_statement():
    """The empty case is the one a report generator breaks on, and it is a real
    answer: "this account did nothing that month" is worth being able to send."""
    account = make_account()
    add_leg(account, opened=START - timedelta(days=90), closed=START - timedelta(days=89), pnl="5")

    data = statement_report(account, start=START, end=END)
    pdf = build_statement_pdf(data)

    assert data["closed"] == data["open"] == data["failed"] == []
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_filename_names_the_account_and_the_period():
    account = make_account(label="Partner A / EU")
    data = statement_report(account, start=START, end=END)

    name = statement_filename(data)

    assert name.endswith(".pdf")
    assert "/" not in name and " " not in name
    assert START.strftime("%Y-%m-%d") in name


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_period_that_ends_before_it_starts_is_refused():
    """Silently swapping them would produce a statement for a period nobody
    asked for, which is worse than an error the operator can see."""
    account = make_account()

    response = staff_client().get(
        f"/api/accounts/accounts/{account.id}/statement/",
        {"start": "2026-03-31", "end": "2026-03-01"},
    )

    assert response.status_code == 400


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_unparseable_date_is_refused_not_ignored():
    account = make_account()

    response = staff_client().get(
        f"/api/accounts/accounts/{account.id}/statement/", {"start": "last tuesday"}
    )

    assert response.status_code == 400


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_statement_is_staff_only_and_respects_visibility():
    """The PDF carries everything the report does, so it filters identically:
    an account the caller cannot list is a 404 here too, not a download of it."""
    hidden = make_account(label="quiet", hidden=True)
    visible = make_account(label="loud")
    client = staff_client()

    assert client.get(f"/api/accounts/accounts/{visible.id}/statement/").status_code == 200
    assert client.get(f"/api/accounts/accounts/{hidden.id}/statement/").status_code == 404

    anonymous = Client()
    path = f"/api/accounts/accounts/{visible.id}/statement/"
    assert anonymous.get(path).status_code in (401, 403)


# --- the two languages ----------------------------------------------------


def _flowable_text(flowables) -> str:
    """Every string the layout will actually draw, flattened.

    Reading the built PDF back would mean decoding compressed streams and
    subset fonts; the story is the same words one step earlier, and it is where
    a stray figure would be introduced.
    """
    from reportlab.platypus import KeepTogether, Paragraph, Table

    out: list[str] = []
    for item in flowables:
        if isinstance(item, Paragraph):
            out.append(item.text)
        elif isinstance(item, Table):
            for row in item._cellvalues:
                out.append(_flowable_text(row))
        elif isinstance(item, KeepTogether):
            out.append(_flowable_text(item._content))
        elif isinstance(item, list | tuple):
            out.append(_flowable_text(item))
    return " ".join(out)


def _rich_account():
    """One account with something in every section, so nothing is skipped."""
    account = make_account(label="partner-alpha")
    for index, pnl in enumerate(["120.40", "-45.10", "310.00"]):
        add_leg(
            account,
            opened=START + timedelta(hours=index),
            closed=START + timedelta(hours=index, minutes=30),
            pnl=pnl,
            symbol=["BTCUSDT", "ETHUSDT", "SOLUSDT"][index],
        )
    add_leg(account, opened=END - timedelta(hours=2), closed=None)
    add_leg(account, opened=START + timedelta(days=1), closed=None, ok=False)
    add_movement(account, when=START + timedelta(days=1), amount="1000")
    add_movement(
        account, when=START + timedelta(days=3), amount="250",
        kind=FundMovementType.WITHDRAWAL,
    )
    return account


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
@pytest.mark.parametrize("lang", ["en", "fa"])
def test_no_percentage_reaches_the_page(lang):
    """The admin asked for a statement that talks in money only.

    A return, a win rate or a share of the split expressed as a percentage
    invites the reader to apply it to a number that is not on the page, so the
    rule is absolute rather than a matter of taste — and it is pinned here
    because the natural way to add a column is to compute one.
    """
    data = statement_report(_rich_account(), start=START, end=END)

    text = _flowable_text(Statement(data, lang).story())

    assert "%" not in text
    assert "percent" not in text.lower()


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_persian_renders_with_its_own_font_embedded():
    """Helvetica has no Arabic glyphs, so a Persian statement set in it comes
    out as a page of blanks that still passes every "is this a PDF" check."""
    data = statement_report(_rich_account(), start=START, end=END)

    english = build_statement_pdf(data, "en")
    persian = build_statement_pdf(data, "fa")

    assert persian.startswith(b"%PDF-")
    assert b"Vazirmatn" in persian
    assert b"Vazirmatn" not in english
    assert persian != english


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_filename_says_which_language_it_is():
    """Both files are legitimate and look alike in a downloads folder."""
    data = statement_report(make_account(), start=START, end=END)

    assert statement_filename(data, "en").endswith("-en.pdf")
    assert statement_filename(data, "fa").endswith("-fa.pdf")


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_the_route_serves_the_language_asked_for():
    account = make_account()
    path = f"/api/accounts/accounts/{account.id}/statement/"
    client = staff_client()

    persian = client.get(path, {"lang": "fa"})
    default = client.get(path)

    assert persian.status_code == default.status_code == 200
    assert "-fa.pdf" in persian["Content-Disposition"]
    assert "-en.pdf" in default["Content-Disposition"]


@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_an_unknown_language_falls_back_rather_than_failing():
    """A statement in the wrong language is recoverable in one click; a 400 in
    the middle of sending a partner their month is not."""
    account = make_account()

    response = staff_client().get(
        f"/api/accounts/accounts/{account.id}/statement/", {"lang": "de"}
    )

    assert response.status_code == 200
    assert "-en.pdf" in response["Content-Disposition"]

"""The Properties tab on a bot's own page — `docs/bots.md`, `apps/pine/properties.py`.

The merge rule is platform → script → panel and it lives in `properties.resolve`.
These tests are about the surface in front of it: that the panel is handed the
*outcome* rather than the rule, that an override is refused by name instead of
being clamped into something the operator did not type, and — the one that
matters most — that a property the backtest honours and live does not still says
so once the panel is the thing that set it.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.bots.models import Bot
from tests import pine_corpus
from tests.bot_factory import make_bot

pytestmark = pytest.mark.django_db

DECLARED = (pine_corpus.ACCEPT / "26_strategy_properties.pine").read_text()

#: Declares two properties and leaves the other fourteen alone. The corpus
#: fixture sets all sixteen, which cannot demonstrate the difference between
#: "the script chose this" and "nobody did".
SPARSE = """//@version=5
strategy("sparse", initial_capital = 25000, pyramiding = 2)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("L", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("L")
plot(fast)
"""


def staff() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def patch(client: Client, url: str, payload: dict):
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


def bot_with_declared_properties(client: Client, source: str = DECLARED) -> Bot:
    """A bot on a version saved through the API, so `properties` is really populated."""
    strategy = client.post(
        "/api/bots/strategies/",
        data=json.dumps({"name": f"declared-{abs(hash(source)) % 10000}"}),
        content_type="application/json",
    ).json()
    version = client.post(
        f"/api/bots/strategies/{strategy['id']}/versions/",
        data=json.dumps({"source": source}),
        content_type="application/json",
    ).json()
    bot = make_bot(name="props")
    bot.strategy_version_id = version["id"]
    bot.save(update_fields=["strategy_version"])
    return bot


# --- the endpoint -----------------------------------------------------------


def test_properties_is_staff_only():
    bot = make_bot()
    assert Client().get(f"/api/bots/bots/{bot.id}/properties/").status_code in (401, 403)


def test_properties_returns_the_resolved_set_and_the_form():
    client = staff()
    bot = make_bot()
    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()

    assert body["bot"] == bot.id
    # Every field concrete: the panel never has to ask a second time.
    assert body["resolved"]["initial_capital"] == "10000"
    assert body["resolved"]["currency"] == "USDT"
    assert body["resolved"]["default_qty_type"] == "platform"

    # The form travels with it, in TradingView's four groups.
    assert [row["key"] for row in body["schema"]["categories"]] == [
        "capital",
        "sizing",
        "costs",
        "execution",
    ]
    assert len(body["schema"]["fields"]) == 16


def test_a_script_declaration_is_reported_as_the_scripts_and_not_the_panels():
    """ "From the script" is the whole reason `declared` exists.

    A stored `StrategyVersion.properties` is a *resolved* set, so it carries all
    sixteen keys. Replaying it wholesale would caption every field "from the
    script" — including the ten the author never mentioned.
    """
    client = staff()
    bot = bot_with_declared_properties(client, SPARSE)
    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()

    assert body["resolved"]["initial_capital"] == "25000"
    assert body["resolved"]["pyramiding"] == 2
    assert set(body["resolved"]["declared"]) == {"initial_capital", "pyramiding"}
    # The fourteen the author never mentioned are the platform's, and saying
    # otherwise would put "from the script" under every field on the form.
    for untouched in ("margin_long", "slippage", "commission_value", "currency"):
        assert untouched not in body["resolved"]["declared"]
    assert body["resolved"]["overridden"] == []


def test_the_panel_wins_over_the_script():
    client = staff()
    bot = bot_with_declared_properties(client, SPARSE)
    assert (
        patch(
            client,
            f"/api/bots/bots/{bot.id}/",
            {"property_overrides": {"initial_capital": "5000"}},
        ).status_code
        == 200
    )

    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()
    assert body["resolved"]["initial_capital"] == "5000"
    assert body["resolved"]["overridden"] == ["initial_capital"]
    # The script still owns everything the panel did not touch.
    assert body["resolved"]["pyramiding"] == 2


# --- refusing, rather than quietly correcting -------------------------------


def test_an_unknown_property_is_refused_by_name():
    client = staff()
    bot = make_bot()
    response = patch(client, f"/api/bots/bots/{bot.id}/", {"property_overrides": {"leverage": 10}})
    assert response.status_code == 400
    assert "leverage" in json.dumps(response.json())


def test_a_negative_entry_count_is_refused_rather_than_floored():
    """`_clean` floors these at zero. Storing that silently is the bug.

    Somebody typing -3 into a form is looking at the field; coming back with 0
    and no message would leave the next backtest captioned with a number nobody
    chose.
    """
    client = staff()
    bot = make_bot()
    response = patch(
        client, f"/api/bots/bots/{bot.id}/", {"property_overrides": {"pyramiding": -3}}
    )
    assert response.status_code == 400
    bot.refresh_from_db()
    assert bot.property_overrides == {}


def test_capital_cannot_be_zero():
    client = staff()
    bot = make_bot()
    assert (
        patch(
            client,
            f"/api/bots/bots/{bot.id}/",
            {"property_overrides": {"initial_capital": "0"}},
        ).status_code
        == 400
    )


def test_clearing_an_override_hands_the_field_back():
    """`null` means "stop overriding", not "pin this to None"."""
    client = staff()
    bot = bot_with_declared_properties(client, SPARSE)
    patch(client, f"/api/bots/bots/{bot.id}/", {"property_overrides": {"initial_capital": "5000"}})
    patch(client, f"/api/bots/bots/{bot.id}/", {"property_overrides": {"initial_capital": None}})

    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()
    assert body["overrides"] == {}
    assert body["resolved"]["initial_capital"] == "25000"  # the script's again


def test_overrides_are_stored_as_json_that_reads_back():
    """Decimal and StrEnum both survive `_clean` and neither survives JSONField."""
    client = staff()
    bot = make_bot()
    patch(
        client,
        f"/api/bots/bots/{bot.id}/",
        {"property_overrides": {"initial_capital": "5000", "default_qty_type": "cash"}},
    )
    bot.refresh_from_db()
    assert bot.property_overrides == {"initial_capital": "5000", "default_qty_type": "cash"}


# --- the sentences that keep it honest --------------------------------------


def test_an_override_that_live_will_not_honour_says_so():
    """Spec §5 is the invariant; this tab cannot move it, and must not imply it can."""
    client = staff()
    bot = make_bot()
    patch(
        client,
        f"/api/bots/bots/{bot.id}/",
        {
            "property_overrides": {
                "default_qty_type": "percent_of_equity",
                "default_qty_value": "10",
            }
        },
    )
    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()

    assert body["live_departures"], "changing order size must be reported as backtest-only"
    assert any("99%" in line for line in body["live_departures"])


def test_a_property_this_platform_cannot_honour_at_all_is_still_listed():
    """Q20: parsed-and-dropped is only allowed out loud.

    `calc_on_every_tick` has nothing to recalculate from here. Hiding the row
    would read as a platform that never heard of it.
    """
    client = staff()
    bot = make_bot()
    patch(client, f"/api/bots/bots/{bot.id}/", {"property_overrides": {"calc_on_every_tick": True}})
    body = client.get(f"/api/bots/bots/{bot.id}/properties/").json()

    keys = [row["key"] for row in body["schema"]["fields"]]
    assert "calc_on_every_tick" in keys
    assert body["inert"], "an inert property must say it is inert"


def test_every_backtest_only_field_carries_its_sentence_in_the_schema():
    """The warning is a fact about the property, so it ships with the form.

    Not only once the value departs: the question asked *while typing* is "will
    this reach live", and a note that appears after the fact answers it late.
    """
    client = staff()
    bot = make_bot()
    fields = {
        row["key"]: row
        for row in client.get(f"/api/bots/bots/{bot.id}/properties/").json()["schema"]["fields"]
    }
    for key in ("initial_capital", "default_qty_type", "pyramiding", "margin_long"):
        assert fields[key]["backtest_only"], f"{key} must carry its live-departure sentence"
    for key in ("calc_on_every_tick", "fill_orders_on_standard_ohlc"):
        assert fields[key]["inert"], f"{key} must say it does nothing here"

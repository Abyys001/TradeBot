"""Tests for pro features (versioning, journal, marketplace)."""
import pytest
from django.contrib.auth import get_user_model

from apps.pro.models import MarketplacePackage, StrategyVersion, TradeJournal
from apps.strategies.models import Strategy


def _login(client, username="pro"):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="pw")
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_version_snapshot_increments(client):
    user = _login(client)
    strat = Strategy.objects.create(user=user, name="S", type="pine", symbol="BTC", source="v1")
    r1 = client.post(f"/api/pro/strategies/{strat.pk}/versions/", {}, content_type="application/json")
    assert r1.json()["version"] == 1
    strat.source = "v2"
    strat.save(update_fields=["source"])
    r2 = client.post(f"/api/pro/strategies/{strat.pk}/versions/", {}, content_type="application/json")
    assert r2.json()["version"] == 2
    assert StrategyVersion.objects.filter(strategy=strat).count() == 2


@pytest.mark.django_db
def test_version_restore_overwrites_source(client):
    user = _login(client)
    strat = Strategy.objects.create(user=user, name="S", type="pine", symbol="BTC", source="orig")
    client.post(f"/api/pro/strategies/{strat.pk}/versions/", {}, content_type="application/json")
    strat.source = "changed"
    strat.save(update_fields=["source"])
    client.post(f"/api/pro/strategies/{strat.pk}/versions/1/restore/", {}, content_type="application/json")
    strat.refresh_from_db()
    assert strat.source == "orig"


@pytest.mark.django_db
def test_journal_create_and_list(client):
    _login(client)
    client.post(
        "/api/pro/journal/",
        {"title": "Entry", "body": "reason", "tags": ["btc"]},
        content_type="application/json",
    )
    resp = client.get("/api/pro/journal/")
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["title"] == "Entry"
    assert entries[0]["tags"] == ["btc"]


@pytest.mark.django_db
def test_journal_is_per_user(client):
    u1 = _login(client, "u1")
    TradeJournal.objects.create(user=u1, title="mine", body="")
    User = get_user_model()
    other = User.objects.create_user(username="u2", password="pw")
    TradeJournal.objects.create(user=other, title="theirs", body="")
    resp = client.get("/api/pro/journal/")
    titles = [e["title"] for e in resp.json()["entries"]]
    assert titles == ["mine"]


@pytest.mark.django_db
def test_marketplace_publish_and_list(client):
    _login(client)
    client.post(
        "/api/pro/marketplace/",
        {"name": "EMA Bot", "description": "d", "source": "src", "is_public": True},
        content_type="application/json",
    )
    resp = client.get("/api/pro/marketplace/")
    pkgs = resp.json()["packages"]
    assert len(pkgs) == 1
    assert pkgs[0]["name"] == "EMA Bot"


@pytest.mark.django_db
def test_marketplace_hides_private(client):
    _login(client)
    User = get_user_model()
    author = User.objects.create_user(username="author", password="pw")
    MarketplacePackage.objects.create(author=author, name="secret", source="s", is_public=False)
    resp = client.get("/api/pro/marketplace/")
    assert resp.json()["packages"] == []


@pytest.mark.django_db
def test_marketplace_import_creates_strategy(client):
    user = _login(client)
    User = get_user_model()
    author = User.objects.create_user(username="author", password="pw")
    pkg = MarketplacePackage.objects.create(author=author, name="Pub", source="bot-src", is_public=True)
    resp = client.post(
        f"/api/pro/marketplace/{pkg.pk}/import/",
        {"symbol": "ETH"},
        content_type="application/json",
    )
    sid = resp.json()["strategy_id"]
    strat = Strategy.objects.get(pk=sid)
    assert strat.user == user
    assert strat.source == "bot-src"
    assert strat.symbol == "ETH"


@pytest.mark.django_db
def test_pro_requires_auth(client):
    resp = client.get("/api/pro/journal/")
    assert resp.status_code in (401, 403)

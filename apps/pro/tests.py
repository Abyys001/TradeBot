"""Tests for pro features (versioning, replay)."""
import pytest
from django.contrib.auth import get_user_model

from apps.pro.models import StrategyVersion
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
def test_pro_requires_auth(client):
    resp = client.post("/api/pro/replay/", {}, content_type="application/json")
    assert resp.status_code in (401, 403)

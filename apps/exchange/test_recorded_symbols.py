"""Recorded-symbol control surface: what the dashboard switches on and off."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.exchange.models import RecordedSymbol

User = get_user_model()


@pytest.fixture
def admin_client(db):
    user = User.objects.create_user(username="boss", password="x", role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def investor_client(db):
    user = User.objects.create_user(username="inv", password="x", role=User.Role.INVESTOR)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_active_symbols_seeds_from_settings_when_table_empty(db, settings):
    settings.TABDEAL_INGEST_SYMBOLS = ["BTC_USDT", "ETH_USDT"]
    assert RecordedSymbol.active_symbols() == ["BTC_USDT", "ETH_USDT"]


def test_active_symbols_prefers_the_database(db, settings):
    settings.TABDEAL_INGEST_SYMBOLS = ["BTC_USDT"]
    RecordedSymbol.objects.create(symbol="SOL_USDT")
    assert RecordedSymbol.active_symbols() == ["SOL_USDT"]


def test_all_paused_means_record_nothing_not_fall_back_to_env(db, settings):
    """An explicit pause must not silently resurrect the env default."""
    settings.TABDEAL_INGEST_SYMBOLS = ["BTC_USDT"]
    RecordedSymbol.objects.create(symbol="SOL_USDT", is_active=False)
    assert RecordedSymbol.active_symbols() == []


def test_admin_can_add_pause_and_remove(admin_client):
    resp = admin_client.post("/api/marketdata/recorded/", {"symbol": "eth-usdt"}, format="json")
    assert resp.status_code == 201
    assert resp.data["symbol"] == "ETH_USDT"  # normalized
    pk = resp.data["id"]

    assert admin_client.patch(
        f"/api/marketdata/recorded/{pk}/", {"is_active": False}, format="json"
    ).status_code == 200
    assert RecordedSymbol.objects.get(pk=pk).is_active is False

    assert admin_client.delete(f"/api/marketdata/recorded/{pk}/").status_code == 204
    assert not RecordedSymbol.objects.filter(pk=pk).exists()


def test_symbol_format_is_validated(admin_client):
    resp = admin_client.post("/api/marketdata/recorded/", {"symbol": "BTC"}, format="json")
    assert resp.status_code == 400
    assert "BTC_USDT" in str(resp.data)


def test_duplicate_symbol_rejected(admin_client):
    admin_client.post("/api/marketdata/recorded/", {"symbol": "BTC_USDT"}, format="json")
    resp = admin_client.post("/api/marketdata/recorded/", {"symbol": "BTC_USDT"}, format="json")
    assert resp.status_code == 400


def test_investors_cannot_change_what_is_recorded(investor_client):
    assert investor_client.get("/api/marketdata/recorded/").status_code == 403
    assert investor_client.post(
        "/api/marketdata/recorded/", {"symbol": "BTC_USDT"}, format="json"
    ).status_code == 403
    assert investor_client.post(
        "/api/marketdata/backfill/", {"symbols": ["BTC_USDT"]}, format="json"
    ).status_code == 403


def test_backfill_requires_a_target(admin_client):
    assert admin_client.post("/api/marketdata/backfill/", {}, format="json").status_code == 400


def test_backfill_queues_a_task(admin_client, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    resp = admin_client.post(
        "/api/marketdata/backfill/",
        {"symbols": ["BTC_USDT"], "timeframes": ["1h"]},
        format="json",
    )
    assert resp.status_code == 202
    assert resp.data["status"] == "queued"

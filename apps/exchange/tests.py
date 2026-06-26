"""Tests for the Hyperliquid exchange layer (no live network)."""
from unittest import mock

import pandas as pd
import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import ExchangeCredential, Network

import eth_account

from . import candles, hl_client


def _make_cred():
    User = get_user_model()
    user = User.objects.create_user(username="bob", password="pw")
    cred = ExchangeCredential(
        user=user,
        label="agent",
        wallet_address="0x" + "11" * 20,
        network=Network.TESTNET,
    )
    cred.set_agent_key("0x" + "aa" * 32)
    cred.save()
    return cred


@pytest.mark.django_db
def test_verify_credential_success_marks_active():
    cred = _make_cred()
    fake_info = mock.Mock()
    fake_info.user_state.return_value = {"marginSummary": {}}
    fake_info.extra_agents.return_value = [eth_account.Account.from_key(cred.get_agent_key()).address]

    with mock.patch.object(hl_client, "build_info", return_value=fake_info):
        ok, detail = hl_client.verify_credential(cred)

    assert ok is True
    cred.refresh_from_db()
    assert cred.is_active is True
    assert cred.agent_address
    assert cred.last_verified_at is not None


@pytest.mark.django_db
def test_verify_credential_no_state_marks_inactive():
    cred = _make_cred()
    fake_info = mock.Mock()
    fake_info.user_state.return_value = None

    with mock.patch.object(hl_client, "build_info", return_value=fake_info):
        ok, detail = hl_client.verify_credential(cred)

    assert ok is False
    cred.refresh_from_db()
    assert cred.is_active is False


@pytest.mark.django_db
def test_verify_credential_network_error_is_handled():
    cred = _make_cred()
    with mock.patch.object(hl_client, "build_info", side_effect=ConnectionError):
        ok, detail = hl_client.verify_credential(cred)
    assert ok is False
    assert "failed" in detail


def _hl_candle(ts, o, h, l, c, v="100"):
    return {"t": ts, "o": str(o), "h": str(h), "l": str(l), "c": str(c), "v": str(v)}


def test_fetch_candles_normalizes_hl_response():
    rows = [_hl_candle(3000, 10, 11, 9, 10.5), _hl_candle(2000, 9, 10, 8, 9.5)]
    fake_info = mock.Mock()
    fake_info.candles_snapshot.return_value = rows

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = candles.fetch_candles("BTC", "1m", 2, network="testnet")

    assert len(df) == 2
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df.iloc[0]["ts"] == 2000
    assert df.iloc[1]["close"] == 10.5


def test_fetch_candles_raises_on_error():
    fake_info = mock.Mock()
    fake_info.candles_snapshot.side_effect = RuntimeError("api down")

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        with pytest.raises(candles.CandleFetchError):
            candles.fetch_candles("BTC", "1m", 10, network="testnet")


def test_fetch_candles_range_paginates_and_dedupes():
    from apps.exchange import history

    bar = 60_000  # 1m
    end_ms = 12_000 * bar
    # Backward pagination: first window is [end-window, end], then steps back.
    batch_recent = [_hl_candle(300_000, 1, 1, 1, 3), _hl_candle(360_000, 1, 1, 1, 4)]
    batch_older = [_hl_candle(0, 1, 1, 1, 1), _hl_candle(bar, 1, 1, 1, 2), _hl_candle(300_000, 1, 1, 1, 3)]
    fake_info = mock.Mock()
    fake_info.candles_snapshot.side_effect = [batch_recent, batch_older, []]

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = history.fetch_candles_range("BTC", "1m", 0, end_ms, network="testnet", sleep=0)

    assert fake_info.candles_snapshot.call_count >= 2
    assert list(df["ts"]) == [0, bar, 300_000, 360_000]


def test_fetch_candles_range_stops_at_history_floor():
    from apps.exchange import history

    fake_info = mock.Mock()
    fake_info.candles_snapshot.return_value = []  # no data at all
    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = history.fetch_candles_range("BTC", "1h", 0, 10_000_000, network="testnet", sleep=0)
    assert df.empty


@pytest.mark.django_db
def test_candle_store_roundtrip_and_merge(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path)
    from apps.exchange import candle_store

    df1 = candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5), _hl_candle(2000, 2, 3, 1, 2.5)])
    path = candle_store.save_candles("BTC", "1h", df1)
    assert path.exists()

    # Merge with an overlapping + a new row; dedupe on ts, keep ascending order.
    df2 = candles._normalize_rows([_hl_candle(2000, 2, 3, 1, 2.5), _hl_candle(3000, 3, 4, 2, 3.5)])
    candle_store.save_candles("BTC", "1h", df2)

    out = candle_store.load_candles("BTC", "1h")
    assert list(out["ts"]) == [1000, 2000, 3000]

    sliced = candle_store.load_candles("BTC", "1h", start=2000, end=3000)
    assert list(sliced["ts"]) == [2000, 3000]


@pytest.mark.django_db
def test_list_datasets(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path)
    from apps.exchange import candle_store

    df = candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5)])
    candle_store.save_candles("ETH", "4h", df)

    datasets = candle_store.list_datasets()
    assert len(datasets) == 1
    assert datasets[0]["coin"] == "ETH"
    assert datasets[0]["interval"] == "4h"
    assert datasets[0]["bars"] == 1
    assert datasets[0]["start_ts"] == 1000


def test_publish_closed_candle_pubsub():
    from apps.exchange import subscriptions

    fake_redis = mock.Mock()
    fake_redis.publish.return_value = 1
    with mock.patch.object(subscriptions, "_client", return_value=fake_redis):
        count = subscriptions.publish_closed_candle(
            network="testnet",
            coin="BTC",
            interval="1m",
            ts=1000,
            open_=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=10,
        )
    assert count == 1
    fake_redis.publish.assert_called_once()


def _make_user():
    User = get_user_model()
    return User.objects.create_user(username="alice", password="pw")


@pytest.mark.django_db
def test_create_download_bad_dates(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {
            "coins": ["BTC"],
            "intervals": ["1h"],
            "start": "2024-06-01",
            "end": "2024-01-01",
        },
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "start" in resp.json()["error"]


@pytest.mark.django_db
def test_create_download_bad_interval(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {"coins": ["BTC"], "intervals": ["99x"], "start": "2024-01-01", "end": "2024-06-01"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_download_bad_network(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {
            "coins": ["BTC"],
            "intervals": ["1h"],
            "start": "2024-01-01",
            "end": "2024-06-01",
            "network": "invalid",
        },
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_download_celery_failure(client):
    user = _make_user()
    client.force_login(user)
    with mock.patch("apps.exchange.views.download_history_task.delay", side_effect=RuntimeError("broker down")):
        resp = client.post(
            "/api/history/downloads/",
            {"coins": ["BTC"], "intervals": ["1h"], "start": "2024-01-01", "end": "2024-06-01"},
            content_type="application/json",
        )
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "failed"
    assert "broker down" in body["error"]


def test_download_history_skips_unknown_coin():
    from apps.exchange import history_download

    with mock.patch.object(history_download, "known_perp_coins", return_value={"BTC"}):
        outcome = history_download.download_history(
            ["FAKECOIN"],
            ["1h"],
            1_000,
            2_000,
            network="mainnet",
        )
    assert outcome["progress"]["FAKECOIN/1h"]["status"] == "skipped"


def test_download_history_partial_outcome():
    from apps.exchange import history_download

    def fake_pair(coin, interval, start_ms, end_ms, *, network="mainnet", known=None):
        if coin == "BTC":
            return {"key": f"{coin}/{interval}", "status": "done", "bars": 10}
        return {"key": f"{coin}/{interval}", "status": "failed", "error": "api down"}

    with mock.patch.object(history_download, "download_pair", side_effect=fake_pair):
        outcome = history_download.download_history(
            ["BTC", "ETH"],
            ["1h"],
            1_000,
            2_000,
        )
    assert outcome["progress"]["BTC/1h"]["status"] == "done"
    assert outcome["progress"]["ETH/1h"]["status"] == "failed"


@pytest.mark.django_db
def test_final_job_status_empty_is_failed():
    from apps.exchange.models import HistoryDownload
    from apps.exchange.tasks import _final_job_status

    progress = {"BTC/1h": {"status": "empty", "bars": 0}}
    assert _final_job_status(progress) == HistoryDownload.Status.FAILED


@pytest.mark.django_db
def test_final_job_status_partial_pair():
    from apps.exchange.models import HistoryDownload
    from apps.exchange.tasks import _final_job_status

    progress = {"BTC/1h": {"status": "partial", "bars": 5000}}
    assert _final_job_status(progress) == HistoryDownload.Status.PARTIAL


@pytest.mark.django_db
def test_download_task_status_partial():
    from apps.exchange.models import HistoryDownload
    from apps.exchange.tasks import _final_job_status, download_history_task

    user = _make_user()
    job = HistoryDownload.objects.create(
        user=user,
        coins=["BTC", "ETH"],
        intervals=["1h"],
        start_ms=1_000,
        end_ms=2_000,
    )
    progress = {
        "BTC/1h": {"status": "done", "bars": 5},
        "ETH/1h": {"status": "failed", "error": "timeout"},
    }
    assert _final_job_status(progress) == HistoryDownload.Status.PARTIAL

    with mock.patch(
        "apps.exchange.tasks.download_history",
        return_value={"progress": progress, "end_ms": 2_000},
    ):
        result = download_history_task(job.id)

    assert result["ok"] is True
    job.refresh_from_db()
    assert job.status == HistoryDownload.Status.PARTIAL
    assert "ETH/1h" in job.error


@pytest.mark.django_db
def test_download_task_missing_job():
    from apps.exchange.tasks import download_history_task

    result = download_history_task(999_999)
    assert result["ok"] is False


def _hl_funding(ts, rate, premium="0.0001"):
    return {"coin": "BTC", "fundingRate": str(rate), "premium": str(premium), "time": ts}


def test_fetch_funding_range_paginates_and_dedupes():
    from apps.exchange import history

    # First page hits the 500-row cap (forces another call); second is partial.
    page1 = [_hl_funding(1000 + i, 0.0001) for i in range(500)]
    page2 = [_hl_funding(1499, 0.0001), _hl_funding(1600, 0.0002)]  # overlap 1499
    fake_info = mock.Mock()
    fake_info.funding_history.side_effect = [page1, page2, []]

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = history.fetch_funding_range("BTC", 1000, 2000, network="testnet", sleep=0)

    assert fake_info.funding_history.call_count >= 2
    assert list(df.columns) == ["ts", "funding_rate", "premium"]
    # Ascending, deduped (1499 appears once).
    assert df["ts"].is_monotonic_increasing
    assert df["ts"].duplicated().sum() == 0
    assert df["ts"].iloc[-1] == 1600


def test_fetch_funding_range_raises_on_error():
    from apps.exchange import history

    fake_info = mock.Mock()
    fake_info.funding_history.side_effect = RuntimeError("api down")
    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        with pytest.raises(history.HistoryFetchError):
            history.fetch_funding_range("BTC", 1000, 2000, network="testnet", sleep=0)


def test_fetch_open_interest_snapshot():
    from apps.exchange import history

    meta = {"universe": [{"name": "BTC"}, {"name": "ETH"}, {"name": "SOL"}]}
    ctxs = [{"openInterest": "123.5"}, {"openInterest": "42"}, {"openInterest": "7"}]
    fake_info = mock.Mock()
    fake_info.meta_and_asset_ctxs.return_value = (meta, ctxs)

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = history.fetch_open_interest_snapshot(["BTC", "ETH"], network="testnet")

    assert list(df["coin"]) == ["BTC", "ETH"]
    assert df[df["coin"] == "BTC"]["open_interest"].iloc[0] == 123.5
    assert "SOL" not in set(df["coin"])


@pytest.mark.django_db
def test_funding_store_roundtrip(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store
    import pandas as pd

    df1 = pd.DataFrame({"ts": [1000, 2000], "funding_rate": [0.1, 0.2], "premium": [0.0, 0.0]})
    candle_store.save_funding("BTC", df1)
    df2 = pd.DataFrame({"ts": [2000, 3000], "funding_rate": [0.2, 0.3], "premium": [0.0, 0.0]})
    candle_store.save_funding("BTC", df2)

    out = candle_store.load_funding("BTC")
    assert list(out["ts"]) == [1000, 2000, 3000]
    assert list(candle_store.load_funding("BTC", start=2000)["ts"]) == [2000, 3000]


@pytest.mark.django_db
def test_open_interest_store_appends(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store
    import pandas as pd

    candle_store.save_open_interest("BTC", pd.DataFrame({"ts": [1000], "open_interest": [10.0]}))
    candle_store.save_open_interest("BTC", pd.DataFrame({"ts": [2000], "open_interest": [20.0]}))

    out = candle_store.load_open_interest("BTC")
    assert list(out["ts"]) == [1000, 2000]
    assert list(out["open_interest"]) == [10.0, 20.0]


@pytest.mark.django_db
def test_list_datasets_includes_all_kinds(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store
    import pandas as pd

    candle_store.save_candles("ETH", "4h", candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5)]))
    candle_store.save_funding("BTC", pd.DataFrame({"ts": [1000], "funding_rate": [0.1], "premium": [0.0]}))
    candle_store.save_open_interest("SOL", pd.DataFrame({"ts": [1000], "open_interest": [5.0]}))

    kinds = {(d["coin"], d["kind"]) for d in candle_store.list_datasets()}
    assert ("ETH", "ohlcv") in kinds
    assert ("BTC", "funding") in kinds
    assert ("SOL", "open_interest") in kinds


@pytest.mark.django_db
def test_create_download_rejects_trades(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {"coins": ["BTC"], "data_types": ["trades"], "start": "2024-01-01", "end": "2024-06-01"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "trades" in resp.json()["error"]


@pytest.mark.django_db
def test_create_download_invalid_data_type(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {"coins": ["BTC"], "data_types": ["bogus"], "start": "2024-01-01", "end": "2024-06-01"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_download_funding_only_no_intervals(client):
    user = _make_user()
    client.force_login(user)
    with mock.patch("apps.exchange.views.download_history_task.delay") as delay:
        resp = client.post(
            "/api/history/downloads/",
            {"coins": ["BTC"], "data_types": ["funding"], "start": "2024-01-01", "end": "2024-06-01"},
            content_type="application/json",
        )
    assert resp.status_code == 202
    assert resp.json()["data_types"] == ["funding"]
    delay.assert_called_once()


@pytest.mark.django_db
def test_create_download_ohlcv_requires_intervals(client):
    user = _make_user()
    client.force_login(user)
    resp = client.post(
        "/api/history/downloads/",
        {"coins": ["BTC"], "data_types": ["ohlcv"], "start": "2024-01-01", "end": "2024-06-01"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_download_history_funding_and_oi():
    from apps.exchange import history_download

    def fake_funding(coin, start_ms, end_ms, *, network="mainnet", known=None):
        return {"key": f"{coin}/funding", "status": "done", "bars": 3}

    def fake_oi(coins, *, network="mainnet", known=None):
        return {f"{coins[0]}/oi": {"key": f"{coins[0]}/oi", "status": "done", "bars": 1}}

    with mock.patch.object(history_download, "known_perp_coins", return_value={"BTC"}), \
        mock.patch.object(history_download, "download_funding", side_effect=fake_funding), \
        mock.patch.object(history_download, "download_open_interest", side_effect=fake_oi):
        outcome = history_download.download_history(
            ["BTC"], [], 1_000, 2_000, data_types=["funding", "open_interest"],
        )
    assert outcome["progress"]["BTC/funding"]["status"] == "done"
    assert outcome["progress"]["BTC/oi"]["status"] == "done"


@pytest.mark.django_db
def test_save_candles_concurrent(tmp_path, settings):
    import threading

    settings.CANDLE_DATA_DIR = str(tmp_path)
    from apps.exchange import candle_store

    def make_df(offset):
        return candles._normalize_rows(
            [_hl_candle(1000 + offset, 1, 2, 0.5, 1.5), _hl_candle(2000 + offset, 2, 3, 1, 2.5)]
        )

    errors = []

    def worker(offset):
        try:
            candle_store.save_candles("BTC", "1h", make_df(offset))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i * 10_000,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    out = candle_store.load_candles("BTC", "1h")
    assert len(out) == 8


@pytest.mark.django_db
def test_hybrid_save_writes_pg_and_parquet(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store
    from apps.exchange.models import Candle

    df = candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5)])
    path = candle_store.save_candles("HYBRID", "1h", df, network="mainnet")
    assert path.exists()
    assert Candle.objects.filter(asset="HYBRID", timeframe="1h", network="mainnet").count() == 1

    df2 = candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5), _hl_candle(2000, 2, 3, 1, 2.5)])
    candle_store.save_candles("HYBRID", "1h", df2, network="mainnet")
    assert Candle.objects.filter(asset="HYBRID", timeframe="1h").count() == 2


@pytest.mark.django_db
def test_latest_timestamp_and_delete_dataset(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store

    df = candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5), _hl_candle(2000, 2, 3, 1, 2.5)])
    candle_store.save_candles("ETH", "4h", df, network="mainnet")
    assert candle_store.latest_timestamp("mainnet", "ETH", "4h", kind="ohlcv") == 2000

    assert candle_store.delete_dataset("mainnet", "ETH", "4h", kind="ohlcv")
    assert candle_store.latest_timestamp("mainnet", "ETH", "4h", kind="ohlcv") is None


@pytest.mark.django_db
def test_delete_dataset_api_kinds(client, tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store

    user = _make_user()
    client.force_login(user)

    candle_store.save_candles(
        "BTC",
        "1h",
        candles._normalize_rows([_hl_candle(1000, 1, 2, 0.5, 1.5)]),
        network="mainnet",
    )
    candle_store.save_funding(
        "BTC",
        pd.DataFrame({"ts": [1000], "funding_rate": [0.1], "premium": [0.0]}),
        network="mainnet",
    )
    candle_store.save_open_interest(
        "BTC",
        pd.DataFrame({"ts": [1000], "open_interest": [123.0]}),
        network="mainnet",
    )

    ohlcv = client.delete(
        "/api/history/datasets/",
        {"network": "mainnet", "coin": "BTC", "interval": "1h", "kind": "ohlcv"},
    )
    assert ohlcv.status_code == 200

    funding = client.delete(
        "/api/history/datasets/",
        {"network": "mainnet", "coin": "BTC", "interval": "funding", "kind": "funding"},
    )
    assert funding.status_code == 200, funding.content

    oi = client.delete(
        "/api/history/datasets/",
        {"network": "mainnet", "coin": "BTC", "interval": "open_interest", "kind": "open_interest"},
    )
    assert oi.status_code == 200, oi.content


@pytest.mark.django_db
def test_download_retry_endpoint(client):
    user = _make_user()
    client.force_login(user)
    from apps.exchange.models import HistoryDownload

    job = HistoryDownload.objects.create(
        user=user,
        status=HistoryDownload.Status.FAILED,
        network="mainnet",
        coins=["BTC"],
        intervals=["1h"],
        data_types=["ohlcv"],
        start_ms=1,
        end_ms=2,
        progress={"BTC/1h": {"key": "BTC/1h", "status": "done", "bars": 10}},
        error="worker died",
    )

    with mock.patch("apps.exchange.views.download_history_task") as task:
        task.delay.return_value = None
        resp = client.post(f"/api/history/downloads/{job.id}/retry/")
    assert resp.status_code == 202
    job.refresh_from_db()
    assert job.status == HistoryDownload.Status.PENDING
    assert job.error == ""


@pytest.mark.django_db
def test_load_candles_falls_back_to_db(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from decimal import Decimal

    from apps.exchange import candle_store
    from apps.exchange.models import Candle

    Candle.objects.create(
        network="mainnet",
        asset="FALLBACK",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("1"),
    )

    out = candle_store.load_candles("FALLBACK", "1h", network="mainnet")
    assert len(out) == 1
    assert int(out.iloc[0]["ts"]) == 1000


@pytest.mark.django_db
def test_retry_stale_endpoint(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.exchange.models import HistoryDownload

    user = _make_user()
    client.force_login(user)
    job = HistoryDownload.objects.create(
        user=user,
        status=HistoryDownload.Status.PENDING,
        network="mainnet",
        coins=["BTC"],
        intervals=["1h"],
        data_types=["ohlcv"],
        start_ms=1,
        end_ms=2,
    )
    HistoryDownload.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(seconds=200),
    )

    with mock.patch("apps.exchange.views.download_history_task") as task:
        task.delay.return_value = None
        resp = client.post("/api/history/downloads/retry-stale/")
    assert resp.status_code == 200
    body = resp.json()
    assert job.id in body["retried"]
    assert body["count"] == 1
    job.refresh_from_db()
    assert job.status == HistoryDownload.Status.PENDING


@pytest.mark.django_db
def test_data_quality_validate_and_gaps(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from decimal import Decimal

    import pandas as pd

    from apps.exchange import data_quality
    from apps.exchange.models import Candle

    for ts in [0, 3_600_000, 10_800_000]:
        Candle.objects.create(
            network="mainnet",
            asset="GAP",
            timeframe="1h",
            timestamp=ts,
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=Decimal("1"),
        )

    df = pd.DataFrame(
        {
            "ts": [0, 3_600_000, 10_800_000],
            "open": [1.0, 1.0, 1.0],
            "high": [2.0, 2.0, 2.0],
            "low": [0.5, 0.5, 0.5],
            "close": [1.5, 1.5, 1.5],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    assert data_quality.validate_candles(df) == []
    gaps = data_quality.find_gaps("GAP", "1h", network="mainnet", source="db")
    assert len(gaps) == 1
    assert gaps[0]["missing_bars"] == 1


@pytest.mark.django_db
def test_history_gaps_and_quality_api(client):
    from decimal import Decimal

    from apps.exchange.models import Candle

    user = _make_user()
    client.force_login(user)
    Candle.objects.create(
        network="mainnet",
        asset="APIQ",
        timeframe="1h",
        timestamp=0,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("1"),
    )
    resp = client.get("/api/history/quality/", {"coin": "APIQ", "interval": "1h"})
    assert resp.status_code == 200
    assert "healthy" in resp.json()
    resp2 = client.get("/api/history/gaps/", {"coin": "APIQ", "interval": "1h"})
    assert resp2.status_code == 200
    assert "gaps" in resp2.json()


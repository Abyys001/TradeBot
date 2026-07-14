"""Copytrading hardening tests: idempotency, error isolation, fee math."""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.copytrading.fees import apply_profit_share
from apps.copytrading.models import (
    CopyOrder,
    CopySignal,
    CopySubscription,
    CopyTrade,
    PlatformFeeConfig,
)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    CREDENTIAL_ENC_KEY="dGVzdC1rZXktZm9yLXRlc3Rpbmctb25seQ==",
)
class FeeMathTestCase(TestCase):
    """Verify HWM fee math with atomic updates."""

    def setUp(self):
        from apps.accounts.models import User
        from apps.credentials.models import Exchange, ExchangeCredential

        self.user = User.objects.create_user(
            username="admin1", password="pass1234!", role="admin"
        )
        self.investor = User.objects.create_user(
            username="investor1", password="pass1234!", role="investor"
        )
        self.cred = ExchangeCredential.objects.create(
            user=self.investor,
            exchange=Exchange.TABDEAL,
            label="test",
        )
        self.signal = CopySignal.objects.create(
            owner=self.user,
            name="test-signal",
            secret_token="test-token-123",
        )
        self.sub = CopySubscription.objects.create(
            signal=self.signal,
            credential=self.cred,
        )
        PlatformFeeConfig.objects.create(owner=self.user, share_pct=20)

    def _create_closed_trade(self, pnl: float) -> CopyTrade:
        entry = CopyOrder.objects.create(
            subscription=self.sub, pair="BTCUSDT", side="buy",
            size=Decimal("1.0"), status="filled",
        )
        exit_order = CopyOrder.objects.create(
            subscription=self.sub, pair="BTCUSDT", side="sell",
            size=Decimal("1.0"), status="filled",
        )
        return CopyTrade.objects.create(
            subscription=self.sub,
            entry_order=entry,
            exit_order=exit_order,
            status=CopyTrade.Status.CLOSED,
            gross_pnl=Decimal(str(pnl)),
        )

    def test_winning_trade_charges_fee(self):
        trade = self._create_closed_trade(100.0)
        entry = apply_profit_share(trade)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, Decimal("20.00000000"))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.high_water_mark, Decimal("100.00000000"))

    def test_losing_trade_no_fee(self):
        trade = self._create_closed_trade(-50.0)
        entry = apply_profit_share(trade)
        self.assertIsNone(entry)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.high_water_mark, Decimal("0"))

    def test_recovery_no_fee_until_exceeds_hwm(self):
        # Win 100, then lose 80 (net +20), then win 50 (net +70).
        t1 = self._create_closed_trade(100.0)
        apply_profit_share(t1)

        t2 = self._create_closed_trade(-80.0)
        entry2 = apply_profit_share(t2)
        self.assertIsNone(entry2)  # still under HWM of 100

        t3 = self._create_closed_trade(50.0)
        entry3 = apply_profit_share(t3)
        self.assertIsNone(entry3)  # cumulative = 70, still under HWM of 100

        t4 = self._create_closed_trade(40.0)
        entry4 = apply_profit_share(t4)
        self.assertIsNotNone(entry4)  # cumulative = 110, exceeds HWM
        # profit_above = 110 - 100 = 10, fee = 10 * 20% = 2
        self.assertEqual(entry4.amount, Decimal("2.00000000"))

    def test_multiple_wins_accumulate(self):
        t1 = self._create_closed_trade(100.0)
        apply_profit_share(t1)
        t2 = self._create_closed_trade(50.0)
        entry = apply_profit_share(t2)
        self.assertIsNotNone(entry)
        # cumulative = 150, profit_above = 150 - 100 = 50, fee = 10
        self.assertEqual(entry.amount, Decimal("10.00000000"))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    CREDENTIAL_ENC_KEY="dGVzdC1rZXktZm9yLXRlc3Rpbmctb25seQ==",
)
class IdempotencyTestCase(TestCase):
    """Verify clientOrderId generation for idempotency."""

    def test_generate_client_order_id_deterministic(self):
        from apps.copytrading.tasks import _generate_client_order_id

        action = {"type": "entry", "oid": "test-oid"}
        ts = 1700000000.0
        id1 = _generate_client_order_id(1, action, ts)
        id2 = _generate_client_order_id(1, action, ts)
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 32)  # SHA256 truncated to 32

    def test_different_subs_different_ids(self):
        from apps.copytrading.tasks import _generate_client_order_id

        action = {"type": "entry", "oid": "test-oid"}
        ts = 1700000000.0
        id1 = _generate_client_order_id(1, action, ts)
        id2 = _generate_client_order_id(2, action, ts)
        self.assertNotEqual(id1, id2)

    def test_different_actions_different_ids(self):
        from apps.copytrading.tasks import _generate_client_order_id

        action1 = {"type": "entry", "oid": "oid-1"}
        action2 = {"type": "close", "oid": "oid-1"}
        ts = 1700000000.0
        id1 = _generate_client_order_id(1, action1, ts)
        id2 = _generate_client_order_id(1, action2, ts)
        self.assertNotEqual(id1, id2)

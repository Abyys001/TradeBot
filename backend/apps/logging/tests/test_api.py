from django.contrib.auth.models import User
from django.test import TestCase

from apps.logging.models import LogEntry


class LogEntryAPITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password="pass", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.url = "/api/logging/logs/"

    def _log(self, **kwargs):
        defaults = {
            "level": "INFO",
            "category": "SYSTEM",
            "source": "test",
            "message": "test message",
        }
        defaults.update(kwargs)
        LogEntry.objects.create(**defaults)

    def test_list_returns_entries(self):
        self._log(message="first")
        self._log(message="second")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_filter_by_level(self):
        self._log(level="INFO")
        self._log(level="ERROR")
        resp = self.client.get(self.url, {"level": "ERROR"})
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["level"], "ERROR")

    def test_filter_by_category(self):
        self._log(category="ENGINE")
        self._log(category="EXCHANGE")
        resp = self.client.get(self.url, {"category": "ENGINE"})
        self.assertEqual(len(resp.data), 1)

    def test_filter_by_source(self):
        self._log(source="apps.engine.fanout")
        self._log(source="apps.exchanges.binance")
        resp = self.client.get(self.url, {"source": "apps.engine"})
        self.assertEqual(len(resp.data), 1)

    def test_filter_by_account(self):
        self._log(account_id=1)
        self._log(account_id=2)
        resp = self.client.get(self.url, {"account_id": 1})
        self.assertEqual(len(resp.data), 1)

    def test_filter_by_exchange(self):
        self._log(exchange="binance")
        self._log(exchange="bybit")
        resp = self.client.get(self.url, {"exchange": "binance"})
        self.assertEqual(len(resp.data), 1)

    def test_search_message(self):
        self._log(message="rate limit exceeded")
        self._log(message="order placed")
        resp = self.client.get(self.url, {"search": "rate"})
        self.assertEqual(len(resp.data), 1)

    def test_prune_action(self):
        self._log()
        self._log()
        resp = self.client.post(self.url + "prune/", {"days": 30})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pruned", resp.data)

    def test_unauthenticated_denied(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_ordering_is_newest_first(self):
        self._log(message="old")
        self._log(message="new")
        resp = self.client.get(self.url)
        self.assertEqual(resp.data[0]["message"], "new")
        self.assertEqual(resp.data[1]["message"], "old")

    def test_default_response_is_capped(self):
        for i in range(5):
            self._log(message=f"entry {i}")
        resp = self.client.get(self.url, {"limit": 3})
        self.assertEqual(len(resp.data), 3)
        # newest three, still newest-first
        self.assertEqual(resp.data[0]["message"], "entry 4")
        self.assertEqual(resp.data[2]["message"], "entry 2")

    def test_limit_is_capped_at_maximum(self):
        for i in range(3):
            self._log(message=f"entry {i}")
        resp = self.client.get(self.url, {"limit": 999999})
        self.assertEqual(len(resp.data), 3)

    def test_before_id_pages_backwards(self):
        ids = [self._log_and_get_id(message=f"entry {i}") for i in range(5)]
        resp = self.client.get(self.url, {"limit": 2, "before_id": ids[3]})
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0]["message"], "entry 2")
        self.assertEqual(resp.data[1]["message"], "entry 1")

    def _log_and_get_id(self, **kwargs):
        defaults = {
            "level": "INFO",
            "category": "SYSTEM",
            "source": "test",
            "message": "test message",
        }
        defaults.update(kwargs)
        return LogEntry.objects.create(**defaults).id

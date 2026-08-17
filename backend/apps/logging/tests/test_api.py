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

    def test_prune_rejects_a_non_numeric_window(self):
        """A 500 from the endpoint that deletes rows leaves the admin guessing
        whether anything was deleted."""
        resp = self.client.post(self.url + "prune/", {"days": "soon"})
        self.assertEqual(resp.status_code, 400)

    def test_prune_refuses_to_delete_everything(self):
        self._log()
        resp = self.client.post(self.url + "prune/", {"days": 0})
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(LogEntry.objects.filter(source="test").exists())

    def test_facets_serve_every_level_and_category_the_backend_writes(self):
        resp = self.client.get(self.url + "facets/")
        self.assertEqual(resp.status_code, 200)
        # The filter dropdowns are built from this; AUTH and MARKET_DATA were
        # missing from the panel's own hardcoded list.
        self.assertIn("AUTH", resp.data["categories"])
        self.assertIn("MARKET_DATA", resp.data["categories"])
        self.assertEqual(resp.data["levels"], ["INFO", "WARNING", "ERROR", "CRITICAL"])

    def test_request_id_filter_traces_one_request(self):
        self._log(message="a", request_id="abc123")
        self._log(message="b", request_id="def456")
        resp = self.client.get(self.url, {"request_id": "abc123"})
        self.assertEqual([row["message"] for row in resp.data], ["a"])

    def test_reading_the_log_does_not_write_to_the_log(self):
        """The access middleware skips this prefix: otherwise the panel's own
        refresh appeared in the tail it was refreshing, and each refresh added
        another row."""
        self.client.get(self.url)
        self.assertEqual(LogEntry.objects.count(), 0)

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

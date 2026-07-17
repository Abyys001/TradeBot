from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Lead


class PublicPerformanceViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_public_performance_is_accessible_without_auth(self):
        resp = self.client.get(reverse("public-performance"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("headline", body)
        self.assertIn("equity_curve", body)
        self.assertIn("disclaimer", body)
        self.assertNotIn("investors", body)
        self.assertNotIn("username", str(body).lower())
        self.assertNotIn("credential", str(body).lower())


class LeadCreateViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_creates_lead_without_auth(self):
        resp = self.client.post(
            reverse("public-lead-create"),
            {"name": "Jane", "email": "jane@example.com", "contact": "", "message": "Hi", "locale": "en"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.count(), 1)

    def test_honeypot_silently_drops_submission(self):
        resp = self.client.post(
            reverse("public-lead-create"),
            {"name": "Bot", "email": "bot@example.com", "website": "http://spam.example"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.count(), 0)

    def test_duplicate_email_within_window_is_deduped(self):
        payload = {"name": "Jane", "email": "dup@example.com"}
        self.client.post(reverse("public-lead-create"), payload)
        self.client.post(reverse("public-lead-create"), payload)
        self.assertEqual(Lead.objects.filter(email="dup@example.com").count(), 1)

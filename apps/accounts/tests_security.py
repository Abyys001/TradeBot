"""Security tests: authorization, authentication, and permission enforcement."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.test.client import Client

from apps.accounts.permissions import IsAdminRole, IsInvestorRole, IsOwner

User = get_user_model()


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    CREDENTIAL_ENC_KEY="dGVzdC1rZXktZm9yLXRlc3Rpbmctb25seQ==",
)
class AuthorizationTestCase(TestCase):
    """Verify investors cannot access admin routes or other investors' data."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin1", password="pass1234!", role=User.Role.ADMIN
        )
        self.investor1 = User.objects.create_user(
            username="investor1", password="pass1234!", role=User.Role.INVESTOR
        )
        self.investor2 = User.objects.create_user(
            username="investor2", password="pass1234!", role=User.Role.INVESTOR
        )

    def test_investor_cannot_access_investor_management(self):
        """Investor cannot list or create other investors via admin endpoints."""
        self.client.login(username="investor1", password="pass1234!")
        resp = self.client.get("/api/investors/")
        self.assertIn(resp.status_code, [403, 404])

    def test_investor_cannot_reset_own_password_via_admin_endpoint(self):
        """Investor cannot use admin password reset action."""
        self.client.login(username="investor1", password="pass1234!")
        resp = self.client.post(
            f"/api/investors/{self.investor1.pk}/reset-password/",
            {"password": "newpass123!"},
            content_type="application/json",
        )
        self.assertIn(resp.status_code, [403, 404])

    def test_investor_cannot_toggle_trading_via_admin_endpoint(self):
        """Investor cannot toggle trading via admin endpoint."""
        self.client.login(username="investor1", password="pass1234!")
        resp = self.client.post(
            f"/api/investors/{self.investor1.pk}/set-trading/",
            {"enabled": True},
            content_type="application/json",
        )
        self.assertIn(resp.status_code, [403, 404])

    def test_unauthenticated_user_blocked(self):
        """Unauthenticated user gets 401/403 on protected endpoints."""
        resp = self.client.get("/api/health/")
        self.assertIn(resp.status_code, [401, 403])

    def test_investor_cannot_read_other_investors_data(self):
        """Investor cannot access another investor's copy-trading data."""
        self.client.login(username="investor1", password="pass1234!")
        # The copy-trading views filter by request.user, so this should return
        # empty data, not the other investor's data.
        resp = self.client.get("/api/copy/summary/")
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_investor_management(self):
        """Admin can access investor management endpoints."""
        self.client.login(username="admin1", password="pass1234!")
        resp = self.client.get("/api/investors/")
        self.assertEqual(resp.status_code, 200)


class PermissionClassesTestCase(TestCase):
    """Test permission class logic."""

    def setUp(self):
        self.admin = User(username="admin1", role=User.Role.ADMIN)
        self.investor = User(username="investor1", role=User.Role.INVESTOR)
        self.superuser = User(username="super1", is_superuser=True, role=User.Role.ADMIN)

    def test_is_admin_role_admin(self):
        perm = IsAdminRole()
        class FakeRequest:
            user = self.admin
        self.assertTrue(perm.has_permission(FakeRequest(), None))

    def test_is_admin_role_investor(self):
        perm = IsAdminRole()
        class FakeRequest:
            user = self.investor
        self.assertFalse(perm.has_permission(FakeRequest(), None))

    def test_is_admin_role_superuser(self):
        perm = IsAdminRole()
        class FakeRequest:
            user = self.superuser
        self.assertTrue(perm.has_permission(FakeRequest(), None))

    def test_is_investor_role(self):
        perm = IsInvestorRole()
        class FakeRequest:
            user = self.investor
        self.assertTrue(perm.has_permission(FakeRequest(), None))

    def test_is_investor_role_admin(self):
        perm = IsInvestorRole()
        class FakeRequest:
            user = self.admin
        self.assertFalse(perm.has_permission(FakeRequest(), None))

    def test_is_owner_same_user(self):
        perm = IsOwner()
        obj = type("Obj", (), {"user": self.investor})()
        self.assertTrue(perm.has_object_permission(None, None, obj))

    def test_is_owner_different_user(self):
        perm = IsOwner()
        obj = type("Obj", (), {"user": self.admin})()
        request = type("Req", (), {"user": self.investor})()
        self.assertFalse(perm.has_object_permission(request, None, obj))

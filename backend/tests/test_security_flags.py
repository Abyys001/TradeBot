"""The switches themselves: off by default, and impossible to strand yourself with.

``docs/security-plan.md`` §0 says the escapes exist before the first control
does. These are the tests for the escapes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from apps.security import flags
from apps.security.models import SecurityEvent, SecurityEventKind, SecurityPolicy, TotpDevice


def _security(**overrides) -> dict:
    from django.conf import settings

    return {**settings.SECURITY, **overrides}


@pytest.mark.django_db
def test_every_switch_is_off_before_anybody_touches_anything():
    values = flags.policy()
    for name in flags.SWITCHES:
        assert values[name] is False, f"{name} arrived switched on"
    assert values["csp_mode"] == "off"


@pytest.mark.django_db
def test_nothing_the_middleware_looks_at_is_active_by_default():
    """The guard clause that keeps the request path free. See middleware.py."""
    assert flags.policy()["_middleware_active"] is False


@pytest.mark.django_db
def test_a_flag_survives_the_round_trip():
    flags.set_flags({"login_rate_limit": True}, actor="admin")
    assert flags.policy()["login_rate_limit"] is True
    assert flags.policy()["_middleware_active"] is False  # not a middleware switch


@pytest.mark.django_db
def test_turning_on_a_middleware_switch_wakes_the_middleware():
    flags.set_flags({"idle_timeout": True}, actor="admin")
    assert flags.policy()["_middleware_active"] is True


@pytest.mark.django_db
def test_an_unknown_setting_is_refused_rather_than_ignored():
    """A typo that silently does nothing is a control the operator thinks is on."""
    with pytest.raises(flags.PolicyError):
        flags.set_flags({"two_factor_maybe": True}, actor="admin")


@pytest.mark.django_db
def test_the_environment_pin_makes_every_switch_inert():
    flags.set_flags({"idle_timeout": True, "login_rate_limit": True}, actor="admin")
    with override_settings(SECURITY=_security(FEATURES=False)):
        flags.invalidate()
        values = flags.policy()
        assert values["idle_timeout"] is False
        assert values["login_rate_limit"] is False
        assert values["_middleware_active"] is False


@pytest.mark.django_db
def test_the_environment_pin_refuses_to_arm_but_still_allows_disarming():
    """`manage.py security_off` has to work whatever else is wrong."""
    with override_settings(SECURITY=_security(FEATURES=False)):
        flags.invalidate()
        with pytest.raises(flags.PolicyError):
            flags.set_flags({"idle_timeout": True}, actor="admin")
        flags.set_flags({"idle_timeout": False}, actor="admin")


@pytest.mark.django_db
def test_the_second_factor_cannot_be_armed_without_an_enrolled_device():
    """Arming a prompt nobody can answer is the lock-out this layer is built around."""
    with pytest.raises(flags.PolicyError, match="recovery codes"):
        flags.set_flags({"two_factor": True}, actor="admin")


@pytest.mark.django_db
def test_the_second_factor_cannot_be_armed_on_a_half_finished_enrolment():
    user = User.objects.create_user("admin", password="pw", is_staff=True)
    TotpDevice.objects.create(user=user, secret="x", confirmed_at=timezone.now())
    with pytest.raises(flags.PolicyError):
        flags.set_flags({"two_factor": True}, actor="admin")

    TotpDevice.objects.filter(user=user).update(recovery_acknowledged_at=timezone.now())
    flags.set_flags({"two_factor": True}, actor="admin")
    assert flags.policy()["two_factor"] is True


@pytest.mark.django_db
def test_the_allowlist_cannot_be_armed_empty():
    """An empty list means 'nobody', so it is refused rather than obeyed."""
    with pytest.raises(flags.PolicyError, match="at least one address"):
        flags.set_flags({"ip_allowlist": True}, actor="admin")

    flags.set_flags({"ip_allowlist": True, "allowed_ips": "10.0.0.0/8"}, actor="admin")
    assert flags.policy()["ip_allowlist"] is True


@pytest.mark.django_db
def test_an_unparseable_allowlist_entry_is_dropped_not_raised():
    """It is read on every request; a typo saved last week must not 500 the panel."""
    networks = flags.parse_networks("10.0.0.1\nnot-an-address\n192.168.0.0/16")
    assert len(networks) == 2


@pytest.mark.django_db
def test_a_policy_change_is_always_recorded_even_with_the_log_off():
    assert flags.policy()["audit_log"] is False
    flags.set_flags({"login_rate_limit": True}, actor="admin")
    event = SecurityEvent.objects.get(kind=SecurityEventKind.POLICY_CHANGED)
    assert event.username == "admin"
    assert "login_rate_limit" in event.detail["changed"]


@pytest.mark.django_db
def test_a_no_op_save_records_nothing():
    flags.set_flags({"login_rate_limit": False}, actor="admin")
    assert not SecurityEvent.objects.exists()


@pytest.mark.django_db
def test_security_off_clears_every_switch():
    flags.set_flags(
        {"login_rate_limit": True, "idle_timeout": True, "csp_mode": "enforce"}, actor="admin"
    )
    call_command("security_off")
    values = flags.policy()
    assert not any(values[name] for name in flags.SWITCHES)
    assert values["csp_mode"] == "off"


@pytest.mark.django_db
def test_security_off_can_clear_exactly_one_switch():
    flags.set_flags({"login_rate_limit": True, "idle_timeout": True}, actor="admin")
    call_command("security_off", "--flag", "idle_timeout")
    values = flags.policy()
    assert values["idle_timeout"] is False
    assert values["login_rate_limit"] is True


@pytest.mark.django_db
def test_security_off_refuses_a_name_that_is_not_a_switch():
    with pytest.raises(CommandError):
        call_command("security_off", "--flag", "nonsense")


@pytest.mark.django_db
def test_the_policy_row_is_a_singleton():
    flags.set_flags({"idle_timeout": True}, actor="a")
    flags.set_flags({"login_rate_limit": True}, actor="b")
    assert SecurityPolicy.objects.count() == 1

"""Signum integration tests."""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.integrations.models import SignumConfig
from apps.integrations.signum import build_signum_payload, render_alert_message, send_signum_webhook

User = get_user_model()


def test_render_alert_message_placeholders():
    template = (
        '{"action": "{{strategy.order.action}}", "ticker": "{{ticker}}", '
        '"position_size": "{{strategy.position_size}}", "time": "{{time}}", '
        '"bot_id": "OLD", "order_size": "OLD"}'
    )
    out = render_alert_message(
        template,
        action="buy",
        ticker="HYPE",
        position_size=1.5,
        timestamp_ms=1_700_000_000_000,
        bot_id="BOT123",
        order_size="80%",
    )
    assert '"buy"' in out or "buy" in out
    assert "HYPE" in out
    assert "BOT123" in out
    assert "80%" in out


@pytest.mark.django_db
def test_build_signum_payload_uses_config_bot_id():
    user = User.objects.create_user(username="signum_user", password="x")
    cfg = SignumConfig.objects.create(user=user, enabled=True, use_settings_bot_id=True)
    cfg.set_bot_id("SECRET_BOT")
    cfg.save()
    template = '{"bot_id": "PINE_ID", "action": "{{strategy.order.action}}"}'
    out = build_signum_payload(
        template,
        user=user,
        action="sell",
        ticker="HYPE",
        position_size=0,
        timestamp_ms=1_700_000_000_000,
    )
    assert "SECRET_BOT" in out
    assert "sell" in out


@pytest.mark.django_db
@mock.patch("apps.integrations.signum.requests.post")
def test_send_signum_webhook(mock_post):
    mock_post.return_value = mock.Mock(ok=True, status_code=200, text="ok")
    user = User.objects.create_user(username="wh_user", password="x")
    cfg = SignumConfig.objects.create(user=user, enabled=True)
    cfg.set_webhook_url("https://example.com/hook")
    cfg.save()
    result = send_signum_webhook(user, '{"action": "buy"}')
    assert result["ok"] is True
    mock_post.assert_called_once()

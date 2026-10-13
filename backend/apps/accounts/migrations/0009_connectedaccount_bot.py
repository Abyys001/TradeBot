"""Q42: an account is driven by the admin's ticket or by one bot, never both.

The two independent switches this replaces are folded in rather than dropped:

  - an account open to bots is handed to the bot that was running — under the
    old one-at-a-time rule there is at most one, and it was the only bot that
    could have been routing to it. With none running it stays manual, because
    guessing which stopped bot it meant is guessing about partner capital.
  - an account open to *neither* hand is paused, which is what "takes no new
    entries" already means. Leaving it manual would have quietly opened it to
    the ticket on upgrade.
"""

import django.db.models.deletion
from django.db import migrations, models


def fold_switches(apps, schema_editor):
    Account = apps.get_model("accounts", "ConnectedAccount")
    Bot = apps.get_model("bots", "Bot")
    running = Bot.objects.filter(state__in=["paper", "live"]).order_by("-updated_at").first()
    if running is not None:
        Account.objects.filter(bot_trading_enabled=True).update(bot=running)
    Account.objects.filter(
        manual_trading_enabled=False, bot__isnull=True, status="active"
    ).update(status="paused")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_connectedaccount_bot_trading_enabled_and_more"),
        ("bots", "0009_botrun_manual_flat_bar_botrun_manual_flat_side"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectedaccount",
            name="bot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accounts",
                to="bots.bot",
            ),
        ),
        migrations.RunPython(fold_switches, migrations.RunPython.noop),
        migrations.RemoveField(model_name="connectedaccount", name="manual_trading_enabled"),
        migrations.RemoveField(model_name="connectedaccount", name="bot_trading_enabled"),
    ]

"""Remove integrations.TelegramConfig — apps.telegram is now the sole owner
of Telegram config/alerts after the origin/main merge.

Best-effort data migration: copy the encrypted bot token + enabled flag from any
existing integrations.TelegramConfig into apps.telegram.TelegramConfig (only when
the target has no token yet), then drop the model. Chat ids are re-collected via
apps.telegram's AlertWhitelist, so they are not migrated here.
"""
from django.db import migrations


def copy_to_telegram_app(apps, schema_editor):
    OldConfig = apps.get_model("integrations", "TelegramConfig")
    NewConfig = apps.get_model("telegram", "TelegramConfig")
    for old in OldConfig.objects.all():
        try:
            new, _ = NewConfig.objects.get_or_create(user_id=old.user_id)
            if not new.bot_token_enc and old.bot_token_enc:
                new.bot_token_enc = old.bot_token_enc
                new.enabled = old.enabled
                new.save(update_fields=["bot_token_enc", "enabled"])
        except Exception:
            # Never fail the migration on a data-copy hiccup; the config can be
            # re-entered in the UI.
            continue


def noop_reverse(apps, schema_editor):
    # Reverse recreates the table via the schema op below; no data to restore.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_telegramconfig"),
        ("telegram", "0002_alter_alertwhitelist_id_alter_telegramconfig_id"),
    ]

    operations = [
        migrations.RunPython(copy_to_telegram_app, noop_reverse),
        migrations.DeleteModel(name="TelegramConfig"),
    ]
